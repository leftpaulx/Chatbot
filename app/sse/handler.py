import asyncio
import json
import logging

from app.schemas.chat import ChatRequest
from app.services.snowflake_api import create_thread, cortex_agent_stream
from app.services.snowflake_setup import bind_brand_to_snowflake_session, snowflake_session
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
    widget protocol (markdown / text / chart / thread / error / done).

    The agent object handles tool orchestration, SQL execution, and response
    generation — the handler only needs to relay events and track thread state.

    Event reference:
    https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-agents-run
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
            logger.exception("thread.create_failed error=%s", exc)
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
    emitted_tables = 0
    emitted_charts = 0
    unknown_event_types: set[str] = set()

    # One Snowpark session per HTTP request: SET brand then close when done.
    guardrail_session = None

    try:
        if brand:

            def _open_session_with_brand():
                s = snowflake_session()
                bind_brand_to_snowflake_session(s, brand)
                return s

            guardrail_session = await asyncio.to_thread(_open_session_with_brand)
            logger.info("snowflake.brand_guardrail bound brand=%s", brand)

        async for item in cortex_agent_stream(
            jwt_token, snowflake_account, prompt, thread_id, parent_message_id
        ):
            event_type = item.get("event") or ""
            raw_data = item.get("data", "")

            # --- robust payload decode: always coerce to a dict ---
            try:
                parsed = json.loads(raw_data) if raw_data else {}
            except json.JSONDecodeError:
                parsed = {}
            data: dict = parsed if isinstance(parsed, dict) else {}

            try:
                # -- fatal error from upstream --
                if event_type == "error":
                    message = data.get("message", raw_data) if data else raw_data
                    code = data.get("code", "")
                    req_id = data.get("request_id", "")
                    logger.error(
                        "agent.error code=%s request_id=%s message=%s",
                        code, req_id, message,
                    )
                    yield construct_sse(event="error", data=f"Error: {message}")
                    break

                # -- agent status updates (planning, reasoning, etc.) --
                elif event_type == "response.status":
                    message = data.get("message", "Processing")
                    status = data.get("status", "")
                    logger.debug("agent.status status=%s message=%s", status, message)
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
                    tool_type = data.get("type", "")
                    logger.info(
                        "agent.tool_use name=%s type=%s", tool_name, tool_type,
                    )
                    friendly = TOOL_FRIENDLY_NAMES.get(tool_name, f"Using tool: {tool_name}")
                    yield construct_sse(event="markdown", data=friendly)

                # -- tool execution progress --
                elif event_type == "response.tool_result.status":
                    message = data.get("message", "Processing tool results")
                    logger.debug(
                        "agent.tool_status tool=%s status=%s message=%s",
                        data.get("tool_type"), data.get("status"), message,
                    )
                    yield construct_sse(event="markdown", data=message)

                # -- full tool result (e.g. analyst returned rows) --
                elif event_type == "response.tool_result":
                    logger.debug(
                        "agent.tool_result name=%s status=%s",
                        data.get("name"), data.get("status"),
                    )

                # -- analyst delta (think / sql / text / result_set partials) --
                elif event_type == "response.tool_result.analyst.delta":
                    delta = data.get("delta", {}) or {}
                    logger.debug(
                        "agent.analyst_delta has_sql=%s has_text=%s has_results=%s",
                        bool(delta.get("sql")),
                        bool(delta.get("text")),
                        bool(delta.get("result_set")),
                    )

                # -- table result from analyst tool --
                elif event_type == "response.table":
                    table_md = _result_set_to_markdown(data)
                    if table_md:
                        emitted_tables += 1
                        has_streamed_text = True
                        logger.info(
                            "agent.table emitted title=%s rows=%d",
                            data.get("title", ""),
                            len((data.get("result_set") or {}).get("data", []) or []),
                        )
                        yield construct_sse(event="text", data=table_md)

                # -- chart result (Vega-Lite spec) --
                elif event_type == "response.chart":
                    chart_spec = data.get("chart_spec", "")
                    if chart_spec:
                        emitted_charts += 1
                        logger.info(
                            "agent.chart emitted tool_use_id=%s spec_len=%d",
                            data.get("tool_use_id", ""), len(chart_spec),
                        )
                        chart_payload = json.dumps({
                            "tool_use_id": data.get("tool_use_id", ""),
                            "chart_spec": chart_spec,
                        })
                        yield construct_sse(event="chart", data=chart_payload)
                    else:
                        logger.warning("agent.chart empty_spec data_keys=%s", list(data.keys()))

                # -- thread metadata (message IDs for conversation continuity) --
                elif event_type == "metadata":
                    meta = data.get("metadata", data) or {}
                    if meta.get("role") == "assistant":
                        assistant_message_id = meta.get("message_id")
                        logger.debug(
                            "agent.metadata assistant_message_id=%s",
                            assistant_message_id,
                        )

                # -- non-fatal warnings (log only) --
                elif event_type == "response.warning":
                    logger.warning("agent.warning: %s", data.get("message", ""))

                # -- final aggregated response (last event from the agent) --
                elif event_type == "response":
                    got_response_event = True
                    logger.info(
                        "agent.response_done tables=%d charts=%d streamed_text=%s",
                        emitted_tables, emitted_charts, has_streamed_text,
                    )

                    if not has_streamed_text:
                        content = data.get("content", []) or []
                        for block in content:
                            if not isinstance(block, dict):
                                continue
                            if block.get("type") == "text":
                                text = block.get("text", "")
                                if text:
                                    yield construct_sse(event="text", data=text)
                            elif block.get("type") == "chart":
                                chart_obj = block.get("chart") or {}
                                spec = chart_obj.get("chart_spec", "")
                                if spec:
                                    chart_payload = json.dumps({
                                        "tool_use_id": chart_obj.get("tool_use_id", ""),
                                        "chart_spec": spec,
                                    })
                                    yield construct_sse(event="chart", data=chart_payload)

                    thread_data = json.dumps({
                        "thread_id": thread_id,
                        "parent_message_id": assistant_message_id or 0,
                    })
                    yield construct_sse(event="thread", data=thread_data)
                    yield construct_sse(event="done", data="[Done]")
                    break

                # -- anything else: log once per type, keep streaming --
                else:
                    if event_type and event_type not in unknown_event_types:
                        unknown_event_types.add(event_type)
                        logger.warning(
                            "agent.unknown_event type=%s keys=%s",
                            event_type, list(data.keys()) if data else [],
                        )

            except Exception as exc:
                # One bad event must not kill the whole stream or the UX.
                logger.exception(
                    "handler.event_processing_failed event=%s data_type=%s error=%s",
                    event_type, type(parsed).__name__, exc,
                )
                yield construct_sse(
                    event="error",
                    data=f"Error processing agent response ({event_type}): {exc}",
                )
                break

    except Exception as exc:
        # Failure inside the upstream stream itself (network, timeout, etc.)
        logger.exception("handler.stream_failed error=%s", exc)
        yield construct_sse(event="error", data=f"Agent stream failed: {exc}")

    finally:
        if guardrail_session is not None:
            try:
                await asyncio.to_thread(guardrail_session.close)
            except Exception:
                logger.exception("snowflake.brand_guardrail_session_close_failed")

    # Fallback done if the stream ended without a response event
    if not got_response_event:
        logger.info(
            "handler.stream_ended_without_response tables=%d charts=%d streamed_text=%s",
            emitted_tables, emitted_charts, has_streamed_text,
        )
        thread_data = json.dumps({
            "thread_id": thread_id,
            "parent_message_id": assistant_message_id or 0,
        })
        yield construct_sse(event="thread", data=thread_data)
        yield construct_sse(event="done", data="[Done]")


def _result_set_to_markdown(data: dict) -> str:
    """Convert a response.table event payload to a markdown table."""
    result_set = data.get("result_set", {}) or {}
    meta = result_set.get("resultSetMetaData", {}) or {}
    rows_data = result_set.get("data", []) or []
    row_types = meta.get("rowType", []) or []

    if not row_types or not rows_data:
        return ""

    headers = [col.get("name", "") for col in row_types if isinstance(col, dict)]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in rows_data[:50]:
        lines.append("| " + " | ".join(str(cell) for cell in row) + " |")

    title = data.get("title", "")
    prefix = f"\n**{title}**\n\n" if title else "\n"
    return prefix + "\n".join(lines) + "\n"
