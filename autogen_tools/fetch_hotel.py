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


def fetch_hotel_func(hotel_id: Annotated[Union[int, str], "Id of the hotel"],
                     thread_id: Annotated[str, "this is equivalent to the user session id"]) -> str:
    if not hotel_id:
        raise ValueError(
            "hotel_id is required. If you don't have a room_id, you can fetch all hotels using the FetchHotelsTool.")

    try:
        scopes = ["read_rooms"]
        token = asgardeo_manager.get_app_token(scopes)
        logger.info(f"Successfully fetched token with scopes: {scopes} using agent credentials.")
    except Exception as e:
        raise Exception("Failed to get token. Retry the operation.")

    headers = {
        'Authorization': f'Bearer {token}'
    }

    api_response = requests.get(f"{os.environ['HOTEL_API_BASE_URL']}/hotels/{hotel_id}", headers=headers)

    if api_response.status_code != 200:
        raise Exception(f"Failed to fetch hotel with id {hotel_id}")

    rooms_data = api_response.json()

    state_manager.add_state(thread_id, FlowState.FETCHED_HOTEL)

    response = Response(
        chat_response=None,
        tool_response=rooms_data
    )
    return CrewOutput(response=response, frontend_state=FrontendState.NO_STATE).model_dump_json()


fetch_hotel_tool = FunctionTool(
    fetch_hotel_func, description="Fetches a single hotel by id.", name="FetchHotelTool", strict=True
)
