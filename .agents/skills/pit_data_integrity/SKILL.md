---
name: PIT Data Integrity & Anti-Lookahead
description: Actionable checklists and engineering standards to enforce point-in-time data safety and prevent look-ahead leakage in historical backtests.
---

# Point-in-Time Data Integrity & Anti-Lookahead

This skill provides the actionable standards, verification steps, and adversarial checklists to ensure look-ahead leakage is prevented during historical data translation, factor loading, and backtest execution.

---

## 1. Actionable Governance Checks

When writing or modifying data layers, adapters, or backtests, follow this workflow:

1. **Verify the `as_of` Anchor**:
   * Ensure that `as_of` is the absolute decision boundary. Any record (price, dividend, split, fact) with publication, filing, or effective timestamps *after* `as_of` must be discarded.
2. **Audit Period Semantics**:
   * Keep `raw_close`, `adjusted_close`, `splits`, and `dividends` separate. Never use `adjusted_close` directly in backtests without proving future dividends/splits are look-ahead isolated.
3. **Gate yfinance Financials**:
   * Label yfinance statement values as `REAL_PIT_UNVERIFIED`.
   * Enforce a hard gate in historical factor queries to reject `REAL_PIT_UNVERIFIED` records if the target date is in the past.
4. **Renormalize on Missing**:
   * If factors are rejected, trigger weight renormalization in the scoring engine instead of crashing the pipeline.

---

## 2. Adversarial Leakage Test Checklist

Always execute or implement tests for these 8 adversarial scenarios when making database or adapter modifications:

| Test Case | Adversarial Action | Required Guardrail / Test Logic |
| --- | --- | --- |
| **TEST 1: Future Filing Rejection** | Amended SEC filing inserted with `filed_at > as_of` | Query snapshot at `as_of` and assert the amended value is **NOT** returned. |
| **TEST 2: yfinance Restated Value** | yfinance statement outputs restated value `Y` mapping to historical period | Query must classify this value as `REAL_PIT_UNVERIFIED` and reject it in backtests. |
| **TEST 3: Future Dividend Leak** | Dividend announced or paid *after* `as_of` | Validate `announced_at <= as_of` and `effective_at <= as_of`. Assert future dividends are excluded. |
| **TEST 4: Future Split Adjustment** | Split occurring *after* `as_of` | Verify historical price index at `as_of` does not contain back-adjusted split ratios. |
| **TEST 5: Future Analyst Revision** | Analyst estimate revised *after* `as_of` | Query must assert revision values are excluded from the `as_of` snapshot. |
| **TEST 6: Future Earnings Result** | Earnings report released *after* `as_of` | Query must verify `earnings_dates` with release date > `as_of` are blocked. |
| **TEST 7: Future Shares Revision** | Shares outstanding modified *after* `as_of` | Revisions in shares outstanding must be ignored in backtests if published later. |
| **TEST 8: Current Statement Query** | yfinance current financials queried for past date | Audit must classify this data as `REAL_PIT_UNVERIFIED` and block it from factor calculations. |

---

## 3. Standard Reporting Structure

When documenting audit results, structure findings using these fields:

```markdown
### 1. Hypothesis
[Describe the look-ahead risk, data discrepancy, or leakage vector being examined]

### 2. Evidence
[Present quantitative stats, comparison tables, or test pass metrics demonstrating the issue or its resolution]

### 3. Limitation
[Log any environment constraints, scipy/lxml parser limitations, or proxies used]

### 4. Verdict
[One of: YFINANCE PIT SAFE FOR DEFINED USE, YFINANCE AUXILIARY ONLY, or YFINANCE BLOCKED]

### 5. Next Action
[State concrete coding, testing, or pipeline adjustments required]
```
