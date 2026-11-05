"""Host the existing React build and the protected Python API together."""
from __future__ import annotations

import os
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db
from app.main import app as backend


def create_hosted_app(directory: Path) -> FastAPI:
    if not (directory / "index.html").is_file():
        raise RuntimeError("Build webapp/dist before starting the hosted application")
    hosted = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    expected_revision = ScriptDirectory.from_config(Config("alembic.ini")).get_current_head()

    @hosted.get("/", include_in_schema=False)
    def index():
        return RedirectResponse("/concurrent-training/", status_code=307)

    @hosted.get("/ready", include_in_schema=False)
    def ready(db: Session = Depends(get_db)):
        try:
            revision = db.execute(text("select version_num from alembic_version")).scalar()
            if revision != expected_revision:
                return JSONResponse({"status": "not_ready", "database": "migration_required"}, status_code=503)
        except Exception:
            # Never expose connection strings, SQL, tokens, or driver errors.
            return JSONResponse({"status": "not_ready", "database": "unavailable"}, status_code=503)
        return JSONResponse({"status": "ready", "database": "connected"})

    hosted.mount("/concurrent-training", StaticFiles(directory=directory, html=True), name="webapp")
    # API URLs and its authentication stay unchanged, including OAuth callbacks.
    hosted.mount("/", backend)
    return hosted


def build_app() -> FastAPI:
    return create_hosted_app(Path(os.environ.get("CT_WEBAPP_DIRECTORY", "webapp/dist")))
