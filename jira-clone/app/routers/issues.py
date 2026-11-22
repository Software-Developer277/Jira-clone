from quart import Blueprint, g, jsonify, request
from sqlalchemy import func, or_, select, text, update

from .. import models
from ..auth import auth_required, require_member
from ..db import db_session
from ..quotas import check_issue_quota
from ..serializers import activity_dict, comment_dict, issue_dict, workspace_user_map

bp = Blueprint("issues", __name__, url_prefix="/api")

STATUSES = {"BACKLOG", "IN_PROGRESS", "IN_REVIEW", "DONE"}
PRIORITIES = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
ISSUE_TYPES = {"BUG", "FEATURE", "TASK"}


async def load_issue_context(db, issue_id: int):
    """Returns (issue, project, workspace, error_response) with membership enforced."""
    issue = await db.get(models.Issue, issue_id)
    if issue is None:
        return None, None, None, (jsonify(error="Issue not found"), 404)
    project = await db.get(models.Project, issue.project_id)
    if project is None or project.deleted_at is not None:
        return None, None, None, (jsonify(error="Project not found"), 404)
    ws, member, err = await require_member(db, project.workspace_id)
    if err:
        return None, None, None, err
    return issue, project, ws, None


@bp.get("/projects/<int:pid>/issues")
@auth_required
async def list_issues(pid):
    async with db_session() as db:
        project = await db.get(models.Project, pid)
        if project is None or project.deleted_at is not None:
            return jsonify(error="Project not found"), 404
        _, _, err = await require_member(db, project.workspace_id)
        if err:
            return err
        stmt = select(models.Issue).where(models.Issue.project_id == pid)
        status = request.args.get("status", "").strip()
        priority = request.args.get("priority", "").strip()
        assignee = request.args.get("assignee_id", "").strip()
        query = request.args.get("q", "").strip()
        if status:
            stmt = stmt.where(models.Issue.status == status)
        if priority:
            stmt = stmt.where(models.Issue.priority == priority)
        if assignee:
            stmt = stmt.where(models.Issue.assignee_id == int(assignee))
        if query:
            like = f"%{query}%"
            stmt = stmt.where(
                or_(models.Issue.title.ilike(like), models.Issue.description.ilike(like))
            )
        stmt = stmt.order_by(models.Issue.id)
        result = await db.execute(stmt)
        names = await workspace_user_map(db, project.workspace_id)
        return jsonify([issue_dict(i, names) for i in result.scalars()])


@bp.post("/projects/<int:pid>/issues")
@auth_required
async def create_issue(pid):
    data = await request.get_json(silent=True) or {}
    title = str(data.get("title", "")).strip()
    if not title:
        return jsonify(error="title is required"), 400
    issue_type = str(data.get("issue_type", "TASK")).upper()
    priority = str(data.get("priority", "MEDIUM")).upper()
    if issue_type not in ISSUE_TYPES or priority not in PRIORITIES:
        return jsonify(error="Invalid issue_type or priority"), 400
    async with db_session() as db:
        project = await db.get(models.Project, pid)
        if project is None or project.deleted_at is not None:
            return jsonify(error="Project not found"), 404
        ws, member, err = await require_member(db, project.workspace_id)
        if err:
            return err
        quota = await check_issue_quota(db, ws, pid)
        if quota:
            return quota  # 402 -> frontend shows upgrade modal
        assignee_id = data.get("assignee_id")
        if assignee_id is not None:
            member_row = (
                await db.execute(
                    select(models.WorkspaceMember).where(
                        models.WorkspaceMember.workspace_id == ws.id,
                        models.WorkspaceMember.user_id == int(assignee_id),
                    )
                )
            ).scalar_one_or_none()
            if member_row is None:
                return jsonify(error="Assignee must be a workspace member"), 400
        # Atomic sequential key generation: single UPDATE ... RETURNING is race-safe
        # even when two users create issues at the exact same moment.
        number = (
            await db.execute(
                text(
                    "UPDATE issue_counters SET count = count + 1 "
                    "WHERE project_id = :pid RETURNING count"
                ),
                {"pid": pid},
            )
        ).scalar_one()
        issue = models.Issue(
            project_id=pid,
            issue_key=f"{project.key}-{number}",
            title=title,
            description=str(data.get("description", "")),
            issue_type=issue_type,
            priority=priority,
            status="BACKLOG",
            assignee_id=assignee_id,
            reporter_id=g.current_user.id,
            story_points=data.get("story_points"),
        )
        db.add(issue)
        await db.flush()
        db.add(
            models.Activity(
                issue_id=issue.id,
                actor_id=g.current_user.id,
                action="created",
                detail=f"{g.current_user.name} created issue {issue.issue_key}",
            )
        )
        names = await workspace_user_map(db, ws.id)
        return jsonify(issue_dict(issue, names)), 201


@bp.get("/issues/<int:iid>")
@auth_required
async def get_issue(iid):
    async with db_session() as db:
        issue, project, ws, err = await load_issue_context(db, iid)
        if err:
            return err
        names = await workspace_user_map(db, ws.id)
        return jsonify(issue_dict(issue, names))


@bp.patch("/issues/<int:iid>")
@auth_required
async def update_issue(iid):
    data = await request.get_json(silent=True) or {}
    if "version" not in data:
        return jsonify(error="version is required (optimistic locking)"), 400
    async with db_session() as db:
        issue, project, ws, err = await load_issue_context(db, iid)
        if err:
            return err
        expected = int(data["version"])
        if issue.version != expected:
            return (
                jsonify(
                    error="Issue was modified by another user",
                    code="stale_version",
                    server_version=issue.version,
                ),
                409,
            )
        changes = {}
        for field in ("title", "description"):
            if field in data and data[field] != getattr(issue, field):
                changes[field] = data[field]
        for field, allowed in (("issue_type", ISSUE_TYPES), ("priority", PRIORITIES), ("status", STATUSES)):
            if field in data:
                value = str(data[field]).upper()
                if value not in allowed:
                    return jsonify(error=f"Invalid {field}"), 400
                if value != getattr(issue, field):
                    changes[field] = value
        if "assignee_id" in data:
            value = data["assignee_id"]
            if value is not None:
                row = (
                    await db.execute(
                        select(models.WorkspaceMember).where(
                            models.WorkspaceMember.workspace_id == ws.id,
                            models.WorkspaceMember.user_id == int(value),
                        )
                    )
                ).scalar_one_or_none()
                if row is None:
                    return jsonify(error="Assignee must be a workspace member"), 400
            if value != issue.assignee_id:
                changes["assignee_id"] = value
        if "story_points" in data and data["story_points"] != issue.story_points:
            changes["story_points"] = data["story_points"]

        if changes:
            # Atomic conditional update: succeeds only if version still matches.
            result = await db.execute(
                update(models.Issue)
                .where(models.Issue.id == iid, models.Issue.version == expected)
                .values(**changes, version=models.Issue.version + 1)
            )
            await db.flush()
            if result.rowcount == 0:
                await db.rollback()
                fresh = await db.get(models.Issue, iid)
                return (
                    jsonify(
                        error="Issue was modified by another user",
                        code="stale_version",
                        server_version=fresh.version,
                    ),
                    409,
                )
            actor = g.current_user.name
            if "status" in changes:
                label = changes["status"].replace("_", " ").title()
                db.add(models.Activity(
                    issue_id=iid, actor_id=g.current_user.id,
                    action="status_changed", detail=f"{actor} moved issue to {label}"))
            if "assignee_id" in changes:
                names = await workspace_user_map(db, ws.id)
                target = names.get(changes["assignee_id"], "Unassigned")
                db.add(models.Activity(
                    issue_id=iid, actor_id=g.current_user.id,
                    action="assignee_changed", detail=f"{actor} assigned issue to {target}"))
            if "priority" in changes:
                db.add(models.Activity(
                    issue_id=iid, actor_id=g.current_user.id,
                    action="priority_changed",
                    detail=f"{actor} changed priority to {changes['priority']}"))
        await db.refresh(issue)
        names = await workspace_user_map(db, ws.id)
        return jsonify(issue_dict(issue, names))


@bp.post("/issues/<int:iid>/comments")
@auth_required
async def add_comment(iid):
    data = await request.get_json(silent=True) or {}
    content = str(data.get("content", "")).strip()
    if not content:
        return jsonify(error="content is required"), 400
    async with db_session() as db:
        issue, project, ws, err = await load_issue_context(db, iid)
        if err:
            return err
        comment = models.Comment(issue_id=iid, author_id=g.current_user.id, content=content)
        db.add(comment)
        await db.flush()
        db.add(models.Activity(
            issue_id=iid, actor_id=g.current_user.id, action="commented",
            detail=f"{g.current_user.name} commented"))
        names = await workspace_user_map(db, ws.id)
        return jsonify(comment_dict(comment, names)), 201


@bp.get("/issues/<int:iid>/comments")
@auth_required
async def list_comments(iid):
    async with db_session() as db:
        issue, project, ws, err = await load_issue_context(db, iid)
        if err:
            return err
        result = await db.execute(
            select(models.Comment)
            .where(models.Comment.issue_id == iid)
            .order_by(models.Comment.id.desc())
        )
        names = await workspace_user_map(db, ws.id)
        return jsonify([comment_dict(c, names) for c in result.scalars()])


@bp.get("/issues/<int:iid>/activity")
@auth_required
async def list_activity(iid):
    async with db_session() as db:
        issue, project, ws, err = await load_issue_context(db, iid)
        if err:
            return err
        result = await db.execute(
            select(models.Activity)
            .where(models.Activity.issue_id == iid)
            .order_by(models.Activity.id.desc())
        )
        names = await workspace_user_map(db, ws.id)
        return jsonify([activity_dict(a, names) for a in result.scalars()])
