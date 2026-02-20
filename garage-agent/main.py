"""FastAPI entrypoint for the Garage Agent backend.

This file stays intentionally small so feature modules can be added cleanly:
- `routes/` for API and webhook endpoints
- `services/` for booking/follow-up business logic
- `db/` for SQLAlchemy models and session management
- `scheduler/` for APScheduler reminder jobs
"""

import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI

from db.init_db import init_db
from routes import webhook

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Initialize app resources before serving traffic."""
    # Ensure SQL tables exist at app startup.
    init_db()
    logger.info("Database tables initialized.")
    yield

app = FastAPI(
    title="Garage Agent API",
    version="0.1.0",
    description="AI-enabled garage booking backend foundation.",
    lifespan=lifespan,
)

app.include_router(webhook.router)


@app.get("/", tags=["health"])
def root() -> dict[str, str]:
    """Simple status endpoint for uptime checks."""
    return {"status": "Garage Agent Running"}
