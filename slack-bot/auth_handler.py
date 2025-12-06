import google_auth_oauthlib.flow
from google.oauth2.credentials import Credentials
import os

# In production, use a database (Firestore/Redis)
user_tokens = {}

current_dir = os.path.dirname(os.path.abspath(__file__))
CLIENT_SECRETS_FILE = os.path.join(current_dir, "client_secrets.json")
# We need cloud-platform to access Discovery Engine
SCOPES = ['https://www.googleapis.com/auth/cloud-platform', 'openid', 'email']
REDIRECT_URI = 'http://localhost:5000/oauth2callback'

def get_google_auth_url(slack_user_id):
    flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE, scopes=SCOPES)
    flow.redirect_uri = REDIRECT_URI
    
    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        state=slack_user_id
    )
    return authorization_url

def exchange_code_for_credentials(state_slack_user_id, auth_response_url):
    flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE, scopes=SCOPES, state=state_slack_user_id)
    flow.redirect_uri = REDIRECT_URI
    flow.fetch_token(authorization_response=auth_response_url)
    
    user_tokens[state_slack_user_id] = flow.credentials
    return flow.credentials

def get_creds_for_user(slack_user_id):
    return user_tokens.get(slack_user_id)