# Quant Stock Recommendation (personal, zero-cost, frozen P6-11B model)

A local tool for an individual investor. It ranks current U.S. large-cap stocks
with a frozen quantitative model and shows, transparently, which candidates
qualify and why the others don't. It uses public data only (Yahoo Finance via
`yfinance`, SEC EDGAR, Wikipedia), **places no orders**, and is not investment advice.

Two modes share **one** canonical pipeline (`pipeline/canonical.py`):

| Mode | Command | What it does |
|---|---|---|
| A. Automated Market Scan | `python app.py scan --capital 50000` | Current S&P 500 → data → gates → frozen scoring → MODEL_RANK_E → portfolio gates → TOP-5 / watchlist |
| B. Direct Ticker Evaluation | `python app.py evaluate NVDA AAPL --capital 50000` | Scores your tickers inside the same S&P 500 cross-section with the same rules, and reports each one's individual verdict *and* the portfolio-level status |

> **What a REAL RECOMMENDATION means:** every data and decision gate passed. It does
> **not** mean the stocks will rise, that the ranking predicts returns, or that the
> strategy is profitable. Predictive power is unproven. `python app.py track` records
> what actually happens afterwards.

---

## 1. Project location

The project lives at **`~/Developer/quant-stock-engine`**. P6-19 moved it out of
`~/Desktop/퀀트 예측 프로그램`, because iCloud "Desktop & Documents" sync offloaded
source files on this nearly full disk (590 offloaded files, 202 of them `.py`). Python
then hung while macOS downloaded them back. `~/Developer` is not synced by iCloud.

The original Desktop folder was **not modified or deleted**. Once you are satisfied
with the new location you may archive or remove it yourself (see §7). `app.py doctor`
warns if the project is ever run from an iCloud-synced folder.

## 2. Installation (macOS Apple Silicon)

Requires Python ≥ 3.10 (verified on python.org **Python 3.14.2**) and internet access.

```bash
cd ~/Developer/quant-stock-engine
```

```bash
python3 -m venv .venv
```

```bash
.venv/bin/python -m pip install -r requirements.txt
```

Optional, to run the test suite:

```bash
.venv/bin/python -m pip install -r requirements-dev.txt
```

## 3. Configuration (`.env`)

Copy the template and fill it in. `.env` is git-ignored; never commit it.

```bash
cp .env.example .env
```

| Variable | Required | Purpose |
|---|---|---|
| `SEC_USER_AGENT` | **yes**, for SEC data | SEC's fair-access policy asks automated clients to identify themselves: `"<AppName>/<version> <your real e-mail>"`, for example `QuantStockEngine/1.0 you@yourmail.com`. Placeholder domains (`example.com`, …) are rejected. If it is not set, SEC is **not queried at all**, ROE and profit margin come from Yahoo only, and every report says so. The value is never printed or written to artifacts. |
| `QPP_CAPITAL` | yes, unless you pass `--capital` | Investment capital in USD used for position sizing. **There is no default.** |
| `NEWS_API_KEY` | no | Legacy NewsAPI integration; not used by the recommendation pipeline. |
| `QPP_LOG_LEVEL` | no | `WARNING` (default) or `INFO` |
| `QPP_FINANCIAL_WORKERS` | no | Concurrent fundamentals fetches (default 4; SEC is paced at 8 req/s and Yahoo at ~3 req/s) |
| `QPP_PROVIDER_TESTS` | no | `1` enables live-provider tests |

Variables already set in your shell (for example in `~/.zprofile`) take precedence
over `.env`.

### Capital

Capital must be given explicitly every time, in one of these ways:

* `--capital 50000` on the command line (wins), or
* `QPP_CAPITAL=50000` in `.env`, or
* the interactive menu asks for it.

Missing, zero, negative or non-numeric capital stops the run *before* any data is
fetched (exit code 2). The capital used and its source are printed and stored in
`validation_result.json`. The frozen caps (20% per position, 30% hard ceiling, 40%
Technology) are unchanged.

## 4. Startup

Check the environment (add `--network` to also test provider reachability):

```bash
.venv/bin/python app.py doctor --network
```

Interactive menu:

```bash
.venv/bin/python app.py
```

| Command | Purpose |
|---|---|
| `app.py scan --capital 50000 [--limit 25] [--open]` | Mode A. `--limit` gives a bounded validation scan (labelled `bounded`). |
| `app.py evaluate TICKER… --capital 50000 [--open]` | Mode B |
| `app.py status [RUN_ID]` | Show the latest or a given run |
| `app.py tracking status` | Prospective ledger contents, cohorts, latest outcome update |
| `app.py tracking update` | Fetch completed daily bars, recompute paper outcomes, write the report (safe to rerun) |
| `app.py tracking report [--open]` | Write `tracking/reports/latest.md` / `latest.html` |
| `app.py tracking verify` | Hash chains, run-artifact integrity, reconstruction, replay |
| `app.py tracking exclusions [--add RUN_ID --category PRE_FIX\|DATA_INVALID --reason "…"]` | List or append exclusions (never deletes) |
| `app.py tracking replay [UPDATE_ID]` | Recompute an update from its stored price snapshot (offline) |
| `app.py track` | Alias: `tracking update` + `tracking report` |
| `app.py doctor [--network]` | Environment, configuration, location, disk and provider checks |

**VSCode:** open `~/Developer/quant-stock-engine`, select the interpreter
`./.venv/bin/python`, then use **Run and Debug** ("App: …" asks for capital; "Tests: full suite").

Each command runs once in the foreground and exits. No background processes are left
behind. Ctrl+C stops a run; its diagnostics are kept as `INTERRUPTED`.

## 5. User guide

### Automated Market Scan

```bash
.venv/bin/python app.py scan --capital 50000 --open
```

* A cold full scan fetches fundamentals for about 500 symbols, which takes a few
  minutes. Fundamentals are cached for 20 h (labelled `CACHED`), so later runs that
  day are faster.
* Every completed full scan that ends in a REAL RECOMMENDATION is recorded in the
  immutable prospective ledger `tracking/ledger/observations.jsonl` (P6-20). The
  record covers the TOP-5 and the watchlist, built from the run's own artifacts.
  Bounded scans and Direct Ticker Evaluations are never recorded.

### Prospective paper tracking (P6-20)

Recommended routine: run a full scan **before 09:30 ET** on a trading day (23:30 KST in
winter, 22:30 KST during US daylight saving time). Its paper entry is then that day's
open. After **17:00 ET** (07:00 KST the next morning in winter, 06:00 in summer) run:

```bash
.venv/bin/python app.py tracking update
```

```bash
.venv/bin/python app.py tracking report --open
```

* Paper entry is the first regular-session open *after* the recommendation
  timestamp: premarket gives the same day's open; regular session, after hours or a
  weekend gives the next session's open. A closing price from before the
  recommendation is never used.
* Each pick then follows the frozen rules (hard stop, EMA20, trailing ATR, entry #2,
  30-day review) via the unmodified engine. Signals are filled at the next open. The
  window ends at an exit or at the frozen 30-day review.
* SPY is measured over the identical window. Cost scenarios are hypothetical. No
  annualised figures and no significance claims are reported. Results stay
  `INSUFFICIENT_SAMPLE` until there are at least 30 completed observations.
* **These are paper results from the original recommendations, not your actual
  returns.** Runs found invalid later are excluded by appended events, never by
  editing or deleting records.
* Full method: `reports/P6-20_TRACKING_SPECIFICATION.md`.

### Direct Ticker Evaluation

```bash
.venv/bin/python app.py evaluate NVDA AAPL TSLA PLTR --capital 50000 --open
```

* The frozen model ranks *cross-sectionally*, so your tickers are scored together with
  the current S&P 500 constituents (same contracts, gates, weights and MODEL_RANK_E).
  Tickers outside the S&P 500 are not dropped; they are marked `in_sp500: false`.
* Each ticker gets an **individual evaluation** (alpha, percentile, factor z-scores,
  MODEL_RANK_E rank, ADV20, data status). A single ticker is evaluated even when the
  portfolio as a whole cannot be a valid recommendation. The portfolio-level status
  is reported separately.
* Verdicts: `TOP5`, `WATCHLIST`, `RANKED_NOT_SELECTED`, `BEAR_REJECTED`,
  `QUARANTINED` (with reasons such as missing PER, `LIQUIDITY_REJECTED`,
  `NON_EQUITY_INSTRUMENT_ETF` or `SYMBOL_NOT_FOUND_OR_NO_PROVIDER_DATA`), and
  `NOT_EVALUATED` (invalid symbol format).

### Reading the result

| Outcome | Meaning |
|---|---|
| **REAL RECOMMENDATION** | Five portfolio-eligible positions passed every gate (data, freshness, provenance, liquidity, frozen scoring, BEAR filter, sector cap, sizing). |
| **DATA-INCOMPLETE / NO VALID RECOMMENDATION** | The pipeline ran, but fewer than five positions survived. Nothing is recommended. The reason is shown. |
| **LIVE DATA UNAVAILABLE** | The universe or market data could not be obtained. Nothing is scored. |

For each selected stock the report shows: ticker and name, MODEL_RANK_E rank and
score, alpha and cross-sectional percentile, factor z-scores, sector, ADV20 and
liquidity status, price/volume/fundamental status with last bar date, target weight,
shares, the 2×ATR hard stop, and the frozen entry and exit rules. Excluded candidates
are listed with their reasons. A sector note appears when a non-Technology sector
exceeds 40%: the frozen engine caps only "Technology", so this is reported, not
enforced.

### Where things are

| Path | Content |
|---|---|
| `runs/<run_id>/` | `run_manifest.json` (parameters, versions, frozen fingerprints), `execution_status.json`, `checkpoints.jsonl`, `provider_summary.json`, `candidate_flow.json`, `validation_result.json`, `failure.json` (on failure), `report.md`, `report.html` |
| `runs/LATEST` | id of the latest run |
| `tracking/ledger/` | immutable prospective ledger (`observations.jsonl`) and events (`events.jsonl`), hash-chained |
| `tracking/prices/`, `tracking/outcomes/`, `tracking/updates.jsonl` | price snapshots, computed outcomes and the update log (replayable) |
| `tracking/reports/latest.html` | prospective performance report |
| `tracking/recommendation_ledger.jsonl`, `tracking/outcomes.json` | P6-19 schema-1 tracker files (preserved, superseded, no longer written) |
| `cache.nosync/provider/` | fundamentals cache (safe to delete; it is rebuilt) |
| `docs/DATA_INPUT_SPECIFICATION.md` | approved input definitions (ADV20, sector, eligibility, SEC periods, revenue concept, P/B consistency) |
| `tracking/excluded_runs.json` | P6-19 exclusion list (preserved; mirrored into `tracking/ledger/events.jsonl`) |
| `reports/` | phase reports, roadmap, test results |

## 6. Tests

```bash
.venv/bin/python -m pytest tests -q
```

The suite runs offline inside a throw-away sandbox (`tests/conftest.py`):

* network access is blocked unless `QPP_PROVIDER_TESTS=1`;
* any test that writes to the real `data/`, `reports/`, `runs/` or `tracking/` fails,
  and the file is restored;
* legacy tests that conflict with the frozen specification are explicitly isolated as
  strict `xfail`, with documented reasons (never skipped silently).

Frozen-core parity only:

```bash
.venv/bin/python -m pytest tests/test_p6_18_frozen_core_parity.py tests/test_p6_19_hardening.py::TestFrozenSourcePinned -q
```

## 7. Troubleshooting

| Symptom | Fix |
|---|---|
| A command hangs at start | Run `app.py doctor`. If it reports an iCloud location or offloaded files, run the project from `~/Developer/quant-stock-engine`. |
| `ERROR: Capital is not configured` | Pass `--capital 50000` or set `QPP_CAPITAL` in `.env`. |
| `NOTE: SEC EDGAR disabled` | Set `SEC_USER_AGENT="QuantStockEngine/1.0 <your e-mail>"` in `.env` or in your shell profile. |
| `LIVE DATA UNAVAILABLE` | Run `app.py doctor --network`. The cause is usually connectivity, or Yahoo or Wikipedia being temporarily unavailable. Try again later; rate limits are never bypassed. |
| Disk almost full (`doctor` WARN) | Safe to delete (regenerable): `cache.nosync/`, `.venv` (recreate it per §2). Do not delete `data/`, `tracking/` or the `runs/<id>/` folders of recorded runs: `tracking verify` and the diagnostics need them. |
| `tracking update` says FAILED | The provider was unreachable. Earlier records and outcomes are untouched; run it again later. |
| All observations `PENDING_OUTCOME` | Expected until the entry session's daily bar is complete (after 17:00 ET) and the 30-day window has passed. |
| Removing the old Desktop copy | Only after you have checked the new location. Move `~/Desktop/퀀트 예측 프로그램` to the Trash in Finder (reversible until you empty the Trash). |

## 8. Security

* No credentials are stored in source. Secrets go only in `.env` (git-ignored) or your shell.
* **NewsAPI key rotation (required, one-time):** an old NewsAPI key was hard-coded in
  earlier versions, so treat it as exposed. Sign in at <https://newsapi.org/account>,
  regenerate the key, and if you still want NewsAPI put the new key in `.env` as
  `NEWS_API_KEY`. NewsAPI is optional; the recommendation pipeline does not use it.
* The SEC contact e-mail is personal data. It is used only as the HTTP User-Agent for
  SEC requests and is never written to run artifacts or reports.

---

See `reports/ROADMAP.md` for engineering status and
`reports/P6-19_IMPLEMENTATION_REPORT.md` for the verification, changes and evidence.
