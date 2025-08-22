from snowflake.snowpark import Session
from app.services.snowflake_api import cortex_complete_async

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
