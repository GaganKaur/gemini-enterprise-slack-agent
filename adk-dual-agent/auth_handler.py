import google_auth_oauthlib.flow
from google.oauth2.credentials import Credentials
import os
import federated_auth

# In production, use a database (Firestore/Redis)
user_tokens = {}

# NEW: We need to temporarily hold the Flow object to preserve the PKCE "code_verifier"
pending_flows = {} 

current_dir = os.path.dirname(os.path.abspath(__file__))
CLIENT_SECRETS_FILE = os.path.join(current_dir, "client_secrets.json")
SCOPES =['https://www.googleapis.com/auth/cloud-platform', 'openid', 'email','https://www.googleapis.com/auth/drive.readonly', 'https://www.googleapis.com/auth/bigquery.readonly']
REDIRECT_URI = 'http://localhost:8080/oauth2callback'

def get_google_auth_url(slack_user_id):
    flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE, scopes=SCOPES)
    flow.redirect_uri = REDIRECT_URI
    
    authorization_url, state = flow.authorization_url(
        access_type='offline',
        prompt='consent',
        include_granted_scopes='true',
        state=slack_user_id
    )
    
    # CRITICAL FIX: Save the flow object into our temporary dictionary 
    # so we don't lose the secret code_verifier!
    pending_flows[slack_user_id] = flow
    
    return authorization_url

def exchange_code_for_credentials(state_slack_user_id, auth_response_url):
    # CRITICAL FIX: Retrieve the EXACT SAME flow object we created in step 1
    flow = pending_flows.get(state_slack_user_id)
    
    if not flow:
        raise ValueError("Login session expired or invalid state. Please try logging in again.")

    # Fetch the token (This will now succeed because the flow remembers the code_verifier!)
    flow.fetch_token(authorization_response=auth_response_url)
    
    # Save the successful credentials
    user_tokens[state_slack_user_id] = flow.credentials
    
    # Automatically sync Google Workspace connectors with Gemini Enterprise EngineUserData upon login
    try:
        federated_auth.sync_workspace_connectors(flow.credentials.token)
    except Exception as e:
        print(f"[WARNING] Failed to sync workspace connectors on login: {e}")
    
    # Clean up the pending flow to free up memory
    if state_slack_user_id in pending_flows:
        del pending_flows[state_slack_user_id]
        
    return flow.credentials

def get_creds_for_user(slack_user_id):
    return user_tokens.get(slack_user_id)