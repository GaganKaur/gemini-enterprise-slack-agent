"""Defines the GE agent."""
import os
from google.adk.agents import llm_agent
from google.adk.apps.app import App
import prompts
import tools
import vertexai

vertexai.init(
    project=os.environ.get("GCP_PROJECT_ID"), 
    location=os.environ.get("GOOGLE_DISCOVERY_LOCATION", "global")
)

root_agent = llm_agent.Agent(
    model=os.environ.get("GOOGLE_LLM_MODEL", "gemini-2.5-pro"), 
    name="ge_agent",
    description="An enterprise orchestrator that answers questions and executes workflows.",
    instruction=prompts.AGENT_PROMPT,
    tools=[
        tools.update_state,
        tools.get_state,
        tools.call_agentspace_search_api,
        tools.invoke_specialized_workflow_agent,  # Tool 2: Low-Code Agent Executions! 
    ],
)

app = App(root_agent=root_agent, name="ge_agent")