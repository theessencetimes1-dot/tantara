from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from app.db import SessionLocal
from app.models import User
from app.security import create_token, current_user, verify_password

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class Login(BaseModel):
    email: str
    password: str


@router.post("/login")
def login(payload: Login):
    with SessionLocal() as s:
        user = s.scalar(select(User).where(User.email == payload.email.lower()))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(401, "Invalid email or password")
    public = {k: getattr(user, k) for k in ("id", "name", "email", "role", "avatar_initials", "title")}
    return {"access_token": create_token(user.id), "token_type": "bearer", "user": public}


@router.get("/me")
def me(user=Depends(current_user)):
    return user
