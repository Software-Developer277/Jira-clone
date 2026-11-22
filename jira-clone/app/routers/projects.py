import re
from datetime import datetime, timezone

from quart import Blueprint, g, jsonify, request
from sqlalchemy import func, select

from .. import models
from ..auth import auth_required, require_member
from ..db import db_session
from ..quotas import check_project_quota
from ..serializers import project_dict

bp = Blueprint("projects", __name__, url_prefix="/api")

KEY_RE = re.compile(r"^[A-Z][A-Z0-9]{1,9}$")


async def get_project_for_user(db, pid: int):
    """Load project and enforce workspace membership.

    Returns (project, workspace, member, error_response).
    """
    project = await db.get(models.Project, pid)
    if project is None or project.deleted_at is not None:
        return None, None, None, (jsonify(error="Project not found"), 404)
    ws, member, err = await require_member(db, project.workspace_id)
    if err:
        return None, None, None, err
    return project, ws, member, None


@bp.get("/workspaces/<int:wid>/projects")
@auth_required
async def list_projects(wid):
    async with db_session() as db:
        ws, member, err = await require_member(db, wid)
        if err:
            return err
        result = await db.execute(
            select(models.Project)
            .where(models.Project.workspace_id == wid, models.Project.deleted_at.is_(None))
            .order_by(models.Project.id)
        )
        return jsonify([project_dict(p) for p in result.scalars()])


@bp.post("/workspaces/<int:wid>/projects")
@auth_required
async def create_project(wid):
    data = await request.get_json(silent=True) or {}
    name = str(data.get("name", "")).strip()
    key = str(data.get("key", "")).strip().upper()
    description = str(data.get("description", "")).strip()
    if not name:
        return jsonify(error="name is required"), 400
    if not KEY_RE.match(key):
        return jsonify(error="key must be 2-10 chars: A-Z / 0-9, starting with a letter"), 400
    async with db_session() as db:
        ws, member, err = await require_member(db, wid)
        if err:
            return err
        quota = await check_project_quota(db, ws)
        if quota:
            return quota
        existing = (
            await db.execute(
                select(models.Project).where(
                    models.Project.workspace_id == wid, models.Project.key == key
                )
            )
        ).scalar_one_or_none()
        if existing:
            return jsonify(error="Key already used in this workspace"), 409
        project = models.Project(
            workspace_id=wid, name=name, key=key, description=description, lead_id=g.current_user.id
        )
        db.add(project)
        await db.flush()
        db.add(models.IssueCounter(project_id=project.id, count=0))
        return jsonify(project_dict(project)), 201


@bp.get("/projects/<int:pid>")
@auth_required
async def get_project(pid):
    async with db_session() as db:
        project, ws, member, err = await get_project_for_user(db, pid)
        if err:
            return err
        return jsonify(project_dict(project))


@bp.patch("/projects/<int:pid>")
@auth_required
async def update_project(pid):
    data = await request.get_json(silent=True) or {}
    async with db_session() as db:
        project, ws, member, err = await get_project_for_user(db, pid)
        if err:
            return err
        if member.role not in ("owner", "admin") and project.lead_id != g.current_user.id:
            return jsonify(error="Not allowed"), 403
        for field in ("name", "description"):
            if field in data:
                setattr(project, field, str(data[field]).strip())
        return jsonify(project_dict(project))


@bp.delete("/projects/<int:pid>")
@auth_required
async def delete_project(pid):
    force = request.args.get("force") in ("1", "true")
    async with db_session() as db:
        project, ws, member, err = await get_project_for_user(db, pid)
        if err:
            return err
        if member.role not in ("owner", "admin") and project.lead_id != g.current_user.id:
            return jsonify(error="Not allowed"), 403
        active = (
            await db.execute(
                select(func.count(models.Issue.id)).where(
                    models.Issue.project_id == pid, models.Issue.status != "DONE"
                )
            )
        ).scalar_one()
        if active > 0 and not force:
            return (
                jsonify(
                    error="Project has active issues",
                    code="has_active_issues",
                    active_issues=active,
                    hint="Retry with ?force=1 to soft-delete (issues are preserved).",
                ),
                409,
            )
        # Soft delete: rows stay in DB (auditability), hidden from all queries.
        project.deleted_at = datetime.now(timezone.utc)
        return jsonify(ok=True, soft_deleted=True, active_issues_preserved=active)
