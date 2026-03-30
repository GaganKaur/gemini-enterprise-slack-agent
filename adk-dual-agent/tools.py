import os
import logging
import json
import requests
import concurrent.futures
from typing import Optional, Tuple
from google.adk.tools.tool_context import ToolContext
from google.auth.transport.requests import Request
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# --- CONFIGURATION ---
PROJECT_ID = os.environ.get("GCP_PROJECT_ID")
PROJECT_NUMBER = os.environ.get("GCP_PROJECT_NUMBER") 
LOCATION = os.environ.get("GOOGLE_DISCOVERY_LOCATION", "global")
ENGINE_ID = os.environ.get("ENGINE_ID") 
COLLECTION = "default_collection"
USER_CREDENTIAL_CACHE = {}

def update_state(key: str, value: str, tool_context: ToolContext):
    tool_context.state[key] = value
    return value

def get_state(key: str, tool_context: ToolContext) -> str:
    return tool_context.state.get(key, None)

def get_valid_user_creds(tool_context: ToolContext):
    slack_user_id = getattr(tool_context, "user_id", None) or tool_context.state.get("slack_user_id")
    if not slack_user_id: raise ValueError("System Error: Unable to identify user context.")
    user_creds = USER_CREDENTIAL_CACHE.get(slack_user_id)
    if not user_creds: raise ValueError("System Error: Credentials not found. Please log in again.")
    if not user_creds.valid: user_creds.refresh(Request())
    return user_creds

# =================================================================
# ⚙️ INTERNAL API 1: CORE SEARCH (For Workspace & GDrive)
# =================================================================
def _run_core_search_api(query: str, token: str) -> str:
    print(f"[DEBUG] 🔍 [Core Search API] Thread started...")
    url = f"https://discoveryengine.googleapis.com/v1alpha/projects/{PROJECT_NUMBER}/locations/{LOCATION}/collections/{COLLECTION}/engines/{ENGINE_ID}/servingConfigs/default_config:search"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json", "X-Goog-User-Project": PROJECT_ID}
    
    payload = {
        "query": query,
        "pageSize": 5, 
        "contentSearchSpec": {
            "summarySpec": {
                "summaryResultCount": 5,
                "includeCitations": False, # 🚨 TURNED OFF AT THIS TIME
                "ignoreAdversarialQuery": True,
                "ignoreNonSummarySeekingQuery": False 
            }
        }
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        if response.status_code != 200: return ""
            
        data = response.json()
        summary_text = data.get("summary", {}).get("summaryText", "")
        
        return summary_text
        
    except Exception as e:
        print(f"[DEBUG] ❌ [Core Search API] Error: {e}")
        return ""

# =================================================================
# ⚙️ INTERNAL API 2: STREAM ASSIST (For BQ, GCS, Agentic Data)
# =================================================================
def _run_stream_assist_api(query: str, token: str, session_id: str = None) -> Tuple[str, str]:
    print(f"[DEBUG] 🌊 [StreamAssist API] Thread started...")
    url = f"https://discoveryengine.googleapis.com/v1alpha/projects/{PROJECT_NUMBER}/locations/{LOCATION}/collections/{COLLECTION}/engines/{ENGINE_ID}/assistants/default_assistant:streamAssist"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json", "X-Goog-User-Project": PROJECT_ID}
    
    query_to_send = f"Please summarize the information found in the documents regarding: {query}"
    payload = {"query": {"text": query_to_send}}
    if session_id: payload["session"] = session_id
        
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        if response.status_code != 200: return "", None
            
        response_chunks = response.json()
        if isinstance(response_chunks, dict): response_chunks = [response_chunks]

        accumulated_text = ""
        new_session_id = None

        for chunk in response_chunks:
            if "sessionInfo" in chunk and "session" in chunk["sessionInfo"]:
                new_session_id = chunk["sessionInfo"]["session"]
                
            answer = chunk.get("answer", {})
            if answer.get("state") == "SKIPPED": continue
            
            if "replyText" in answer.get("reply", {}):
                accumulated_text += answer["reply"]["replyText"]
                
            for rep in answer.get("replies",[]):
                content_block = rep.get("groundedContent", {}).get("content", {})
                if content_block.get("thought") is True: continue
                if content_block.get("role") == "model" and "text" in content_block:
                    accumulated_text += content_block["text"]
                
        return accumulated_text, new_session_id
        
    except Exception as e:
        print(f"[DEBUG] ❌ [StreamAssist API] Error: {e}")
        return "", None

# =================================================================
# 🛠️ THE SMART BLENDED SEARCH TOOL
# =================================================================
def call_agentspace_search_api(query: str, tool_context: ToolContext) -> str:
    print(f"\n[DEBUG] --- Executing Blended Search Tool ---")
    
    try:
        user_creds = get_valid_user_creds(tool_context)
        token = user_creds.token
        session_id = tool_context.state.get("vertex_search_session_id")
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            future_search = executor.submit(_run_core_search_api, query, token)
            future_stream = executor.submit(_run_stream_assist_api, query, token, session_id)
            
            search_text = future_search.result()
            stream_text, new_session_id = future_stream.result()

        if new_session_id:
            tool_context.state["vertex_search_session_id"] = new_session_id

        if not search_text and not stream_text:
            return "I searched all enterprise systems but could not find any information regarding this query."

        blended_response = ""
        if search_text and not stream_text:
            blended_response = search_text
        elif stream_text and not search_text:
            blended_response = stream_text
        elif search_text and stream_text:
            blended_response = (
                "### Information from Workspace Documents:\n" + search_text + "\n\n" +
                "### Information from Databases & Systems:\n" + stream_text
            )

        print(f"[DEBUG] Total Blended Response Length: {len(blended_response)}")
        return blended_response

    except Exception as e:
        logger.error(f"Blended Search Error: {e}", exc_info=True)
        return f"System Error: {str(e)}"