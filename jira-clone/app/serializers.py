"""JSON serializers shared by routers."""
from sqlalchemy import select

from . import models


def dt(value):
    return value.isoformat() if value else None


def user_dict(u):
    return {"id": u.id, "email": u.email, "name": u.name}


def workspace_dict(ws, role=None):
    return {
        "id": ws.id,
        "name": ws.name,
        "slug": ws.slug,
        "owner_id": ws.owner_id,
        "plan_tier": ws.plan_tier,
        "role": role,
    }


def project_dict(p):
    return {
        "id": p.id,
        "workspace_id": p.workspace_id,
        "name": p.name,
        "key": p.key,
        "description": p.description or "",
        "lead_id": p.lead_id,
        "deleted_at": dt(p.deleted_at),
    }


def issue_dict(i, names=None):
    names = names or {}
    return {
        "id": i.id,
        "project_id": i.project_id,
        "issue_key": i.issue_key,
        "title": i.title,
        "description": i.description or "",
        "issue_type": i.issue_type,
        "priority": i.priority,
        "status": i.status,
        "assignee_id": i.assignee_id,
        "assignee_name": names.get(i.assignee_id),
        "reporter_id": i.reporter_id,
        "reporter_name": names.get(i.reporter_id),
        "story_points": i.story_points,
        "version": i.version,
        "created_at": dt(i.created_at),
        "updated_at": dt(i.updated_at),
    }


def comment_dict(c, names=None):
    names = names or {}
    return {
        "id": c.id,
        "issue_id": c.issue_id,
        "author_id": c.author_id,
        "author_name": names.get(c.author_id),
        "content": c.content,
        "created_at": dt(c.created_at),
    }


def activity_dict(a, names=None):
    names = names or {}
    return {
        "id": a.id,
        "issue_id": a.issue_id,
        "actor_id": a.actor_id,
        "actor_name": names.get(a.actor_id),
        "action": a.action,
        "detail": a.detail,
        "created_at": dt(a.created_at),
    }


async def workspace_user_map(db, workspace_id: int) -> dict:
    """workspace_id -> {user_id: name} for display fields."""
    result = await db.execute(
        select(models.User)
        .join(models.WorkspaceMember, models.WorkspaceMember.user_id == models.User.id)
        .where(models.WorkspaceMember.workspace_id == workspace_id)
    )
    return {u.id: u.name for u in result.scalars()}
