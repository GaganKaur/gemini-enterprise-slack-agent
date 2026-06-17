# Gemini Enterprise Latency Benchmarking Harness

This folder contains a complete concurrent benchmarking suite designed to measure and validate Gemini Enterprise latency metrics (TTFT and TTLT) in your Google Cloud environment (**`corp-vertias-d`**).

It enables automated, head-to-head performance evaluations of:
1.  **Programmatic `streamAssist` REST API** (intent classifier bypass routing).
2.  **Web App UI Preview Chat** (automated headless browser interactions).

---

## 📋 1. Prerequisites & Environment Prep

Before running the benchmarks, complete these steps on your development workstation:

### A. Authenticate Google Cloud CLI (Matching Profile)
Ensure your active `gcloud` profile and Google Cloud credentials match the target GCP environment:
1. Check your currently active `gcloud` account and project:
   ```bash
   gcloud config list
   ```
2. If the active account or project does not match your target environment, switch them:
   ```bash
   gcloud config set account <your-corp-email>
   gcloud config set project corp-vertias-d
   ```
3. Authorize Google Application Default Credentials (ADC) for the Python client library:
   ```bash
   gcloud auth application-default login
   ```

> [!IMPORTANT]
> **Account Alignment Constraint**  
> The Google account authorized in your terminal must **exactly match** the account you use to log in to the Google Cloud Console (Vertex AI Search) in Chrome. Discrepancies between your CLI authentication and your browser session will lead to benchmark execution failures.

### B. Install Python & Dependency Manager (`uv`)
We use `uv` to automatically bootstrap isolated virtual environments and pin package dependencies:
```bash
# Install uv locally
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env
```

### C. Browser Environment (Chrome Profile Selection)
The UI benchmark runs locally by launching an interactive Chrome window.
1. **Interactive Login Mode (Default)**:  
   When you start the benchmark runner, it will automatically launch a new Chrome browser window and navigate to the Vertex AI Search console.
   * You **must** log in using the same account configured in Step A (`<your-corp-email>`).
   * If you have multiple Chrome profiles, ensure you are signing in to the profile associated with that email.
2. **CDP Option (Optional / Headless VMs)**:  
   If you are running the test harness on a remote VM, you can connect to an already active local Chrome session instead by launching Chrome with a remote debugging port (e.g., `9222`):
   ```bash
   # Start Chrome with remote debugging active (e.g. on macOS)
   /Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222
   ```
   *Note: `9222` is just an example port. You can choose any free port (e.g., `9333`) as long as you match it when passing `--cdp-url` to the benchmark runner script. Additionally, make sure you launch this debugging session under the Chrome profile containing your active Google Cloud Console credentials.*

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

Run the benchmark runner script using `uv` to trigger isolated execution:

```bash
# Navigate to the test_harness directory
cd tools/test_harness

# Option A: Execute in interactive mode (opens a browser window for login)
PYTHONPATH=src uv run python3 src/run_concurrent_benchmark.py --manifest=manifests/manifest_multi_query_template.json

# Option B: Execute connecting to an already running Chrome (on port 9222)
PYTHONPATH=src uv run python3 src/run_concurrent_benchmark.py \
  --manifest=manifests/manifest_multi_query_template.json \
  --cdp-url=http://localhost:9222
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
