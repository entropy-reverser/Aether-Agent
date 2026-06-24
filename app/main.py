"""app.main — FastAPI application entry point.

Mounts the routing router and exposes the app object for ``uvicorn app.main:app``.
"""

from __future__ import annotations

from fastapi import FastAPI

from app.api.routes import router
from app.api.wiki_routes import router as wiki_router
from app.utils.logger import logger


def create_app() -> FastAPI:
    """Build the FastAPI app. Kept as a function for test client reuse."""
    app = FastAPI(
        title="Aether-Agent v2",
        description="Zero-LLM score-based model routing engine + self-growing wiki",
        version="0.2.0",
    )
    app.include_router(router)
    app.include_router(wiki_router)
    logger.info("FastAPI app created; routing + wiki routers mounted")
    return app


app = create_app()
