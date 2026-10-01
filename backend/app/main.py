"""FastAPI application. Run with: uvicorn app.main:app --reload"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import auth, detections, missions
from .api.runner import MissionRunner
from .config import Settings
from .db import init_db, make_engine
from .seed import fail_interrupted_missions, seed_users


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    engine = make_engine(settings.database_url)
    runner = MissionRunner(engine)

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

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(auth.router)
    app.include_router(missions.router)
    app.include_router(detections.router)

    @app.get("/api/health", tags=["health"])
    def health() -> dict:
        return {"status": "ok", "uav_source": settings.uav_source}

    return app


app = create_app()
