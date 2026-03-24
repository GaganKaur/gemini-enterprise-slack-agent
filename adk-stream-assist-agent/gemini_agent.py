"""Defines the GE agent."""
import os
from google.adk.agents import llm_agent
from google.adk.apps.app import App
import prompts
import tools
import vertexai

# Initialize Vertex AI
vertexai.init(project=os.environ.get("GCP_PROJECT_ID"), location="global")

root_agent = llm_agent.Agent(
    model="gemini-2.5-pro", 
    name="ge_agent",
    description="Helpful agent that answers questions securely using enterprise data.",
    instruction=prompts.AGENT_PROMPT,
    tools=[
        tools.update_state,
        tools.get_state,
        # SWAPPED: Replaced call_agentspace_search_api with the new streamAssist tool
        tools.call_agentspace_search_api, 
    ],
)
app = App(root_agent=root_agent, name="ge_agent")