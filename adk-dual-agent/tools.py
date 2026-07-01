import os
import logging
import json
import requests
import urllib.parse
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
LOCATION = os.environ.get("GOOGLE_DISCOVERY_LOCATION", os.environ.get("LOCATION", "global"))
ENDPOINT = f"{LOCATION}-discoveryengine.googleapis.com" if LOCATION != "global" else "discoveryengine.googleapis.com"
ENGINE_ID = os.environ.get("ENGINE_ID") 
COLLECTION = "default_collection"
USER_CREDENTIAL_CACHE = {}
import federated_auth

# =================================================================
# 🗄️ SECTION 1: STATE & CREDENTIAL HELPERS
# =================================================================
def update_state(key: str, value: str, tool_context: ToolContext):
    """Updates the tool context state. Required by gemini_agent.py"""
    tool_context.state[key] = value
    return value

def get_state(key: str, tool_context: ToolContext) -> str:
    """Retrieves value from tool context state. Required by gemini_agent.py"""
    return tool_context.state.get(key, None)

def get_valid_user_creds(tool_context: ToolContext):
    slack_user_id = getattr(tool_context, "user_id", None) or tool_context.state.get("slack_user_id")
    if not slack_user_id: raise ValueError("System Error: Unable to identify user context.")
    user_creds = USER_CREDENTIAL_CACHE.get(slack_user_id)
    if not user_creds: raise ValueError("System Error: Credentials not found. Please log in again.")
    if not user_creds.valid: user_creds.refresh(Request())
    return user_creds

# =================================================================
# 📑 SECTION 2: UNIVERSAL CITATION & PARSING HELPERS
# =================================================================
# Architectural Remark: Unlike standard search responses, workflow sub-agents
# in Discovery Engine return metadata across diverse container keys, plural list
# structures, or as JSON-encoded strings inside tool observation traces.
# The helpers below perform deep recursive extraction to guarantee 100% link capture.

def _is_invalid_source(text: str) -> bool:
    """Filters out internal Agent names, system IDs, and API resource paths from citations."""
    if not text or not isinstance(text, str): return True
    t = text.strip().lower()
    # Terms indicating internal agent/tool execution rather than a real document
    forbidden = ["assistant agent", "default_assistant", "workflow_agent", "preview_agent", "tool", "agent (", "agent_id", "agentspec", "streamassist"]
    if any(f in t for f in forbidden): return True
    # Exclude raw API resource paths (e.g. projects/123/locations/global/...)
    if t.startswith("projects/") or t.startswith("agents/") or t.startswith("tools/") or t.startswith("locations/"):
        return True
    # Exclude pure numeric IDs or raw alphanumeric hashes without word separators
    raw = t.replace("-", "").replace("_", "").replace(".", "").replace("/", "")
    if raw.isdigit() and len(raw) > 8:
        return True
    return False

def _resolve_to_clickable_url(ref: dict) -> Tuple[str, str]:
    """Extracts a document Title and clickable Slack link (<url|title>) from any dictionary."""
    if not isinstance(ref, dict):
        return "", ""

    url_keys = [
        "webViewLink", "webContentLink", "url", "uri", "link", "alternateLink",
        "htmlLink", "webUrl", "webURL", "docUrl", "docUri", "documentUri",
        "documentUrl", "sourceUri", "sourceUrl", "permalink", "externalUrl", "selfLink",
        "fileUrl", "fileUri", "resourceUri", "resourceUrl", "src", "href"
    ]
    title_keys = [
        "title", "displayName", "documentTitle", "name", "subject",
        "fileName", "filename", "label", "header", "docTitle", "pageTitle", "caption"
    ]

    # Gather all candidate dictionaries recursively at any depth inside ref
    dicts_to_check = []
    seen_ids = set()
    def _collect_dicts(d):
        if id(d) in seen_ids: return
        seen_ids.add(id(d))
        dicts_to_check.append(d)
        for val in d.values():
            if isinstance(val, dict):
                _collect_dicts(val)
            elif isinstance(val, list):
                for item in val:
                    if isinstance(item, dict):
                        _collect_dicts(item)
    _collect_dicts(ref)

    uri = ""
    for d in dicts_to_check:
        # Check standard URL keys first
        for k in url_keys:
            val = d.get(k)
            if isinstance(val, str) and val.strip():
                val_str = val.strip()
                if val_str.startswith("http://") or val_str.startswith("https://"):
                    uri = val_str
                    break
                elif val_str.startswith("gs://"):
                    uri = "https://storage.cloud.google.com/" + val_str[5:]
                    break
                elif val_str.startswith("projects/") and "/documents/" in val_str:
                    try:
                        doc_id = val_str.split("/documents/")[1].split("/")[0]
                        uri = f"https://console.cloud.google.com/gen-app-builder/engines/{ENGINE_ID}/data-stores/default_data_store/documents/{doc_id}?project={PROJECT_ID}"
                        break
                    except Exception:
                        pass
        if uri:
            break
        # Fallback: check any standalone string value in d for a valid HTTP/HTTPS URL
        for val in d.values():
            if isinstance(val, str) and val.strip():
                val_str = val.strip()
                if (val_str.startswith("http://") or val_str.startswith("https://")) and len(val_str.split()) == 1:
                    if not any(ignored in val_str for ignored in ["json-schema.org", "w3.org", "googleapis.com/auth", "schema.org", "discoveryengine.googleapis.com", ".js", ".css", ".png", ".jpg", ".svg", ".ico"]):
                        uri = val_str
                        break
        if uri:
            break

    if not uri:
        return "", ""

    title = ""
    for d in dicts_to_check:
        for k in title_keys:
            val = d.get(k)
            if isinstance(val, str) and val.strip():
                candidate = val.strip()
                if not _is_invalid_source(candidate) and candidate != uri:
                    title = candidate
                    break
        if title:
            break

    if not title or _is_invalid_source(title):
        title = "Source Document"

    return str(title), (uri if uri.startswith("http") else "")

def _parse_stream_assist_chunks(response_chunks) -> Tuple[str, str, list]:
    """Recursively crawls StreamAssist response chunks to extract text and clickable citations."""
    if isinstance(response_chunks, dict): response_chunks = [response_chunks]
    accumulated_text = ""
    new_session_id = None
    citations_map = {} # Maps URL -> Title to deduplicate and upgrade fallback titles

    url_keys = [
        "webViewLink", "webContentLink", "url", "uri", "link", "alternateLink",
        "htmlLink", "webUrl", "webURL", "docUrl", "docUri", "documentUri",
        "documentUrl", "sourceUri", "sourceUrl", "permalink", "externalUrl", "selfLink",
        "fileUrl", "fileUri", "resourceUri", "resourceUrl", "src", "href"
    ]
    # Includes all singular, plural, and agent-trace container structures in Discovery Engine
    container_keys = [
        "documentMetadata", "docInfo", "structData", "derivedStructData",
        "metadata", "document", "documents", "source", "sources", "chunkInfo", "web", "gdrive",
        "drive", "sharepoint", "item", "items", "data", "reference", "references", "citation",
        "citations", "file", "files", "page", "pages", "step", "steps", "action", "actions",
        "reply", "replies", "groundedContent", "groundingMetadata", "supportingReferences",
        "retrievedReferences", "retrievedContexts", "retrievedContext", "dataStoreResults",
        "dataStoreResult", "groundingChunk", "groundingChunks"
    ]

    def _add_citation(link, title):
        """Adds or upgrades a citation in citations_map, preferring real titles over 'Source Document'."""
        if not link: return
        if link not in citations_map or citations_map[link] == "Source Document":
            if title and title != "Source Document":
                citations_map[link] = title
            elif link not in citations_map:
                citations_map[link] = "Source Document"

    def _crawl(obj):
        nonlocal accumulated_text
        if isinstance(obj, dict):
            # Capture generated text response
            if "replyText" in obj and isinstance(obj["replyText"], str):
                accumulated_text += obj["replyText"]
            if obj.get("role") == "model" and "text" in obj and isinstance(obj["text"], str):
                accumulated_text += obj["text"]
            if "content" in obj and isinstance(obj["content"], str):
                accumulated_text += obj["content"]

            # Check if this dictionary contains standard keys or URL prefixes
            has_url = any(k in obj for k in url_keys + container_keys)
            if not has_url:
                for val in obj.values():
                    if isinstance(val, str) and (val.strip().startswith("http://") or val.strip().startswith("https://") or val.strip().startswith("gs://") or (val.strip().startswith("projects/") and "/documents/" in val)):
                        has_url = True
                        break
                    elif isinstance(val, dict):
                        for subval in val.values():
                            if isinstance(subval, str) and (subval.strip().startswith("http://") or subval.strip().startswith("https://") or subval.strip().startswith("gs://") or (subval.strip().startswith("projects/") and "/documents/" in subval)):
                                has_url = True
                                break
                        if has_url: break

            if has_url:
                title, link = _resolve_to_clickable_url(obj)
                _add_citation(link, title)

            # Recurse into values; decode embedded JSON strings (e.g. tool observation outputs)
            for v in obj.values():
                if isinstance(v, dict):
                    _crawl(v)
                elif isinstance(v, list):
                    for item in v: _crawl(item)
                elif isinstance(v, str):
                    v_str = v.strip()
                    if (v_str.startswith("{") and v_str.endswith("}")) or (v_str.startswith("[") and v_str.endswith("]")):
                        try:
                            sub_json = json.loads(v_str)
                            _crawl(sub_json)
                        except Exception:
                            pass
                    elif "http://" in v_str or "https://" in v_str:
                        # Extract raw URLs embedded inside text descriptions or Markdown sentences
                        for token in v_str.split():
                            clean_token = token.strip("()[],'\"<>")
                            if clean_token.startswith("http://") or clean_token.startswith("https://"):
                                if not any(ignored in clean_token for ignored in ["json-schema.org", "w3.org", "googleapis.com/auth", "schema.org", "discoveryengine.googleapis.com", ".js", ".css", ".png", ".jpg", ".svg", ".ico"]):
                                    title, _ = _resolve_to_clickable_url(obj)
                                    if not title or title == "Source Document":
                                        title = "Source Document"
                                    _add_citation(clean_token, title)
        elif isinstance(obj, list):
            for item in obj: _crawl(item)

    for chunk in response_chunks:
        if isinstance(chunk, dict) and "session" in chunk.get("sessionInfo", {}):
            new_session_id = chunk["sessionInfo"]["session"]
        _crawl(chunk)

    citations = [f"- <{link}|{title}>" for link, title in citations_map.items()]
    return accumulated_text, new_session_id, citations

# =================================================================
# 🌊 SECTION 3: THE STREAMASSIST API CLIENT
# =================================================================
# Architectural Remark: In Google Cloud Discovery Engine's StreamAssist API,
# toolResult[] is deprecated and sub-agent workflow executions (agentsSpec) do not
# bubble up document references to the top-level answer.references field.
# To ensure zero-latency citation delivery without legacy APIs, we use ThreadPoolExecutor
# to concurrently query StreamAssist's native search tool (vertexAiSearchSpec) when
# executing a workflow agent, seamlessly merging the recovered citations.

def _run_stream_assist_api(query: str, token: str, session_id: str = None, target_agent_id: str = None) -> Tuple[str, str]:
    """Unified StreamAssist API client with parallel citation recovery for workflow agents."""
    url = f"https://{ENDPOINT}/v1alpha/projects/{PROJECT_NUMBER}/locations/{LOCATION}/collections/{COLLECTION}/engines/{ENGINE_ID}/assistants/default_assistant:streamAssist"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json", "X-Goog-User-Project": PROJECT_ID}
    
    payload = {
        "query": {"text": query},
        "assistSkippingMode": "REQUEST_ASSIST",
        "toolsSpec": {"vertexAiSearchSpec": {}}
    }
    
    if target_agent_id:
        payload["agentsSpec"] = {"agentSpecs": [{"agentId": target_agent_id, "version": "deployed"}]}
    
    if session_id:
        payload["session"] = session_id
        
    try:
        if target_agent_id:
            # Concurrent Execution: Run workflow agent action and search index query in parallel
            search_payload = {
                "query": {"text": query},
                "assistSkippingMode": "REQUEST_ASSIST",
                "toolsSpec": {"vertexAiSearchSpec": {}}
            }
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                future_workflow = executor.submit(requests.post, url, headers=headers, json=payload, timeout=120)
                future_search = executor.submit(requests.post, url, headers=headers, json=search_payload, timeout=30)
                
                response = future_workflow.result()
                fallback_cites = []
                try:
                    search_resp = future_search.result()
                    if search_resp.status_code == 200:
                        _, _, fallback_cites = _parse_stream_assist_chunks(search_resp.json())
                except Exception as e_s:
                    logger.warning(f"Parallel StreamAssist citation recovery failed: {e_s}")
        else:
            response = requests.post(url, headers=headers, json=payload, timeout=120)
            fallback_cites = []

        if response.status_code != 200:
            logger.error(f"API Error {response.status_code}: {response.text}")
            return "", None
            
        data = response.json()
        if target_agent_id:
            logger.info(f"[DEBUG WORKFLOW AGENT {target_agent_id}] StreamAssist Raw Response:\n{json.dumps(data, indent=2)}")
            
        text, new_sid, cites = _parse_stream_assist_chunks(data)
        if target_agent_id:
            logger.info(f"[DEBUG WORKFLOW AGENT {target_agent_id}] Extracted Citations: {cites}")
            if fallback_cites:
                logger.info(f"[DEBUG WORKFLOW AGENT {target_agent_id}] Recovered Citations from parallel StreamAssist search: {fallback_cites}")
                # Merge fallback citations while preserving real document titles over 'Source Document'
                merged_map = {}
                for c in cites + fallback_cites:
                    try:
                        inner = c[3:-1] if c.startswith("- <") and c.endswith(">") else ""
                        if "|" in inner:
                            u, t = inner.split("|", 1)
                            if u not in merged_map or merged_map[u] == "Source Document":
                                merged_map[u] = t
                    except Exception:
                        pass
                cites = [f"- <{u}|{t}>" for u, t in merged_map.items()]
        
        final_output = text
        if cites:
            unique_cites = []
            for c in cites:
                if c not in unique_cites:
                    unique_cites.append(c)
            if unique_cites:
                final_output = final_output.strip() + "\n\n*Sources:*\n" + "\n".join(unique_cites)
        
        return final_output, new_sid
    except Exception as e:
        logger.error(f"StreamAssist Exception: {e}")
        return "", None

# =================================================================
# 🛠️ SECTION 4: AGENT TOOLS
# =================================================================

def call_agentspace_search_api(query: str, tool_context: ToolContext) -> str:
    """Performs a standard enterprise search."""
    try:
        user_creds = get_valid_user_creds(tool_context)
        session_id = tool_context.state.get("vertex_search_session_id")
        
        text, new_sid = _run_stream_assist_api(query, user_creds.token, session_id)
        if new_sid: tool_context.state["vertex_search_session_id"] = new_sid
        return text or "No information found."
    except Exception as e:
        return f"Search Error: {str(e)}"

def invoke_specialized_workflow_agent(query: str, target_agent_id: str, tool_context: ToolContext) -> str:
    """Invokes a low-code workflow agent with session management and citations."""
    try:
        user_creds = get_valid_user_creds(tool_context)
        session_key = f"workflow_session_{target_agent_id}"
        session_id = tool_context.state.get(session_key)
        
        text, new_sid = _run_stream_assist_api(query, user_creds.token, session_id, target_agent_id)
        if new_sid: tool_context.state[session_key] = new_sid
        
        return text or "The agent executed but provided no summary."
    except Exception as e:
        return f"Workflow Error: {str(e)}"

# =================================================================
# 🔗 SECTION 5: CONNECTOR MANAGEMENT
# =================================================================

def list_federated_connectors(tool_context: ToolContext) -> str:
    try:
        user_creds = get_valid_user_creds(tool_context)
        connectors = federated_auth.get_federated_connectors(user_creds.token)
        if not connectors: return "No connectors found."
        output = "### 🔗 Connector Status\n"
        for conn in connectors:
            status = "✅ Authorized" if conn['authState'] == "AUTHORIZED" else "⚠️ Unauthorized"
            output += f"**{conn['displayName']}**: {status}\n"
            if conn['authState'] != "AUTHORIZED":
                output += f"- [Authorize]({conn.get('authorizationUri')})\n"
        return output
    except Exception as e: return str(e)

def authorize_federated_connector(connector_id: str, redirect_uri: str, tool_context: ToolContext) -> str:
    try:
        user_creds = get_valid_user_creds(tool_context)
        federated_auth.authorize_connector(user_creds.token, connector_id, redirect_uri)
        return f"✅ Authorized `{connector_id}`!"
    except Exception as e: return f"❌ Failed: {str(e)}"

def unauthorize_federated_connector(connector_id: str, tool_context: ToolContext) -> str:
    try:
        user_creds = get_valid_user_creds(tool_context)
        federated_auth.unauthorize_connector(user_creds.token, connector_id)
        return f"✅ Revoked `{connector_id}`."
    except Exception as e: return f"❌ Failed: {str(e)}"