import os
import time
import threading
import asyncio
import logging
import re
from flask import Flask, request
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from dotenv import load_dotenv

# --- ADK IMPORTS ---
from google.adk.runners import Runner
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.genai import types 

# Local Imports
import auth_handler
import agent  # Imports your agent.py
from agent import app as adk_app
import tools

load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- CONFIG: OAUTH LOCALHOST ---
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE'] = '1'

# --- 1. SETUP FLASK (OAuth Callback) ---
flask_app = Flask(__name__)

# @flask_app.route("/oauth2callback")
# def oauth2callback():
#     slack_user_id = request.args.get('state')
#     try:
#         auth_handler.exchange_code_for_credentials(slack_user_id, request.url)
#         # Notify user in Slack
#         slack_app.client.chat_postMessage(
#             channel=slack_user_id,
#             text="✅ *Login successful!* You can now ask your question."
#         )
#         return "Login successful! You can close this window."
#     except Exception as e:
#         return f"Login failed: {e}"

@flask_app.route("/oauth2callback")
def oauth2callback():
    slack_user_id = request.args.get('state')
    try:
        # 1. Exchange code for token
        auth_handler.exchange_code_for_credentials(slack_user_id, request.url)
        
        # 2. Notify user in Slack
        slack_app.client.chat_postMessage(
            channel=slack_user_id,
            text="✅ *Login successful!* You can now ask your question."
        )
        
        # 3. Return HTML that redirects back to Slack
        return """
        <html>
            <head>
                <title>Login Successful</title>
                <style>
                    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; text-align: center; padding-top: 50px; background-color: #f8f9fa; }
                    h1 { color: #28a745; }
                    p { color: #6c757d; }
                </style>
            </head>
            <body>
                <h1>✅ Login Successful!</h1>
                <p>We are taking you back to Slack...</p>
                <p><small>If Slack doesn't open, <a href="slack://open">click here</a>.</small></p>
                
                <script>
                    // 1. Attempt to open the Slack Desktop App
                    window.location.href = "slack://open";
                    
                    // 2. Attempt to close this tab after 2 seconds
                    // (Note: Browsers may block this if the tab wasn't opened by script, but it's worth a try)
                    setTimeout(function() { 
                        window.close(); 
                    }, 2000);
                </script>
            </body>
        </html>
        """
    except Exception as e:
        return f"<h1>Login Failed</h1><p>{e}</p>"

# --- 2. SETUP ADK RUNNER ---
session_service = InMemorySessionService()

APP_NAME = "ge_agent" 
runner = Runner(app=adk_app, session_service=session_service)


# --- SLACK ---
slack_app = App(token=os.environ["SLACK_BOT_TOKEN"])

def process_request(slack_user_id, user_text, say):
    # A. Auth Check
    user_creds = auth_handler.get_creds_for_user(slack_user_id)
    if not user_creds or not user_creds.valid:
        login_url = auth_handler.get_google_auth_url(slack_user_id)
        say(blocks=[{"type": "section", "text": {"type": "mrkdwn", "text": f"Hi <@{slack_user_id}>! Please login."}}, {"type": "actions", "elements": [{"type": "button", "text": {"type": "plain_text", "text": "Login with Google"}, "url": login_url, "style": "primary", "action_id": "login_btn"}]}], text="Please login.")
        return

    # Start dynamic message and capture metadata
    initial_resp = say("⚡ *Thinking...*")
    message_ts = initial_resp["ts"]
    channel_id = initial_resp["channel"]

    # Save to Global Cache
    tools.USER_CREDENTIAL_CACHE[slack_user_id] = user_creds

    async def run_adk_workflow(channel, ts):
        print(f"DEBUG: [1] Starting Workflow for {slack_user_id}")
        session_id = f"slack-{slack_user_id}"
        
        # 1. GET OR CREATE SESSION
        print(f"DEBUG: [2] Checking for Session {session_id}")
        
        # Try to get existing session
        session = await session_service.get_session(
            app_name=APP_NAME, 
            user_id=slack_user_id, 
            session_id=session_id
        )

        # If it doesn't exist, create it
        if not session:
            print(f"DEBUG: [2a] Creating New Session {session_id}")
            session = await session_service.create_session(
                app_name=APP_NAME, 
                user_id=slack_user_id, 
                session_id=session_id
            )
        else:
            print(f"DEBUG: [2b] Found Existing Session {session_id}")
        
        # 2. Inject/Update State (Happens for both new and existing sessions)
        session.state["slack_user_id"] = slack_user_id
        print(f"DEBUG: [3] State Injected: {session.state}")

        # 3. Prepare Input
        new_message = types.Content(role="user", parts=[types.Part(text=user_text)])
        response_text = ""
        
        print(f"DEBUG: [4] Starting Runner Loop...")
        last_update_time = 0.0
        update_interval = 0.8  # seconds
        called_tools = set()

        try:
            async for adk_event in runner.run_async(user_id=slack_user_id, session_id=session_id, new_message=new_message):
                if adk_event.content:
                    if adk_event.content.role == "model":
                        for part in adk_event.content.parts:
                            updated = False
                            if part.text: 
                                response_text += part.text
                                updated = True
                            
                            if part.function_call:
                                tool_name = part.function_call.name
                                if tool_name not in called_tools:
                                    called_tools.add(tool_name)
                                    tool_display_name = "Knowledge Base" if tool_name == "call_agentspace_search_api" else tool_name
                                    response_text += f"\n\n🔍 *Searching {tool_display_name}...*"
                                    updated = True
                            
                            if updated:
                                now = time.time()
                                if now - last_update_time >= update_interval:
                                    try:
                                        slack_app.client.chat_update(
                                            channel=channel,
                                            ts=ts,
                                            text=response_text + " █"
                                        )
                                        last_update_time = now
                                    except Exception as e:
                                        print(f"DEBUG: [WARN] chat_update failed: {e}")
        except Exception as inner_e:
            print(f"DEBUG: [ERROR] Runner crashed: {inner_e}")
            raise inner_e

        # Final update to clean up and remove cursor
        try:
            slack_app.client.chat_update(
                channel=channel,
                ts=ts,
                text=response_text if response_text else "I processed the request, but the agent returned no text."
            )
        except Exception as e:
            print(f"DEBUG: [WARN] final chat_update failed: {e}")

        print(f"DEBUG: [5] Finished Loop. Response length: {len(response_text)}")
        return response_text

    try:
        asyncio.run(run_adk_workflow(channel_id, message_ts))
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        try:
            slack_app.client.chat_update(
                channel=channel_id,
                ts=message_ts,
                text=f"❌ *I encountered an error:* {e}"
            )
        except Exception as update_err:
            print(f"DEBUG: Failed to update error status in Slack: {update_err}")

# --- LISTENERS ---
@slack_app.action(re.compile(".*"))
def handle_actions(ack): ack()

@slack_app.message()
def handle_dm(message, say): process_request(message['user'], message['text'], say)

@slack_app.event("app_mention")
def handle_app_mention_events(event, say): process_request(event['user'], event['text'], say)

# --- RUN ---
def run_flask(): flask_app.run(host='127.0.0.1', port=5000)

if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    SocketModeHandler(slack_app, os.environ["SLACK_APP_TOKEN"]).start()