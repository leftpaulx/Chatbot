import asyncio
from snowflake.snowpark import Session
from snowflake.cortex import complete
import aiohttp

async def execute_sql_async(sql: str, session: Session, max_rows: int = 1000):
    """
    Execute a SQL query asynchronously (runs blocking Snowflake query in a thread).
    Args:
        sql: str - The SQL query to execute
        session: snowflake.snowpark.Session - The Snowflake session
        max_rows: int - The maximum number of rows to return
    Returns:
        df: pandas.DataFrame | str - Result dataframe or error string
    """
        # Offload the blocking Snowflake call to a thread
    df = await asyncio.to_thread(
        lambda: session.sql(sql.replace(";", "")).limit(max_rows).to_pandas()
    )
    return df


async def cortex_complete_async(prompt: str, session: Session) -> str:
    """
    Offload the synchronous Snowflake Cortex Complete() call. This can be replaced with any other LLM.
    Args:
        prompt: str - The prompt to send to the chatbot
        session: snowflake.snowpark.Session - The Snowflake session
    Returns:
        response: str - The response from the chatbot
    """
    return await asyncio.to_thread(lambda: complete('claude-3-5-sonnet', prompt, session=session))


async def cortex_agent_stream(jwt_token:str,snowflake_account:str, prompt:str):
    url = f"https://{snowflake_account}.snowflakecomputing.com/api/v2/cortex/agent:run"
    payload = {
    "model": "claude-3-5-sonnet",
    "response_instruction": 'You should always be friendly and helpful',
    "messages": [          
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": prompt
                }
            ]
        }
    ],
    "tools": [
        {
            "tool_spec": {
                "type": "cortex_analyst_text_to_sql",
                "name": "analyze_data"
            }
        }
        
    ],
    "tool_resources": {
        "analyze_data": {"semantic_model_file": "@OB_AI.CHATBOT.APP/client_analytics.yaml"}
    }
    } 
    headers = {
        "Authorization": f"Bearer {jwt_token}",
        "X-Snowflake-Authorization-Token-Type": "KEYPAIR_JWT",
        "Content-Type": "application/json"
    }
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=120)) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    # surface the upstream error as an SSE error event
                    yield {"event": "error", "data": f"HTTP {resp.status}: {body}"}
                    return
                event, data = None, None
                async for raw_bytes in resp.content:
                    for ch in raw_bytes.splitlines():
                        line = ch.decode("utf-8")
                        if line == "": # if the line is empty (end of an event), yield the data and reset the event and data
                            if data:
                                yield {"event": event, "data": data}
                                event, data = None, None
                            continue
                        if line.startswith("event: "):
                            event = line[7:]
                        elif line.startswith("data: "):
                            data = line[6:]
                if data: # in case the last line is not empty, yield the data
                    yield {"event": event, "data": data}
        except asyncio.TimeoutError:
            yield {"event": "error", "data": 'Agent Call Timed Out!'}