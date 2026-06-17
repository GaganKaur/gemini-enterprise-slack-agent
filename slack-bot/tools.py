import os
import json
import httpx
from google.adk.tools.tool_context import ToolContext

# Configuration
PROJECT = os.environ.get("GCP_PROJECT_ID")
LOCATION = "global"
ENGINE_ID = os.environ.get("ENGINE_ID") 

# GLOBAL CACHE
USER_CREDENTIAL_CACHE = {}

# --- HELPER FUNCTIONS ---
def update_state(key: str, value: str, tool_context: ToolContext):
    tool_context.state[key] = value
    return value

def get_state(key: str, tool_context: ToolContext) -> str:
    return tool_context.state.get(key, None)

# --- SEARCH TOOL ---
def call_agentspace_search_api(query: str, tool_context: ToolContext) -> str:
    print(f"\n[DEBUG] --- Tool 'call_agentspace_search_api' started ---")

    # 1. GET USER ID
    slack_user_id = getattr(tool_context, "user_id", None)
    if not slack_user_id:
        slack_user_id = tool_context.state.get("slack_user_id")
    
    if not slack_user_id:
        return "System Error: Unable to identify user context."

    print(f"[DEBUG] identified user: {slack_user_id}")

    # 2. RETRIEVE CREDENTIALS
    user_creds = USER_CREDENTIAL_CACHE.get(slack_user_id)

    if not user_creds:
        print(f"[DEBUG] ERROR: No credentials found in cache for {slack_user_id}")
        return "System Error: Credentials not found. Please log in again."

    # Make sure token is valid
    if not user_creds.valid:
        from google.auth.transport.requests import Request
        try:
            user_creds.refresh(Request())
        except Exception as refresh_err:
            print(f"[DEBUG] Failed to refresh credentials: {refresh_err}")
            return "System Error: Session expired. Please log in again."

    # 3. SETUP STREAMING ENDPOINT URL & HEADERS
    url = (
        f"https://discoveryengine.googleapis.com/v1alpha/"
        f"projects/{PROJECT}/locations/{LOCATION}/collections/default_collection/"
        f"engines/{ENGINE_ID}/assistants/default_assistant:streamAssist"
    )
    
    headers = {
        "Authorization": f"Bearer {user_creds.token}",
        "Content-Type": "application/json",
        "X-Goog-User-Project": PROJECT
    }

    payload = {
        "query": {
            "text": query
        },
        "assistSkippingMode": "REQUEST_ASSIST"
    }

    full_answer_text = ""
    citations = []

    print(f"[DEBUG] Querying streaming RAG API: {url}")

    try:
        # 4. EXECUTE STREAMING CALL TO PREVENT GFE TIMEOUT
        with httpx.Client(timeout=60.0) as http_client:
            with http_client.stream("POST", url, json=payload, headers=headers) as response:
                if response.status_code != 200:
                    err_content = response.read().decode("utf-8")
                    print(f"[DEBUG] API Error response: {err_content}")
                    return f"System Error: RAG API returned HTTP {response.status_code}"

                buffer = ""
                brace_count = 0
                in_object = False

                for chunk in response.iter_bytes():
                    if not chunk:
                        continue

                    segment = chunk.decode("utf-8", errors="ignore")
                    for char in segment:
                        if in_object:
                            buffer += char

                        if char == "{":
                            if brace_count == 0:
                                in_object = True
                                buffer = "{"
                            brace_count += 1
                        elif char == "}":
                            brace_count -= 1
                            if brace_count == 0 and in_object:
                                try:
                                    obj = json.loads(buffer)
                                    # Extract assistToken if present
                                    assist_token = obj.get("assistToken")
                                    if assist_token:
                                        tool_context.state["latest_assist_token"] = assist_token
                                    answer_obj = obj.get("answer", {})

                                    # Extract plan details if emitted in stream
                                    for reply in answer_obj.get("replies", []):
                                        content_block = reply.get("groundedContent", {}).get("content", {})
                                        if content_block.get("role") == "model" and "text" in content_block:
                                            print(f"[PLAN CHUNK] {content_block['text']}", flush=True)

                                    # Extract text output
                                    if "answerText" in answer_obj:
                                        full_answer_text += answer_obj["answerText"]
                                    elif "replyText" in answer_obj.get("reply", {}):
                                        text = answer_obj["reply"]["replyText"]
                                        full_answer_text += text

                                    # Extract source references
                                    for step in answer_obj.get("steps", []):
                                        for action in step.get("actions", []):
                                            for source in action.get("sources", []):
                                                title = source.get("title", "Document")
                                                uri = source.get("uri", "")
                                                if uri and (title, uri) not in citations:
                                                    citations.append((title, uri))
                                except Exception:
                                    pass

                                buffer = ""
                                in_object = False

        # 5. FORMAT OUTPUT
        if not full_answer_text:
            return "I searched the knowledge base but couldn't generate a summary."

        if citations:
            formatted_citations = "\n".join([f"- <{url}|{title}>" for title, url in citations])
            return f"{full_answer_text}\n\n*Sources:*\n{formatted_citations}"

        return full_answer_text

    except Exception as e:
        print(f"[DEBUG] CRITICAL API ERROR: {e}")
        return f"System Error: {str(e)}"