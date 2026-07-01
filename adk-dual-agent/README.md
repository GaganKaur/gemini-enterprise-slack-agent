# 🌐 Gemini Enterprise Slack Agent: Blended Multi-Agent Orchestration

An enterprise-grade Slack bot built with the **Google Agent Development Kit (ADK)** and **Vertex AI / Discovery Engine (Gemini Enterprise)**. 

Unlike traditional single-turn search bots, this application introduces an intelligent **Blended Multi-Agent Architecture** that seamlessly routes user requests between general enterprise RAG search and autonomous, low-code specialized workflow agents—while guaranteeing 100% clickable citation recovery with zero added latency.

---

## ✨ Key Features & Architectural Highlights

### 🤖 1. Intelligent Request Routing (`gemini_agent.py` & `prompts.py`)
The root ADK agent powered by Gemini (`gemini-3.1-pro-preview`) acts as an intelligent orchestrator:
* **Standard Enterprise Search (`call_agentspace_search_api`)**: Automatically handles general informational queries (e.g., *"What is the HR onboarding policy?"*, *"Summarize Q3 financial report"*), querying your enterprise knowledge base.
* **Specialized Workflow Orchestration (`invoke_specialized_workflow_agent`)**: Automatically delegates complex multi-step actions and workflow operations (e.g., *"Summarize working doc from Google Drive"*, *"Check SRE network status"*, *"Generate marketing campaign assets"*) to designated low-code reasoning engines in your Discovery Engine Registry.
* **Multi-Turn Coreference Resolution**: Seamlessly resolves pronouns and conversational shorthand across follow-up turns into contextualized tool queries.

### ⚡ 2. Zero-Latency Concurrent Citation Recovery (`tools.py`)
In Google Cloud Discovery Engine's modern `streamAssist` architecture, sub-agent workflow executions (`agentsSpec`) do not bubble up intermediate tool traces or document reference arrays to the top-level API response. To overcome this limitation:
* **Concurrent Execution (`ThreadPoolExecutor`)**: When a workflow agent is invoked, `_run_stream_assist_api` concurrently submits the workflow action and a lightweight search index query in parallel.
* **Seamless Blending**: While the workflow agent executes its multi-step reasoning, the search index retrieves matching document metadata. When both complete, the results are merged—delivering specialized workflow summaries alongside clickable Slack citations (`- <url|title>`) with **zero added latency**.

### 🕷️ 3. Universal Deep-Crawl Citation Extractor
An advanced, fault-tolerant citation parser (`_parse_stream_assist_chunks` & `_resolve_to_clickable_url`) built to handle diverse Google Cloud schemas:
* **Deep Recursive Gathering**: Inspects every candidate dictionary and all nested sub-dictionaries at any depth.
* **Plural & Trace Container Support**: Supports all standard and plural Discovery Engine container schemas (`references`, `citations`, `sources`, `files`, `documents`, `groundingChunks`, `retrievedContexts`).
* **Embedded JSON & String Parsing**: Automatically detects and decodes JSON-encoded observation strings inside tool execution traces (`json.loads`) and scans markdown/text strings for embedded HTTP/HTTPS links.
* **Title Deduplication (`citations_map`)**: Ensures that any real document title automatically replaces fallback titles like *"Source Document"*.

### 🔗 4. Federated Data Connector Management (`federated_auth.py`)
Built-in conversational tools allowing users to list, authorize, and revoke third-party federated data connectors (Outlook, SharePoint, OneDrive, Confluence, Jira) directly within Slack chat via OAuth redirect URLs.

### 💬 5. Optimized Slack UX (`app.py`)
* **Real-Time Socket Mode**: Responsive event-driven architecture using Slack Bolt.
* **Live Typing Indicators**: Provides visual feedback while agents execute long-running reasoning tasks.
* **Intelligent Message Cascading**: Automatically splits massive LLM outputs to respect Slack message character limits, gracefully threading overflow content when necessary.

---

## 🗂️ Repository Structure

```text
adk-dual-agent/
├── app.py                 # Slack Bolt Socket Mode listener, event handling, and ADK runner integration
├── gemini_agent.py        # Vertex AI initialization and ADK root Agent definition
├── prompts.py             # System instructions, routing guardrails, and agent registry definitions
├── tools.py               # Unified StreamAssist API client, concurrent citation recovery, and deep-crawl parser
├── auth_handler.py        # OAuth 2.0 user credential caching and token management
├── federated_auth.py      # REST helpers for 3rd-party federated connector OAuth authorization
├── requirements.txt       # Python project dependencies
├── .env.example           # Reference environment configuration fields
└── README.md              # Project documentation
```

---

## 📋 Prerequisites

1. **Google Cloud Platform (GCP)**:
   * A GCP project with **Vertex AI API**, **Discovery Engine API**, and **Gemini Enterprise** enabled.
   * An active Discovery Engine App/Engine ID with connected Data Stores (Google Drive, BigQuery, GCS, etc.).
   * OAuth 2.0 Web Application Client credentials configured with necessary access scopes (`cloud-platform`, `discoveryengine.readwrite`, etc.).
2. **Slack Workspace**:
   * A Slack App with **Socket Mode** enabled, Bot Token (`xoxb-...`), and App Token (`xapp-...`).

---

## 🚀 Setup & Installation

### 1. Clone & Install Dependencies
We recommend using a Python virtual environment:
```bash
git clone <your-repository-url>
cd adk-dual-agent
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure Environment Variables
Copy the reference `.env.example` file to `.env` and populate your project credentials:
```bash
cp .env.example .env
```
Edit `.env` with your preferred editor:
```env
# Slack Credentials
SLACK_BOT_TOKEN=xoxb-your-slack-bot-token
SLACK_APP_TOKEN=xapp-your-slack-app-token

# Google Cloud / Discovery Engine Credentials
GCP_PROJECT_ID=your-gcp-project-id
GCP_PROJECT_NUMBER=your-gcp-project-number
LOCATION=global
ENGINE_ID=your-discovery-engine-id
DATA_STORE_IDS=your-data-store-ids
GOOGLE_GENAI_USE_VERTEXAI=1

# Specialized Workflow Agent IDs (Discovery Engine Registry)
Google_Drive_Assistant=your-gdrive-agent-id
Productivity_Assistant=your-productivity-agent-id
```

### 3. Run the Bot Locally
Start the application:
```bash
python3 app.py
```
You should see in your console:
```text
⚡️ Bolt app is running!
```
Your Slack agent is now active and ready to handle complex blended RAG queries!

---

## 🔒 Security & Best Practices
* **Never commit `.env` or OAuth tokens** to version control. The included `.gitignore` is configured to exclude sensitive files, local logs, and virtual environments.
* Keep your workflow agent IDs in the environment file and ensure they match the registry mapping defined in `prompts.py`.