import logging
import os
from typing import List, Optional
from dotenv import load_dotenv
from langchain_openai import AzureChatOpenAI
from autogen import create_agentchat
from fastapi import FastAPI, HTTPException, Depends, Header, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
import jwt
from jwt.exceptions import InvalidTokenError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from utils.constants import FlowState
from utils.state_manager import state_manager
from utils.asgardeo_manager import AuthCode, asgardeo_manager
from utils.chat_history import ChatHistory, chat_history_manager
from fastapi.responses import JSONResponse
import urllib3
import ast

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

load_dotenv(override=True)

os.makedirs('logs', exist_ok=True)
logging.config.fileConfig('logging.conf', disable_existing_loggers=False)

app = FastAPI(title="LLM Chat API")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "https://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBearer()


def get_user_from_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        token = credentials.credentials
        payload = jwt.decode(token, options={"verify_signature": False})
        user_id = payload.get("sub")
        asgardeo_manager.store_user_claims(user_id, payload)
        return user_id
    except InvalidTokenError:
        raise HTTPException(
            status_code=401,
            detail="Invalid authentication token"
        )


class ChatMessage(BaseModel):
    message: str


class ChatRequest(BaseModel):
    message: str
    threadId: Optional[str] = None


class Response(BaseModel):
    chat_response: Optional[str] = None
    tool_response: Optional[dict] = None


class ChatResponse(BaseModel):
    response: Response
    frontend_state: str
    message_states: List[str]


@app.post("/chat", response_model=ChatResponse)
async def chat(
        request: ChatRequest,
        user_id: str = Depends(get_user_from_token),
        ThreadID: Optional[str] = Header(None)
):
    try:
        user_message = request.message
        print("User message:", user_message)
        thread_id = ThreadID or request.threadId
        if not asgardeo_manager.get_user_id_from_thread_id(thread_id):
            asgardeo_manager.store_user_id_against_thread_id(thread_id, user_id)

        chat_history_manager.add_user_message(thread_id, user_message)
        crew_response = await create_agentchat(user_message, thread_id)
        chat_response = crew_response.messages[-1].content.rstrip('TERMINATE').strip()
        print(f"Chat response:{chat_response}")
        crew_dict = ast.literal_eval(chat_response)
        chat_history_manager.add_assistant_message(thread_id, str(crew_dict))

        chat_response = crew_dict.get('response', {})
        frontend_state = crew_dict.get('frontend_state', {})
        tool_response = chat_response.get("tool_response", {})
        tool_response_dict = tool_response.to_dict() if hasattr(tool_response, 'to_dict') else tool_response
        response = Response(
            chat_response=chat_response.get("chat_response", ""),
            tool_response=tool_response_dict
        )
        message_states = [state.name for state in state_manager.get_message_states(thread_id)]
        state_manager.clear_message_states(thread_id)
        return ChatResponse(response=response, frontend_state=frontend_state, message_states=message_states)
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/callback")
async def callback(
        code: str,
        state: str,
):
    try:
        auth_code: AuthCode = asgardeo_manager.state_mapping.get(state)
        if not auth_code:
            raise HTTPException(status_code=400, detail="Invalid state")
        auth_code.code = code
        asgardeo_manager.state_mapping[state] = auth_code
        token = asgardeo_manager.fetch_user_token(state)
        thread_id = asgardeo_manager.get_thread_id_from_state(state)
        state_manager.add_state(thread_id, FlowState.BOOKING_AUTORIZED)
        return HTMLResponse(
            content=f"<html><body><script>window.location.href = '{os.environ['WEBSITE_URL']}/auth_success';</script></body></html>",
            status_code=200)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/google_callback")
async def callback(
        code: str,
        state: str,
):
    try:
        auth_code: AuthCode = asgardeo_manager.state_mapping.get(state)
        if not auth_code:
            raise HTTPException(status_code=400, detail="Invalid state")
        auth_code.code = code
        asgardeo_manager.state_mapping[state] = auth_code
        token = asgardeo_manager.fetch_google_token(state)
        thread_id = asgardeo_manager.get_thread_id_from_state(state)
        state_manager.add_state(thread_id, FlowState.CALENDAR_AUTORIZED)
        return HTMLResponse(
            content=f"<html><body><script>window.location.href = '{os.environ['WEBSITE_URL']}/auth_success';</script></body></html>",
            status_code=200)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/state/{thread_id}")
async def callback(
        thread_id: str
):
    try:
        states = {
            "states": [state.name for state in state_manager.get_states(thread_id)]
        }
        return JSONResponse(content=states)
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health_check():
    return {"status": "healthy"}
