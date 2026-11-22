from quart import Blueprint, g, jsonify, request
from sqlalchemy import select

from .. import models
from ..auth import auth_required, require_member
from ..db import db_session
from ..serializers import user_dict, workspace_dict

bp = Blueprint("workspaces", __name__, url_prefix="/api")


@bp.post("/workspaces")
@auth_required
async def create_workspace():
    data = await request.get_json(silent=True) or {}
    name = str(data.get("name", "")).strip()
    slug = str(data.get("slug", "")).strip().lower()
    if not name or not slug:
        return jsonify(error="name and slug are required"), 400
    async with db_session() as db:
        exists = (
            await db.execute(select(models.Workspace).where(models.Workspace.slug == slug))
        ).scalar_one_or_none()
        if exists:
            return jsonify(error="Slug already in use"), 409
        ws = models.Workspace(name=name, slug=slug, owner_id=g.current_user.id)
        db.add(ws)
        await db.flush()
        db.add(models.WorkspaceMember(workspace_id=ws.id, user_id=g.current_user.id, role="owner"))
        return jsonify(workspace_dict(ws, "owner")), 201


@bp.get("/workspaces")
@auth_required
async def list_workspaces():
    async with db_session() as db:
        result = await db.execute(
            select(models.Workspace, models.WorkspaceMember.role)
            .join(models.WorkspaceMember, models.WorkspaceMember.workspace_id == models.Workspace.id)
            .where(models.WorkspaceMember.user_id == g.current_user.id)
        )
        return jsonify([workspace_dict(ws, role) for ws, role in result.all()])


@bp.post("/workspaces/<int:wid>/invite")
@auth_required
async def invite_member(wid):
    data = await request.get_json(silent=True) or {}
    email = str(data.get("email", "")).strip().lower()
    role = data.get("role", "member")
    if role not in ("admin", "member"):
        return jsonify(error="role must be 'admin' or 'member'"), 400
    async with db_session() as db:
        ws, member, err = await require_member(db, wid)
        if err:
            return err
        if member.role not in ("owner", "admin"):
            return jsonify(error="Admin rights required"), 403
        user = (
            await db.execute(select(models.User).where(models.User.email == email))
        ).scalar_one_or_none()
        if user is None:
            return jsonify(error="No registered user with this email"), 404
        existing = (
            await db.execute(
                select(models.WorkspaceMember).where(
                    models.WorkspaceMember.workspace_id == wid,
                    models.WorkspaceMember.user_id == user.id,
                )
            )
        ).scalar_one_or_none()
        if existing:
            return jsonify(error="Already a member"), 409
        db.add(models.WorkspaceMember(workspace_id=wid, user_id=user.id, role=role))
        return jsonify(ok=True, user=user_dict(user)), 201


@bp.get("/workspaces/<int:wid>/members")
@auth_required
async def list_members(wid):
    async with db_session() as db:
        ws, member, err = await require_member(db, wid)
        if err:
            return err
        result = await db.execute(
            select(models.User, models.WorkspaceMember.role)
            .join(models.WorkspaceMember, models.WorkspaceMember.user_id == models.User.id)
            .where(models.WorkspaceMember.workspace_id == wid)
        )
        return jsonify([{**user_dict(u), "role": role} for u, role in result.all()])


@bp.post("/workspaces/<int:wid>/upgrade")
@auth_required
async def upgrade_plan(wid):
    async with db_session() as db:
        ws, member, err = await require_member(db, wid)
        if err:
            return err
        if member.role != "owner":
            return jsonify(error="Only the owner can upgrade the plan"), 403
        ws.plan_tier = "pro"
        return jsonify(workspace_dict(ws, member.role))
