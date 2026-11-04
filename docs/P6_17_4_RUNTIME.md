# P6-17.4 Runtime Contract

## Canonical production route

`QuantTradingSystemV2(mode="live", run_research=False)` uses only:

`DataLoader → provenance/required-data gate → FactorEngine → frozen DEFAULT_FACTOR_WEIGHTS → DecisionEngine/MODEL_RANK_E → final portfolio validity`.

Regime weight mutation, `FactorWeightOptimizer`, `LearningEngine`, Meta Alpha, LLM scoring, and synthetic alternative-data fallbacks are not imported into this route. They remain research/backtest-only behavior behind `run_research=True` or a non-live mode.

`status == "SUCCESS"` means the pipeline executed. `recommendation_status` is final truth and is `REAL RECOMMENDATION` only when five final, portfolio-eligible positions remain.

## Provider states

`REAL` is a genuine validated observation. `PARTIAL`, `STALE`, `UNAVAILABLE`, and `MOCK` are preserved in machine-readable diagnostics and quarantine a required candidate from the production frozen model. Legacy `FALLBACK` remains readable only for compatibility and is synthetic/degraded, never usable as REAL.

Financial diagnostics record field-level SEC EDGAR or yfinance provenance. SEC is primary for ROE/profit margin when a CIK is supplied; yfinance values are labelled by field rather than silently merged.

The legacy `alpha_engine` fallback modules now label simulated prices and mock SEC filings as `MOCK`. The canonical live route does not call those modules.

## Local VSCode startup

The repository requires Python 3; this machine has no `python` executable alias. From the workspace root:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m unittest tests.test_p6_17_4_reconciliation tests.test_p6_11b_decision_engine
```

In VSCode select `.venv/bin/python` as the interpreter. The checked-in settings already add the workspace to import resolution. Optional NewsAPI and pytrends features degrade to `UNAVAILABLE`; they must not block application import or create synthetic inputs.
