import hmac
import logging

from fastapi import HTTPException, Request

from app.core.config import settings

logger = logging.getLogger(__name__)


async def verify_api_key(request: Request) -> None:
    """FastAPI dependency -- reject requests without a valid API key."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    token = auth[7:]
    if not hmac.compare_digest(token, settings.API_KEY):
        raise HTTPException(status_code=401, detail="Invalid API key")
