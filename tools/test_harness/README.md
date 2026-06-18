# Gemini Enterprise Latency Benchmarking Harness

This folder contains a complete concurrent benchmarking suite designed to measure and validate Gemini Enterprise latency metrics (TTFT and TTLT) in your Google Cloud environment (**`corp-vertias-d`**).

It enables automated, head-to-head performance evaluations of:
1.  **Programmatic `streamAssist` REST API** (intent classifier bypass routing).
2.  **Web App UI Preview Chat** (automated headless browser interactions).

## 📊 Latency Benchmarking Architecture

To evaluate the RAG Search latency profiles across different data connector complexities (Single-Connector vs Multi-Connector Federated RAG), the test harness runs concurrent queries via two distinct pathways.

![Latency Benchmarking Architecture](architecture.png)

*(You can view or edit the source definition in the [Graphviz DOT Source](architecture.dot) file.)*

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

> [!WARNING]
> **No Pre-opened Browser Assumption**  
> Do **NOT** assume that a Chrome window is already open or authenticated with your target GCP account. You must explicitly verify that:
> 1. A Google Chrome window is active and visible on your desktop.
> 2. You are logged into the correct Google Cloud account in that browser profile.
> 3. If running in CDP mode (`--cdp-url`), Chrome must be explicitly running with remote debugging active and have the Vertex AI Search page open and authenticated.

The UI benchmark runs locally by launching an interactive Chrome window.
1. **Interactive Login Mode (Default)**:  
   When you start the benchmark runner, it will automatically launch a new Chrome browser window and navigate to the Google Cloud Console (Gen App Builder) sign-in page.
   * You **must** log in using the same account configured in Step A (`<your-corp-email>`).
   * If you have multiple Chrome profiles, ensure you are signing in to the profile associated with that email.
2. **CDP Option (Optional / Headless VMs)**:  
   If you are running the test harness on a remote VM, or need to target a specific authenticated Chrome profile (e.g. your corporate Argolis account) when multiple profiles exist, you can connect to an already active local Chrome session instead by launching Chrome with a remote debugging port and profile directory specified:
   
   **How to identify your Chrome Profile Directory**:
   1. Open the Google Chrome application.
   2. Switch to the correct Chrome Profile that is logged in to your target Google/Argolis account.
   3. In that specific profile's window, navigate to `chrome://version/`.
   4. Locate the **Profile Path** row. For example, you should see an output like this:
      ```text
      Google Chrome    149.0.7827.116 (Official Build) (arm64) 
      Revision         059c64964087769ae0661a8792d569c1cf46f636-refs/branch-heads/7827_102@{#41}
      OS               macOS Version 26.5.1 (Build 25F80)
      Profile Path     /Users/thomascummins/Library/Application Support/Google/Chrome/Profile 1
      ```
   5. The folder at the end of the path (e.g., `Profile 1`) is your profile directory name.
   
   **Launch Chrome on macOS with port and profile parameters**:
   ```bash
   # Start Chrome with remote debugging active and your chosen profile selected
   /Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222 --profile-directory="Profile 1"
   ```
   *Note: `9222` is just an example port. You can choose any free port (e.g., `7679`) as long as you match it when passing `--cdp-url` to the benchmark runner script.*

---

## 🛠️ 2. Configuration & Parameter Setup

The harness is configured using a JSON manifest file located at `manifests/manifest_multi_query_template.json`. Open this file and customize the target resource fields to match your environment:

```json
{
  "project_id": "corp-vertias-d",              // Your target Yahoo GCP Project
  "engine_id": "yahoo_1780365163254",          // Vertex AI Search Engine ID
  "iterations": 5,                            // Sample size per scenario (n=5)
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

To ensure the test harness is properly configured, execute the benchmark in two separate phases:

### Phase 1: Run the Environment Smoke Test
Before executing the full benchmark suite, run a single-iteration smoke test to verify your credentials, browser launching, and report rendering configuration.

1. Navigate to the test harness directory:
   ```bash
   cd tools/test_harness
   ```
2. Run the smoke test using your active environment folder (e.g., `yahoo_environment`):
   ```bash
   # NATIVE LOCAL RUN (Interactive Mode)
   PYTHONPATH=src uv run python3 src/run_concurrent_benchmark.py --manifest=manifests/yahoo_environment/verify_manifest.json

   # REMOTE VM RUN (CDP Mode - connects to your active browser window)
   PYTHONPATH=src uv run python3 src/run_concurrent_benchmark.py \
     --manifest=manifests/yahoo_environment/verify_manifest.json \
     --cdp-url=http://localhost:9222
   ```

#### 🛡️ Expected Smoke Test Results:
* **Terminal output**:
  ```text
  Loading configuration manifest: manifests/yahoo_environment/verify_manifest.json
  Initialized local execution folder: runs/run_20260617_185229_verify
  Resolving credentials...
  Initializing Playwright browser context...
  Authentication successful! Detected Configuration ID: c33a03fe-9fbc-4ce7-ad44-85195fbe5625
  Scheduling concurrent runs for scenario: Q1. GDrive - PTO Rollover (Stream)...
  Scheduling concurrent runs for scenario: Q1. GDrive - PTO Rollover (UI)...
  Generated unified latency comparison chart at: runs/run_20260617_185229_verify/charts/combined_latency_comparison.png
  All runs artifacts written successfully to: runs/run_20260617_185229_verify
  ```
* **Generated Assets**:
  A timestamped folder `runs/run_<timestamp>_verify/` containing:
  - `report.md`: Master Markdown report summary.
  - `results.json`: Raw execution metrics and API details.
  - `charts/`: Comparative grouped bar charts and bin-distribution graphs.
  - `screenshots/`: Snapshots of the browser UI interactions during execution.

---

### Phase 2: Run the Full Latency Audit
Once the smoke test completes successfully, you are ready to kick off the full benchmarking execution.

1. Execute the full audit manifest:
   ```bash
   # NATIVE LOCAL RUN (Interactive Mode)
   PYTHONPATH=src uv run python3 src/run_concurrent_benchmark.py --manifest=manifests/yahoo_environment/manifest_multi_query.json

   # REMOTE VM RUN (CDP Mode)
   PYTHONPATH=src uv run python3 src/run_concurrent_benchmark.py \
     --manifest=manifests/yahoo_environment/manifest_multi_query.json \
     --cdp-url=http://localhost:9222
   ```
2. This runs **5 iterations** across **9 unique scenarios** for both REST API and Web UI (90 total requests). It may take 10 to 15 minutes to complete depending on network conditions.
3. The results will be aggregated inside a master report at `runs/run_<timestamp>_002/report.md`.

---

## ❓ 4. FAQs & Troubleshooting

### Q1: I get `browser_type.launch: Display not found. Are you running in a headless environment?`
* **Why this happens**: You are running the benchmark on a remote Linux server/VM (e.g. Cloudtop) which lacks a physical monitor display, but the script is attempting to launch a headful GUI Chrome window.
* **How to fix**: 
  - **Local machine execution**: Run the script natively on your macOS/Windows laptop.
  - **CDP mode fallback**: Start Chrome on your machine with remote debugging active, forward that port to the VM, and append the `--cdp-url` argument to your run command.

### Q2: The script hangs or fails with `ERROR: Authentication timed out or Configuration ID not detected`
* **Why this happens**: The interactive browser window popped up, but login was not completed within the 60-second window, or the browser profile did not match your terminal's `gcloud` context.
* **How to fix**:
  1. Verify your CLI configuration by running `gcloud config list` and `gcloud auth list`. Ensure the active account matches the email profile you use in the browser.
  2. Start the script again, and immediately log in to the Vertex AI console once the Chrome tab opens.

### Q3: I get `ModuleNotFoundError: No module named 'src'`
* **Why this happens**: Python cannot resolve the path to the internal imports inside the `src/` directory.
* **How to fix**: Ensure you prepended `PYTHONPATH=src` to the command line, and that you are executing the command from the `tools/test_harness` root directory.

### Q4: Scenario tasks fail with `PermissionDenied` or `403` status codes
* **Why this happens**: Your Google account lacks access rights to the Vertex AI Search engine, or the IDs configured in your manifest do not exist.
* **How to fix**:
  1. Open the Vertex AI Search console in Chrome and check that you can query the datastores manually.
  2. Verify that `project_id`, `engine_id`, and `sub_agent_id` configured in your manifest folder (e.g., `yahoo_environment/manifest_multi_query.json`) match the values shown in the console URL.

---

## 📊 5. Interpreting Output Reports

All results, logs, chart distributions, and visual validation snapshots are written to a unique timestamped folder under `runs/run_<timestamp>/`:

### A. The Master Markdown Report (`report.md`)
This report aggregates the benchmark run details:
*   **Run Execution Metadata**: Displays active execution parameters:
    *   **Concurrency Limit**: Total number of simultaneous workers.
    *   **Total Duration**: Wall-clock execution time.
    *   **Average Throughput**: Total queries divided by duration, representing average queries per minute (QPM) submitted to the API.
*   **Query Complexity Profiling**: Each test scenario is tagged with a Complexity Level:
    *   *Level 1*: Intrinsic Knowledge / Grounding Bypassed (e.g. hello, greetings).
    *   *Level 2*: Single-Connector RAG (searching a single index).
    *   *Level 3*: Multi-Connector Federated RAG (searching 2–3 active indexes).
    *   *Level 4*: Custom Agent Tooling / Reasoning (orchestrator routing).
*   **Unified Latency Comparison Chart**: Grouped bar chart comparing TTFT and TTLT (with error range bars) for all scenarios.
*   **Performance Scale Tables**: Displays detailed lists of status codes, TTFT, TTLT, characters per second, and Google Cloud Console Trace Links for every run.

### B. Standard Metrics Focus
Following Google's internal latency playbook guidelines, performance validation is analyzed using **Percentile Distributions (P50, P90, P95, P99)** rather than raw averages:
*   **P50 (Median)**: Represents typical user experience.
*   **P90 / P95 (General Trend)**: Standard benchmark metrics for identifying general latency trends while ignoring network spikes.
*   **P99 (Worst Case)**: Identifies tail latency, slow cold starts, and rare freezes.
*   **Min / Max / Avg**: Included as fallback boundaries to highlight raw scaling limits.

---

## 📂 6. Folder Directory Map
*   `src/run_concurrent_benchmark.py`: Main concurrent worker harness script.
*   `src/browser_controller.py`: Playwright POM controller encapsulating shadow DOM page logic.
*   `src/chart_generator.py`: Plotting utility generating latency bar charts and distribution timelines.
*   `manifests/`: Configuration JSON files mapping connected data connector test cases.
*   `docs/multi_query_audit_reference.md`: A reference output report compiling baseline metrics.
