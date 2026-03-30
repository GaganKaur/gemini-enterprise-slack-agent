import os
import threading
import asyncio
import logging
import re
import time # Added for the typing effect throttle
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
import gemini_agent  
from gemini_agent import app as adk_app
import tools

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE'] = '1'

# --- 1. SETUP FLASK (OAuth Callback) ---
flask_app = Flask(__name__)

@flask_app.route("/oauth2callback")
def oauth2callback():
    slack_user_id = request.args.get('state')
    try:
        auth_handler.exchange_code_for_credentials(slack_user_id, request.url)
        slack_app.client.chat_postMessage(
            channel=slack_user_id,
            text="✅ *Login successful!* You can now ask your question."
        )
        return """
        <html>
            <head>
                <title>Login Successful</title>
                <style>
                    body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; text-align: center; padding-top: 50px; background-color: #f8f9fa; }
                    h1 { color: #28a745; }
                    p { color: #6c757d; }
                </style>
            </head>
            <body>
                <h1>✅ Login Successful!</h1>
                <p>We are taking you back to Slack...</p>
                <p><small>If Slack doesn't open, <a href="slack://open">click here</a>.</small></p>
                <script>
                    window.location.href = "slack://open";
                    setTimeout(function() { window.close(); }, 2000);
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

def acknowledge_event(ack):
    """Acknowledge the Slack event immediately to prevent 3-second retries."""
    ack()

def process_request(event, say, client):
    """This runs in the background (Lazy Listener)"""
    slack_user_id = event.get('user')
    user_text = event.get('text', '')
    channel_id = event.get('channel')
    
    # Strip bot mention
    user_text = user_text.split(">", 1)[-1].strip() if ">" in user_text else user_text

    # A. Auth Check
    user_creds = auth_handler.get_creds_for_user(slack_user_id)
    if not user_creds or not user_creds.valid:
        login_url = auth_handler.get_google_auth_url(slack_user_id)
        say(blocks=[
            {"type": "section", "text": {"type": "mrkdwn", "text": f"Hi <@{slack_user_id}>! Please login."}}, 
            {"type": "actions", "elements":[{"type": "button", "text": {"type": "plain_text", "text": "Login with Google"}, "url": login_url, "style": "primary", "action_id": "login_btn"}]}
        ], text="Please login.")
        return

    # B. Send initial placeholder message and grab its Timestamp (ts)
    initial_msg = say(f"Let me check that for you, <@{slack_user_id}>... :mag:")
    message_ts = initial_msg["ts"]

    # Save to Global Cache for ADK Tools
    tools.USER_CREDENTIAL_CACHE[slack_user_id] = user_creds

    async def run_adk_workflow():
        session_id = f"slack-{slack_user_id}"
        session = await session_service.get_session(app_name=APP_NAME, user_id=slack_user_id, session_id=session_id)

        if not session:
            session = await session_service.create_session(app_name=APP_NAME, user_id=slack_user_id, session_id=session_id)
        
        session.state["slack_user_id"] = slack_user_id

        new_message = types.Content(role="user", parts=[types.Part(text=user_text)])
        response_text = ""
        last_update_time = time.time()
        
        # ---------------------------------------------------------
        # 🚨 THE LIVE-TYPING FIX: Safe limit for chat.update
        # ---------------------------------------------------------
        MAX_UPDATE_LENGTH = 3000 # Leave plenty of room for Slack blocks/formatting

        try:
            async for adk_event in runner.run_async(user_id=slack_user_id, session_id=session_id, new_message=new_message):
                if adk_event.content:
                    if adk_event.content.role == "model":
                        for part in adk_event.content.parts:
                            if part.text: 
                                response_text += part.text
                                
                            if part.function_call:
                                # Safe tool update (Trims existing text if it's too long)
                                display_text = response_text if len(response_text) < MAX_UPDATE_LENGTH else response_text[:MAX_UPDATE_LENGTH] + "\n\n*(Generating long response...)*"
                                client.chat_update(
                                    channel=channel_id,
                                    ts=message_ts,
                                    text=f"_{display_text}_\n\n*Using tool:* `{part.function_call.name}` ⚙️"
                                )
                                last_update_time = time.time()

                # --- LIVE TYPING UI EFFECT (Safely Truncated) ---
                if time.time() - last_update_time > 1.5 and response_text:
                    if len(response_text) < MAX_UPDATE_LENGTH:
                        # Normal typing update
                        client.chat_update(
                            channel=channel_id,
                            ts=message_ts,
                            text=response_text + " ⏳"
                        )
                    else:
                        client.chat_update(
                            channel=channel_id,
                            ts=message_ts,
                            text=response_text[:MAX_UPDATE_LENGTH] + "\n\n*(Still generating long response...)* ⏳"
                        )
                    
                    last_update_time = time.time()

        except Exception as inner_e:
            logger.error(f"Runner crashed: {inner_e}", exc_info=True)
            raise inner_e

        return response_text

    try:
        final_answer = asyncio.run(run_adk_workflow())
        
        # ---------------------------------------------------------
        # 🚨 THE FINAL DELIVERY FIX: Threading the Overflow
        # ---------------------------------------------------------
        if final_answer:
            MAX_SLACK_LENGTH = 3500
            
            if len(final_answer) <= MAX_SLACK_LENGTH:
                client.chat_update(channel=channel_id, ts=message_ts, text=final_answer)
            else:
                # 1. Update the main message with the first chunk
                first_chunk = final_answer[:MAX_SLACK_LENGTH] + "...\n\n*(Continued in thread 👇)*"
                client.chat_update(channel=channel_id, ts=message_ts, text=first_chunk)
                
                # 2. Break the overflow into chunks and send as threaded replies
                overflow_text = final_answer[MAX_SLACK_LENGTH:]
                chunks = [overflow_text[i:i+MAX_SLACK_LENGTH] for i in range(0, len(overflow_text), MAX_SLACK_LENGTH)]
                
                for chunk in chunks:
                    client.chat_postMessage(
                        channel=channel_id,
                        thread_ts=message_ts,
                        text=chunk
                    )
        else:
            client.chat_update(channel=channel_id, ts=message_ts, text="I processed the request, but returned no text.")
            
    except Exception as e:
        logger.error(f"Error executing ADK workflow: {e}", exc_info=True)
        client.chat_update(channel=channel_id, ts=message_ts, text=f"I encountered an error while processing: `{e}`")
    

# --- LISTENERS ---
@slack_app.action(re.compile(".*"))
def handle_actions(ack): ack()

@slack_app.message()
def handle_dm(ack, event, say, client): 
    ack()
    process_request(event, say, client)

@slack_app.event("app_mention")
def handle_app_mention_events(ack, event, say, client): 
    ack()
    process_request(event, say, client)

# --- RUN ---
def run_flask(): flask_app.run(host='127.0.0.1', port=5000)

if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    SocketModeHandler(slack_app, os.environ["SLACK_APP_TOKEN"]).start()