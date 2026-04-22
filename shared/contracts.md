# SSE Protocol Contract

Shared specification between the backend (`app/`) and the widget (`frontend/widget/`).

## Endpoint

`POST /chat`

### Request Headers

| Header | Value |
|--------|-------|
| `Content-Type` | `application/json` |
| `Authorization` | `Bearer <API_KEY>` |

### Request Body

```json
{
  "prompt": "string (required)",
  "brand": "string (required)",
  "thread_id": "string (optional – omit for first message)",
  "parent_message_id": 0
}
```

`thread_id` and `parent_message_id` enable conversation continuity via
[Cortex Agent Threads](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-agents-threads).
On the first message, omit both fields — the backend creates a thread automatically
and returns the context via a `thread` event. On follow-up messages, pass the
`thread_id` and `parent_message_id` received from the previous `thread` event.

### Response

`Content-Type: text/event-stream`

---

## Event Types

### `markdown`

Status and narration messages during processing. Widget renders these as
transient status indicators that are replaced as new ones arrive.

```
event: markdown
data: Analyzing your question
```

### `text`

Answer content, streamed progressively as token deltas. The widget appends
each `text` event's data to the assistant bubble and re-renders markdown.

```
event: text
data: Based on the data, your AOV last month was
```

### `chart`

A chart produced by the Cortex Agent (Vega-Lite v5). The widget renders
the spec inline in the current assistant bubble, below any streamed text.
Multiple `chart` events may be emitted per response (one per agent chart).

```
event: chart
data: {"tool_use_id":"toolu_123","chart_spec":"{\"$schema\":\"https://vega.github.io/schema/vega-lite/v5.json\",...}"}
```

`chart_spec` is the raw Vega-Lite specification as a JSON string, forwarded
verbatim from the agent's `response.chart` event.

### `thread`

Thread context for conversation continuity. Sent once, before `done`.
The widget stores these values and sends them back in the next request.

```
event: thread
data: {"thread_id":"1234567890","parent_message_id":456}
```

### `error`

Error messages. The stream may continue after an error event.

```
event: error
data: Error: Agent call timed out
```

### `done`

End-of-stream sentinel. No more events will follow.

```
event: done
data: [Done]
```

---

## Event Ordering

1. One or more `markdown` events (status updates during processing)
2. Zero or more `text` events (answer tokens — streamed progressively)
3. Zero or more `chart` events (Vega-Lite specs, interleaved with `text`)
4. Exactly one `thread` event (thread context for follow-up messages)
5. Zero or more `error` events
6. Exactly one `done` event (terminal)

## Wire Format

- Each field on its own line: `event: <type>` and `data: <content>`
- Multi-line data uses multiple `data:` lines
- Events are separated by double newlines (`\n\n`)
- All content is UTF-8 encoded

## Architecture Notes

The backend uses the **Agent Object API** (`/api/v2/databases/{db}/schemas/{schema}/agents/{name}:run`)
with **server-managed threads**. This means:

- **Tools, model, and instructions** are configured on the `PROFITABILITY_AGENT` object — not in the request body.
- **Conversation history** is managed server-side via threads — the widget does not send chat history.
- **Authentication** uses a shared Bearer API key validated by the backend.
- **Brand context** is supplied by the widget in the request body.
- **SQL execution and response generation** are handled entirely by the agent — the backend only relays events.
