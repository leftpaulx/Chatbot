import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes.chat import router as chat_router
from app.core.config import settings
from app.core.project_logging import setup_project_logging
from app.middleware.rate_limit import RateLimitMiddleware

setup_project_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(application: FastAPI):
    logger.info("app.startup origins=%s concurrency=%d", settings.ALLOWED_ORIGINS, settings.MAX_CONCURRENCY)
    yield
    logger.info("app.shutdown draining connections")


app = FastAPI(title="OB Chatbot", lifespan=lifespan)

origins = [o.strip() for o in settings.ALLOWED_ORIGINS.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["POST", "GET", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)
app.add_middleware(RateLimitMiddleware)

app.include_router(chat_router)


@app.exception_handler(Exception)
async def _unhandled_exception(request: Request, exc: Exception):
    logger.exception("unhandled_error path=%s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.get("/health")
async def health():
    try:
        from app.services.snowflake_setup import get_jwt_cached_async
        await get_jwt_cached_async()
        return {"status": "ok", "jwt_cached": True}
    except Exception as exc:
        logger.warning("health.degraded error=%s", exc)
        return JSONResponse(
            status_code=503,
            content={"status": "degraded", "error": str(exc)},
        )


_widget_dist = os.path.join(os.path.dirname(__file__), "..", "frontend", "widget", "dist")
if os.path.isdir(_widget_dist):
    app.mount("/widget", StaticFiles(directory=_widget_dist, html=True), name="widget")
