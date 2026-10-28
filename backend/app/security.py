"""stdlib scrypt credentials and HS256 bearer authentication."""

import base64
import hashlib
import hmac
import json
import os
import time

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import get_settings
from app.db import SessionLocal
from app.models import User


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return base64.urlsafe_b64encode(salt).decode() + "$" + base64.urlsafe_b64encode(dk).decode()


def verify_password(password: str, encoded: str) -> bool:
    try:
        salt, expected = encoded.split("$")
        salt = base64.urlsafe_b64decode(salt)
        expected = base64.urlsafe_b64decode(expected)
        return hmac.compare_digest(hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1), expected)
    except Exception:
        return False


def _key():
    p = get_settings().data_dir / ".secret"
    p.parent.mkdir(parents=True, exist_ok=True)
    if not p.exists():
        fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(os.urandom(48))
    return p.read_bytes()


def _b64(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def create_token(uid):
    head = _b64(b'{"alg":"HS256","typ":"JWT"}')
    body = _b64(json.dumps({"sub": uid, "exp": int(time.time()) + 86400}).encode())
    sig = _b64(hmac.new(_key(), f"{head}.{body}".encode(), hashlib.sha256).digest())
    return f"{head}.{body}.{sig}"


bearer = HTTPBearer(auto_error=False)


def current_user(creds: HTTPAuthorizationCredentials | None = Depends(bearer)):
    if not creds:
        raise HTTPException(401, "Authentication required")
    try:
        a, b, sig = creds.credentials.split(".")
        expected = _b64(hmac.new(_key(), f"{a}.{b}".encode(), hashlib.sha256).digest())
        payload = json.loads(base64.urlsafe_b64decode(b + "=" * ((4 - len(b) % 4) % 4)))
        if not hmac.compare_digest(sig, expected) or payload["exp"] < time.time():
            raise ValueError()
        with SessionLocal() as session:
            user = session.get(User, payload["sub"])
        if user is None:
            raise ValueError()
        return {k: getattr(user, k) for k in ("id", "name", "email", "role", "avatar_initials", "title")}
    except Exception:
        raise HTTPException(401, "Invalid or expired token")


def require_roles(*roles):
    def dependency(user=Depends(current_user)):
        if user["role"] not in roles:
            raise HTTPException(403, "Insufficient role")
        return user

    return dependency


def audit(user, action, obj_type, obj_id):
    from app.db import session_scope
    from app.services.audit import record

    with session_scope() as session:
        record(session, user["id"], action, obj_type, obj_id)
