"""The dashboard's ROS 2 button: start and stop the project's ROS 2 nodes in WSL (app.ros_wsl), supervisors only.

Once started, the nodes read every mission as it flies (/mission/info, /sensors/readings, /uav/..., the detector
node's /landmine/candidates) and take commands (/mission/start, /mission/control, /mission/fly), which come back to
this backend as the supervisor who pressed the button.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from app.api.deps import SettingsDep, SupervisorUser
from app.config import Settings
from app.ros_wsl import RosStartFailed
from app.security import create_token, password_fingerprint

router = APIRouter(prefix="/api/ros", tags=["ros"])
NO_WSL = "ROS 2 starts from here only on Windows with WSL"


class RosStatus(BaseModel):
    available: bool  # this backend can start ROS 2 (Windows with WSL)
    running: bool
    distro: str
    message: str = ""


def _launcher(request: Request):
    return request.app.state.ros


async def _status(request: Request, settings: Settings, message: str = "") -> RosStatus:
    ros = _launcher(request)
    if ros is None:
        return RosStatus(available=False, running=False, distro="", message=NO_WSL)
    return RosStatus(available=True, running=await ros.running(), distro=settings.ros_wsl_distro, message=message)


@router.get("", response_model=RosStatus)
async def ros_status(request: Request, settings: SettingsDep, _: SupervisorUser) -> RosStatus:
    return await _status(request, settings)


@router.post("/start", response_model=RosStatus)
async def start_ros(request: Request, settings: SettingsDep, user: SupervisorUser) -> RosStatus:
    ros = _launcher(request)
    if ros is None:
        raise HTTPException(status.HTTP_409_CONFLICT, NO_WSL)
    server = request.scope.get("server") or ("127.0.0.1", 8000)
    url = settings.ros_backend_url or f"http://127.0.0.1:{server[1]}"
    token = create_token(
        user.id, user.role, settings.secret_key, settings.token_ttl_s, password_fingerprint(user.password_hash)
    )
    try:
        await ros.start(url, token)
    except (RosStartFailed, ValueError) as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e)) from e
    return await _status(request, settings, "ROS 2 started")


@router.post("/stop", response_model=RosStatus)
async def stop_ros(request: Request, settings: SettingsDep, _: SupervisorUser) -> RosStatus:
    ros = _launcher(request)
    if ros is None:
        raise HTTPException(status.HTTP_409_CONFLICT, NO_WSL)
    try:
        await ros.stop()
    except RosStartFailed as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e)) from e
    return await _status(request, settings, "ROS 2 stopped")
