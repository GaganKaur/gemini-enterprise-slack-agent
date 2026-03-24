# ADK + StreamAssist Slack Agent

This folder contains an alternative, advanced approach to connecting Slack with Gemini Enterprise (Vertex AI Search). 

### Key Differences from the Standard Approach:
1. **StreamAssist API (`discoveryengine.AssistantServiceClient`):** Replaces the standard `/answer` API. This method dynamically summarize keyword searches and maintain conversational memory (multi-turn RAG).
2. **Google Agent Development Kit (ADK):** Uses `gemini-2.5-pro` as an orchestrator to dynamically route user questions to the Vertex AI Search tool, and handles the live "typing" streaming effect in the Slack UI.
3. **True User Identity (OAuth + PKCE):** Instead of using a God-Mode Service Account, this app spins up a lightweight Flask server to facilitate a 3-legged OAuth flow. It passes the end-user's specific Google Workspace token to Vertex AI, ensuring **Document-Level Security (ACLs)** are strictly enforced.

### Setup
1. Copy `.env.example` to `.env` and fill in your credentials.
2. Download your Google OAuth `client_secrets.json` and place it in this folder.
3. Run `pip install -r requirements.txt`.
4. Run `python3 app.py`.