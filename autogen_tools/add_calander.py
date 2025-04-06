from datetime import date, timedelta
from autogen_core.tools import FunctionTool, BaseTool
import os
from typing import Type, Optional, Any
# from crewai.tools import BaseTool
from pydantic import BaseModel, Field
import requests
from typing_extensions import Annotated
from schemas import CrewOutput, Response
from utils.state_manager import state_manager
from utils.asgardeo_manager import asgardeo_manager
from utils.constants import FlowState, FrontendState
from datetime import datetime


def add_calendar_func(title: Annotated[str, "Title of the booking"],
                      start: Annotated[str, "Start date of the booking (YYYY-MM-DD)"],
                      end: Annotated[str, "End date of the booking (YYYY-MM-DD)"],
                      thread_id: Annotated[str, "this is equivalent to the user session id"]) -> str:
    try:
        start_date_obj = datetime.strptime(start, "%Y-%m-%d").date()
        end_date_obj = datetime.strptime(end, "%Y-%m-%d").date()
        # Get the access token for authentication
        user_id = asgardeo_manager.get_user_id_from_thread_id(thread_id)
        access_token = asgardeo_manager.get_user_google_token(user_id, ["openid", "create_bookings"])

        # Format dates as 'YYYY-MM-DD'
        start_date = start_date_obj.isoformat()
        # Add 1 day to end date since Google Calendar's end.date is exclusive
        end_date = (end_date_obj + timedelta(days=1)).isoformat()

        # Construct the event body
        event = {
            "summary": title,
            "start": {"date": start_date},
            "end": {"date": end_date}
        }

        # Set up headers with the access token
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }

        # Make the API request
        response = requests.post(
            "https://www.googleapis.com/calendar/v3/calendars/primary/events",
            headers=headers,
            json=event
        )

        # Check the response
        if response.status_code == 200:
            message = f"Event created successfully in your calendar"
            frontend_state = FrontendState.ADDED_TO_CALENDAR
            state_manager.add_state(thread_id, FlowState.ADDED_TO_CALENDAR)
        else:
            message = "An error occurred while adding the event to the calendar. Please try the Add to Calendar tool again."
            frontend_state = FrontendState.CALENDAR_ERROR

        response = Response(
            chat_response=message,
            tool_response={}
        )
        return CrewOutput(response=response, frontend_state=frontend_state).model_dump_json()

    except requests.exceptions.RequestException as e:
        error_response = Response(
            chat_response=f"An error occurred while adding the event to the calendar, please try again.",
            tool_response={}
        )
        return CrewOutput(response=error_response, frontend_state=FrontendState.CALENDAR_ERROR).model_dump_json()
    except Exception as e:
        error_response = Response(
            chat_response=f"An error occurred while adding the event to the calendar, please try again.",
            tool_response={}
        )
        return CrewOutput(response=error_response, frontend_state=FrontendState.CALENDAR_ERROR).model_dump_json()


add_calendar_tool = FunctionTool(
    add_calendar_func, description="Adds a booking to the calendar.", name="AddCalanderTool", strict=True
)
