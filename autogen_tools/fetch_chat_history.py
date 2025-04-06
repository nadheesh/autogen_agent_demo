from datetime import date
from typing import Type, Optional, Optional
from crewai.tools import BaseTool
from pydantic import BaseModel, Field
from utils.chat_history import chat_history_manager, ChatHistory
from typing_extensions import Annotated
from autogen_core.tools import FunctionTool, BaseTool
from schemas import CrewOutput, Response
from utils.asgardeo_manager import asgardeo_manager


def fetch_chat_history_func(thread_id: Annotated[str, "this is equivalent to the user session id"]) -> str:
    chat_history: ChatHistory = chat_history_manager.get_chat_history(thread_id)
    return chat_history.get_messages_as_string()


fetch_chat_history_tool = FunctionTool(
    fetch_chat_history_func, description="Fetches the chat history", name="FetchChatHistoryTool", strict=True
)
