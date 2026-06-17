# Reflective Handoff: Test Harness Simplification & Local Execution

This document serves as the context transfer file for the local Jetski IDE agent running on your MacBook to resume and complete the simplification of the Yahoo Gemini Enterprise Latency Test Harness.

---

## 1. Current Context & Objectives

*   **Repository Location**: `tools/gemini-enterprise-slack-agent/tools/test_harness`
*   **Active Git Branch**: `feat/test-harness`
*   **Target Objective**: Modify the test harness to run completely locally on a developer machine (Mac/Linux/Windows) without complex remote port-forwarding configurations or pre-running Chrome with CDP flags.

---

## 2. Working Directory Structure & Key Files

All relevant code and configurations have been consolidated inside `tools/test_harness/`:
1.  **[src/run_concurrent_benchmark.py](file:///usr/local/google/home/thomascummins/Dev/projects/engagements/yahoo/tools/gemini-enterprise-slack-agent/tools/test_harness/src/run_concurrent_benchmark.py)**: The main test runner script. Authenticates API calls via Google Application Default Credentials (ADC) and coordinates concurrent runs (Sync API, Stream API, and Browser UI).
2.  **[src/browser_controller.py](file:///usr/local/google/home/thomascummins/Dev/projects/engagements/yahoo/tools/gemini-enterprise-slack-agent/tools/test_harness/src/browser_controller.py)**: Playwright page controller that automates query inputs into the ProseMirror editor and extracts TTFT/TTLT metrics.
3.  **[src/chart_generator.py](file:///usr/local/google/home/thomascummins/Dev/projects/engagements/yahoo/tools/gemini-enterprise-slack-agent/tools/test_harness/src/chart_generator.py)**: Script that reads execution `results.json` and renders Matplotlib charts.
4.  **[manifests/thomas_test_environment/verify_manifest.json](file:///usr/local/google/home/thomascummins/Dev/projects/engagements/yahoo/tools/gemini-enterprise-slack-agent/tools/test_harness/manifests/thomas_test_environment/verify_manifest.json)**: Minimal manifest for smoke testing in Thomas's environment.
5.  **[README.md](file:///usr/local/google/home/thomascummins/Dev/projects/engagements/yahoo/tools/gemini-enterprise-slack-agent/tools/test_harness/README.md)**: Setup and guide for running the harness.

---

## 3. The Implementation Plan (Next Steps for the Local Agent)

The local agent should implement the approved [test_harness_simplification_plan.md](file:///usr/local/google/home/thomascummins/.gemini/jetski/brain/53ba961d-8367-4e6d-9405-732264857432/test_harness_simplification_plan.md):

### Step 1: Implement Interactive Browser Authentication in `src/run_concurrent_benchmark.py`
Modify `main_async` to:
- Accept an optional `--cdp-url` CLI flag.
- **If `--cdp-url` is omitted**:
  1. Launch a fresh local browser instance:
     ```python
     browser = await p.chromium.launch(headless=False, channel="chrome")
     context = await browser.new_context()
     page = await context.new_page()
     ```
  2. Navigate to `https://vertexaisearch.cloud.google.com/home`.
  3. Prompt the user: `"Please log in to the Vertex AI Search console in the opened browser window..."`.
  4. Poll `page.url` for up to 120 seconds to extract the Customer ID (`cid`) matching `/home/cid/([^/?#]+)`.
  5. Once the `cid` is matched, proceed with the UI tests inside the same context.
- **If `--cdp-url` is provided**: Keep existing CDP connection logic.

### Step 2: Simplify Python API Scopes
In `get_credentials()`, remove the redundant drive scope:
```python
def get_credentials():
    credentials, project = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
```
This aligns authentication with standard developer ADC configuration.

### Step 3: Update and Simplify README.md
- Document the new local interactive flow.
- Clarify that no port-forwarding is required when running both Python and Chrome on the local machine.
- Provide simple `uv run` commands.

### Step 4: Verification
Verify local execution by running:
```bash
PYTHONPATH=src uv run python3 src/run_concurrent_benchmark.py --manifest=manifests/thomas_test_environment/verify_manifest.json
```
Ensure that the browser opens, waits for authentication, and correctly executes the suite.
