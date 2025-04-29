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
import os

from dotenv import load_dotenv

from .asgardeo import AsgardeoManager
from .connection import ConnectionManager

load_dotenv("../.env")

client_id = os.environ.get('ASGARDEO_CLIENT_ID')
client_secret = os.environ.get('ASGARDEO_CLIENT_SECRET')
tenant_domain = os.environ.get('ASGARDEO_METADATA_URL')
redirect_url = os.environ.get('ASGARDEO_REDIRECT_URI', 'http://localhost:8000/oauth/callback')

token_endpoint = f"https://{tenant_domain}/oauth2/token"


connection_manager = ConnectionManager()
asgardeo_manager = AsgardeoManager()
