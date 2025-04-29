# tools.py - simplified implementation
import json
import logging
from typing import Literal, Optional, Dict, Any

import httpx
from pydantic import BaseModel

from app import asgardeo_manager, connection_manager

logger = logging.getLogger('agentLogger')


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
    consent_options: Optional[ConsentOptions] = None
    consent_context: Optional[ConsentContext] = None


class AuthRequestResponse(BaseModel):
    type: Literal["auth_request"] = "auth_request"
    auth_url: str
    state: str
    booking_details: Dict[str, Any]


class HotelAPI:
    def __init__(self,
                 base_url: str,
                 session_id: str):
        self.base_url = base_url
        self.session_id = session_id

    async def fetch_hotels(self) -> dict:
        scopes = ["read_hotels"]
        path = "api/hotels"
        return await asgardeo_manager.get(f"{self.base_url}/{path}", scopes)

    async def fetch_rooms(self, hotel_id: int) -> dict:
        scopes = ["read_rooms"]
        path = f"api/hotels/{hotel_id}"
        return await asgardeo_manager.get(f"{self.base_url}/{path}", scopes)

    # In class HotelAPI, modify book_hotel method
    async def book_hotel(self, hotel_name: str,
                         hotel_id: int,
                         room_id: int,
                         date_from: str,
                         date_to: str,
                         total_cost: str) -> str:

        # Create booking details to store
        booking_details = {
            "hotel_id": hotel_id,
            "room_id": room_id,
            "date_from": date_from,
            "date_to": date_to
        }

        booking_confirmation_details = {
            "hotel_name": hotel_name,
            "date_from": date_from,
            "date_to": date_to,
            "total_cost": total_cost
        }

        # Build OAuth authorization URL
        auth_url, state = asgardeo_manager.get_authorization_url(self.session_id)

        # Send auth request to the frontend
        await connection_manager.send_message(self.session_id, AuthRequestResponse(
            auth_url=auth_url,
            state=state,
            booking_details=booking_confirmation_details
        ).model_dump())

        # Wait for authorization or cancellation message
        auth_response = await connection_manager.receive_message(self.session_id)
        auth_data = json.loads(auth_response) if isinstance(auth_response, str) else auth_response
        if auth_data.get("success", False) is False:
            reason = auth_data.get("reason", "unknown")
            if reason == "window_closed":
                return "Booking cancelled. The authorization window was closed."
            else:
                return f"Booking failed. Reason: {reason}"

        auth_code = asgardeo_manager.state_mapping.get(state)
        if auth_code and auth_code.token:
            # We have a token, use it to make the booking
            return str(await self._make_booking(
                hotel_id=booking_details["hotel_id"],
                room_id=booking_details["room_id"],
                date_from=booking_details["date_from"],
                date_to=booking_details["date_to"],
                access_token=auth_code.token["access_token"]
            ))

    async def _make_booking(self, hotel_id: str, room_id: str, date_from: str, date_to: str, access_token: str) -> dict:
        """
        Make an authenticated booking request to the hotel API.

        Args:
            hotel_id: The ID of the hotel to book
            room_id: The ID of the room to book
            date_from: Check-in date (YYYY-MM-DD)
            date_to: Check-out date (YYYY-MM-DD)
            access_token: OAuth access token for authorization

        Returns:
            The JSON response from the booking API
        """
        try:
            # Create an HTTP client with the access token
            async with httpx.AsyncClient() as client:
                # Prepare the request payload
                booking_data = {
                    "check_in": date_from,
                    "check_out": date_to,
                    "hotel_id": int(hotel_id),  # Ensure it's an integer
                    "room_id": int(room_id)  # Ensure it's an integer
                }

                # Set the authorization header with the access token
                headers = {
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json"
                }

                # Make the POST request to the bookings endpoint
                response = await client.post(
                    f"{self.base_url}/api/bookings",
                    json=booking_data,
                    headers=headers
                )

                # Raise an exception for HTTP errors
                response.raise_for_status()

                # Return the JSON response
                return response.json()

        except Exception as e:
            logger.error(f"Unexpected error in booking: {str(e)}")
            return {"error": f"Booking failed due to error: {str(e)}"}

    async def ask_user(self, question: str) -> str:
        print("ask from user:" + question)
        await connection_manager.send_message(self.session_id, TextResponse(
            content=question
        ).model_dump())
        return await connection_manager.receive_message(self.session_id)
