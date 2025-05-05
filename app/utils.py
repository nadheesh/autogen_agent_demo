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
import functools
import inspect
import logging
from collections import OrderedDict
from typing import Any, Callable, Sequence, Dict, Optional
from typing import List

from autogen_core import CancellationToken
from autogen_core.code_executor import Import
from autogen_core.tools import FunctionTool
from pydantic import BaseModel
from pydantic import Field

from app.auth import AuthManager, AuthToken, OAuthGrantType

logger = logging.getLogger(__name__)

TOKEN_FIELD = "token"


class ToolAuthContext(BaseModel):
    """Context information for tool authorization"""
    scopes: List[str] = Field(default_factory=list)
    grant_type: OAuthGrantType = OAuthGrantType.CLIENT_CREDENTIALS


class ToolAuthSpec:
    def __init__(self, manager: AuthManager, context: ToolAuthContext):
        self.manager = manager
        self.context = context
        self._validate_manager()  # Validate the manager based on the grant type
        self._register_scopes()  # Register the context.scopes with the manager

    def _validate_manager(self):
        if self.context.grant_type is OAuthGrantType.AUTHORIZATION_CODE:
            if not self.manager.redirect_uri:
                raise ValueError(
                    "Redirect URI is required for authorization code grant type."
                )
            if not self.manager.get_message_handler():
                raise ValueError(
                    "Message handler is required for authorization code grant type."
                )

    def _register_scopes(self):
        for scope in self.context.scopes:
            self.manager.register_scope(scope)


class SecureFunctionTool(FunctionTool):
    """Extension of FunctionTool that enforces permissions before execution"""

    def __init__(
            self,
            func: Callable[..., Any],
            description: str,
            name: Optional[str] = None,
            auth: Optional[ToolAuthSpec] = None,
            global_imports: Sequence[Import] = [],
            strict: bool = False,
    ):
        # Store the auth context
        self.auth = auth

        # Pending authorization requests
        self._pending_auths: Dict[str, asyncio.Future] = {}

        # Message handlers by session
        self._message_handlers: Dict[str, Callable] = {}

        # Get the original signature
        signature = inspect.signature(func)
        params = OrderedDict(signature.parameters)

        # Remove 'token' parameter from the function signature
        token_field = params.pop(TOKEN_FIELD, None)
        if token_field is None or token_field.annotation is not AuthToken:
            available = ", ".join(f"{p.name}: {p.annotation}" for p in params.values())
            raise Exception(
                f"Expected a parameter named '{TOKEN_FIELD}' with type 'AuthToken' in tool arguments, "
                f"but got: {available or 'no parameters'}.\n"
                f"Ensure your function signature includes '{TOKEN_FIELD}: AuthToken'."
            )

        new_signature = signature.replace(parameters=params.values())

        # Create a new function with the modified signature
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Dummy function to replace the original
            pass

        wrapper.__signature__ = new_signature

        # Initialize the parent FunctionTool
        super().__init__(wrapper, description, name, global_imports, strict)

        # Store the original function
        self._signature = inspect.signature(func)
        self._func = func

    async def run(self, args: BaseModel, cancellation_token: CancellationToken) -> Any:
        # Skip auth if no auth context
        if not self.auth:
            args = args.model_copy(update={TOKEN_FIELD: ""})  # Set a empty token if no auth context
            return await super().run(args, cancellation_token)

        token = None
        if self.auth.context.grant_type == OAuthGrantType.CLIENT_CREDENTIALS:
            # Get token using client credentials
            token = await self.auth.manager.get_token()
        elif self.auth.context.grant_type == OAuthGrantType.AUTHORIZATION_CODE:
            token = await self.auth.manager.request_user_authorization(self.auth.context.scopes, args.model_dump())
            if not token:
                # User did not authorize the request
                raise Exception("User did not authorize the request or authorization timeout.")

        if not token:
            # No token was received
            raise Exception("No token received from authorization request.")

        # Modify args with the token
        args = args.model_copy(update={TOKEN_FIELD: token})

        # Execute the tool
        return await super().run(args, cancellation_token)
