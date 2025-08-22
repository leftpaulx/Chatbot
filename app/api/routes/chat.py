from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from app.schemas.chat import ChatRequest
from app.services.snowflake_setup import get_jwt_cached_async, snowflake_session
from app.sse.handler import parse_sse
from app.core.config import settings
import asyncio



router = APIRouter()
_semaphore = asyncio.Semaphore(settings.MAX_CONCURRENCY) 

@router.post('/chat')
async def chat_endpoint(request: ChatRequest, req: Request):
    """
    The chat endpoint
    Args:
        request: ChatRequest - The chat request
        req: Request - The API request parameter
    Returns:
        StreamingResponse - The streaming response
    """
    if not request.prompt or not request.brand:
        raise HTTPException(status_code=400, detail="Prompt and Brandcode are required")
    jwt_token = await get_jwt_cached_async()
    async def generator():
        SF_SESSION = snowflake_session()
        SF_SESSION.sql(f"SET brand = '{request.brand}'").collect()  # set the brand code for the current session to guardrail data
        async with _semaphore:
            async for evt in parse_sse(jwt_token, settings.SNOWFLAKE_ACCOUNT,request,SF_SESSION):
                if await req.is_disconnected():
                    break
                yield evt
        SF_SESSION.close()
    return StreamingResponse(generator(), media_type="text/event-stream")