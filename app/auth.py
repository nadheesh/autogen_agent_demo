"""
 Copyright (c) 2025, WSO2 LLC. (http://www.wso2.com). All Rights Reserved.

  This software is the property of WSO2 LLC. and its suppliers, if any.
  Dissemination of any information or reproduction of any material contained
  herein is strictly forbidden, unless permitted by WSO2 in accordance with
  the WSO2 Commercial License available at http://wso2.com/licenses.
  For specific language governing the permissions and limitations under
  this license, please see the license as well as any agreement you’ve
  entered into with WSO2 governing the purchase of this software and any
"""
import asyncio
import inspect
import logging
import secrets
import time
from enum import Enum
from typing import List, Dict, Callable, Awaitable, Union, Literal, get_type_hints
from typing import Optional

from authlib.integrations.httpx_client import AsyncOAuth2Client
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class OAuthGrantType(str, Enum):
    """OAuth grant types supported by the tools"""
    CLIENT_CREDENTIALS = "client_credentials"
    AUTHORIZATION_CODE = "authorization_code"


class AuthToken(BaseModel):
    """OAuth token information"""
    access_token: str
    token_type: str = "Bearer"
    expires_in: Optional[int] = None
    refresh_token: Optional[str] = None
    scope: Optional[str] = None
    id_token: Optional[str] = None
    expires_at: Optional[float] = None

    def is_expired(self) -> bool:
        if not self.expires_at:
            return True
        return time.time() >= self.expires_at - 60  # Refresh slightly early


class AuthRequestMessage(BaseModel):
    type: Literal["auth_request"] = "auth_request"
    auth_url: str
    state: str
    scopes: List[str]
    context: Union[dict, BaseModel]


class AuthManager:
    def __init__(self,
                 client_id: str,
                 client_secret: str,
                 tenant_domain: str,
                 redirect_uri: Optional[str] = None,
                 message_handler: Callable[[AuthRequestMessage], Awaitable[None]] = None,
                 scopes: Optional[List[str]] = None):
        self.client_id = client_id
        self.client_secret = client_secret
        self.token_endpoint = f"https://{tenant_domain}/oauth2/token"
        self.authorize_endpoint = f"https://{tenant_domain}/oauth2/authorize"
        self.redirect_uri = redirect_uri
        self.scopes = scopes or []

        # Pending authorization requests
        self._pending_auths: Dict[str, asyncio.Future] = {}

        # Message handler for authorization requests
        self._message_handler: Callable[[AuthRequestMessage], Awaitable[None]] = message_handler

        # Cache client-credentials token
        # Can be used until expired
        self.jwt_token: Optional[AuthToken] = None

        # # TODO - Add support for reusable user token scenarios (when user logged in before using agent)
        # # Cache user token
        # # Used only once for the authorized tool
        # self.user_token: Optional[AuthToken] = None  # cache authorization-grant token

        # Validate the message handler
        self._validate()

    def _validate(self):
        self._validate_message_handler()

    def _validate_message_handler(self):
        message_handler = self._message_handler
        if not message_handler:
            return
        if not callable(message_handler):
            raise TypeError("message_handler must be callable")
        if not inspect.iscoroutinefunction(message_handler):
            raise TypeError("message_handler must be an async function")

        signature = inspect.signature(message_handler)
        params = list(signature.parameters.values())

        if len(params) != 1:
            raise TypeError("message_handler must accept exactly one parameter")

        param_type = get_type_hints(message_handler).get(params[0].name)
        if param_type != AuthRequestMessage:
            raise TypeError(f"message_handler parameter must be of type AuthRequestMessage, not {param_type}")

    @staticmethod
    def _create_state() -> str:
        state = secrets.token_urlsafe(16)
        # self.state_mapping[state] = thread_id
        return state

    def get_message_handler(self) -> Callable[[AuthRequestMessage], Awaitable[None]]:
        return self._message_handler

    async def _fetch_token(self) -> AuthToken:
        client = AsyncOAuth2Client(
            client_id=self.client_id,
            client_secret=self.client_secret,
            scope=self.scopes,
        )

        try:
            token = await client.fetch_token(url=self.token_endpoint)
        except Exception as e:
            logger.error(f"Error fetching token: {e}")
            raise

        print(token)
        return AuthToken(**token)

    async def _fetch_auth_grant_token(self, code: str) -> AuthToken:
        # Exchange code for token
        client = AsyncOAuth2Client(
            client_id=self.client_id,
            client_secret=self.client_secret,
            redirect_uri=self.redirect_uri
        )

        try:
            token = await client.fetch_token(
                self.token_endpoint,
                code=code,
                grant_type=OAuthGrantType.AUTHORIZATION_CODE
            )
        except Exception as e:
            logger.error(f"Error fetching token: {e}")
            raise

        print(token)
        return AuthToken(**token)

    async def get_token(self) -> AuthToken:
        if self.jwt_token and not self.jwt_token.is_expired():
            return self.jwt_token

        self.jwt_token = await self._fetch_token()
        return self.jwt_token

    def register_scope(self, scope: str):
        if scope not in self.scopes:
            self.scopes.append(scope)

            # Invalidate the current token if scopes change
            self.jwt_token = None

    async def request_user_authorization(
            self,
            scopes: List[str],
            context: Union[Dict, BaseModel]
    ) -> Optional["AuthToken"]:
        """
        Requests user authorization and waits for a token asynchronously.

        Args:
            scopes (List[str]): List of scopes to request authorization for.
            context (dict | BaseModel): Additional context to send with the authorization message.

        Returns:
            Optional[AuthToken]: The token received upon user authorization, or None if it fails or times out.
        """
        if not self._message_handler:
            logger.error(f"[Authorization Error] No message handler registered.")
            return None

        state = self._create_state()

        # Create a future to await authorization completion
        future = asyncio.Future()
        self._pending_auths[state] = future

        # Construct authorization URL
        scope = " ".join(scopes)
        auth_url = (
            f"{self.authorize_endpoint}?"
            f"client_id={self.client_id}&"
            f"response_type=code&"
            f"scope={scope}&"
            f"redirect_uri={self.redirect_uri}&"
            f"state={state}"
        )

        # Notify client via handler
        await self._message_handler(
            AuthRequestMessage(
                auth_url=auth_url,
                state=state,
                scopes=scopes,
                context=context
            )
        )

        # Wait for authorization to complete (with timeout)
        try:
            token = await asyncio.wait_for(future, timeout=300)  # 5 minute timeout
            return token
        except asyncio.TimeoutError:
            logger.warning(f"Authorization timed out for session {state}")
            # Clean up the pending auth
            if state in self._pending_auths:
                future = self._pending_auths.pop(state)
                if not future.done():
                    future.cancel()
            return None

    async def process_callback(self, state: str, code: str) -> AuthToken:
        if state not in self._pending_auths:
            logger.error(f"[Authorization Error] No pending authorization for state '{state}'.")
            raise ValueError("Invalid state or no pending authorization")

        token = await self._fetch_auth_grant_token(code)

        # Resolve any pending authorization futures
        if state in self._pending_auths:
            future = self._pending_auths.pop(state)
            if not future.done():
                future.set_result(token)

        return token
