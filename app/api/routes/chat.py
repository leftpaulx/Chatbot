import asyncio
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.core.auth import verify_api_key
from app.core.config import settings
from app.core.project_logging import request_id_var
from app.schemas.chat import ChatRequest
from app.services.snowflake_setup import get_jwt_cached_async
from app.sse.handler import parse_sse

logger = logging.getLogger(__name__)

router = APIRouter()
_semaphore = asyncio.Semaphore(settings.MAX_CONCURRENCY)


@router.post('/chat', dependencies=[Depends(verify_api_key)])
async def chat_endpoint(
    request: ChatRequest,
    req: Request,
):
    if not request.prompt or not request.brand:
        raise HTTPException(status_code=400, detail="Prompt and brand are required")

    rid = uuid.uuid4().hex[:8]
    request_id_var.set(rid)
    logger.info("chat.start brand=%s", request.brand)

    jwt_token = await get_jwt_cached_async()

    async def generator():
        request_id_var.set(rid)
        try:
            async with _semaphore:
                async for evt in parse_sse(jwt_token, settings.SNOWFLAKE_ACCOUNT, request, request.brand):
                    if await req.is_disconnected():
                        break
                    yield evt
        finally:
            logger.info("chat.end brand=%s", request.brand)

    return StreamingResponse(generator(), media_type="text/event-stream")
