### Scenario: {scenario_name}
*   **Complexity Level:** {complexity_level}

#### Percentile Latency Distribution
This table aggregates the percentile scaling metrics (P50, P90, P95, P99) across all successful runs:

| Model | Pathway | Metric | Min | P50 (Median) | P95 | Max |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Gemini 3.5 Flash** | **Programmatic API (Stream)** | **TTFT** | {f_api_ttft_min} | {f_api_ttft_p50} | {f_api_ttft_p95} | {f_api_ttft_max} |
| | | **TTLT** | {f_api_ttlt_min} | {f_api_ttlt_p50} | {f_api_ttlt_p95} | {f_api_ttlt_max} |
| | **Web App UI (Preview)** | **TTFT** | {f_ui_ttft_min} | {f_ui_ttft_p50} | {f_ui_ttft_p95} | {f_ui_ttft_max} |
| | | **TTLT** | {f_ui_ttlt_min} | {f_ui_ttlt_p50} | {f_ui_ttlt_p95} | {f_ui_ttlt_max} |
| **Gemini 3.1 Pro** | **Programmatic API (Stream)** | **TTFT** | {p_api_ttft_min} | {p_api_ttft_p50} | {p_api_ttft_p95} | {p_api_ttft_max} |
| | | **TTLT** | {p_api_ttlt_min} | {p_api_ttlt_p50} | {p_api_ttlt_p95} | {p_api_ttlt_max} |
| | **Web App UI (Preview)** | **TTFT** | {p_ui_ttft_min} | {p_ui_ttft_p50} | {p_ui_ttft_p95} | {p_ui_ttft_max} |
| | | **TTLT** | {p_ui_ttlt_min} | {p_ui_ttlt_p50} | {p_ui_ttlt_p95} | {p_ui_ttlt_max} |

#### Detailed Invocations & Diagnostics

> **💡 TIP: Trace Lookup Guide:** To review any API trace, copy the **Trace ID**, open the [GCP Trace Explorer](https://console.cloud.google.com/traces/explorer?project={project_id}), click the **`Trace ID`** button in the top-right toolbar, paste the Trace ID, and press Enter.

| Run ID | Model | Pathway | status_code | TTFT (s) | TTLT (s) | Speed (char/s) | Trace ID / Screenshot | Span ID |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
{run_rows}

---
