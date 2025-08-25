*Endpoint: POST /chat (SSE)*

*Request (JSON)*

{
  "prompt": "What was our AOV last month?",
  "brand": "gamersupps",
  "history": [
    {"role":"user","message":"Show me revenue by region"},
    {"role":"assistant","message":"Here are last quarter numbers..."}
  ]
}


prompt (string, required): the user question

brand (string, required): brand code; backend enforces row-level guardrails (SET BRAND = '<brand>')

history (optional): recent messages; only {role, message} pairs (no markdown events). The server summarizes the last ~6 messages.

*Response*

Content-Type: text/event-stream
Stream of SSE events:

event: markdown → status / narration / tool messages (render as Markdown)

event: text → final answer chunks

event: error → error message (stream continues to done)

event: done → end sentinel ([Done])

*Example (raw):*

event: markdown
data: Analyzing the prompt

event: markdown
data: Tool: analyze_data is being used

event: markdown
data: Interating with database

event: text
data: • AOV last month was $73.21 (+4.2% MoM) ...

event: done
data: [Done]

*cURL (dev)*
curl -N -X POST \
  -H 'Content-Type: application/json' \
  -d '{
    "prompt": "What was our AOV last month?",
    "brand": "OUTER",
    "history": [
      {"role":"user","message":"Show me revenue by region"},
      {"role":"assistant","message":"Here are last quarter numbers..."}
    ]
  }' \
  http://localhost:8000/chat

*How it Works (Server Flow)*

    1. Validate prompt & brand.

    2. Create Snowflake session for the request, set guardrail:

        SET BRAND = '<brand>';


    3.(Optional) Summarize the last ~6 messages with complete('claude-3-5-sonnet', ...).

    4. Start a Cortex Agent stream with tool cortex_analyst_text_to_sql.

    5. As the agent emits deltas:

    6. Emit tool usage as markdown.

    7. On tool_results.sql, run the SQL via Snowpark (offloaded with asyncio.to_thread).

    8. If a DataFrame returns, summarize results back to natural language (complete(...)) and stream as text.

    9. On completion, send done. If any error occurs, stream error then done.

    10. Close the Snowflake session in a finally block.

*Key Files (by responsibility)*

-- FastAPI app & router: app/main.py, app/api/routes/chat.py

-- SSE helpers: app/sse/*.py

-- Snowflake session & JWT: app/services/snowflake.py, app/core/security.py

-- Snowflake API Calls: app/services/snowflake_api.py

-- Config & logging: app/core/config.py, app/core/logging.py

-- Schemas: app/schemas/chat.py