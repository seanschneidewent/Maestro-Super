"""FastAPI application entry point."""

import asyncio
import logging
import sys
from contextlib import asynccontextmanager
from uuid import uuid4

# Configure logging to output to stdout (Railway captures this)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import get_settings
from app.database.session import SessionLocal
from app.services.core.pass2_worker import run_pass2_worker
from app.services.v3.heartbeat import run_heartbeat_scheduler
from app.services.v3.session_manager import SessionManager, run_checkpoint_loop

logger = logging.getLogger(__name__)
from app.routers import (
    conversations,
    disciplines,
    health,
    pages,
    pointers,
    processing,
    projects,
    v3_sessions,
    v3_telegram,
)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle — start background workers on startup."""
    SessionManager.instance().set_event_loop(asyncio.get_running_loop())

    # Rehydrate active V3 sessions
    db = SessionLocal()
    try:
        SessionManager.instance().rehydrate_active_sessions(db)
    finally:
        db.close()

    # Start Pass 2 enrichment worker
    pass2_task = asyncio.create_task(run_pass2_worker())
    logger.info("Pass 2 enrichment worker launched")

    checkpoint_task = asyncio.create_task(run_checkpoint_loop())
    logger.info("Session checkpoint loop launched")

    # Start Heartbeat scheduler (if enabled)
    heartbeat_task = asyncio.create_task(run_heartbeat_scheduler(SessionLocal))
    logger.info("Heartbeat scheduler launched")

    yield

    # Shutdown: cancel the workers
    pass2_task.cancel()
    checkpoint_task.cancel()
    heartbeat_task.cancel()
    try:
        await pass2_task
    except asyncio.CancelledError:
        logger.info("Pass 2 enrichment worker stopped")
    try:
        await checkpoint_task
    except asyncio.CancelledError:
        logger.info("Session checkpoint loop stopped")
    try:
        await heartbeat_task
    except asyncio.CancelledError:
        logger.info("Heartbeat scheduler stopped")


app = FastAPI(
    title="Maestro Super API",
    description="Construction plan analysis for superintendents",
    version="0.1.0",
    redirect_slashes=False,  # Prevent 307 redirects that break HTTPS through proxies
    lifespan=lifespan,
)

# CORS for frontend
origins = [
    "http://localhost:3000",
    "http://localhost:3001",
    "http://localhost:3002",
    "http://localhost:3003",
    "http://localhost:3004",
    "http://localhost:5173",
]

# Add production frontend URL if configured (handle www and non-www)
if settings.frontend_url:
    origins.append(settings.frontend_url)
    # Also add www/non-www variant
    if "://www." in settings.frontend_url:
        origins.append(settings.frontend_url.replace("://www.", "://"))
    elif "://" in settings.frontend_url:
        origins.append(settings.frontend_url.replace("://", "://www."))

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health.router)
app.include_router(projects.router)
app.include_router(disciplines.router)
app.include_router(pages.router)
app.include_router(pointers.router)
app.include_router(conversations.router)
app.include_router(processing.router)
app.include_router(v3_sessions.router)

# Telegram bot webhook (only mount if configured)
if settings.telegram_bot_token:
    app.include_router(v3_telegram.router)
    logger.info("Telegram webhook router mounted")


# Global exception handlers
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Handle HTTP exceptions with consistent format."""
    error_id = str(uuid4())

    # Determine error type
    if exc.status_code == 429:
        error_type = "rate_limit"
    elif exc.status_code == 404:
        error_type = "not_found"
    elif exc.status_code == 400:
        error_type = "validation"
    elif exc.status_code == 401 or exc.status_code == 403:
        error_type = "auth"
    else:
        error_type = "server_error"

    # If detail is already a dict (from rate limiting), use it directly
    if isinstance(exc.detail, dict):
        content = {**exc.detail, "error_id": error_id}
    else:
        content = {
            "detail": str(exc.detail),
            "error_type": error_type,
            "error_id": error_id,
        }

    logger.warning(
        f"HTTP {exc.status_code} [{error_id}]: {exc.detail} - {request.method} {request.url.path}"
    )

    return JSONResponse(
        status_code=exc.status_code,
        content=content,
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle Pydantic validation errors with field details."""
    error_id = str(uuid4())

    # Format validation errors
    errors = []
    for error in exc.errors():
        field = ".".join(str(loc) for loc in error["loc"])
        errors.append({"field": field, "message": error["msg"]})

    content = {
        "detail": "Validation error",
        "error_type": "validation",
        "error_id": error_id,
        "errors": errors,
    }

    logger.warning(
        f"Validation error [{error_id}]: {errors} - {request.method} {request.url.path}"
    )

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=content,
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch-all handler for unhandled exceptions."""
    error_id = str(uuid4())

    logger.error(
        f"Unhandled exception [{error_id}]: {type(exc).__name__}: {exc} - "
        f"{request.method} {request.url.path}",
        exc_info=True,
    )

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "Internal server error",
            "error_type": "server_error",
            "error_id": error_id,
        },
    )
