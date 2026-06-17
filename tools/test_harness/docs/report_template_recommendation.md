# Recommendations: Gemini Enterprise Latency Report Template Alignment

Based on the official **Gemini Enterprise (GE) Latency Monitoring Playbook** guidelines, we recommend updating our test harness execution report template to align with Google's internal performance standards.

---

## 1. Primary Recommendation: Shift from Averages to Percentiles
The playbook states:
> *"We use Percentiles as our primary aggregation method to understand how Gemini Enterprise is performing. Percentiles provide a more accurate 'source of truth' than simple averages..."*

### Proposed Report Table Schema Update:
We should replace simple Average / Min / Max metrics with **P50**, **P90**, **P95**, and **P99** percentiles to accurately represent the tail latency and user experience distribution.

| Metric | Business Focus | Technical Purpose in Report |
| :--- | :--- | :--- |
| **P5 (Min)** | Theoretical Speed | Minimum possible latency under perfect network/cache conditions. |
| **P50 (Median)**| Typical Speed | Median user experience; 50% of user runs are faster than this. |
| **P90 / P95** | Reliable Speed | **Standard Benchmark**: General performance trends, ignoring network glitches. |
| **P99 (Max)** | Tail Stability | Worst-case tail latency; flags painful "freezes" or connection timeouts. |

---

## 2. Recommendation: Query Complexity Profiling
The playbook notes:
> *"All queries are not created equal: Intrinsic knowledge queries should be fast [...] vs complex queries [...] which involve multi-agent reasoning and intricate tooling."*

We should categorize our 9 test scenarios into **Complexity Profiles** inside the workload specification table:

1.  **Level 1: Intrinsic Knowledge / Grounding Bypassed**: Standard greeting or definition queries (expect < 3s latency).
2.  **Level 2: Single-Connector RAG**: Queries searching a single index (e.g., Q1 GDrive PTO rollover; expect ~15-20s latency).
3.  **Level 3: Multi-Connector Federated RAG**: Queries querying 2-3 indexes (e.g., Q8 Remote Work; expect ~30-40s latency).
4.  **Level 4: Custom Agent Tooling / Reasoning**: Queries invoking external APIs or agentic steps (expect higher cumulative execution times).

---

## 3. Recommendation: Traffic & Volume Correlation
Since latency spikes are highly correlated with traffic volumes, the report header must state the active concurrency parameters:
*   **Total Simultaneous Workers**: (e.g., `Concurrency = 3`).
*   **Average Query Throughput**: A calculated sum of queries submitted per minute during the run to mimic GCP Metrics Explorer request count trends.

---

## 4. Recommendation: Token Usage & Grounding Auditing
To help debug outlier latency spikes (where only P95/P99 rises while P50 remains stable), we should log **token counts** and **grounding metadata** returned in the API payloads (usage logs):
*   **Input Tokens**: Context window size submitted to the model.
*   **Output Tokens**: Length of response generated (determines streaming duration).
*   **Grounding Citations**: Number of search sources matched (correlated with search connector roundtrip delays).
