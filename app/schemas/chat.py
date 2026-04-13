from pydantic import BaseModel, Field
from typing import Literal, Optional


class Chat(BaseModel):
    role: Literal['system', 'user', 'assistant'] = Field(..., description="The role of the message")
    message: str = Field(..., description="The content of the message")


class ChatRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=4000, description="The prompt to send to the chatbot")
    brand: str = Field(..., min_length=1, max_length=100, description="Brand code sent by the embedding portal")
    thread_id: Optional[str] = Field(None, max_length=64, description="Cortex Agent thread ID for conversation continuity")
    parent_message_id: Optional[int] = Field(None, ge=0, description="Last assistant message ID in the thread (0 for first message)")
    history: Optional[list[Chat]] = Field(None, description="Deprecated: threads now handle conversation history server-side")
