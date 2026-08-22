"""ProspectIQ AI — FastAPI application entry point."""
from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.health import router as health_router
from app.api.v1.router import api_router
from app.core.config import settings
from app.core.logging import configure_logging, get_logger

configure_logging()
logger = get_logger(__name__)

DESCRIPTION = """
**ProspectIQ AI** is an autonomous B2B customer-acquisition platform: a department of
AI employees that discovers real businesses worldwide, researches them, finds decision
makers and verified contacts, scores the opportunity, and prepares a human for the
conversation.

### Two rules the API enforces everywhere
1. **No outbound sending.** The platform prepares drafts and requires human approval.
   Nothing is emailed or messaged automatically.
2. **No invented data.** Every stored fact carries a source, a source URL, a confidence
   score and a verification date. Where a fact cannot be established it is returned as
   `unknown` or `needs_verification` — never guessed.
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        "startup",
        app=settings.APP_NAME,
        version=settings.APP_VERSION,
        environment=settings.ENVIRONMENT,
    )
    yield
    logger.info("shutdown")


app = FastAPI(
    title=settings.APP_NAME,
    description=DESCRIPTION,
    version=settings.APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    """Attach a request id and log timing for every call."""
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
    started = time.monotonic()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("unhandled_error", path=request.url.path, request_id=request_id)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error", "request_id": request_id},
            headers={"X-Request-ID": request_id},
        )
    duration_ms = int((time.monotonic() - started) * 1000)
    response.headers["X-Request-ID"] = request_id
    if not request.url.path.startswith(("/docs", "/openapi", "/redoc")):
        logger.info(
            "request",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=duration_ms,
            request_id=request_id,
        )
    return response


# Registered last so it sits outermost: the error response produced by
# `request_context` above must still carry CORS headers, otherwise a 500 reaches
# the browser as an opaque CORS failure and the real error is invisible.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "Content-Disposition"],
)

app.include_router(health_router)
app.include_router(api_router, prefix=settings.API_V1_PREFIX)


@app.get("/", tags=["System"])
def root() -> dict:
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "api": settings.API_V1_PREFIX,
    }
