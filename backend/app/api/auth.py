from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from sqlmodel import select

from app.models import User
from app.config import Settings
from app.schemas import LoginRequest, LoginResponse, SessionUser
from app.security import create_token, password_fingerprint, spend_password_check_time, verify_password

from .deps import CurrentUser, SessionDep, SettingsDep

router = APIRouter(prefix="/api/auth", tags=["auth"])


def session_user(user: User, settings: Settings) -> SessionUser:
    out = SessionUser.model_validate(user)
    if user.role == "supervisor" and settings.database_ui_url:
        out.database_ui_url = settings.database_ui_url
    return out


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, request: Request, session: SessionDep, settings: SettingsDep) -> LoginResponse:
    throttle = request.app.state.login_throttle
    client = request.client.host if request.client else "unknown"
    wait = throttle.retry_after(client, body.username)
    if wait:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too many failed sign-in attempts. Try again later.",
            headers={"Retry-After": str(wait)},
        )
    user = session.exec(select(User).where(User.username == body.username)).first()
    if user is None:
        spend_password_check_time(body.password)  # same response time as a wrong password for a real username
    if user is None or not verify_password(body.password, user.password_hash):
        throttle.record_failure(client, body.username)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid username or password")
    throttle.record_success(client, body.username)
    token = create_token(
        user.id, user.role, settings.secret_key, settings.token_ttl_s, password_fingerprint(user.password_hash)
    )
    return LoginResponse(token=token, user=session_user(user, settings))


@router.get("/me", response_model=SessionUser)
def me(user: CurrentUser, settings: SettingsDep) -> SessionUser:
    return session_user(user, settings)
