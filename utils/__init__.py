import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
    OAUTH_CLIENT_ID = os.getenv('OAUTH_CLIENT_ID')
    OAUTH_CLIENT_SECRET = os.getenv('OAUTH_CLIENT_SECRET')
    OAUTH_TOKEN_URL = os.getenv('OAUTH_TOKEN_URL')
    OAUTH_AUTHORIZE_URL = os.getenv('OAUTH_AUTHORIZE_URL')
    OAUTH_REDIRECT_URI = os.getenv('OAUTH_REDIRECT_URI')
    THIRD_PARTY_API_URL = os.getenv('THIRD_PARTY_API_URL')
    FLASK_SECRET_KEY = os.getenv('FLASK_SECRET_KEY')
    COMPOSIO_API_KEY = os.getenv('COMPOSIO_API_KEY')
    FRONTEND_URL = os.getenv('FRONTEND_URL', 'http://localhost:3000')
