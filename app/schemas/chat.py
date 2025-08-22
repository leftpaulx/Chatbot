from pydantic import BaseModel, Field
from typing import Literal, Optional

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
