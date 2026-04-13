import json
import logging

from app.schemas.chat import ChatRequest
from app.services.snowflake_api import create_thread, cortex_agent_stream
from app.sse.utility import construct_sse

logger = logging.getLogger(__name__)

TOOL_FRIENDLY_NAMES = {
    "profitability_analyst": "Querying your data",
    "profitability_search": "Searching knowledge base",
}


async def parse_sse(
    jwt_token: str,
    snowflake_account: str,
    request: ChatRequest,
    brand: str,
):
    """Parse Cortex Agent Object SSE events and translate them into the
    widget protocol (markdown / text / thread / error / done).

    The agent object handles tool orchestration, SQL execution, and response
    generation — the handler only needs to relay events and track thread state.
    """
    # ---- resolve or create thread ----
    thread_id = request.thread_id
    parent_message_id = request.parent_message_id or 0

    if not thread_id:
        try:
            thread_id = await create_thread(jwt_token, snowflake_account)
            parent_message_id = 0
            logger.info("thread.created thread_id=%s", thread_id)
        except Exception as exc:
            logger.error("thread.create_failed error=%s", exc)
            yield construct_sse(event="error", data=f"Failed to create conversation thread: {exc}")
            yield construct_sse(event="done", data="[Done]")
            return

    yield construct_sse(event="markdown", data="Analyzing your question")

    # Prefix brand context so the agent filters data queries to this brand
    prompt = request.prompt
    if brand:
        prompt = (
            f'[Context: You are answering questions for brand "{brand}". '
            f"All data queries must be filtered to this brand only.]\n\n"
            f"{prompt}"
        )

    assistant_message_id = None
    has_streamed_text = False
    got_response_event = False

    async for item in cortex_agent_stream(
        jwt_token, snowflake_account, prompt, thread_id, parent_message_id
    ):
        event_type = item["event"]
        raw_data = item.get("data", "")

        try:
            data = json.loads(raw_data) if raw_data else {}
        except json.JSONDecodeError:
            data = {}

        # -- fatal error from upstream --
        if event_type == "error":
            message = data.get("message", raw_data) if isinstance(data, dict) else raw_data
            yield construct_sse(event="error", data=f"Error: {message}")
            break

        # -- agent status updates (planning, reasoning, etc.) --
        if event_type == "response.status":
            message = data.get("message", "Processing")
            yield construct_sse(event="markdown", data=message)

        # -- progressive text deltas (typewriter effect) --
        elif event_type == "response.text.delta":
            text = data.get("text", "")
            if text:
                has_streamed_text = True
                yield construct_sse(event="text", data=text)

        # -- complete text block (safety-net if deltas were missed) --
        elif event_type == "response.text":
            if not has_streamed_text:
                text = data.get("text", "")
                if text:
                    has_streamed_text = True
                    yield construct_sse(event="text", data=text)

        # -- tool being invoked --
        elif event_type == "response.tool_use":
            tool_name = data.get("name", "")
            friendly = TOOL_FRIENDLY_NAMES.get(tool_name, f"Using tool: {tool_name}")
            yield construct_sse(event="markdown", data=friendly)

        # -- tool execution progress --
        elif event_type == "response.tool_result.status":
            message = data.get("message", "Processing tool results")
            yield construct_sse(event="markdown", data=message)

        # -- table result from analyst tool --
        elif event_type == "response.table":
            table_md = _result_set_to_markdown(data)
            if table_md:
                has_streamed_text = True
                yield construct_sse(event="text", data=table_md)

        # -- thread metadata (message IDs for conversation continuity) --
        elif event_type == "metadata":
            meta = data.get("metadata", data)
            if meta.get("role") == "assistant":
                assistant_message_id = meta.get("message_id")

        # -- final aggregated response (last event from the agent) --
        elif event_type == "response":
            got_response_event = True
            if not has_streamed_text:
                content = data.get("content", [])
                for block in content:
                    if block.get("type") == "text":
                        text = block.get("text", "")
                        if text:
                            yield construct_sse(event="text", data=text)

            thread_data = json.dumps({
                "thread_id": thread_id,
                "parent_message_id": assistant_message_id or 0,
            })
            yield construct_sse(event="thread", data=thread_data)
            yield construct_sse(event="done", data="[Done]")
            break

        # -- non-fatal warnings (log only) --
        elif event_type == "response.warning":
            message = data.get("message", "")
            logger.warning("agent.warning: %s", message)

    # Fallback done if the stream ended without a response event
    if not got_response_event:
        thread_data = json.dumps({
            "thread_id": thread_id,
            "parent_message_id": assistant_message_id or 0,
        })
        yield construct_sse(event="thread", data=thread_data)
        yield construct_sse(event="done", data="[Done]")


def _result_set_to_markdown(data: dict) -> str:
    """Convert a response.table event payload to a markdown table."""
    result_set = data.get("result_set", {})
    meta = result_set.get("resultSetMetaData", {})
    rows_data = result_set.get("data", [])
    row_types = meta.get("rowType", [])

    if not row_types or not rows_data:
        return ""

    headers = [col["name"] for col in row_types]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in rows_data[:50]:
        lines.append("| " + " | ".join(str(cell) for cell in row) + " |")

    title = data.get("title", "")
    prefix = f"\n**{title}**\n\n" if title else "\n"
    return prefix + "\n".join(lines) + "\n"
