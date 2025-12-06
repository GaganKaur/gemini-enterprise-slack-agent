import os
from google.adk.tools.tool_context import ToolContext
from google.api_core.client_options import ClientOptions
from google.cloud import discoveryengine_v1alpha as discoveryengine

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

    # 3. SETUP CLIENT 
    client_options = ClientOptions(
        api_endpoint=f"{LOCATION}-discoveryengine.googleapis.com" if LOCATION != "global" else None,
        quota_project_id=PROJECT  
    )

    try:
        client = discoveryengine.ConversationalSearchServiceClient(
            credentials=user_creds,
            client_options=client_options
        )

        serving_config = (
            f"projects/{PROJECT}/locations/{LOCATION}/"
            f"collections/default_collection/engines/{ENGINE_ID}/"
            f"servingConfigs/default_config"
        )
        
        # 4. EXECUTE SEARCH
        request = discoveryengine.AnswerQueryRequest(
            serving_config=serving_config,
            query=discoveryengine.Query(text=query),
            answer_generation_spec=discoveryengine.AnswerQueryRequest.AnswerGenerationSpec(
                include_citations=True,
            ),
            query_understanding_spec=discoveryengine.AnswerQueryRequest.QueryUnderstandingSpec(
                query_rephraser_spec=discoveryengine.AnswerQueryRequest.QueryUnderstandingSpec.QueryRephraserSpec(
                    disable=False
                )
            )
        )

        response = client.answer_query(request=request)
        answer_text = response.answer.answer_text
        
        # 5. FORMAT OUTPUT
        citations = []
        if response.answer.citations:
            for citation in response.answer.citations:
                for source in citation.sources:
                    ref_index = int(source.reference_id)
                    if ref_index < len(response.answer.references):
                        ref = response.answer.references[ref_index]
                        uri = ref.chunk_info.document_metadata.uri
                        title = ref.chunk_info.document_metadata.title
                        citations.append(f"- <{uri}|{title}>")
        
        unique_citations = sorted(list(set(citations)))
        
        if not answer_text:
            return "I searched the knowledge base but couldn't generate a summary."

        final_output = f"{answer_text}\n\n*Sources:*\n" + "\n".join(unique_citations)
        return final_output

    except Exception as e:
        print(f"[DEBUG] CRITICAL API ERROR: {e}")
        return f"System Error: {str(e)}"