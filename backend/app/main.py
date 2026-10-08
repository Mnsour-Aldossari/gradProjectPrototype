"""FastAPI application. Run with: uvicorn app.main:app --reload"""

from __future__ import annotations

import faulthandler
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import accuracy, auth, detections, evaluation, heatmap, missions, reports, ros, ws
from .api.runner import MissionRunner
from .api.ws import Hub
from .config import Settings
from .db import init_db, make_engine
from .ros_wsl import RosInWsl
from .seed import fail_interrupted_missions, seed_users
from .uav.px4_mavlink_source import mavsdk_installed

# A crash in native code (MAVSDK's library, for PX4) ends the backend without a Python error; this prints where it was.
faulthandler.enable()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    engine = make_engine(settings.database_url)
    hub = Hub()
    runner = MissionRunner(engine, hub)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        init_db(engine)
        seed_users(engine)
        fail_interrupted_missions(engine)
        yield
        await runner.shutdown()
        engine.dispose()

    app = FastAPI(
        title="UAV-Based Landmine Detection System - Prototype API",
        description="Simulation-based prototype. All detections are potential detections for verification by trained personnel.",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.engine = engine
    app.state.runner = runner
    app.state.hub = hub
    app.state.ros = RosInWsl(settings.ros_wsl_distro) if settings.ros_wsl else None

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(auth.router)
    app.include_router(missions.router)
    app.include_router(heatmap.router)
    app.include_router(reports.router)
    app.include_router(detections.router)
    app.include_router(evaluation.router)
    app.include_router(accuracy.router)
    app.include_router(ros.router)
    app.include_router(ws.router)

    @app.get("/api/health", tags=["health"])
    def health() -> dict:
        # px4_available: the server can talk to PX4 (MAVSDK installed); whether PX4 runs shows when a mission starts.
        # px4_restarts: PX4 SITL is started at a mission's takeoff point when needed (Docker on this machine).
        # px4_gazebo: PX4 SITL can also be started in Gazebo's window (WSL on this Windows PC).
        # px4_manage_off: both are turned off with PX4_MANAGE_DOCKER=0.
        return {
            "status": "ok",
            "px4_available": mavsdk_installed(),
            "px4_restarts": settings.px4_manage_docker,
            "px4_gazebo": settings.px4_manage_gazebo,
            "px4_manage_off": settings.px4_manage_off,
            "database": engine.dialect.name,  # sqlite or postgresql: which one holds the data
        }

    return app


app = create_app()
