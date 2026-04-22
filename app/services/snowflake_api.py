import asyncio
import json
import logging
from typing import Optional

import aiohttp
from snowflake.snowpark import Session
from snowflake.cortex import complete

from app.core.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
#  Thread management (Cortex Agent Threads API)
# ---------------------------------------------------------------------------

async def create_thread(jwt_token: str, snowflake_account: str) -> str:
    """Create a new Cortex Agent thread. Returns the thread ID as a string."""
    url = f"https://{snowflake_account}.snowflakecomputing.com/api/v2/cortex/threads"
    headers = {
        "Authorization": f"Bearer {jwt_token}",
        "X-Snowflake-Authorization-Token-Type": "KEYPAIR_JWT",
        "Content-Type": "application/json",
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(
            url, headers=headers, json={"origin_application": "ob_chatbot"}
        ) as resp:
            body = await resp.text()
            if resp.status != 200:
                raise RuntimeError(f"Thread creation failed ({resp.status}): {body}")
            # API may return a bare ID string or a full JSON object
            try:
                data = json.loads(body)
                if isinstance(data, dict):
                    return str(data["thread_id"])
                return str(data)
            except (json.JSONDecodeError, KeyError):
                return body.strip().strip('"')


# ---------------------------------------------------------------------------
#  Agent Object streaming (new API)
# ---------------------------------------------------------------------------

async def cortex_agent_stream(
    jwt_token: str,
    snowflake_account: str,
    prompt: str,
    thread_id: Optional[str] = None,
    parent_message_id: int = 0,
):
    """Stream SSE events from the Cortex Agent Object API.

    Uses the agent-object endpoint so tools, model, and instructions are
    configured on the PROFITABILITY_AGENT object — not in the request body.
    When a thread_id is supplied the agent continues the threaded conversation.
    """
    url = f"https://{snowflake_account}.snowflakecomputing.com{settings.AGENT_PATH}"

    payload: dict = {
        "messages": [
            {
                "role": "user",
                "content": [{"type": "text", "text": prompt}],
            }
        ],
    }

    if thread_id is not None:
        payload["thread_id"] = int(thread_id)
        payload["parent_message_id"] = parent_message_id

    headers = {
        "Authorization": f"Bearer {jwt_token}",
        "X-Snowflake-Authorization-Token-Type": "KEYPAIR_JWT",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
    }

    timeout = aiohttp.ClientTimeout(total=settings.AGENT_TIMEOUT_SEC)

    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(
                url, headers=headers, json=payload, timeout=timeout
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    yield {"event": "error", "data": f"HTTP {resp.status}: {body}"}
                    return

                event_type, data_buf = None, None
                async for raw_bytes in resp.content:
                    for chunk in raw_bytes.splitlines():
                        line = chunk.decode("utf-8")
                        if line == "":
                            if data_buf is not None:
                                logger.debug(
                                    "cortex.sse_event type=%s data_len=%d preview=%s",
                                    event_type,
                                    len(data_buf),
                                    (data_buf[:200] + "...") if len(data_buf) > 200 else data_buf,
                                )
                                yield {"event": event_type, "data": data_buf}
                                event_type, data_buf = None, None
                            continue
                        if line.startswith("event: "):
                            event_type = line[7:]
                        elif line.startswith("data: "):
                            piece = line[6:]
                            data_buf = piece if data_buf is None else data_buf + "\n" + piece

                # flush any trailing event
                if data_buf is not None:
                    logger.debug(
                        "cortex.sse_event type=%s data_len=%d (trailing)",
                        event_type, len(data_buf),
                    )
                    yield {"event": event_type, "data": data_buf}

        except asyncio.TimeoutError:
            yield {"event": "error", "data": "Agent call timed out"}


# ---------------------------------------------------------------------------
#  Legacy utilities (kept for optional direct-query use outside the agent)
# ---------------------------------------------------------------------------

async def execute_sql_async(sql: str, session: Session, max_rows: int = 1000):
    df = await asyncio.to_thread(
        lambda: session.sql(sql.replace(";", "")).limit(max_rows).to_pandas()
    )
    return df


async def cortex_complete_async(prompt: str, session: Session) -> str:
    return await asyncio.to_thread(
        lambda: complete("claude-sonnet-4-5", prompt, session=session)
    )
