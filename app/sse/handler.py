from app.schemas.chat import ChatRequest
from snowflake.snowpark import Session
from app.sse.utility import construct_sse, summarize_question_with_history, create_prompt_summarize_cortex_analyst_results
from app.services.snowflake_api import cortex_complete_async, execute_sql_async, cortex_agent_stream
from app.core.config import settings
import asyncio
import json
import pandas as pd

async def parse_sse(jwt_token:str,snowflake_account:str,request:ChatRequest,session:Session):
    """
    Parse the SSE data and stream the response  
    Args:
        jwt_token: str - The JWT token
        snowflake_account: str - The Snowflake account
        request: ChatRequest - The chat request
        session: snowflake.snowpark.Session - The Snowflake session
    """
    yield construct_sse(
        event = 'markdown',
        data = 'Analyzing the prompt'
    )
    # try:
    #     prompt = await prompt_guardrail(request.prompt,request.brand,session)
    # except Exception as e:
    #     yield construct_sse(
    #         event = 'error',
    #         data = f'Analyzing the prompt failed with error: {e}'
    #     )
    #     return
    prompt = request.prompt
    if request.history:
        history_json = [chat.model_dump() for chat in request.history]
        try:
            prompt = await summarize_question_with_history(history_json,prompt,session)
        except Exception as e:
            yield construct_sse(
                event = 'error',
                data = f'Summarizing the question failed with error: {e}'
            )
            return
    bot_text_message = ""  # Accumulate partial text
    async for item in cortex_agent_stream(jwt_token,snowflake_account,prompt):
        if item["event"] == "error":
            yield construct_sse(
                event = 'error',
                data = f'Error: {item["data"]}'
            )
            break
        if item['event'] == 'done':
            if bot_text_message:    # if there is a message, yield it before done
                yield construct_sse(
                    event = 'text',
                    data = bot_text_message
                )
                bot_text_message = ""
            yield construct_sse(
                event = 'done',
                data = '[Done]'
            )
            break
        if  item['event'] != 'message.delta':
            continue
        try:
            data = json.loads(item['data'])
        except json.JSONDecodeError:
            continue
        content = data.get("delta", {}).get("content", [])
        for obj in content:
            if obj['type'] == 'tool_use':
                tool_name = obj.get("tool_use", {}).get("name", "Unknown Tool")
                yield construct_sse(
                    event = 'markdown',
                    data = f'Tool: {tool_name} is being used'
                )
            elif obj['type'] == 'tool_results':
                result_json = obj.get("tool_results", {}).get("content", [{}])[0].get("json", {})
                # Grab interesting parts
                _search = result_json.get("searchResults", [])
                _sql = result_json.get("sql", [])
                _suggestions = result_json.get("suggestions", [])
                _assistant_text = result_json.get("text", "")
                yield construct_sse(
                    event = 'markdown',
                    data = _assistant_text
                )
                if _sql:
                    yield construct_sse(
                        event = 'markdown',
                        data = 'Searching the database'
                    )
                    try:
                        df = await asyncio.wait_for(execute_sql_async(_sql, session), timeout=settings.SQL_TIMEOUT_SEC)
                    except asyncio.TimeoutError:
                        yield construct_sse(
                            event = 'error',
                            data = 'Executing the SQL query timed out'
                        )
                        return
                    except Exception as e:
                        yield construct_sse(
                            event = 'error',
                            data = f'Executing the SQL query failed with error: {e}'
                        )
                        return
                    if isinstance(df, pd.DataFrame) and not df.empty:
                        yield construct_sse(
                            event = 'markdown',
                            data = 'Crafting a response'
                        )
                        sql_prompt = create_prompt_summarize_cortex_analyst_results(prompt, df, _sql)
                        try:
                            response = await cortex_complete_async(sql_prompt, session)
                            yield construct_sse(
                                event = 'text',
                                data = response
                            )   
                        except Exception as e:
                            yield construct_sse(
                                event = 'error',
                                data = f'Summarizing the data failed with error: {e}'
                            )
                            return
            elif obj['type'] == 'text':
                bot_text_message += obj["text"]
    if bot_text_message: # fallback if text message is not yielded before done
        yield construct_sse(
            event = 'text',
            data = bot_text_message
        )