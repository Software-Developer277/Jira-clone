"""Password hashing, bearer-token auth, workspace membership enforcement."""
import hashlib
import hmac
import os
import secrets
from functools import wraps

from quart import g, jsonify, request
from sqlalchemy import select

from . import models
from .db import db_session

PBKDF2_ITERATIONS = 100_000


def hash_password(password: str) -> str:
    salt = os.urandom(16).hex()
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), PBKDF2_ITERATIONS).hex()
    return f"{salt}${dk}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt, dk = stored.split("$")
    except ValueError:
        return False
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), PBKDF2_ITERATIONS).hex()
    return hmac.compare_digest(candidate, dk)


async def user_by_token(db, token: str):
    api_token = await db.get(models.ApiToken, token)
    if api_token is None:
        return None
    return await db.get(models.User, api_token.user_id)


def auth_required(fn):
    """Decorator: validates Bearer token, loads user into g.current_user."""

    @wraps(fn)
    async def wrapper(*args, **kwargs):
        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return jsonify(error="Missing Authorization token"), 401
        async with db_session() as db:
            user = await user_by_token(db, header[7:].strip())
        if user is None:
            return jsonify(error="Invalid or revoked token"), 401
        g.current_user = user
        return await fn(*args, **kwargs)

    return wrapper


async def require_member(db, workspace_id: int):
    """Enforce multi-tenancy: returns (workspace, membership, error_response).

    error_response is None on success; otherwise a (jsonify, status) tuple.
    """
    ws = await db.get(models.Workspace, workspace_id)
    if ws is None:
        return None, None, (jsonify(error="Workspace not found"), 404)
    result = await db.execute(
        select(models.WorkspaceMember).where(
            models.WorkspaceMember.workspace_id == workspace_id,
            models.WorkspaceMember.user_id == g.current_user.id,
        )
    )
    member = result.scalar_one_or_none()
    if member is None:
        return ws, None, (jsonify(error="Not a workspace member"), 403)
    return ws, member, None
