import logging
import os
from typing import Dict, List, Optional
import uuid
import requests
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class AuthToken(BaseModel):
    id: str
    scopes: List[str]
    token: str


class AuthCode(BaseModel):
    state: str
    user_id: str
    code: Optional[str]
    scopes: List[str]


class AsgardeoManager:
    """
    Manages OAuth2 authentication flow and token management
    """

    def __init__(self):
        # Initialize OAuth2 configuration
        self.client_id = os.environ['CLIENT_ID']
        self.client_secret = os.environ['CLIENT_SECRET']
        self.token_url = os.environ['TOKEN_URL']
        self.ciba_url = os.environ['CIBA_URL']
        self.authorize_url = os.environ['AUTHORIZE_URL']
        self.redirect_uri = os.environ['REDIRECT_URI']
        self.google_redirect_uri = os.environ['GOOGLE_REDIRECT_URI']

        self.auth_codes: Dict[str, AuthCode] = {}  # Store AuthCode by session_id
        self.auth_tokens: Dict[str, AuthToken] = {}  # Store AuthToken by token_id
        self.thread_user_map: Dict[str, str] = {}  # Store user_id against thread_id
        self.state_thread_map: Dict[str, str] = {}  # Store thread_id against state
        self.state_mapping: Dict[str, AuthCode] = {}
        self.user_claims: Dict[str, Dict] = {}

    def store_auth_code(self, user_id: str, code: str):
        """Store authentication code and user_id"""
        code_entry: AuthCode = self.get_auth_code(user_id)
        if not code_entry:
            raise ValueError("No auth code found for user")
        code_entry.code = code
        self.auth_codes[user_id] = code_entry

    def get_auth_code(self, user_id: str) -> Optional[AuthCode]:
        """Retrieve the AuthCode for a user_id"""
        return self.auth_codes.get(user_id)

    def get_authorization_url(self, thread_id: str, user_id: str, scopes: List[str] = ["openid"]) -> str:
        """
        Generate the authorization URL for the OAuth2 flow matching the exact format provided,
        with scopes passed as a list
        """
        try:

            scopes_str = " ".join(scopes)
            nonce = str(uuid.uuid4())[:16]
            state = str(uuid.uuid4())

            authorization_url = (
                f"{self.authorize_url}?"
                f"client_id={self.client_id}&"
                f"redirect_uri={self.redirect_uri}&"
                f"scope={scopes_str}&"
                f"response_type=code&"
                f"response_mode=query&"
                f"state={state}&"
                f"nonce={nonce}"
            )
            self.store_thread_id_against_state(thread_id, state)
            auth_code = AuthCode(state=state, user_id=user_id, code=None, scopes=scopes)
            self.state_mapping[state] = auth_code
            # Store auth code entry
            self.auth_codes[self.get_token_key(user_id, scopes)] = auth_code
            return authorization_url
        except Exception as e:
            raise

    def get_google_authorization_url(self, thread_id: str, user_id: str, scopes: List[str] = ["openid"], ) -> str:
        """
        Generate the authorization URL for the OAuth2 flow matching the exact format provided,
        with scopes passed as a list
        """
        try:

            scopes_str = " ".join(scopes)
            nonce = str(uuid.uuid4())[:16]
            state = str(uuid.uuid4())

            authorization_url = (
                f"{self.authorize_url}?"
                f"client_id={self.client_id}&"
                f"redirect_uri={self.google_redirect_uri}&"
                f"scope={scopes_str}&"
                f"response_type=code&"
                f"response_mode=query&"
                f"selector=calendar&"
                f"reAuth=true&"
                f"share_federated_token=true&"
                f"federated_token_scope=Google Calendar;https://www.googleapis.com/auth/calendar.events.owned openid&"
                f"state={state}&"
                f"nonce={nonce}"
            )
            self.store_thread_id_against_state(thread_id, state)
            auth_code = AuthCode(state=state, user_id=user_id, code=None, scopes=scopes)
            self.state_mapping[state] = auth_code
            # Store auth code entry
            self.auth_codes[self.get_token_key(user_id, scopes)] = auth_code
            return authorization_url
        except Exception as e:
            raise

    def fetch_user_token(self, state: str) -> str:
        """
        Exchange authorization code for access token
        """
        code_entry: AuthCode = self.state_mapping.get(state)
        if not code_entry:
            raise ValueError("No auth code found for user")
        try:
            response = requests.post(
                self.token_url,
                data={
                    "grant_type": "authorization_code",
                    "code": code_entry.code,
                    "scope": " ".join(code_entry.scopes),
                    "redirect_uri": self.redirect_uri,
                    "client_id": self.client_id,
                    "client_secret": self.client_secret
                },
                verify=False
            )
            data = response.json()
            print(data)
            access_token = data.get("access_token")
            token_key = self.get_token_key(code_entry.user_id, code_entry.scopes)
            token = AuthToken(id=code_entry.user_id, scopes=code_entry.scopes, token=access_token)
            self.auth_tokens[token_key] = token
            fed_tokens = data.get("federated_tokens")
            print(fed_tokens)
            if fed_tokens:
                fed_access_token = fed_tokens[0].get("accessToken")
                token = AuthToken(id=code_entry.user_id, scopes=code_entry.scopes, token=fed_access_token)
                self.auth_tokens[token_key + "_google"] = token
            return access_token
        except Exception as e:
            print(e)
            raise

    def fetch_google_token(self, state: str) -> str:
        """
        Exchange authorization code for access token
        """
        code_entry: AuthCode = self.state_mapping.get(state)
        if not code_entry:
            raise ValueError("No auth code found for user")
        try:
            response = requests.post(
                self.token_url,
                data={
                    "grant_type": "authorization_code",
                    "code": code_entry.code,
                    "scope": " ".join(code_entry.scopes),
                    "redirect_uri": self.google_redirect_uri,
                    "client_id": self.client_id,
                    "client_secret": self.client_secret
                },
                verify=False
            )
            data = response.json()
            print(data)
            access_token = data.get("access_token")
            token_key = self.get_token_key(code_entry.user_id, code_entry.scopes)
            token = AuthToken(id=code_entry.user_id, scopes=code_entry.scopes, token=access_token)
            self.auth_tokens[token_key] = token
            fed_tokens = data.get("federated_tokens")
            print(fed_tokens)
            if fed_tokens:
                fed_access_token = fed_tokens[0].get("accessToken")
                token = AuthToken(id=code_entry.user_id, scopes=code_entry.scopes, token=fed_access_token)
                self.auth_tokens[token_key + "_google"] = token
            return access_token
        except Exception as e:
            print(e)
            raise

    def fetch_app_token(self, scopes: List[str]) -> str:
        """
        Get an access token for the app
        """
        try:
            response = requests.post(
                self.token_url,
                data={
                    "grant_type": "client_credentials",
                    "scope": " ".join(scopes),
                    "client_id": self.client_id,
                    "client_secret": self.client_secret
                },
                verify=False
            )
            data = response.json()
            return data.get("access_token")
        except Exception as e:
            raise

    def initiate_ciba(self, thread_id: str, scopes: List[str]) -> str:
        """
        Initiate CIBA flow
        """
        user_id = self.get_user_id_from_thread_id(thread_id)
        user_claims = self.get_user_claims(user_id)
        username = user_claims.get("username")
        try:
            response = requests.post(
                self.ciba_url,
                data={
                    "login_hint": username,
                    "binding_message": "UpgradeRoom",
                    "scope": " ".join(scopes),
                    "client_id": self.client_id,
                    "client_secret": self.client_secret
                },
                verify=False
            )
            data = response.json()
            print(data)
            return data.get("auth_req_id")
        except Exception as e:
            raise Exception("Failed to initiate CIBA flow")

    def get_ciba_token(self, auth_req_id: str) -> dict:
        """
        Get CIBA token and return state with token or error
        """
        try:
            response = requests.post(
                self.token_url,
                data={
                    "grant_type": "urn:openid:params:grant-type:ciba",
                    "auth_req_id": auth_req_id,
                    "client_id": self.client_id,
                    "client_secret": self.client_secret
                },
                verify=False
            )
            print(response.json())
            if response.status_code == 200:
                data = response.json()
                return {
                    "state": "success",
                    "token": data.get("access_token")
                }
            else:
                data = response.json()
                error = data.get("error")
                if error == "authorization_pending":
                    return {
                        "state": "pending",
                        "error": "authorization_pending"
                    }
                else:
                    return {
                        "state": "error",
                        "error": error or "Unknown error"
                    }
        except Exception as e:
            return {
                "state": "error",
                "error": str(e)
            }

    def get_app_token(self, scopes: List[str]) -> str:
        """
        Get valid m2m token.
        """
        token_entry: AuthToken = self.auth_tokens.get(self.get_token_key("m2m", scopes))
        if token_entry:
            return token_entry.token
        fetch_token = self.fetch_app_token(scopes)
        token = AuthToken(id="m2m", scopes=scopes, token=fetch_token)
        self.auth_tokens[self.get_token_key("m2m", scopes)] = token
        return fetch_token

    def get_user_token(self, user_id: str, scopes: List[str]) -> str:
        """
        Get valid m2m token.
        """
        token_key = self.get_token_key(user_id, scopes)
        token_entry: AuthToken = self.auth_tokens.get(token_key)
        if token_entry:
            return token_entry.token
        return None

    def get_user_google_token(self, user_id: str, scopes: List[str]) -> str:
        """
        Get valid m2m token.
        """
        token_key = self.get_token_key(user_id, scopes)
        token_entry: AuthToken = self.auth_tokens.get(token_key + "_google")
        if token_entry:
            return token_entry.token
        return None

    def get_token_key(self, id: str, scopes: List[str]) -> str:
        """
        Get token key from id and scopes
        """
        return id + '_' + "_".join(scopes)

    def store_user_id_against_thread_id(self, thread_id: str, user_id: str):
        """
        Store user_id against thread_id
        """
        self.thread_user_map[thread_id] = user_id

    def get_user_id_from_thread_id(self, thread_id: str) -> str:
        """
        Get user_id from thread_id
        """
        return self.thread_user_map.get(thread_id)

    def store_thread_id_against_state(self, thread_id: str, state: str):
        """
        Store thread_id against state
        """
        self.state_thread_map[state] = thread_id

    def get_thread_id_from_state(self, state: str) -> str:
        """
        Get thread_id from state
        """
        return self.state_thread_map.get(state)

    def store_user_claims(self, user_id: str, claims: Dict):
        """
        Store user claims
        """
        self.user_claims[user_id] = claims

    def get_user_claims(self, user_id: str) -> Dict:
        """
        Get user claims
        """
        return self.user_claims.get(user_id)


asgardeo_manager = AsgardeoManager()
