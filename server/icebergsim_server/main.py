"""App factory and local entry point. Localhost-only by default (SPEC §20)."""

from __future__ import annotations

from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from icebergsim._version import SPEC_VERSION
from icebergsim_server.routes import api_router

_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EXAMPLES_DIR = _REPO_ROOT / "spec" / "examples"
DEFAULT_STATIC_DIR = _REPO_ROOT / "web" / "dist"


def create_app(
    *,
    examples_dir: Path | None = None,
    static_dir: Path | None = DEFAULT_STATIC_DIR,
) -> FastAPI:
    app = FastAPI(title="ICEBERGSIM v2", version=SPEC_VERSION)
    app.include_router(api_router(examples_dir or DEFAULT_EXAMPLES_DIR))
    if static_dir is not None and static_dir.is_dir():
        # The built SPA; html=True serves index.html at / and on client-side routes.
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="spa")
    return app


def run() -> None:
    """Console entry point: ``icebergsim-server`` (local-only operation, SPEC §20)."""
    uvicorn.run(create_app(), host="127.0.0.1", port=8000)
