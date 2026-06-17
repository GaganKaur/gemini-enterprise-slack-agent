# Performance & Latency Audit Report: Gemini Enterprise UAT Ingestion

**Document Owner**: Thomas Cummins (`thomascummins@google.com`)  
**Executed At**: `2026-06-17T17:33:19Z`  
**Run Reference**: [run_20260617_165559_002](file:///usr/local/google/home/thomascummins/Dev/projects/engagements/yahoo/reproduction_kit/runs/run_20260617_165559_002)  
**Status**: COMPLETE (n=10, 180 total runs)

---

## 1. Executive Summary
This performance audit evaluates latency metrics comparing the **`streamAssist` REST API** (via intent classifier bypass routing) against the **Web App UI Preview Chat** inside the Vertex AI Search & Conversation console. 

### Key Findings:
1. **Programmatic Speedup**: Bypassing the frontend console yields massive startup efficiency. The `streamAssist` API is **2.2x to 5.8x faster** than the Web UI at returning the first token (TTFT).
2. **Connector Overhead Scaling**: Adding data connectors increases overall RAG latency (TTLT) linearly. Average stream TTLT starts at **~20.1s** for single connectors, scales to **~30.6s** for two, and reaches **~40.2s** for three active connectors.
3. **UI Overhead Penalty**: Web UI preview page loads introduce heavy browser rendering and session initialization overhead, causing high startup (TTFT) variations (ranging from 16.9s up to 45.5s).

---

## 2. Test Objectives & Scope
The objective is to establish baseline latencies for the Yahoo Gemini Enterprise (GE) integration, identifying performance bottlenecks as data ingestion scales across multiple connected enterprise sources.

*   **Metric 1**: Time to First Token (TTFT) — Measures interactive response responsiveness.
*   **Metric 2**: Time to Last Token (TTLT) — Measures total document generation latency.
*   **Scale Range**: 1 to 3 active data connectors (Google Drive, Confluence, Jira, Mock LumApps GCS).

---

## 3. Test Configuration & Environment
The audit was executed programmatically inside a headless Chromium session connecting over CDP to the active corporate profile:

*   **Customer ID (CID)**: `c33a03fe-9fbc-4ce7-ad44-85195fbe5625`
*   **Target GCP Project**: `genai-alpha-422116`
*   **Target API Endpoint**: `/v1alpha/`
*   **Classifier Skip Mode**: `"assistSkippingMode": "REQUEST_ASSIST"`
*   **Orchestration Route**: `agentsSpec.agentSpecs[0].agentId = "core_assistant"`
*   **Benchmark Concurrency**: `3` simultaneous execution workers.
*   **Sample Size (n)**: `10` consecutive iterations per scenario (180 runs total).

---

## 4. Workload / Test Cases Specification
The benchmark suite executes 9 test scenarios mapping to different connector layouts:

| Query ID | Target Connectors | Active | Test Query String |
| :--- | :--- | :---: | :--- |
| **Q1** | Google Drive | 1 | "what is the company PTO policy?" |
| **Q2** | Confluence | 1 | "how do I configure my corporate VPN on gLinux?" |
| **Q3** | Jira | 1 | "what is the status of my broken keyboard replacement ticket?" |
| **Q4** | LumApps GCS Bucket | 1 | "what is the rollout timeline for the new corporate portal?" |
| **Q5** | Confluence + Jira | 2 | "what is the current status of corporate VPN issues?" |
| **Q6** | Google Drive + Confluence | 2 | "what is the laptop upgrade cycle policy?" |
| **Q7** | LumApps GCS + Jira | 2 | "what tools do I need for my developer workspace?" |
| **Q8** | GDrive + Conf + Jira | 3 | "what is the company policy for remote work and workspace setup?" |
| **Q9** | LumApps + Conf + Jira | 3 | "what is the 3-way checklist for onboarding IT tools?" |

---

## 5. Unified Benchmarking Results

### 📊 Performance Scale Matrix (n=10)
Averages and key percentiles computed over 10 consecutive successful runs (seconds).

| Scenario / Query ID | Connectors | Complexity Level | API Used | P50 TTFT (s) | P90 TTFT (s) | P95 TTFT (s) | P99 TTFT (s) | P50 TTLT (s) | P90 TTLT (s) | P95 TTLT (s) | P99 TTLT (s) | Success Rate |
| :--- | :---: | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Q1. GDrive - PTO Rollover (Stream)** | 1 | Level 2: Single-Connector RAG | streamAssist API | 8.155 | 9.511 | 9.511 | 9.511 | 18.929 | 28.203 | 28.203 | 28.203 | 100.0% |
| **Q1. GDrive - PTO Rollover (UI)** | 1 | Level 2: Single-Connector RAG | Web App UI | 19.530 | 39.172 | 39.172 | 39.172 | 20.568 | 40.768 | 40.768 | 40.768 | 100.0% |
| **Q2. Confluence - VPN Configuration (Stream)** | 1 | Level 2: Single-Connector RAG | streamAssist API | 7.495 | 10.123 | 10.123 | 10.123 | 22.921 | 32.110 | 32.110 | 32.110 | 100.0% |
| **Q2. Confluence - VPN Configuration (UI)** | 1 | Level 2: Single-Connector RAG | Web App UI | 23.051 | 31.132 | 31.132 | 31.132 | 24.349 | 33.148 | 33.148 | 33.148 | 100.0% |
| **Q3. Jira - Broken Keyboard Status (Stream)** | 1 | Level 2: Single-Connector RAG | streamAssist API | 7.709 | 10.301 | 10.301 | 10.301 | 17.765 | 26.064 | 26.064 | 26.064 | 100.0% |
| **Q3. Jira - Broken Keyboard Status (UI)** | 1 | Level 2: Single-Connector RAG | Web App UI | 16.099 | 25.244 | 25.244 | 25.244 | 18.139 | 26.323 | 26.323 | 26.323 | 100.0% |
| **Q4. LumApps GCS - Rollout Latency (Stream)** | 1 | Level 2: Single-Connector RAG | streamAssist API | 8.235 | 13.587 | 13.587 | 13.587 | 19.676 | 23.099 | 23.099 | 23.099 | 100.0% |
| **Q4. LumApps GCS - Rollout Latency (UI)** | 1 | Level 2: Single-Connector RAG | Web App UI | 20.949 | 26.372 | 26.372 | 26.372 | 23.921 | 27.267 | 27.267 | 27.267 | 100.0% |
| **Q5. Confluence + Jira - VPN Issues (Stream)** | 2 | Level 3: Multi-Connector Federated RAG (2 Connectors) | streamAssist API | 7.773 | 10.882 | 10.882 | 10.882 | 28.116 | 34.404 | 34.404 | 34.404 | 100.0% |
| **Q5. Confluence + Jira - VPN Issues (UI)** | 2 | Level 3: Multi-Connector Federated RAG (2 Connectors) | Web App UI | 26.718 | 42.026 | 42.026 | 42.026 | 28.674 | 43.673 | 43.673 | 43.673 | 100.0% |
| **Q6. GDrive + Confluence - Laptop Upgrade Cycle (Stream)** | 2 | Level 3: Multi-Connector Federated RAG (2 Connectors) | streamAssist API | 7.747 | 14.291 | 14.291 | 14.291 | 33.738 | 60.360 | 60.360 | 60.360 | 100.0% |
| **Q6. GDrive + Confluence - Laptop Upgrade Cycle (UI)** | 2 | Level 3: Multi-Connector Federated RAG (2 Connectors) | Web App UI | 27.888 | 41.379 | 41.379 | 41.379 | 28.669 | 42.553 | 42.553 | 42.553 | 100.0% |
| **Q7. LumApps + Jira - Dev Workspace Tools (Stream)** | 2 | Level 3: Multi-Connector Federated RAG (2 Connectors) | streamAssist API | 7.760 | 8.571 | 8.571 | 8.571 | 25.047 | 46.074 | 46.074 | 46.074 | 100.0% |
| **Q7. LumApps + Jira - Dev Workspace Tools (UI)** | 2 | Level 3: Multi-Connector Federated RAG (2 Connectors) | Web App UI | 23.404 | 24.413 | 24.413 | 24.413 | 24.667 | 25.604 | 25.604 | 25.604 | 100.0% |
| **Q8. GDrive + Confluence + Jira - Remote Work (Stream)** | 3 | Level 3: Multi-Connector Federated RAG (3 Connectors) | streamAssist API | 7.812 | 11.914 | 11.914 | 11.914 | 36.965 | 53.627 | 53.627 | 53.627 | 100.0% |
| **Q8. GDrive + Confluence + Jira - Remote Work (UI)** | 3 | Level 3: Multi-Connector Federated RAG (3 Connectors) | Web App UI | 41.362 | 83.984 | 83.984 | 83.984 | 52.204 | 86.990 | 86.990 | 86.990 | 90.0% |
| **Q9. 3-Way IT Checklist (Stream)** | 3 | Level 3: Multi-Connector Federated RAG (3 Connectors) | streamAssist API | 7.705 | 10.958 | 10.958 | 10.958 | 30.684 | 159.801 | 159.801 | 159.801 | 100.0% |
| **Q9. 3-Way IT Checklist (UI)** | 3 | Level 3: Multi-Connector Federated RAG (3 Connectors) | Web App UI | 30.533 | 47.632 | 47.632 | 47.632 | 37.049 | 48.902 | 48.902 | 48.902 | 100.0% |

### 📈 Unified Latency Comparison (P50 vs. P90 TTLT)
![Unified Latency Comparison](assets/run_002_multi_query/charts/combined_latency_comparison.png)

### 📈 Latency Overhead Scaling Summary
![Latency Scaling Across Connectors](assets/latency_scaling.png)
_source: [latency_scaling.dot](assets/latency_scaling.dot) | [latency_scaling.png](assets/latency_scaling.png)_

## 6. Detailed Performance Timelines & Analysis

### Query Scenario: Q1

#### **streamAssist API** - `Q1. GDrive - PTO Rollover (Stream)`
*   **Complexity Profile**: `Level 2: Single-Connector RAG`
*   **Success Rate**: `100.0%`
*   **TTFT (P50/P90/P95/P99)**: 8.155 s / 9.511 s / 9.511 s / 9.511 s (Min: 6.001 s, Max: 9.511 s, Avg: 7.964 s)
*   **TTLT (P50/P90/P95/P99)**: 18.929 s / 28.203 s / 28.203 s / 28.203 s (Min: 16.265 s, Max: 28.203 s, Avg: 19.303 s)

##### Telemetry Charts:
![Runs Telemetry](assets/run_002_multi_query/charts/q1_gdrive_pto_rollover_stream_runs.png)
![Histogram Telemetry](assets/run_002_multi_query/charts/q1_gdrive_pto_rollover_stream_histogram.png)

#### **Web App UI** - `Q1. GDrive - PTO Rollover (UI)`
*   **Complexity Profile**: `Level 2: Single-Connector RAG`
*   **Success Rate**: `100.0%`
*   **TTFT (P50/P90/P95/P99)**: 19.530 s / 39.172 s / 39.172 s / 39.172 s (Min: 17.373 s, Max: 39.172 s, Avg: 23.769 s)
*   **TTLT (P50/P90/P95/P99)**: 20.568 s / 40.768 s / 40.768 s / 40.768 s (Min: 17.977 s, Max: 40.768 s, Avg: 24.560 s)

##### Telemetry Charts:
![Runs Telemetry](assets/run_002_multi_query/charts/q1_gdrive_pto_rollover_ui_runs.png)
![Histogram Telemetry](assets/run_002_multi_query/charts/q1_gdrive_pto_rollover_ui_histogram.png)

---

### Query Scenario: Q2

#### **streamAssist API** - `Q2. Confluence - VPN Configuration (Stream)`
*   **Complexity Profile**: `Level 2: Single-Connector RAG`
*   **Success Rate**: `100.0%`
*   **TTFT (P50/P90/P95/P99)**: 7.495 s / 10.123 s / 10.123 s / 10.123 s (Min: 6.813 s, Max: 10.123 s, Avg: 7.838 s)
*   **TTLT (P50/P90/P95/P99)**: 22.921 s / 32.110 s / 32.110 s / 32.110 s (Min: 18.885 s, Max: 32.110 s, Avg: 23.802 s)

##### Telemetry Charts:
![Runs Telemetry](assets/run_002_multi_query/charts/q2_confluence_vpn_configuration_stream_runs.png)
![Histogram Telemetry](assets/run_002_multi_query/charts/q2_confluence_vpn_configuration_stream_histogram.png)

#### **Web App UI** - `Q2. Confluence - VPN Configuration (UI)`
*   **Complexity Profile**: `Level 2: Single-Connector RAG`
*   **Success Rate**: `100.0%`
*   **TTFT (P50/P90/P95/P99)**: 23.051 s / 31.132 s / 31.132 s / 31.132 s (Min: 20.214 s, Max: 31.132 s, Avg: 24.635 s)
*   **TTLT (P50/P90/P95/P99)**: 24.349 s / 33.148 s / 33.148 s / 33.148 s (Min: 21.535 s, Max: 33.148 s, Avg: 26.192 s)

##### Telemetry Charts:
![Runs Telemetry](assets/run_002_multi_query/charts/q2_confluence_vpn_configuration_ui_runs.png)
![Histogram Telemetry](assets/run_002_multi_query/charts/q2_confluence_vpn_configuration_ui_histogram.png)

---

### Query Scenario: Q3

#### **streamAssist API** - `Q3. Jira - Broken Keyboard Status (Stream)`
*   **Complexity Profile**: `Level 2: Single-Connector RAG`
*   **Success Rate**: `100.0%`
*   **TTFT (P50/P90/P95/P99)**: 7.709 s / 10.301 s / 10.301 s / 10.301 s (Min: 6.019 s, Max: 10.301 s, Avg: 7.711 s)
*   **TTLT (P50/P90/P95/P99)**: 17.765 s / 26.064 s / 26.064 s / 26.064 s (Min: 13.007 s, Max: 26.064 s, Avg: 18.045 s)

##### Telemetry Charts:
![Runs Telemetry](assets/run_002_multi_query/charts/q3_jira_broken_keyboard_status_stream_runs.png)
![Histogram Telemetry](assets/run_002_multi_query/charts/q3_jira_broken_keyboard_status_stream_histogram.png)

#### **Web App UI** - `Q3. Jira - Broken Keyboard Status (UI)`
*   **Complexity Profile**: `Level 2: Single-Connector RAG`
*   **Success Rate**: `100.0%`
*   **TTFT (P50/P90/P95/P99)**: 16.099 s / 25.244 s / 25.244 s / 25.244 s (Min: 13.128 s, Max: 25.244 s, Avg: 16.975 s)
*   **TTLT (P50/P90/P95/P99)**: 18.139 s / 26.323 s / 26.323 s / 26.323 s (Min: 14.387 s, Max: 26.323 s, Avg: 18.484 s)

##### Telemetry Charts:
![Runs Telemetry](assets/run_002_multi_query/charts/q3_jira_broken_keyboard_status_ui_runs.png)
![Histogram Telemetry](assets/run_002_multi_query/charts/q3_jira_broken_keyboard_status_ui_histogram.png)

---

### Query Scenario: Q4

#### **streamAssist API** - `Q4. LumApps GCS - Rollout Latency (Stream)`
*   **Complexity Profile**: `Level 2: Single-Connector RAG`
*   **Success Rate**: `100.0%`
*   **TTFT (P50/P90/P95/P99)**: 8.235 s / 13.587 s / 13.587 s / 13.587 s (Min: 6.213 s, Max: 13.587 s, Avg: 8.324 s)
*   **TTLT (P50/P90/P95/P99)**: 19.676 s / 23.099 s / 23.099 s / 23.099 s (Min: 16.482 s, Max: 23.099 s, Avg: 19.371 s)

##### Telemetry Charts:
![Runs Telemetry](assets/run_002_multi_query/charts/q4_lumapps_gcs_rollout_latency_stream_runs.png)
![Histogram Telemetry](assets/run_002_multi_query/charts/q4_lumapps_gcs_rollout_latency_stream_histogram.png)

#### **Web App UI** - `Q4. LumApps GCS - Rollout Latency (UI)`
*   **Complexity Profile**: `Level 2: Single-Connector RAG`
*   **Success Rate**: `100.0%`
*   **TTFT (P50/P90/P95/P99)**: 20.949 s / 26.372 s / 26.372 s / 26.372 s (Min: 17.306 s, Max: 26.372 s, Avg: 21.459 s)
*   **TTLT (P50/P90/P95/P99)**: 23.921 s / 27.267 s / 27.267 s / 27.267 s (Min: 19.131 s, Max: 27.267 s, Avg: 23.108 s)

##### Telemetry Charts:
![Runs Telemetry](assets/run_002_multi_query/charts/q4_lumapps_gcs_rollout_latency_ui_runs.png)
![Histogram Telemetry](assets/run_002_multi_query/charts/q4_lumapps_gcs_rollout_latency_ui_histogram.png)

---

### Query Scenario: Q5

#### **streamAssist API** - `Q5. Confluence + Jira - VPN Issues (Stream)`
*   **Complexity Profile**: `Level 3: Multi-Connector Federated RAG (2 Connectors)`
*   **Success Rate**: `100.0%`
*   **TTFT (P50/P90/P95/P99)**: 7.773 s / 10.882 s / 10.882 s / 10.882 s (Min: 5.661 s, Max: 10.882 s, Avg: 7.854 s)
*   **TTLT (P50/P90/P95/P99)**: 28.116 s / 34.404 s / 34.404 s / 34.404 s (Min: 21.019 s, Max: 34.404 s, Avg: 28.831 s)

##### Telemetry Charts:
![Runs Telemetry](assets/run_002_multi_query/charts/q5_confluence_jira_vpn_issues_stream_runs.png)
![Histogram Telemetry](assets/run_002_multi_query/charts/q5_confluence_jira_vpn_issues_stream_histogram.png)

#### **Web App UI** - `Q5. Confluence + Jira - VPN Issues (UI)`
*   **Complexity Profile**: `Level 3: Multi-Connector Federated RAG (2 Connectors)`
*   **Success Rate**: `100.0%`
*   **TTFT (P50/P90/P95/P99)**: 26.718 s / 42.026 s / 42.026 s / 42.026 s (Min: 17.304 s, Max: 42.026 s, Avg: 28.199 s)
*   **TTLT (P50/P90/P95/P99)**: 28.674 s / 43.673 s / 43.673 s / 43.673 s (Min: 18.229 s, Max: 43.673 s, Avg: 30.123 s)

##### Telemetry Charts:
![Runs Telemetry](assets/run_002_multi_query/charts/q5_confluence_jira_vpn_issues_ui_runs.png)
![Histogram Telemetry](assets/run_002_multi_query/charts/q5_confluence_jira_vpn_issues_ui_histogram.png)

---

### Query Scenario: Q6

#### **streamAssist API** - `Q6. GDrive + Confluence - Laptop Upgrade Cycle (Stream)`
*   **Complexity Profile**: `Level 3: Multi-Connector Federated RAG (2 Connectors)`
*   **Success Rate**: `100.0%`
*   **TTFT (P50/P90/P95/P99)**: 7.747 s / 14.291 s / 14.291 s / 14.291 s (Min: 6.214 s, Max: 14.291 s, Avg: 8.284 s)
*   **TTLT (P50/P90/P95/P99)**: 33.738 s / 60.360 s / 60.360 s / 60.360 s (Min: 27.026 s, Max: 60.360 s, Avg: 35.773 s)

##### Telemetry Charts:
![Runs Telemetry](assets/run_002_multi_query/charts/q6_gdrive_confluence_laptop_upgrade_cycle_stream_runs.png)
![Histogram Telemetry](assets/run_002_multi_query/charts/q6_gdrive_confluence_laptop_upgrade_cycle_stream_histogram.png)

#### **Web App UI** - `Q6. GDrive + Confluence - Laptop Upgrade Cycle (UI)`
*   **Complexity Profile**: `Level 3: Multi-Connector Federated RAG (2 Connectors)`
*   **Success Rate**: `100.0%`
*   **TTFT (P50/P90/P95/P99)**: 27.888 s / 41.379 s / 41.379 s / 41.379 s (Min: 21.837 s, Max: 41.379 s, Avg: 28.593 s)
*   **TTLT (P50/P90/P95/P99)**: 28.669 s / 42.553 s / 42.553 s / 42.553 s (Min: 23.379 s, Max: 42.553 s, Avg: 29.823 s)

##### Telemetry Charts:
![Runs Telemetry](assets/run_002_multi_query/charts/q6_gdrive_confluence_laptop_upgrade_cycle_ui_runs.png)
![Histogram Telemetry](assets/run_002_multi_query/charts/q6_gdrive_confluence_laptop_upgrade_cycle_ui_histogram.png)

---

### Query Scenario: Q7

#### **streamAssist API** - `Q7. LumApps + Jira - Dev Workspace Tools (Stream)`
*   **Complexity Profile**: `Level 3: Multi-Connector Federated RAG (2 Connectors)`
*   **Success Rate**: `100.0%`
*   **TTFT (P50/P90/P95/P99)**: 7.760 s / 8.571 s / 8.571 s / 8.571 s (Min: 7.130 s, Max: 8.571 s, Avg: 7.842 s)
*   **TTLT (P50/P90/P95/P99)**: 25.047 s / 46.074 s / 46.074 s / 46.074 s (Min: 20.718 s, Max: 46.074 s, Avg: 27.257 s)

##### Telemetry Charts:
![Runs Telemetry](assets/run_002_multi_query/charts/q7_lumapps_jira_dev_workspace_tools_stream_runs.png)
![Histogram Telemetry](assets/run_002_multi_query/charts/q7_lumapps_jira_dev_workspace_tools_stream_histogram.png)

#### **Web App UI** - `Q7. LumApps + Jira - Dev Workspace Tools (UI)`
*   **Complexity Profile**: `Level 3: Multi-Connector Federated RAG (2 Connectors)`
*   **Success Rate**: `100.0%`
*   **TTFT (P50/P90/P95/P99)**: 23.404 s / 24.413 s / 24.413 s / 24.413 s (Min: 20.362 s, Max: 24.413 s, Avg: 22.706 s)
*   **TTLT (P50/P90/P95/P99)**: 24.667 s / 25.604 s / 25.604 s / 25.604 s (Min: 22.254 s, Max: 25.604 s, Avg: 24.202 s)

##### Telemetry Charts:
![Runs Telemetry](assets/run_002_multi_query/charts/q7_lumapps_jira_dev_workspace_tools_ui_runs.png)
![Histogram Telemetry](assets/run_002_multi_query/charts/q7_lumapps_jira_dev_workspace_tools_ui_histogram.png)

---

### Query Scenario: Q8

#### **streamAssist API** - `Q8. GDrive + Confluence + Jira - Remote Work (Stream)`
*   **Complexity Profile**: `Level 3: Multi-Connector Federated RAG (3 Connectors)`
*   **Success Rate**: `100.0%`
*   **TTFT (P50/P90/P95/P99)**: 7.812 s / 11.914 s / 11.914 s / 11.914 s (Min: 6.324 s, Max: 11.914 s, Avg: 7.796 s)
*   **TTLT (P50/P90/P95/P99)**: 36.965 s / 53.627 s / 53.627 s / 53.627 s (Min: 30.096 s, Max: 53.627 s, Avg: 38.127 s)

##### Telemetry Charts:
![Runs Telemetry](assets/run_002_multi_query/charts/q8_gdrive_confluence_jira_remote_work_stream_runs.png)
![Histogram Telemetry](assets/run_002_multi_query/charts/q8_gdrive_confluence_jira_remote_work_stream_histogram.png)

#### **Web App UI** - `Q8. GDrive + Confluence + Jira - Remote Work (UI)`
*   **Complexity Profile**: `Level 3: Multi-Connector Federated RAG (3 Connectors)`
*   **Success Rate**: `90.0%`
*   **TTFT (P50/P90/P95/P99)**: 41.362 s / 83.984 s / 83.984 s / 83.984 s (Min: 31.644 s, Max: 83.984 s, Avg: 45.492 s)
*   **TTLT (P50/P90/P95/P99)**: 52.204 s / 86.990 s / 86.990 s / 86.990 s (Min: 37.281 s, Max: 86.990 s, Avg: 53.066 s)

##### Telemetry Charts:
![Runs Telemetry](assets/run_002_multi_query/charts/q8_gdrive_confluence_jira_remote_work_ui_runs.png)
![Histogram Telemetry](assets/run_002_multi_query/charts/q8_gdrive_confluence_jira_remote_work_ui_histogram.png)

---

### Query Scenario: Q9

#### **streamAssist API** - `Q9. 3-Way IT Checklist (Stream)`
*   **Complexity Profile**: `Level 3: Multi-Connector Federated RAG (3 Connectors)`
*   **Success Rate**: `100.0%`
*   **TTFT (P50/P90/P95/P99)**: 7.705 s / 10.958 s / 10.958 s / 10.958 s (Min: 6.746 s, Max: 10.958 s, Avg: 8.092 s)
*   **TTLT (P50/P90/P95/P99)**: 30.684 s / 159.801 s / 159.801 s / 159.801 s (Min: 25.138 s, Max: 159.801 s, Avg: 42.249 s)

##### Telemetry Charts:
![Runs Telemetry](assets/run_002_multi_query/charts/q9_3_way_it_checklist_stream_runs.png)
![Histogram Telemetry](assets/run_002_multi_query/charts/q9_3_way_it_checklist_stream_histogram.png)

#### **Web App UI** - `Q9. 3-Way IT Checklist (UI)`
*   **Complexity Profile**: `Level 3: Multi-Connector Federated RAG (3 Connectors)`
*   **Success Rate**: `100.0%`
*   **TTFT (P50/P90/P95/P99)**: 30.533 s / 47.632 s / 47.632 s / 47.632 s (Min: 23.189 s, Max: 47.632 s, Avg: 31.543 s)
*   **TTLT (P50/P90/P95/P99)**: 37.049 s / 48.902 s / 48.902 s / 48.902 s (Min: 26.768 s, Max: 48.902 s, Avg: 35.938 s)

##### Telemetry Charts:
![Runs Telemetry](assets/run_002_multi_query/charts/q9_3_way_it_checklist_ui_runs.png)
![Histogram Telemetry](assets/run_002_multi_query/charts/q9_3_way_it_checklist_ui_histogram.png)

---

## 7. Audit Artifacts & References
All execution outputs, logs, code controllers, and telemetry database files are preserved in the local workspace:

*   **Master Telemetry Database**: [results.json](assets/run_002_multi_query/results.json)
*   **Comprehensive Run Report**: [report.md](assets/run_002_multi_query/report.md)
*   **Execution Logs**: [task-4221.log](assets/run_002_multi_query/task-4221.log)
*   **Consolidated Page Object Model**: [browser_controller.py](../src/browser_controller.py)
*   **Diagnostic DOM Scrapes**: [extracted_texts.json](assets/run_002_multi_query/extracted_texts.json)
*   **Visual Validation Capture**: [debug_page_25s.png](assets/run_002_multi_query/debug_page_25s.png)
