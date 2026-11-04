# US Prospective Tracking Specification (multi-market edition)

Status: **in force, unchanged from P6-20**. Authoritative detail: `reports/P6-20_TRACKING_SPECIFICATION.md`. Input rules for runs after commit `63c283d`: `docs/DATA_INPUT_SPECIFICATION.md` (spec `P6-20-A`).

P6-21..25 did **not** change any US tracking rule. They only add the guarantees below, which keep US tracking isolated from the Korean engine.

| Item | Rule |
|---|---|
| Market | US only. Ledger `tracking/ledger/`, prices `tracking/prices/`, outcomes `tracking/outcomes/`, reports `tracking/reports/`. All paths are unchanged. |
| Market identity of existing records | Records written before P6-21 have no `market` field. They are **US by construction**, because every such run came from the US canonical pipeline. They are not rewritten: rewriting would break the hash chain and the `verify` reconstruction. |
| New US runs | The run manifest now also carries `market: "US"` and `market_config_version: "US-1"`. Ledger record construction is unchanged. |
| Eligibility | Unchanged, plus one new reason, `NOT_A_US_MARKET_RUN`: any run whose manifest says `market != "US"` is refused by the US ledger. KR runs live under `runs/KR/` and are never synced into the US ledger. |
| Currency | USD only. Capital comes from `--capital` / `QPP_CAPITAL`. |
| Benchmark | SPY over identical windows (unchanged) |
| Entry, exit, horizon | Frozen P6-11B rules through the unmodified `evaluate_existing_position`; next-open fills on the NYSE calendar (unchanged) |
| Cohorts | `VALID_PROSPECTIVE / PRE_FIX_EXCLUDED / DATA_INVALID` × `PENDING / COMPLETED / INCOMPLETE`. Summaries are split by data-input spec version (P6-20 vs P6-20-A). |
| Official statistics scope | `US × VALID_PROSPECTIVE × PORTFOLIO_TOP5 × COMPLETED_OUTCOME`, in USD. Never pooled with KR. |
| Commands | `python app.py tracking status\|update\|report\|exclusions\|verify\|replay` (identical; `--market US` is the default) |
