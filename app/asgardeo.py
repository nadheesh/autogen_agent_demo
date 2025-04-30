import logging
import secrets
import time
from typing import Optional, Dict, List

from authlib.integrations.httpx_client import AsyncOAuth2Client
from pydantic import BaseModel

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Create a model for storing authorization codes and state
class AuthCode(BaseModel):
    state: str
    code: Optional[str] = None
    token: Optional[dict] = None
    thread_id: str  # This corresponds to our session_id
    created_at: float = time.time()


# Create a manager for Asgardeo authentication
class AsgardeoManager:
    def __init__(self,
                 client_id: str,
                 client_secret: str,
                 token_endpoint: str,
                 redirect_uri: str):
        self.state_mapping: Dict[str, AuthCode] = {}
        self.client_id = client_id
        self.client_secret = client_secret
        self.token_endpoint = token_endpoint
        self.redirect_uri = redirect_uri

    def create_state(self, thread_id: str) -> str:
        """Create a new state for authorization flow and associate it with a thread ID"""
        state = secrets.token_urlsafe(16)
        self.state_mapping[state] = AuthCode(state=state, thread_id=thread_id)
        return state

    def get_thread_id_from_state(self, state: str) -> str:
        """Get the thread ID associated with a state"""
        auth_code = self.state_mapping.get(state)
        if not auth_code:
            raise ValueError("Invalid state")
        return auth_code.thread_id

    def get_authorization_url(self, session_id: str) -> (str, str):
        # Generate state and associate with this session
        state = self.create_state(session_id)

        # Build OAuth authorization URL
        return (
                   f"{self.token_endpoint.replace('token', 'authorize')}?"
                   f"client_id={self.client_id}&"
                   f"response_type=code&"
                   f"scope=openid+book_hotel&"
                   f"redirect_uri={self.redirect_uri}&"
                   f"state={state}"
               ), state

    async def get(self, url: str, scope: List[str]):
        client = AsyncOAuth2Client(
            client_id=self.client_id,
            client_secret=self.client_secret,
            scope=scope)

        _ = await client.fetch_token(url=self.token_endpoint)

        # Authenticated request
        response = await client.get(url)
        return response.json()

    async def fetch_user_token(self, state: str) -> dict:
        """Exchange authorization code for token"""
        auth_code = self.state_mapping.get(state)
        if not auth_code or not auth_code.code:
            raise ValueError("Invalid state or missing code")

        # Create OAuth client
        client = AsyncOAuth2Client(
            client_id=self.client_id,
            client_secret=self.client_secret,
            redirect_uri=self.redirect_uri
        )

        # Exchange code for token
        try:
            token = await client.fetch_token(
                self.token_endpoint,
                code=auth_code.code,
                grant_type="authorization_code"
            )

            # Store token with the state
            auth_code.token = token
            self.state_mapping[state] = auth_code
            return token
        except Exception as e:
            logger.error(f"Error fetching token: {str(e)}")
            raise
