from datetime import date
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


def fetch_booking_func(booking_id: Annotated[Union[int, str], "Id of the booking"],
                       thread_id: Annotated[str, "this is equivalent to the user session id"]) -> str:
    try:
        token = asgardeo_manager.get_app_token(["read_bookings"])
    except Exception as e:
        raise Exception("Failed to get token. Retry the operation.")

    headers = {
        'Authorization': f'Bearer {token}'
    }

    api_response = requests.get(f"{os.environ['HOTEL_API_BASE_URL']}/bookings/{booking_id}", headers=headers)
    rooms_data = api_response.json()

    state_manager.add_state(thread_id, FlowState.FETCHED_BOOKINGS)

    response = Response(
        chat_response=None,
        tool_response=rooms_data
    )
    return CrewOutput(response=response, frontend_state=FrontendState.NO_STATE).model_dump_json()


fetch_booking_tool = FunctionTool(
    fetch_booking_func, description="Fetch a booking by id.", name="FetchBookingsTool", strict=True
)
