from datetime import date
import logging
import os
from typing import Type, Optional, Union
import threading
import time
from crewai.tools import BaseTool
from pydantic import BaseModel, Field
from utils.state_manager import state_manager
from utils.email_manager import email_manager
from utils.constants import FlowState, FrontendState
import requests
from schemas import CrewOutput, Response
from utils.asgardeo_manager import asgardeo_manager
from typing_extensions import Annotated
from autogen_core.tools import FunctionTool, BaseTool


def _process_upgrade_in_background(thread_id, booking_id: Union[int, str], room_id: Union[int, str]):
    """Process the room upgrade request in background."""
    try:
        time.sleep(30)
        auth_req_id = asgardeo_manager.initiate_ciba(thread_id, ["openid", "booking_upgrade"])
        # Poll for token with retries
        max_retries = 60
        retry_interval = 15  # Set to 15 seconds
        retries = 0
        time.sleep(retry_interval)

        while retries < max_retries:
            response = asgardeo_manager.get_ciba_token(auth_req_id)
            if response.get("state") == "success":
                # Upgrade room with the obtained token
                access_token = response.get("access_token")
                user_id = asgardeo_manager.get_user_id_from_thread_id(thread_id)
                user_claims = asgardeo_manager.get_user_claims(user_id)
                username = user_claims.get("username")
                email = user_claims.get("email")
                email_content = get_email(booking_id, room_id, username)
                email_manager.send_html_email(email, "Room Upgrade", email_content)
                print(f"Upgrading room with booking_id: {booking_id}")
                return

            elif response.get("state") == "pending" or response.get("state") == "slow_down":
                # Continue polling
                print("Polling for token...")
                retries += 1
                time.sleep(retry_interval)  # Sleep for 15 seconds
                continue

            else:
                print(f"Failed to get token for booking_id: {booking_id}")
                return


    except Exception as e:
        print(f"Error in background thread: {str(e)}")


def get_email(booking_id: Union[int, str], room_id: Union[int, str], username: str) -> str:
    try:
        token = asgardeo_manager.get_app_token(["read_bookings"])
    except Exception as e:
        raise Exception("Failed to get token. Retry the operation.")

    headers = {
        'Authorization': f'Bearer {token}'
    }

    api_response = requests.get(f"{os.environ['HOTEL_API_BASE_URL']}/bookings/{booking_id}", headers=headers)
    rooms_data = api_response.json()
    booking_preview_data = {
        "room_id": room_id,
        "check_in": rooms_data.get("check_in"),
        "check_out": rooms_data.get("check_out")
    }
    try:
        token = asgardeo_manager.get_app_token(["read_rooms"])
    except Exception as e:
        raise

    headers = {
        'Authorization': f'Bearer {token}'
    }
    api_response = requests.post(f"{os.environ['HOTEL_API_BASE_URL']}/bookings/preview", json=booking_preview_data,
                                 headers=headers)
    booking_preview_data = api_response.json()
    html = f"""<!DOCTYPE html>
                <html lang="en">
                <head>
                    <meta charset="UTF-8">
                    <meta name="viewport" content="width=device-width, initial-scale=1.0">
                    <title>Room Upgrade Confirmation - Gardeo Hotel</title>
                    <style>
                        body {{ font-family: Arial, sans-serif; color: #333; }}
                        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #ddd; border-radius: 5px; }}
                        h1 {{ color: #005f73; }}
                        .details {{ margin-top: 15px; }}
                        .details p {{ margin: 5px 0; }}
                        .footer {{ margin-top: 20px; font-size: 0.9em; color: #555; }}
                    </style>
                </head>
                <body>
                    <div class="container">
                        <h1>Room Upgrade Confirmation - Gardeo Hotel</h1>
                        <p>Dear {username},</p>

                        <p>Warm greetings from Gardeo Hotel!</p>

                        <p>We are delighted to inform you that your room upgrade request has been successfully processed. Below are your updated reservation details:</p>

                        <div class="details">
                            <p><strong>Room Type:</strong> {booking_preview_data['room_type']}</p>
                            <p><strong>Total Price:</strong> ${booking_preview_data['total_price']}</p>
                            <p><strong>Check-in Date:</strong> {booking_preview_data['check_in']}</p>
                            <p><strong>Check-out Date:</strong> {booking_preview_data['check_out']}</p>
                        </div>

                        <p>Thank you for choosing Gardeo Hotel. We look forward to providing you with a comfortable and memorable stay.</p>

                        <p>Please feel free to contact us if you require any further assistance.</p>

                        <p>Ayubowan! (May you live long!)</p>

                        <p>Warm regards,</p>

                        <p>Kisali<br>Gardeo Hotel</p>

                        <div class="footer">
                            <p>Bohoma Isthuthi! (Thank you very much!)</p>
                        </div>
                    </div>
                </body>
                </html>"""
    return html


def upgrade_room_func(booking_id: Annotated[Union[int, str], "Id of the booking"],
                      room_id: Annotated[Union[int, str],"Id of the room"],
                      thread_id: Annotated[str, "this is equivalent to the user session id"]) -> str:
    if not booking_id:
        raise ValueError(
            "booking_id is required. If you don't have a booking_id, you need to create a booking first.")

    # Start a background thread for processing
    bg_thread = threading.Thread(
        target=_process_upgrade_in_background,
        args=(thread_id, booking_id, room_id),
        daemon=True
    )
    bg_thread.start()
    state_manager.add_state(thread_id, FlowState.PROCCESING_UPGRADE)
    response = Response(
        chat_response="Currently, the room you've requested is not available. As soon as it becomes available, we will upgrade your reservation and notify you via email.",
        tool_response={"status": "processing", "booking_id": booking_id}
    )

    return CrewOutput(response=response, frontend_state=FrontendState.PROCCESING_UPGRADE).model_dump_json()


upgrade_room_tool = FunctionTool(
    upgrade_room_func, description="Upgrades a room.", name="RoomUpgradeTool", strict=True
)
