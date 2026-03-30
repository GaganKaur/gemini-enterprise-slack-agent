# Gemini Enterprise Slack Agent: Blended RAG Architecture

This directory contains an advanced, enterprise-grade integration between **Slack** and **GGemini Enterprise**. 

Unlike standard search bots, this agent utilizes a "Blended Dual-Tool" architecture orchestrated by the **Google Agent Development Kit (ADK)** to securely query structured databases, unstructured cloud storage, and highly restricted Google Workspace documents simultaneously.

## 🌟 Key Features

* **3-Legged OAuth with PKCE:** The bot uses a lightweight Flask server to authenticate individual Slack users via Google OAuth, ensuring strict **Document-Level Security (ACLs)** for Google Drive and Google Workspace files.
* **Dual-Tool Concurrent Searching:**
  * **Core Search API:** Natively handles Google Workspace ACLs, retrieves highly restricted Google Drive documents, and generates precise, clickable citations.
  * **StreamAssist API:** Leverages advanced Agentic schemas to search BigQuery, Cloud Storage (GCS), and federated data simultaneously.
* **Smart Multi-Turn Memory:** The ADK Agent seamlessly resolves pronouns and contextual follow-ups (e.g., "Tell me more about it") into highly targeted database queries.
* **Intelligent Slack UX:** Provides a "live typing" indicator in Slack. Gracefully bypasses Slack's 4000-character limit by splitting massive LLM summaries into readable blocks and cleanly cascading overflow text into Slack threads.

## 📋 Prerequisites

1. A Google Cloud Project with **Vertex AI Search** enabled and a **Gemini Enterprise** app set.
2. The Search Engine/App created in the GCP Console with your Data Stores attached (GDrive, BQ, GCS, etc.).
3. An **OAuth 2.0 Client ID** (Web Application) configured in GCP with the `cloud-platform`, `openid`, and `drive.readonly` scopes.
4. A Slack App configured with Socket Mode enabled.

## 🚀 Setup & Installation

1. **Configure Environment Variables:**
   Copy `.env.example` to `.env` and fill in your details:
   ```env
   SLACK_BOT_TOKEN=xoxb-your-bot-token
   SLACK_APP_TOKEN=xapp-your-app-token
   GCP_PROJECT_ID=your-project-id
   GCP_PROJECT_NUMBER=your-project-number
   GOOGLE_DISCOVERY_LOCATION=global
   ENGINE_ID=your-engine-id
   GOOGLE_OAUTH_CLIENT_SECRETS_NAME=your-secret-manager-name (if using secrets)