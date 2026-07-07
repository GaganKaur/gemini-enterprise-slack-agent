# {report_title}
Executed at: `{timestamp}` | Model: **{model_used}** | using manifest: [{manifest_rel}]({manifest_rel})

## 📋 Test Protocol
This test run follows the standardized benchmarking execution methodology defined in the [README.md]({readme_rel}) guide.

### 📂 Run Directory Structure & Provenance Data
Each benchmarking execution generates a self-contained, idempotent run directory containing all raw metrics, visualizations, and configuration archives:
```text
{run_dir}/
├── report.md                  # This master evaluation report
├── results.json               # Raw JSON metrics and HTTP headers
├── {manifest_filename}        # Archived copy of the exact manifest config used
├── charts/                    # Generated latency comparison & distribution charts
│   ├── combined_latency_comparison.png
│   └── ...
└── screenshots/               # Playwright full-screen visual captures
    └── ...
```

### 📊 Query Complexity Levels
Each benchmarking scenario is profile-tagged using a standardized complexity scale to evaluate how latency scales across different RAG structures:
*   **Level 1: Intrinsic Knowledge / Grounding Bypassed:** Queries answered directly from the model's parametric weights, completely bypassing search connectors (e.g., greetings, general assistance).
*   **Level 2: Single-Connector RAG:** Standard RAG search querying a single connected index (e.g., searching only Google Drive, only Confluence, or only a GCS bucket).
*   **Level 3: Multi-Connector Federated RAG:** Highly complex federated queries requiring parallel searches across multiple distinct connectors (e.g., searching Drive + Confluence, or a 3-way federated search across Drive + Confluence + Jira).
*   **Level 4: Custom Agent Tooling / Reasoning:** Queries requiring multi-turn agentic reasoning, intent routing, or custom programmatic tool execution (e.g., routing to a specialized database sub-agent).

### 🔗 Trace Links vs. UI Screenshots
To ensure a clear understanding of the diagnostics provided for each run:
*   **REST API Traces (Programmatic Pathway):** Programmatic invocations via the `streamAssist` or `assist` endpoints are interceptable by the test harness. We inject a unique `x-cloud-trace-context` header into each request, enabling direct, clickable links to the **Google Cloud Trace console** for deep server-side retrieval and generation timeline analysis.
*   **Web App UI Screenshots (Browser Pathway):** Browser-level preview chat is automated via headless Playwright sessions. Since these run on Google Cloud Console's hosted pages, we cannot programmatically inject trace headers or extract server-side trace IDs. Therefore, Trace Links are not available (`N/A`) for UI tests. Instead, we capture full-screen **visual screenshots** at key interaction points to validate rendering correctness and capture client-side network state.

---

## 📊 Results

### 📈 High-Level Latency Summary
The table below aggregates the average latency metrics across all successful scenarios for both pathways:

| Pathway | Average TTFT (Time to First Token) | Average TTLT (Time to Last Token) |
| :--- | :--- | :--- |
| **Programmatic API (streamAssist)** | {avg_api_ttft} | {avg_api_ttlt} |
| **Web App UI (Preview Chat)** | {avg_ui_ttft} | {avg_ui_ttlt} |

### 🗺️ Unified Latency Comparison
The chart below compares the TTFT and TTLT profiles across all tested query fixtures:

![Unified Latency Comparison]({chart_path})
*(View high-resolution chart in [charts/combined_latency_comparison.png]({chart_path}))*

---

## 🔍 Detailed Scenario Evaluations & Diagnostics
{scenarios_section}

{screenshots_section}

---

## 📁 Additional Test Data

### ⚙️ Run Execution Metadata
*   **Model Used**: `{model_used}`
*   **Concurrency Limit**: `{max_concurrency}` simultaneous workers
*   **Total Duration**: `{total_duration_s:.1f} seconds` ({duration_minutes:.2f} minutes)
*   **Average Throughput**: `{throughput_qpm:.2f} queries per minute` (Volume tracking)
