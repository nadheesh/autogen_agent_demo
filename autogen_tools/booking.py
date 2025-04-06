from datetime import date
import os
from typing import Type, Optional
from crewai.tools import BaseTool
from pydantic import BaseModel, Field
import requests
from typing_extensions import Annotated
from autogen_core.tools import FunctionTool, BaseTool
from schemas import CrewOutput, Response
from utils.state_manager import state_manager
from utils.asgardeo_manager import asgardeo_manager
from utils.constants import FlowState, FrontendState
from datetime import datetime


def create_booking_func(room_id: Annotated[int, "Room ID"],
                        hotel_id: Annotated[int, "Hotel ID"],
                        check_in: Annotated[str, "Check-in date (YYYY-MM-DD)"],
                        check_out: Annotated[str, "Check-out date (YYYY-MM-DD)"],
                        thread_id: Annotated[str, "this is equivalent to the user session id"]) -> str:
    try:
        check_in_obj = datetime.strptime(check_in, "%Y-%m-%d").date()
        check_out_obj = datetime.strptime(check_out, "%Y-%m-%d").date()
        if FlowState.BOOKING_PREVIEW_INITIATED not in state_manager.get_states(thread_id):
            raise Exception("Booking preview not completed")

        state_manager.add_state(thread_id, FlowState.BOOKING_PREVIEW_COMPLETED)
        state_manager.add_state(thread_id, FlowState.BOOKING_INITIATED)
        # Get access token
        user_id = asgardeo_manager.get_user_id_from_thread_id(thread_id)
        access_token = asgardeo_manager.get_user_token(user_id, ["openid", "create_bookings"])

        # Prepare the booking request
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }

        booking_data = {
            "user_id": user_id,
            "room_id": room_id,
            "hotel_id": hotel_id,
            "check_in": check_in_obj.isoformat(),
            "check_out": check_out_obj.isoformat()
        }

        api_response = requests.post(f"{os.environ['HOTEL_API_BASE_URL']}/bookings", json=booking_data,
                                         headers=headers)

        if (api_response.status_code == 200):
            booking_details = api_response.json()
            response_dict = {
                "booking_id": booking_details["id"],
                "total_price": booking_details["total_price"],
                "status": "confirmed"
            }
            hotel_name = booking_details["hotel_name"]
            message = f"Room successfully booked at {hotel_name} for dates {check_in} to {check_out}. Booking ID: {response_dict['booking_id']}"
            frontend_state = FrontendState.BOOKING_COMPLETED
            authorization_url = asgardeo_manager.get_google_authorization_url(thread_id, user_id, ["openid", "create_bookings"])
            state_manager.add_state(thread_id, FlowState.BOOKING_COMPLETED)
        else:
            response_dict = {
                "error": api_response.json().get("detail", "Booking failed"),
                "status": "failed"
            }
            message = f"Failed to book room: {response_dict['error']}"
            frontend_state = FrontendState.BOOKING_COMPLETED_ERROR
            authorization_url = None
        response = Response(
            chat_response=message,
            tool_response={
                "booking_details": response_dict,
                "authorization_url": authorization_url
            }
        )
        return CrewOutput(response=response, frontend_state=frontend_state).model_dump_json()

    except Exception as e:
        error_response = Response(
            chat_response=f"An error occurred while booking the room: {str(e)}",
            tool_response={"error": str(e), "status": "error"}
        )
        return CrewOutput(response=error_response, frontend_state=FrontendState.BOOKING_COMPLETED_ERROR).model_dump_json()


create_booking_tool = FunctionTool(
    create_booking_func, description="Books a hotel room for specified room and dates.", name="BookingTool", strict=True
)
