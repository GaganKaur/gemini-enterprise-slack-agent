# Gemini Enterprise Latency Benchmarking Harness

This folder contains a complete concurrent benchmarking suite designed to measure and validate Gemini Enterprise latency metrics (TTFT and TTLT) in your Google Cloud environment (**`corp-vertias-d`**).

It enables automated, head-to-head performance evaluations of:
1.  **Programmatic `streamAssist` REST API** (intent classifier bypass routing).
2.  **Web App UI Preview Chat** (automated headless browser interactions).

---

## 📋 1. Prerequisites & Environment Prep

Before running the benchmarks, complete these steps on your development workstation:

### A. Authenticate Google Cloud CLI
Ensure you have authorized ambient credentials to make authenticated API requests to your GCP project:
```bash
gcloud auth login
gcloud auth application-default login
```

### B. Install Python & Dependency Manager (`uv`)
We use `uv` to automatically bootstrap isolated virtual environments and pin package dependencies:
```bash
# Install uv locally
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env
```

### C. Launch Chrome with Remote Debugging Active
The Web App UI test requires a running Chrome browser context with remote debugging activated on port `9222`:
```bash
# gLinux / Linux
google-chrome --remote-debugging-port=9222
```

---

## 🛠️ 2. Configuration & Parameter Setup

The harness is configured using a JSON manifest file located at `manifests/manifest_multi_query_template.json`. Open this file and customize the target resource fields to match your environment:

```json
{
  "project_id": "corp-vertias-d",              // Your target Yahoo GCP Project
  "customer_id": "c33a03fe-9fbc-4ce7-ad44-85195fbe5625", // Your Customer ID
  "engine_id": "yahoo_1780365163254",          // Vertex AI Search Engine ID
  "iterations": 10,                            // Sample size per scenario (n=10)
  "concurrency_limit": 3,                      // Max concurrent workers
  "queries": [
    {
      "id": "Q1",
      "text": "what is the company PTO policy?",
      "sub_agent_id": "14356008107232711696"   // Your custom sub-agent ID
    }
  ]
}
```

---

## 🚀 3. Executing the Test Harness

Run the benchmark runner script using `uv` to run isolated execution with all dependencies loaded:

```bash
# Navigate to the test_harness directory
cd tools/test_harness

# Execute the concurrent benchmark
PYTHONPATH=src uv run python3 src/run_concurrent_benchmark.py --manifest=manifests/manifest_multi_query_template.json
```

---

## 📊 4. Interpreting Output Reports

All results, logs, chart distributions, and visual validation snapshots are written to a unique timestamped folder under `runs/run_<timestamp>/`:

### A. The Master Markdown Report (`report.md`)
This report aggregates the benchmark run details:
*   **Unified Latency Comparison Chart**: Grouped bar chart comparing TTFT and TTLT (with error range bars) for all scenarios.
*   **Performance Scale Tables**: Displays detailed lists of status codes, TTFT, TTLT, characters per second, and Google Cloud Console Trace Links for every run.

### B. Standard Metrics Focus
Following Google's internal latency playbook guidelines, performance validation is analyzed using **Percentile Distributions (P50, P90, P95, P99)** rather than raw averages:
*   **P50 (Median)**: Represents typical user experience.
*   **P95 (General Trend)**: Standard benchmark metric for identifying general latency trends while ignoring network spikes.
*   **P99 (Worst Case)**: Identifies tail latency and rare freezes.

---

## 📂 5. Folder Directory Map
*   `src/run_concurrent_benchmark.py`: Main concurrent worker harness script.
*   `src/browser_controller.py`: Playwright POM controller encapsulating shadow DOM page logic.
*   `src/chart_generator.py`: Plotting utility generating latency bar charts and distribution timelines.
*   `manifests/`: Configuration JSON files mapping connected data connector test cases.
*   `docs/multi_query_audit_reference.md`: A reference output report compiling baseline metrics.
