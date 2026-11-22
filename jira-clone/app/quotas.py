"""Free-tier plan quotas: max 1 project and 50 issues per workspace."""
from quart import jsonify
from sqlalchemy import func, select

from . import models

FREE_PROJECT_LIMIT = 1
FREE_ISSUE_LIMIT = 50


def quota_response(resource: str, limit: int):
    return (
        jsonify(
            error=f"Free plan limit reached: maximum {limit} {resource}. Upgrade to Pro for unlimited.",
            code="quota_exceeded",
            resource=resource,
            limit=limit,
        ),
        402,
    )


async def check_project_quota(db, ws):
    if ws.plan_tier != "free":
        return None
    count = (
        await db.execute(
            select(func.count(models.Project.id)).where(
                models.Project.workspace_id == ws.id,
                models.Project.deleted_at.is_(None),
            )
        )
    ).scalar_one()
    if count >= FREE_PROJECT_LIMIT:
        return quota_response("project", FREE_PROJECT_LIMIT)
    return None


async def check_issue_quota(db, ws, project_id: int):
    if ws.plan_tier != "free":
        return None
    count = (
        await db.execute(
            select(func.count(models.Issue.id)).where(models.Issue.project_id == project_id)
        )
    ).scalar_one()
    if count >= FREE_ISSUE_LIMIT:
        return quota_response("issues", FREE_ISSUE_LIMIT)
    return None
