from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlmodel import select

from app.models import User
from app.schemas import LoginRequest, LoginResponse, UserRead
from app.security import create_token, verify_password

from .deps import CurrentUser, SessionDep, SettingsDep

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, session: SessionDep, settings: SettingsDep) -> LoginResponse:
    user = session.exec(select(User).where(User.username == body.username)).first()
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid username or password")
    token = create_token(user.id, user.role, settings.secret_key, settings.token_ttl_s)
    return LoginResponse(token=token, user=UserRead.model_validate(user))


@router.get("/me", response_model=UserRead)
def me(user: CurrentUser) -> User:
    return user
