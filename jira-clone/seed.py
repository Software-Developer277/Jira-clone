"""Demo data: python seed.py  (idempotent — safe to run twice)"""
import asyncio

from sqlalchemy import select

from app import models
from app.auth import hash_password
from app.db import db_session, init_db


async def get_or_create_user(db, email, name, password):
    user = (await db.execute(select(models.User).where(models.User.email == email))).scalar_one_or_none()
    if user is None:
        user = models.User(email=email, name=name, password_hash=hash_password(password))
        db.add(user)
        await db.flush()
    return user


async def main():
    await init_db()
    async with db_session() as db:
        sarah = await get_or_create_user(db, "sarah@acme.dev", "Sarah", "password123")
        john = await get_or_create_user(db, "john@acme.dev", "John", "password123")
        demo = await get_or_create_user(db, "demo@full.dev", "Demo", "password123")

        # --- Workspace 1: Acme Inc (free tier, project WEB with sample issues)
        ws = (await db.execute(select(models.Workspace).where(models.Workspace.slug == "acme"))).scalar_one_or_none()
        if ws is None:
            ws = models.Workspace(name="Acme Inc", slug="acme", owner_id=sarah.id)
            db.add(ws)
            await db.flush()
            db.add(models.WorkspaceMember(workspace_id=ws.id, user_id=sarah.id, role="owner"))
            db.add(models.WorkspaceMember(workspace_id=ws.id, user_id=john.id, role="member"))

        project = (
            await db.execute(
                select(models.Project).where(
                    models.Project.workspace_id == ws.id, models.Project.key == "WEB"
                )
            )
        ).scalar_one_or_none()
        if project is None:
            project = models.Project(
                workspace_id=ws.id, name="Website Redesign", key="WEB",
                description="Public site revamp", lead_id=sarah.id,
            )
            db.add(project)
            await db.flush()

            samples = [
                ("Fix login redirect loop", "BUG", "CRITICAL", "BACKLOG", john.id, 5),
                ("Dark mode toggle", "FEATURE", "HIGH", "IN_PROGRESS", john.id, 8),
                ("Add password reset flow", "FEATURE", "MEDIUM", "IN_REVIEW", sarah.id, 5),
                ("Update pricing page copy", "TASK", "LOW", "DONE", sarah.id, 2),
                ("Optimize hero image sizes", "TASK", "MEDIUM", "BACKLOG", None, 3),
                ("Landing page A/B test setup", "FEATURE", "HIGH", "IN_PROGRESS", sarah.id, 8),
                ("Fix mobile nav overlap", "BUG", "HIGH", "IN_REVIEW", john.id, 3),
                ("Write release notes", "TASK", "LOW", "DONE", sarah.id, 1),
                ("SSO integration research", "FEATURE", "MEDIUM", "BACKLOG", None, 13),
                ("Cookie consent banner", "TASK", "MEDIUM", "IN_PROGRESS", sarah.id, 2),
            ]
            for idx, (title, itype, prio, status, assignee, points) in enumerate(samples, start=1):
                issue = models.Issue(
                    project_id=project.id,
                    issue_key=f"WEB-{idx}",
                    title=title,
                    description=f"## Kontekst\n\n{title} — nümunə məzmun.\n\n- Addım 1\n- Addım 2",
                    issue_type=itype, priority=prio, status=status,
                    assignee_id=assignee, reporter_id=sarah.id, story_points=points,
                )
                db.add(issue)
                await db.flush()
                db.add(models.Activity(
                    issue_id=issue.id, actor_id=sarah.id, action="created",
                    detail=f"Sarah created issue {issue.issue_key}"))
                if idx == 2:
                    db.add(models.Comment(issue_id=issue.id, author_id=john.id,
                                          content="Dark mode **paletini** rəhbərlə təsdiqlədim ✅"))
                    db.add(models.Activity(
                        issue_id=issue.id, actor_id=john.id, action="status_changed",
                        detail="John moved issue to In Progress"))
            db.add(models.IssueCounter(project_id=project.id, count=len(samples)))

        # --- Workspace 2: Quota Demo (free tier, 50/50 issues -> 51st shows upgrade modal)
        ws2 = (await db.execute(select(models.Workspace).where(models.Workspace.slug == "quota-demo"))).scalar_one_or_none()
        if ws2 is None:
            ws2 = models.Workspace(name="Quota Demo", slug="quota-demo", owner_id=demo.id)
            db.add(ws2)
            await db.flush()
            db.add(models.WorkspaceMember(workspace_id=ws2.id, user_id=demo.id, role="owner"))
            project2 = models.Project(
                workspace_id=ws2.id, name="API Service", key="API",
                description="Backend API", lead_id=demo.id,
            )
            db.add(project2)
            await db.flush()
            statuses = ["BACKLOG", "IN_PROGRESS", "IN_REVIEW", "DONE"]
            for n in range(1, 51):
                db.add(models.Issue(
                    project_id=project2.id, issue_key=f"API-{n}",
                    title=f"Sample API task {n}",
                    description="Nümunə ticket.",
                    issue_type="TASK", priority="MEDIUM", status=statuses[n % 4],
                    assignee_id=demo.id if n % 3 else None,
                    reporter_id=demo.id, story_points=n % 8 + 1,
                ))
            db.add(models.IssueCounter(project_id=project2.id, count=50))

    print("Seed hazırdır.")
    print("  sarah@acme.dev / password123  (Acme Inc — owner)")
    print("  john@acme.dev  / password123  (Acme Inc — member)")
    print("  demo@full.dev  / password123  (Quota Demo — 50/50 ticket, 51-ci upgrade modalı)")


if __name__ == "__main__":
    asyncio.run(main())
