"""NEXORA API entry point. Run with:

    uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000

Read-only: every route reads from Snowflake ANALYTICS/CORE views and
tables built in Phases 2D-5. Nothing here writes to Snowflake, retrains a
model, or executes a business action -- see docs/api_reference.md.
"""

import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from backend.core.config import settings
from backend.core.exceptions import register_exception_handlers
from backend.core.logging import get_logger, setup_logging
from backend.routers import customers, decisions, health, metadata, overview, predictions, projects, revenue, support

setup_logging()
logger = get_logger("main")

app = FastAPI(
    title="NEXORA — Enterprise Decision Intelligence API",
    version=settings.app_version,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# CORS: explicit allowlist only (backend.core.config.settings.cors_origins),
# never "*" -- the frontend must never connect directly to Snowflake, and a
# wildcard origin would undermine the point of routing everything through
# this API in the first place.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET"],  # Phase 6 is read-only -- no mutating verbs are exposed
    allow_headers=["*"],
)

register_exception_handlers(app)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    started = time.monotonic()
    response = await call_next(request)
    duration_ms = (time.monotonic() - started) * 1000
    logger.info("%s %s -> %d (%.1fms)", request.method, request.url.path, response.status_code, duration_ms)
    return response


api_router_modules = [health, overview, customers, revenue, projects, support, predictions, decisions, metadata]
for module in api_router_modules:
    app.include_router(module.router, prefix=settings.api_prefix)


@app.get("/", include_in_schema=False)
def root():
    return {"service": settings.app_name, "version": settings.app_version, "docs": "/docs"}
