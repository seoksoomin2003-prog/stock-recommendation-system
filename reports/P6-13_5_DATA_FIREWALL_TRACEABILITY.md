# P6-13.5 Data Firewall Traceability Report

### Objective
Document how the system correctly traces provenance from input generation all the way through decisioning, rejecting compromised or inaccessible data pipelines.

### Traceability Path

1. **Generation (`LLMFundamentalEngine.py`)**
   - In live settings, real data guarantees `data_status="REAL"`.
   - In local or failure settings, mock fallbacks return `data_status="MOCK"`.
   - Propagated to Factor Matrix utilizing Pandas `attrs` extensions.

2. **Availability Check (`FactorEngine.py`)**
   - Deep lookbacks (14 months) are strictly validated.
   - If a ticker lacks historical depth, a `NaN` series is generated and tagged with `data_status="UNAVAILABLE"`.

3. **Batch Filtering (`main.py`)**
   - Analyzes factor combinations.
   - Filters components without valid network responses prior to passing downstream.

4. **Firewall & Quarantine (`DecisionEngine.py` & `main.py`)**
   - The firewall strictly checks the aggregate `data_status` for every ticker candidate.
   - Any `MOCK` or `UNAVAILABLE` flag causes immediate candidate eviction to `quarantined_candidates`.
   - MOCK tickers will definitively *never* be evaluated for TOP5 allocation.

### Result
The firewall completely severs the attack vector where zero-cost or locally mocked data structures could simulate authentic historical market states.
