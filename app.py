import os, base64, hashlib, time, jwt
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
import json
from dotenv import load_dotenv
from snowflake.cortex import complete
from snowflake.core import Root
import json
import pandas as pd
from snowflake.snowpark import Session
import asyncio
import aiohttp
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Literal, Optional


# ---------costruct the request validationmodels---------

class Chat(BaseModel):
    """
    The chat message model for the history
    """
    role: Literal['system', 'user', 'assistant'] = Field(..., description="The role of the message")
    message: str = Field(..., description="The content of the message, only user and assistant text messages are needed")

class ChatRequest(BaseModel):
    """
    The main chat request model
    """
    prompt: str = Field(..., description="The prompt to send to the chatbot")
    brand: str = Field(..., description="The brandcode to guardrail data")
    history: Optional[list[Chat]] = Field(None, description="The history of the chat, markdown events are not needed")






# --------- environment setup functions-------

def encode_private_key(key:str):
    """
    Encode the private key to DER format
    Args:
        key: str - The private key in PEM format
    Returns:
        p_key: cryptography.hazmat.primitives.asymmetric.rsa.RSAPrivateKey - The private key
        pkb: bytes - The private key in DER format
    """
    p_key= serialization.load_pem_private_key(
    key.encode("utf-8"),
    password=None
    )   
    pkb = p_key.private_bytes(
    encoding=serialization.Encoding.DER,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption())
    return p_key, pkb

def generate_jwt_token(p_key,snowflake_acount:str,snowflake_user:str):
    """
    Generate a JWT token
    Args:
        p_key: cryptography.hazmat.primitives.asymmetric.rsa.RSAPrivateKey - The private key
        snowflake_acount: str - The Snowflake account
        snowflake_user: str - The Snowflake user
    Returns:
        jwt_token: str - The JWT token
    """
    pub_der = p_key.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    fp = "SHA256:" + base64.b64encode(hashlib.sha256(pub_der).digest()).decode()
    now = int(time.time())
    exp = now + 59 * 60   # <= 1 hour
    payload = {
        "iss": f"{snowflake_acount}.{snowflake_user}.{fp}",
        "sub": f"{snowflake_acount}.{snowflake_user}",
        "iat": now,
        "exp": exp   # <= 1 hour
    }
    return jwt.encode(payload, p_key, algorithm="RS256"), exp

async def get_jwt_cached_async(p_key, account, user) -> str:   # caching the jwt token
    """
    Get a JWT token and cache it
    Args:
        p_key: cryptography.hazmat.primitives.asymmetric.rsa.RSAPrivateKey - The private key
        account: str - The Snowflake account
        user: str - The Snowflake user
    Returns:
        token: str - The JWT token
    """
    now = int(time.time())
    if _JWT["token"] and (_JWT["exp"] - now) > 120: # 120 seconds margin
        return _JWT["token"]
    async with _JWT_LOCK:
        now = int(time.time())
        if _JWT["token"] and (_JWT["exp"] - now) > 120: # 120 seconds margin
            return _JWT["token"]
        token, exp = generate_jwt_token(p_key, account, user)
        _JWT["token"], _JWT["exp"] = token, exp
        return token

def snowflake_session(pkb,snowflake_account,snowflake_user):
    """
    Create a Snowflake session
    Args:
        pkb: bytes - The private key in DER format
        snowflake_account: str - The Snowflake account
        snowflake_user: str - The Snowflake user
    Returns:
        session: snowflake.snowpark.Session - The Snowflake session
    """
    conn_params = { 
        'account': snowflake_account,
        'user': snowflake_user,
        'authenticator': 'SNOWFLAKE_JWT',
        'private_key': pkb
    }
    session = Session.builder.configs(conn_params).create() 
    return session








# ---------core functions-------

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

# async def prompt_guardrail(prompt:str,brand:str,session: Session) -> str:
#     """
#     Guardrail the prompt to make sure users can only access data for their brand. 
#     Cortex text classifiaction model is used for simplicity and lower overhead.

#     Args:
#         prompt: str - The prompt to send to the chatbot
#         brand: str - The brandcode to guardrail data
#         session: snowflake.snowpark.Session - The Snowflake session
#     Returns:
#         response: str - The response from the chatbot
#     """
#     classification_instruction = [
#         {
#             'label': 'data',
#             'description': 'questions that needs sql queries to solve. data available includes delivery time, financial numbers, order economics and marketing metrics, and retention metrics',
#             'examples': ['what is my aov last month','which region is most profitable','what is my average shipping time']
#         },
#         {
#             'label': 'general',
#             'description': 'general questions that are not data related',
#             'examples': ['why did my orders stuck in customs?', 'what does aov mean?','how do you define transaction amount?']
#         }
#     ]
#     classification = await asyncio.to_thread(lambda: classify_text(prompt, classification_instruction, session))
#     try:
#         classification_json = json.loads(classification)
#     except json.JSONDecodeError:
#         raise ValueError(f"Unable to classify the prompt; Error: {classification}")
#     return f"For {brand}, {prompt}" if classification_json['label'] == 'data' else prompt


async def summarize_question_with_history(chat_history, question, session: Session) -> str:
    """
    Create and execute prompt to summarize chat history
    Args:
        chat_history: json - The chat history
        question: str - The question
        session: Session - The Snowflake session
    Returns:
        summary: str - The summary of the chat history
    """
    start_index = max(0, len(chat_history) -6) # look back 6 messages at most
    context_history = chat_history[start_index:]

    prompt = f"""
        You are a chatbot expert. Refer the latest question received by the chatbot, evaluate this in context of the Chat History found below. 
        Now share a refined query which captures the full meaning of the question being asked. 
        
        If the question appears to be a stand alone question ignore all previous interactions or chat history and focus solely on the question. 
        If it seem to be connected to the prior chat history, only then use the chat history.

        Please use the question as the prominent input and the Chat history as a support input when creating the refined question.
        Please ensure no relevant information in the latest question is lost.
        
        Answer with only the query. Do not add any explanation.

        Chat History: {context_history}
        Question: {question}
    """

    
    summary = await cortex_complete_async(prompt, session)

    return summary

def create_prompt_summarize_cortex_analyst_results(myquestion, df, sql):
    """
    Create prompt to summarize Cortex Analyst results in natural language
    Args:
        myquestion: str - The question
        df: pandas.DataFrame - The result set
        sql: str - The SQL query
    Returns:
        prompt: str - The prompt to summarize the results
    """
    prompt = f"""
    You are an expert data analyst who translated the question contained between <question> and </question> tags:

    <question>
    {myquestion}
    </question>

    Into the SQL query contained between <SQL> and </SQL> tags:

    <SQL>
    {sql}
    </SQL>

    And retrieved the following result set contained between <df> and </df> tags:

    <df>
    {df}
    </df>

    Now share an answer to this question based on the SQL query and result set.
    Be concise and use mainly the CONTEXT provided and do not hallucinate.
    If you don't have the information, just say so.

    Whenever possible, arrange your response as summary and bullet points. 
    Give your recommendation to the business whenever applicable.

    Example:
    - Total Sales:
    -- Top markets showing sales growth:
    -- Markets declined
    - Recommendation:

    Do not mention the CONTEXT in your answer. 

    Answer:
    """

    return prompt

def construct_sse(event,data) -> bytes:
    """
    Construct the SSE data
    Args:
        event: str - The event
        data: str - The data
    Returns:
        sse: bytes - The SSE data
    """
    lines = []
    if event:
        lines.append(f"event: {event}")
    for line in (data.splitlines() or [""]):
        lines.append(f"data: {line}")
    return ("\n".join(lines) + "\n\n").encode("utf-8")



# ---------cortex agent sse handling-------
async def stream_sse(jwt_token:str,snowflake_account:str, prompt:str):
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
        async with session.post(url, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=None)) as resp:
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

# ---------construct the response stream -------
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
    async for item in stream_sse(jwt_token,snowflake_account,prompt):
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
                        data = 'Interating with database'
                    )
                    try:
                        df = await asyncio.wait_for(execute_sql_async(_sql, session), timeout=30)
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
                            data = 'Analyzing the data'
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
        
  
# ---------------------FastAPI Setup--------------------------------
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------environemnt setup---------

_JWT = {"token": None, "exp": 0.0}
_JWT_LOCK = asyncio.Lock()
load_dotenv()
snowflake_account = os.getenv("SNOWFLAKE_ACCOUNT")
snowflake_user = os.getenv("SNOWFLAKE_PROJECT_USER")
private_key = os.getenv("PRIVATE_KEY")
p_key, pkb = encode_private_key(private_key)


#-------- api endpoint---------
@app.post("/chat")
async def chat_endpoint(request: ChatRequest, req: Request):
    if not request.prompt or not request.brand:
        raise HTTPException(status_code=400, detail="Prompt and Brandcode are required")
    jwt_token = await get_jwt_cached_async(p_key, snowflake_account, snowflake_user)
    async def generator():
        SF_SESSION = snowflake_session(pkb, snowflake_account, snowflake_user)
        SF_SESSION.sql(f"SET brand = '{request.brand}'").collect()  # set the brand code for the session to guardrail data
        async for evt in parse_sse(jwt_token, snowflake_account,request,SF_SESSION):
            if await req.is_disconnected():
                break
            yield evt
        SF_SESSION.close()
    return StreamingResponse(generator(), media_type="text/event-stream")



# -------for testing only -------
# async def main():
#     load_dotenv()
#     snowflake_account = os.getenv("SNOWFLAKE_ACCOUNT")
#     snowflake_user = os.getenv("SNOWFLAKE_PROJECT_USER")
#     private_key = os.getenv("PRIVATE_KEY")
#     p_key, pkb = encode_private_key(private_key)
#     session = snowflake_session(pkb,snowflake_account,snowflake_user)
#     jwt_token,_ = generate_jwt_token(p_key,snowflake_account,snowflake_user)
#     prompt = " what's my last month aov?"
#     print(jwt_token)
#     async for evt in stream_sse(jwt_token, snowflake_account,prompt):
#         print(evt)

# asyncio.run(main())


