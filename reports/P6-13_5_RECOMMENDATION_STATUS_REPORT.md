# P6-13.5 Recommendation Status Report

### Separation of Concerns
The P6-13.5 update decouples the concept of *Pipeline Integrity* from *Recommendation Validity*.

**Legacy Limitation:**
- If the pipeline generated fake numbers, the pipeline succeeded (`SUCCESS`), resulting in an artificial asset purchase.

**P6-13.5 Architecture:**
- `status`: Preserved as `SUCCESS` (or `LIVE DATA UNAVAILABLE` if complete API routing fails). Guarantees orchestration and execution compatibility.
- `recommendation_status`: A completely uncoupled variable identifying truth.

### Matrix of Outcomes

| Scenario | Candidate Split | Pipeline `status` | `recommendation_status` | Action |
| --- | --- | --- | --- | --- |
| 100 REAL | 100 REAL / 0 MOCK | `SUCCESS` | `REAL RECOMMENDATION` | Normal Top 5 output |
| 99 REAL, 1 MOCK | 99 REAL / 1 MOCK | `SUCCESS` | `REAL RECOMMENDATION` | Top 5 chosen from 99 REAL |
| 4 REAL, 96 MOCK | 4 REAL / 96 MOCK | `SUCCESS` | `DATA-INCOMPLETE / NO VALID RECOMMENDATION` | No trading permitted. |
| 0 REAL, 10 MOCK | 0 REAL / 10 MOCK | `SUCCESS` | `DATA-INCOMPLETE / NO VALID RECOMMENDATION` | No trading permitted. |

### Live Dry-Run Results
Running the exact production path locally against `["AAPL", "MSFT", "GOOGL"]` immediately triggers a `MOCK` response from the RAG Engine.

The system explicitly generated:
```
Quarantined 3 candidates due to MOCK data: ['AAPL', 'MSFT', 'GOOGL']
NO_VALID_RECOMMENDATION: VERDICT: DATA-INCOMPLETE (All candidates were quarantined)
```
Output Payload:
```json
{
  "status": "SUCCESS",
  "recommendation_status": "DATA-INCOMPLETE / NO VALID RECOMMENDATION",
  "scores": "pd.Series/DataFrame...",
  "weights": "pd.Series/DataFrame..."
}
```
Validation Status: **PASSED**
