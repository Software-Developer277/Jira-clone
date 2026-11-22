import secrets

from quart import Blueprint, jsonify, request
from sqlalchemy import select

from .. import models
from ..auth import auth_required, hash_password, verify_password
from ..serializers import user_dict
from ..db import db_session

bp = Blueprint("auth", __name__, url_prefix="/api")


@bp.post("/auth/register")
async def register():
    data = await request.get_json(silent=True) or {}
    email = str(data.get("email", "")).strip().lower()
    name = str(data.get("name", "")).strip()
    password = str(data.get("password", ""))
    if "@" not in email or not name or len(password) < 6:
        return jsonify(error="Valid email, name and password (min 6 chars) required"), 400
    async with db_session() as db:
        existing = (
            await db.execute(select(models.User).where(models.User.email == email))
        ).scalar_one_or_none()
        if existing:
            return jsonify(error="Email already registered"), 409
        user = models.User(email=email, name=name, password_hash=hash_password(password))
        db.add(user)
        await db.flush()
        token = secrets.token_urlsafe(32)
        db.add(models.ApiToken(token=token, user_id=user.id))
        return jsonify(token=token, user=user_dict(user)), 201


@bp.post("/auth/login")
async def login():
    data = await request.get_json(silent=True) or {}
    email = str(data.get("email", "")).strip().lower()
    password = str(data.get("password", ""))
    async with db_session() as db:
        user = (
            await db.execute(select(models.User).where(models.User.email == email))
        ).scalar_one_or_none()
        if user is None or not verify_password(password, user.password_hash):
            return jsonify(error="Invalid email or password"), 401
        token = secrets.token_urlsafe(32)
        db.add(models.ApiToken(token=token, user_id=user.id))
        return jsonify(token=token, user=user_dict(user))


@bp.get("/auth/me")
@auth_required
async def me():
    from quart import g

    return jsonify(user_dict(g.current_user))


@bp.post("/auth/logout")
@auth_required
async def logout():
    from quart import g

    async with db_session() as db:
        header = request.headers.get("Authorization", "")
        token = await db.get(models.ApiToken, header[7:].strip())
        if token is not None:
            await db.delete(token)
    return jsonify(ok=True)
