from datetime import date
import logging
import os
from typing import Type, Optional, Optional, Union
from crewai.tools import BaseTool
from pydantic import BaseModel, Field
import requests
from utils.state_manager import state_manager
from utils.constants import FlowState, FrontendState
from typing_extensions import Annotated
from autogen_core.tools import FunctionTool, BaseTool
from schemas import CrewOutput, Response
from utils.asgardeo_manager import asgardeo_manager

logger = logging.getLogger('agentLogger')


def fetch_room_func(room_id: Annotated[Union[int, str],"Id of the room"],
                    thread_id: Annotated[str, "this is equivalent to the user session id"]) -> str:
    if not room_id:
        raise ValueError(
            "room_id is required. If you don't have a room_id, you can fetch all rooms using the FetchHotelTool.")

    try:
        scopes = ["read_rooms"]
        token = asgardeo_manager.get_app_token(scopes)
        logger.info(f"Successfully fetched token with scopes: {scopes} using agent credentials.")
    except Exception as e:
        raise Exception("Failed to get token. Retry the operation.")

    headers = {
        'Authorization': f'Bearer {token}'
    }

    api_response = requests.get(f"{os.environ['HOTEL_API_BASE_URL']}/rooms/{room_id}", headers=headers)
    rooms_data = api_response.json()

    state_manager.add_state(thread_id, FlowState.FETCHED_ROOM)

    response = Response(
        chat_response=None,
        tool_response=rooms_data
    )
    return CrewOutput(response=response, frontend_state=FrontendState.NO_STATE).model_dump_json()


fetch_room_tool = FunctionTool(
    fetch_room_func, description="Fetch a single room by id.", name="FetchRoomTool", strict=True
)
