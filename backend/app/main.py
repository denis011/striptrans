from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI
from sqlalchemy.orm import sessionmaker

from app import models  # noqa: F401  registruje tabele
from app.config import Settings, get_settings
from app.db import make_engine, run_migrations
from app.routers import (
    blocks,
    debug,
    exports,
    fonts,
    glossary,
    health,
    pages,
    patches,
    projects,
    ratings,
    review,
    series,
    sfx,
    styles,
)
from app.services.llamaserver import ocr_client


def create_app(
    settings: Settings | None = None, llama_transport: httpx.BaseTransport | None = None
) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        Path(settings.data_dir).mkdir(parents=True, exist_ok=True)
        run_migrations(settings.database_url)
        engine = make_engine(settings.database_url)
        app.state.settings = settings
        app.state.session_factory = sessionmaker(engine)
        app.state.llama = ocr_client(settings, llama_transport)
        yield
        app.state.llama.close()
        engine.dispose()

    app = FastAPI(title="StripTrans", lifespan=lifespan)
    app.include_router(health.router)
    app.include_router(debug.router)
    app.include_router(series.router)
    app.include_router(projects.router)
    app.include_router(pages.router)
    app.include_router(blocks.router)
    app.include_router(patches.router)
    app.include_router(glossary.router)
    app.include_router(sfx.router)
    app.include_router(styles.router)
    app.include_router(ratings.router)
    app.include_router(review.router)
    app.include_router(fonts.router)
    app.include_router(exports.router)
    return app
