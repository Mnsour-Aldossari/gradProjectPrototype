"""Shared FastAPI dependencies: settings, DB session, current user."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel import Session

from app.config import Settings
from app.models import User
from app.security import decode_token

bearer = HTTPBearer(auto_error=False)


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_session(request: Request) -> Iterator[Session]:
    with Session(request.app.state.engine) as session:
        yield session


SettingsDep = Annotated[Settings, Depends(get_settings)]
SessionDep = Annotated[Session, Depends(get_session)]


def get_current_user(
    session: SessionDep,
    settings: SettingsDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> User:
    unauthorized = HTTPException(
        status.HTTP_401_UNAUTHORIZED, "Not authenticated", headers={"WWW-Authenticate": "Bearer"}
    )
    if credentials is None:
        raise unauthorized
    data = decode_token(credentials.credentials, settings.secret_key)
    if data is None:
        raise unauthorized
    user = session.get(User, data["sub"])
    if user is None:
        raise unauthorized
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_supervisor(user: CurrentUser) -> User:
    if user.role != "supervisor":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only a mission supervisor can do this")
    return user


SupervisorUser = Annotated[User, Depends(require_supervisor)]
