# Gemini Enterprise Slack Bot (User-Delegated Access)
This Slack Bot integrates Gemini Enterprise (Discovery Engine) with Slack using a secure, user-delegated authentication flow.

## Key Features
- Zero-Trust Security: The bot does not use a generic Service Account to search. It uses 3-Legged OAuth to act as the specific Slack user.
- ACL Enforcement: Search results respect Google DataSource permissions. Users only see documents they are allowed to see.
- Agentic Workflow: Built using the Google Agent Development Kit (ADK).

## Repository Structure
```bash
/project-root
  ├── app.py                # Main entry point (Slack Bolt + Flask OAuth)
  ├── agent.py              # ADK Agent definition
  ├── tools.py              # Search tool implementation & Credential Cache
  ├── auth_handler.py       # Google OAuth flow helper
  ├── client_secrets.json   # (Download from GCP) OAuth Client Credentials
  ├── requirements.txt      # Python dependencies
  └── .env                  # Configuration secrets
```
### Part 1: Local Test Environment Setup
Follow these steps to run the bot on a local machine using Slack Socket Mode

1. **Prerequisites**
- Python 3.9+
- A Google Cloud Project with billing enabled.
- APIs Enabled: Discovery Engine API, Vertex AI API.
- IAM Role: Your testing user must have Discovery Engine Viewer role on the GCP Project.

2. **Google Cloud Configuration**
    1. Create OAuth Client:
    - Go to APIs & Services > Credentials.
    - Create OAuth Client ID (Application Type: Web Application).
    - Authorized Redirect URI: http://127.0.0.1:5000/oauth2callback
    - Download the JSON file, rename it to client_secrets.json, and place it in the project root.
    2. Configure Consent Screen:
    - Go to OAuth Consent Screen.
    - Set to Internal (if possible) or External (requires adding your email to "Test Users").
    - Add Scopes: openid, email, profile, https://www.googleapis.com/auth/cloud-platform.

3. **Slack App Configuration**
    1. Create an app at api.slack.com/apps.
    2. Socket Mode: Enable it. Generate an App-Level Token (starts with xapp-).
    3. OAuth & Permissions:
    - Add Bot Scopes: app_mentions:read, chat:write.
    - Install App to Workspace. Copy Bot User OAuth Token (starts with xoxb-).
    4. Event Subscriptions: Enable Events. Subscribe to app_mention.

4. **Application Configuration**
Create a .env file in the project root:

```bash
# Google Cloud Config
GCP_PROJECT_ID=your-project-id
DATA_STORE_ID=your-datastore-id

# Slack Config
SLACK_BOT_TOKEN=xoxb-your-bot-token
SLACK_APP_TOKEN=xapp-your-app-token

# Local Development Flags (DO NOT USE IN PROD)
OAUTHLIB_INSECURE_TRANSPORT=1
OAUTHLIB_RELAX_TOKEN_SCOPE=1
```
5. **Running the Bot**
    1. Install dependencies:
```bash
pip install -r requirements.txt
```
2. Run the application:
```bash
python3 app.py
```
3. Test: Go to Slack and mention the bot: @DiscoveryBot help.
    - It will ask you to login.
    - Click the button -> Login with Google.
    - Once redirected back, ask the question again.


### Part 2: Production Deployment Guide
Deploying to production (e.g., Google Cloud Run) requires changing the state management strategy because Cloud Run is stateless (memory is wiped when the container scales down).

### Required Changes

1. **1. Switch Storage to Database (Firestore)**
- Enable Firestore in GCP.
- Update tools.py to save/load credentials from Firestore instead of a dictionary.

2. **Update Redirect URIs**
- Deploy the app to Cloud Run. Copy the service URL (e.g., https://bot-service.run.app).
- Update GCP Console > Credentials: Add https://bot-service.run.app/oauth2callback.
- Update auth_handler.py: Set REDIRECT_URI to the Cloud Run URL.

### IAM Permissions for Production Service Account
The Service Account running the Cloud Run container needs these roles:
- Cloud Datastore User: To Read/Write user tokens to Firestore.
- Logs Writer: To write logs to Cloud Logging.

