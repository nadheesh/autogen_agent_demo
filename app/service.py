import json
import logging
import os
from dataclasses import dataclass
from typing import Literal

# Add these imports to main.py
from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.messages import TextMessage
from autogen_core import MessageContext, RoutedAgent, message_handler
from autogen_core import SingleThreadedAgentRuntime, AgentId
from autogen_core.tools import FunctionTool
from autogen_ext.models.openai import OpenAIChatCompletionClient
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from pydantic import BaseModel
from starlette.responses import HTMLResponse

from app import asgardeo_manager, connection_manager
from tools import HotelAPI

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

hotel_api_base_url = os.environ.get('HOTEL_API_BASE_URL')

ASSISTANT_TYPE = "hotel_booking_assistant"

app = FastAPI()


# Add session middleware to the app
# app.add_middleware(SessionMiddleware, secret_key="12345")


@dataclass
class HotelBookingMessageType:
    content: str


class TextResponse(BaseModel):
    type: Literal["message"] = "message"
    content: str


class ConsentOptions(BaseModel):
    accept: str
    reject: str


class ConsentContext(BaseModel):
    action: str
    details: dict


class ConsentRequestResponse(BaseModel):
    type: Literal["consent_request"] = "consent_request"
    content: str
    consent_options: ConsentOptions
    consent_context: ConsentContext


hotelAPIClient = HotelAPI(hotel_api_base_url, "123")

fetch_hotels_tool = FunctionTool(
    hotelAPIClient.fetch_hotels, description="Fetches all hotels and information about them", name="FetchHotelsTool",
    strict=True
)
book_hotel_tool = FunctionTool(
    hotelAPIClient.book_hotel, description="Books the hotel room selected by the user.", name="BookHotelTool",
    strict=True
)
fetch_hotel_rooms_tool = FunctionTool(
    hotelAPIClient.fetch_rooms,
    description="Fetch the rooms available, and information related such as price, amenities, etc.",
    name="FetchHotelRoomsTool", strict=True
)
ask_user_tool = FunctionTool(
    hotelAPIClient.ask_user, description="Ask user for additional information required to complete their request",
    name="AskUserTool", strict=True
)


class HotelBookingAssistant(RoutedAgent):
    def __init__(self, name: str) -> None:
        super().__init__(name)
        model_client = OpenAIChatCompletionClient(model="gpt-4o")
        self._delegate = AssistantAgent(
            name,
            model_client=model_client,
            tools=[fetch_hotels_tool, fetch_hotel_rooms_tool, book_hotel_tool, ask_user_tool],
            reflect_on_tool_use=True,
            system_message="""You are the Hotel Assistant Agent to help the customers of Gardeo Hotel. Gardeo Hotels offer the finest Sri Lankan hospitality and blend seamlessly with nature, creating luxurious experiences. Answer the given question accurately using the given set of tools.
            
Make sure to follow these rules:
            
1) Always response without IDs, room numbers etc, that does not matter to the user.
2) Always ask for the user consent before proceeding with any action.
3) Always use the correct tools fetch required information before proceeding with the bookings.
4) Use AskUserTool to ask user for any information that is not provided by the user.

Always reply in markdown. Do not perform any actions outside the scope of the task.""")

    @message_handler
    async def handle_hotel_booking_message_type(self, message: HotelBookingMessageType,
                                                ctx: MessageContext) -> TextMessage:
        response = await self._delegate.on_messages(
            [TextMessage(content=message.content, source="user")], ctx.cancellation_token
        )
        for i, msg in enumerate(response.inner_messages):
            print(f"Step {i + 1}: {msg.content}")
        return response.chat_message


# Runtime setup
runtime = SingleThreadedAgentRuntime()


@app.on_event("startup")
async def startup_event():
    await HotelBookingAssistant.register(runtime, ASSISTANT_TYPE, lambda: HotelBookingAssistant(ASSISTANT_TYPE))
    runtime.start()


@app.on_event("shutdown")
async def shutdown_event():
    await runtime.stop()


@app.get("/")
async def root():
    """Redirect to the chat interface HTML page"""
    return HTMLResponse("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Hotel Booking Assistant</title>
        <meta http-equiv="refresh" content="0;url=/chat.html">
    </head>
    <body>
        <p>Redirecting to chat interface...</p>
    </body>
    </html>
    """)


@app.websocket("/chat")
async def websocket_endpoint(websocket: WebSocket, session_id: str = "123"):
    """WebSocket endpoint for chat functionality"""
    session_id = "123"  # We need to use session id from frontend

    await connection_manager.connect(session_id, websocket)
    try:
        # Get the HotelBookingAssistant agent from the runtime
        assistant_agent_id = AgentId(ASSISTANT_TYPE, session_id)

        # Welcome message
        await websocket.send_json(TextResponse(
            content="👋 Welcome to Gardeo Hotel Booking Assistant! How can I help you today?"
        ).model_dump())

        while True:
            user_input = await websocket.receive_text()

            if user_input.strip().lower() == "exit":
                await websocket.close()
                break

            # Send the user message to the agent
            response = await runtime.send_message(
                HotelBookingMessageType(user_input), assistant_agent_id
            )

            # Send the response back to the client
            await websocket.send_json(TextResponse(content=response.content).model_dump())

    except WebSocketDisconnect:
        print(f"Client with session_id {session_id} disconnected")
    except Exception as e:
        print(f"Error in WebSocket connection: {str(e)}")
    finally:
        connection_manager.disconnect(session_id)


# Updated callback endpoint
@app.get("/oauth/callback")
async def callback(
        code: str,
        state: str,
):
    try:
        auth_code = asgardeo_manager.state_mapping.get(state)
        if not auth_code:
            raise HTTPException(status_code=400, detail="Invalid state")

        # Store the code
        auth_code.code = code
        asgardeo_manager.state_mapping[state] = auth_code

        # Fetch the token
        token = await asgardeo_manager.fetch_user_token(state)

        # Get the thread ID (session_id) from the state
        thread_id = asgardeo_manager.get_thread_id_from_state(state)

        # Redirect to a success page
        website_url = os.environ.get('WEBSITE_URL', 'http://localhost:8000')

        return HTMLResponse(
            content=f"""
                    <html>
                    <head>
                        <title>Authorization Successful</title>
                        <script>
                            // Use the correct message type that the main window expects
                            if (window.opener) {{
                                window.opener.postMessage({{
                                    type: 'auth_callback',  // Must match what frontend expects
                                    token: {json.dumps(token)},
                                    state: '{state}'
                                }}, "*");  // Use * instead of specific origin for better compatibility

                                // Let main window know we're authorized before closing
                                window.opener.authorizationCompleted = true;
                                setTimeout(function() {{ window.close(); }}, 1000);
                            }} else {{
                                window.location.href = '{website_url}/auth_success';
                            }}
                        </script>
                    </head>
                    <body>
                        <h2>Authorization Successful</h2>
                        <p>Authorization completed! You can close this window and return to the booking assistant.</p>
                    </body>
                    </html>
                    """
        )
    except Exception as e:
        logger.error(f"Error in callback: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
