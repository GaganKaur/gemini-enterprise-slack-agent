import os
import logging
import json
import requests
from typing import Optional, Tuple
from google.adk.tools.tool_context import ToolContext
from google.auth.transport.requests import Request
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# --- CONFIGURATION ---
PROJECT_ID = os.environ.get("GCP_PROJECT_ID")
PROJECT_NUMBER = os.environ.get("GCP_PROJECT_NUMBER", "390192081005") 
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
# 🚀 THE UNIFIED STREAM ASSIST TOOL
# =================================================================
# =================================================================
# 🚀 THE UNIFIED STREAM ASSIST TOOL
# =================================================================
def call_agentspace_search_api(query: str, tool_context: ToolContext) -> str:
    print(f"\n[DEBUG] --- Executing Unified StreamAssist Tool ---")
    
    try:
        user_creds = get_valid_user_creds(tool_context)
        
        url = f"https://discoveryengine.googleapis.com/v1alpha/projects/{PROJECT_NUMBER}/locations/{LOCATION}/collections/{COLLECTION}/engines/{ENGINE_ID}/assistants/default_assistant:streamAssist"
        headers = {"Authorization": f"Bearer {user_creds.token}", "Content-Type": "application/json", "X-Goog-User-Project": PROJECT_ID}
        
        # Smart Query Wrapper to prevent SKIPPED errors on short keywords
        query_cleaned = query.strip()
        if "?" not in query_cleaned and len(query_cleaned.split()) < 5:
            query_to_send = f"Please summarize the information found in the documents regarding: {query_cleaned}"
        else:
            query_to_send = query_cleaned
            
        payload = {"query": {"text": query_to_send}}
        
        # Multi-turn conversational memory
        existing_session_id = tool_context.state.get("vertex_search_session_id")
        if existing_session_id:
            payload["session"] = existing_session_id

        print(f"[DEBUG] Sending StreamAssist Query: '{query_to_send}'")
        
        # Execute the HTTP request (No stream=True, we parse the full JSON array)
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        
        if response.status_code != 200:
            print(f"[DEBUG] API ERROR: {response.status_code} - {response.text}")
            return f"System Error: API returned {response.status_code}"

        try:
            response_chunks = response.json()
        except json.JSONDecodeError:
            return "System Error: Invalid JSON response."

        if isinstance(response_chunks, dict): 
            response_chunks = [response_chunks]

        accumulated_text = ""
        new_session_id = None
        
        # 🚨 NEW: Dictionaries to hold the strict citation mappings
        all_retrieved_references = {}
        actually_used_indices = set()

        # -----------------------------------------------------
        # 🕵️ THE AGENTIC JSON PARSER 
        # -----------------------------------------------------
        for chunk in response_chunks:
            # 1. Capture Session ID
            session_info = chunk.get("sessionInfo", {})
            if "session" in session_info:
                new_session_id = session_info["session"]
                
            answer = chunk.get("answer", {})
            if answer.get("state") == "SKIPPED":
                continue
            
            # 2. Extract standard reply text (if applicable)
            if "replyText" in answer.get("reply", {}):
                accumulated_text += answer["reply"]["replyText"]
                
            # 3. Extract Advanced Agentic Replies
            for rep in answer.get("replies",[]):
                grounded_content = rep.get("groundedContent", {})
                
                # A. Extract Text 
                content_block = grounded_content.get("content", {})
                if content_block.get("thought") is not True:
                    if content_block.get("role") == "model" and "text" in content_block:
                        accumulated_text += content_block["text"]
                
                # B. Extract Citation Metadata safely
                metadata = grounded_content.get("textGroundingMetadata", {})
                
                # Step 1: Find out which references the model ACTUALLY used to write the answer
                for segment in metadata.get("segments",[]):
                    for ref_idx in segment.get("referenceIndices",[]):
                        actually_used_indices.add(ref_idx)
                
                # Step 2: Map all retrieved references by their index
                for idx, ref in enumerate(metadata.get("references",[])):
                    doc_meta = ref.get("documentMetadata", {})
                    uri = doc_meta.get("uri", "")
                    title = doc_meta.get("title", "Document")
                    if uri:
                        all_retrieved_references[idx] = f"- <{uri}|{title}>"

        # 4. Save Memory State
        if new_session_id:
            tool_context.state["vertex_search_session_id"] = new_session_id
            print(f"[DEBUG] Saved Vertex Session ID: {new_session_id}")

        # 5. Suppress Hallucinated Apologies
        text_lower = accumulated_text.lower()
        if "i am sorry" in text_lower or "unable to find" in text_lower or "i do not have access" in text_lower:
            return "I searched the knowledge base but could not find any relevant information regarding your query."

        if not accumulated_text:
            return "I searched the knowledge base but couldn't generate a summary."

        # 6. 🚨 THE CITATION FIX: Append ONLY the Deduplicated, USED Citations
        citations_list = [all_retrieved_references[idx] for idx in actually_used_indices if idx in all_retrieved_references]
        
        if citations_list:
            unique_citations = list(set(citations_list))
            accumulated_text += "\n\n*Sources:*\n" + "\n".join(unique_citations)

        print(f"[DEBUG] Successfully retrieved text length: {len(accumulated_text)}")
        return accumulated_text

    except Exception as e:
        logger.error(f"StreamAssist Search Error: {e}", exc_info=True)
        return f"System Error: {str(e)}"
    
# =================================================================
# 🛠️ TOOL 3: DYNAMIC LOW-CODE AGENT ROUTER
# =================================================================
def invoke_specialized_workflow_agent(query: str, target_agent_id: str, tool_context: ToolContext) -> str:
    """
    Triggers a specialized low-code workflow agent in Gemini Enterprise.
    
    Args:
        query: The user's specific request, command, or follow-up answer (e.g., "Reset my password", "My employee ID is 12345").
        target_agent_id: The specific ID of the low-code agent that handles this type of request. 
                         (e.g., "12700619530792433291" for CertWarden).
    """
    print(f"\n[DEBUG] --- Executing Dynamic Workflow Agent Tool ---")
    print(f"[DEBUG] Routing to Agent ID: {target_agent_id}")
    
    if not target_agent_id:
        return "System Error: The orchestrator failed to provide a Target Agent ID."

    try:
        user_creds = get_valid_user_creds(tool_context)
        
        url = f"https://discoveryengine.googleapis.com/v1alpha/projects/{PROJECT_NUMBER}/locations/{LOCATION}/collections/{COLLECTION}/engines/{ENGINE_ID}/assistants/default_assistant:streamAssist"
        
        headers = {
            "Authorization": f"Bearer {user_creds.token}",
            "Content-Type": "application/json",
            "X-Goog-User-Project": PROJECT_ID,
            #"Accept": "text/event-stream"
        }

        payload = {
            "query": { "text": query },
            "agentsSpec": {
                "agentSpecs":[
                    { "agentId": target_agent_id }
                ]
            }
        }

        session_key = f"workflow_session_{target_agent_id}"
        existing_session_id = tool_context.state.get(session_key)
        if existing_session_id:
            payload["session"] = existing_session_id

        print(f"[DEBUG] Invoking workflow query: '{query}'")
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        
        if response.status_code != 200:
            return f"System Error: API returned {response.status_code}"

        try:
            response_chunks = response.json()
        except json.JSONDecodeError:
            return "System Error: Invalid JSON response."

        if isinstance(response_chunks, dict):
            response_chunks = [response_chunks]

        accumulated_text = ""
        new_session_id = None

        for chunk in response_chunks:
            if "sessionInfo" in chunk and "session" in chunk["sessionInfo"]:
                new_session_id = chunk["sessionInfo"]["session"]
                
            answer = chunk.get("answer", {})
            if "replyText" in answer.get("reply", {}):
                accumulated_text += answer["reply"]["replyText"]
                
            for rep in answer.get("replies",[]):
                content_block = rep.get("groundedContent", {}).get("content", {})
                if content_block.get("thought") is True: continue
                if content_block.get("role") == "model" and "text" in content_block:
                    accumulated_text += content_block["text"]

        # Save the unique session back to ADK state
        if new_session_id:
            tool_context.state[session_key] = new_session_id
            print(f"[DEBUG] Saved Session ID for Agent {target_agent_id}: {new_session_id}")

        if not accumulated_text:
            return f"The {target_agent_id} workflow agent executed but did not return a text response."
            
        print(f"[DEBUG] Successfully retrieved workflow response.")
        return accumulated_text

    except Exception as e:
        logger.error(f"Workflow Agent Error: {e}", exc_info=True)
        return f"System Error: {str(e)}"
