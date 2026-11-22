from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Workspace(Base):
    __tablename__ = "workspaces"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    plan_tier: Mapped[str] = mapped_column(String(20), default="free")  # free / pro
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class WorkspaceMember(Base):
    __tablename__ = "workspace_members"
    __table_args__ = (UniqueConstraint("workspace_id", "user_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String(20), default="member")  # owner / admin / member


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (UniqueConstraint("workspace_id", "key"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    key: Mapped[str] = mapped_column(String(12))
    description: Mapped[str] = mapped_column(Text, default="")
    lead_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)  # soft delete
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class IssueCounter(Base):
    """Per-project atomic counter backing sequential issue keys (WEB-1, WEB-2...)."""
    __tablename__ = "issue_counters"
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), primary_key=True)
    count: Mapped[int] = mapped_column(default=0)


class Issue(Base):
    __tablename__ = "issues"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    issue_key: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    issue_type: Mapped[str] = mapped_column(String(20), default="TASK")  # BUG / FEATURE / TASK
    priority: Mapped[str] = mapped_column(String(20), default="MEDIUM")  # LOW / MEDIUM / HIGH / CRITICAL
    status: Mapped[str] = mapped_column(String(20), default="BACKLOG")   # BACKLOG / IN_PROGRESS / IN_REVIEW / DONE
    assignee_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reporter_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    story_points: Mapped[int | None] = mapped_column(nullable=True)
    version: Mapped[int] = mapped_column(default=1)  # optimistic locking
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class Comment(Base):
    __tablename__ = "comments"
    id: Mapped[int] = mapped_column(primary_key=True)
    issue_id: Mapped[int] = mapped_column(ForeignKey("issues.id"), index=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Activity(Base):
    """Audit trail: 'Sarah moved issue to In Review', ..."""
    __tablename__ = "activities"
    id: Mapped[int] = mapped_column(primary_key=True)
    issue_id: Mapped[int] = mapped_column(ForeignKey("issues.id"), index=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(32))  # created / status_changed / assignee_changed / priority_changed / commented
    detail: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ApiToken(Base):
    __tablename__ = "api_tokens"
    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
