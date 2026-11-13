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

**Multi-market (P6-21..25).** A second, fully independent engine covers **South Korea** (KOSPI +
KOSDAQ liquid-300, KRW). It has its own data, universe, model (`KR-EXP-0.1`, status **EXPERIMENTAL**)
and paper tracking. It shares infrastructure with the US engine, never model assumptions; see §5a and
`reports/P6-21_ARCHITECTURE.md`. The US engine is unchanged, and every existing command defaults to
`--market US`.

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
| `QPP_CAPITAL_KRW` | for KR, unless you pass `--capital` | KR capital in **KRW**. The USD `QPP_CAPITAL` is never reused for Korea. |
| `OPENDART_API_KEY` | no (KR fundamentals) | Free key from <https://opendart.fss.or.kr/> (인증키 신청). Without it the KR engine runs price-only and reports DART as UNAVAILABLE. |
| `KRX_API_KEY` | no (official KR market data) | Free key from <https://openapi.krx.co.kr/> (sign up, then apply for the daily-trading services: 유가증권/코스닥 일별매매정보). Without it, KR prices come from Yahoo (supplementary) and traded value is the labelled proxy close × volume. |

Variables already set in your shell (for example in `~/.zprofile`) take precedence
over `.env`.

### Capital

Capital must be given explicitly every time, in one of these ways:

* `--capital 50000` on the command line (wins), or
* the capital box on the terminal's model tab (saves `QPP_CAPITAL` or `QPP_CAPITAL_KRW` in `.env`), or
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

### South Korea (P6-21..25, EXPERIMENTAL)

```bash
python app.py --market KR scan --capital 10000000      # liquid-300 scan, TOP-10 (KRW)
python app.py --market KR scan --capital 10000000 --limit 60   # bounded check (never tracked)
python app.py --market KR evaluate 005930 035720       # direct evaluation vs the liquid-300 reference
python app.py --market KR tracking update               # KR paper outcomes (KRW, ^KS11/^KQ11)
python app.py --market KR tracking verify
python app.py dashboard --open                          # US and KR side by side (read-only)
```

* **Universe:**
  * eligible KOSPI + KOSDAQ common stocks from the KRX KIND list, with SPACs, REITs, funds and foreign issuers excluded, each with a stated reason;
  * the top 300 by 20-session average traded value.
* **Model `KR-EXP-0.1`:** price factors only, as fixed by the pre-registered study (`reports/KR_MODEL_RESEARCH_SPECIFICATION.md`):
  * winsorised z-scores and equal weights;
  * TOP-10 equal weight, at most 3 names per KRX industry, whole shares;
  * 20-session holding period. Status **EXPERIMENTAL**: it is not validated and is for paper observation only.
* **Tracking:**
  * `tracking/kr/`, KRW only, cohort `EXPERIMENTAL_PROSPECTIVE`;
  * never pooled with US observations.
* A full KR scan downloads about 2,500 symbols from Yahoo the first time each day (roughly 40 minutes on a slow link). Later runs on the same day reuse `data/kr/cache/`.
* The KR model scan runs in the daily job since 2026-11-12 (user decision), in the evening slots only: once per Korean weekday from 18:00 Seoul time. A morning run scored the day before the last one, because the scan's index data (Yahoo) still ends a day earlier then and its price files are from before the close (found 2026-11-13). The step is skipped without `QPP_CAPITAL_KRW`, waits while a scan started from the screen is running, does not scan a session the button already scanned, allows 90 minutes, and is followed by `--market KR tracking update`. The scan no longer reuses a stored download that does not reach the session it scores, and tracking records one set of observations per scored session: a second scan of the same session picks the same stocks for the same entry session and is not recorded again. The 모델 tab (한국) also has a **스캔 실행** button next to the capital box that starts the same command with the saved capital, one at a time and never beside the daily job's own run (`terminal/model_scan.py`, `/api/model/scan`).

### Personal terminal (TERMINAL-1)

A local web app on this Mac only (`127.0.0.1`), with the screen in Korean. It uses free public data only and has no order execution.

```bash
python app.py terminal --open          # http://127.0.0.1:8765 ; stop with Ctrl+C ; --port N for another port
```

| Tab | Content | Source |
|---|---|---|
| 시장 개요 | indices, rates/FX/commodities, 11 sector ETFs (daily change, 1-month change, 30-day sparkline) | Yahoo Finance (delayed daily bars) |
| 종목 | profile and valuation, candle chart with SMA 20/50/200 and volume (3 months / 1 year / 5 years), 5-year annual financials, latest SEC filings | Yahoo, SEC EDGAR companyfacts / submissions |
| 거시 | 10Y and 2Y Treasury yields, 10Y-2Y spread, effective Fed funds rate, CPI year over year, unemployment, payrolls, KRW/USD | FRED public CSV (personal, non-commercial use, with attribution) |
| 관심종목 | local watchlist (`data/terminal/watchlist.json`) | Yahoo |
| 모델 | frozen P6-11B baseline: latest full scan TOP-5 and tracking status (read-only); challenger models come in stage 3 | `runs/`, `tracking/` |

* Every value carries a status: **실데이터** (real), **지연·오래됨** (stale: provider failed, cached copy shown, or bar older than 5 days) or **데이터 없음** (unavailable).
* During the US regular session the latest daily bar is labelled **장중·미확정** (intraday, unconfirmed).
* Missing values show as "—" and are never filled with 0. For banks, lines such as operating income are left empty.
* Responses are cached under `data/terminal/cache/`, which is ignored by git and safe to delete:
  * quotes and charts: 15 minutes;
  * profile and financials: 20 hours;
  * filings: 1 hour;
  * macro: 6 hours.
* The financials table is for display only and is separate from the P6-20-A model inputs.
* The SEC identity (`SEC_USER_AGENT`) is only ever reported as a status word.
* Specification: `reports/TERMINAL_1_SPECIFICATION.md`.

**Stage 2 (TERMINAL-2): your real portfolio and trade assistant.** Two more tabs; still no order execution.

| Tab | Content |
|---|---|
| 포트폴리오 | Record real fills (deposit, withdraw, buy, sell, dividend, fee, stop/target plan) and see the results (see below) |
| 매매 보조 | Position-size calculator, risk settings, and the P6-11B plan check (see below) |

포트폴리오 shows:
* holdings, moving-average cost and unrealized/realized P&L;
* account equity in USD with the KRW equivalent;
* sector weights;
* alerts: stop hit or near, target reached, missing stop, position or sector over its limit;
* the time-weighted return versus SPY;
* closed-trade statistics.

매매 보조 provides:
* **Position-size calculator:** shares = the smallest of three limits, rounded down:
  * risk limit: equity × risk % ÷ (entry − stop);
  * weight limit: equity × max weight ÷ entry;
  * cash limit: cash ÷ entry.

  If the stop is left empty, it suggests 2 × ATR(14) below the entry.
* **Risk settings:** risk per trade 1%, maximum position 20%, maximum sector 40%, near-stop warning 3%.
* **P6-11B plan check (read-only):** the latest TOP-5 converted to your account size (target shares, first-entry shares, model stop).

How records work:
* Records live in `data/terminal/journal.jsonl`. It stays on this Mac and is ignored by git.
* The file is append-only and hash-chained. Validation rejects overselling, negative cash and future dates.
* A mistaken entry is cancelled with a VOID entry. The original line stays.
* Settings are stored in `data/terminal/settings.json`.

Specification: `reports/TERMINAL_2_SPECIFICATION.md`.

**Stage 3 (TERMINAL-3): challenger models and research lab.**

The frozen P6-11B stays the baseline. Rule-based challengers are observed beside it, prospectively, under one common yardstick.

```bash
python app.py lab update     # refresh ~500 S&P 500 daily bars (about 2-3 minutes) and record today's challenger signals
python app.py lab compare    # prospective comparison summary
```

Run `lab update` once a day after the US close (17:00 ET, about 07:00 KST), or press the button on the 모델 tab. Running it twice on the same day records nothing new.

**Challengers** (price-only, parameters fixed in advance, top 10 stocks at equal weight):
* `MOM_12_1`: 12-month return, skipping the last month;
* `LOWVOL_252`: lowest 252-day volatility;
* `TREND_SWING`: close above SMA200, SMA50 above SMA200, ranked by 6-month return;
* baselines `BASE_SPY` and `BASE_EW` (equal weight across the whole universe).

**Prospective records:**
* stored in `data/lab/ledger.jsonl`, append-only and hash-chained;
* one record per model per completed session;
* the entry is the first regular-session open after the record time, the same rule as P6-20.

**Common yardstick:**
* buy at the entry-session open, sell at the close of the H-th session (H = 5, 20 or 60);
* dividends included, equal weight, excess return versus SPY;
* P6-11B uses its P6-20 `VALID_PROSPECTIVE` TOP-5, the first run of each entry session, read-only;
* because daily cohorts overlap, the screen shows the number of independent samples (about matured ÷ H) and "판단 보류" (no verdict) until there are 12 or more.

**연구실 (research) tab:**
* a monthly-rebalanced historical simulation, about 5 years;
* cost scenarios of 0 and 10 bps one way;
* CAGR, volatility, Sharpe ratio, maximum drawdown and yearly excess return.

Picks are limited to stocks that had already joined the index (Wikipedia "Date added"). Stocks that later left the index are still missing, so results remain biased upward. Treat the lab as reference only.

Specification: `reports/TERMINAL_3_SPECIFICATION.md`.

**점수 (score) tab, same-day check:**
* looking up a stock also shows today's delayed price, opening gap, volume, new filings and news headlines. The check is never added to the score;
* filings become warnings by the rules the score's event reader uses. Headlines are not judged good or bad;
* the ranking opens the top three actionable stocks, and each row below opens in place.

News comes from free feeds: Yahoo Finance RSS (US) and Google News RSS (KR). Yahoo's feed for a ticker can include articles about related companies, and a Korean name search can match unrelated articles.

`python app.py news record` (also `--market KR`) stores new headlines of every scanned stock in `data/news/`: title, link, source and time only. It runs in the daily job and stops at once if a feed refuses requests.

**Stage 4 (TERMINAL-4): daily job and alerts.**

```bash
python app.py automation install       # launchd job hourly from 07:10 to 23:10 KST (later slots retry what failed; a finished day ends in seconds)
python app.py automation status        # schedule, last run, missed sessions, Telegram status
python app.py automation uninstall
```

The job records the day's scores, the lab signals, tracking, news and Korean forward records, backs up the ledgers to
`~/QuantEngineBackups`, checks your alerts at the close and sends one summary by Telegram (optional, `TELEGRAM_BOT_TOKEN` and
`TELEGRAM_CHAT_ID` in `.env`) and as a macOS notification. Each step runs once per session; a failed step is retried in the
next slot. Logs: `data/automation/`. Specification: `reports/TERMINAL_4_SPECIFICATION.md`.

**Collect now (2026-11-10):** the 지금 수집 button in the top bar starts the same job at once (`POST /api/automation/run`), so the
schedule is a safety net, not a requirement. Only steps not yet done for the session run; when everything is current it says so
within seconds. A second run cannot start while one is going, and a day that is not ready is still not recorded. The bar under the
header shows the step in progress (also for a scheduled run) and, at the end, what failed or is not published yet. The run is
detached from the server and held awake against idle sleep (`caffeinate -i`); closing the lid still stops it. Output of the last
button run: `data/automation/manual_run.log`.

**US earnings-date recount (2026-11-10):** at the first run on or after 2026-12-15 (KST) whose US scores were recorded, the job
counts once how many US stocks have no next earnings date in the newest ledger session (`terminal/qsf/earnings_gap.py`), sends the
number by Telegram (macOS notification without Telegram) and writes one line under the item in `reports/DECISIONS_FOR_USER.md`.
An undelivered message is sent again at later runs with the same count. Nothing is scored or recorded differently; filling the
blanks stays a user decision. To count now: `python app.py qsf us-earnings-gap`.

**More terminal tools (2026-11-08):** command bar (`/` or ⌘K, keys 1-9 switch tabs), multi-stock comparison chart (비교),
market heat map and sector rotation graph with each sector's top-scored stocks (시장 지도), peer comparison and A-F grades by
score area (종목), portfolio risk (beta, volatility, VaR, correlation), alert centre (매매 보조) and the economic calendar
(거시: FOMC, US CPI and jobs report, Bank of Korea rate meetings, earnings dates of held and watched stocks). The calendar
dates are copied from the official pages and end where those pages end; add new dates to `terminal/econ_calendar.py`.
None of these change scores or records. See `reports/QSF_TERMINAL_FEATURES_2026_11_08.md`.

**Keeping the terminal running.**

```bash
python app.py terminal-agent install   # start the terminal at login and restart it within 30 s whenever it stops
python app.py terminal-agent status    # installed, running, pid, number of starts
python app.py terminal-agent uninstall # stop it and remove the launchd job
```

* The agent is `~/Library/LaunchAgents/com.quantengine.terminal.plist`. It runs the same `app.py terminal --port 8765` and
  reads `.env` through a login shell; no key is written into the plist.
* While it is installed, `pkill` or Ctrl+C does not keep the server down: launchd starts it again. To stop it for a while use
  `launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.quantengine.terminal.plist` (it comes back at the next login), or
  `uninstall`. To load new code: `launchctl kickstart -k gui/$(id -u)/com.quantengine.terminal`.
* Logs, in `data/terminal/logs/`:
  * `launchd.log`: start-up messages, replaced when over 1 MB;
  * `server_errors.log`: unexpected request errors with tracebacks, `.env` values and e-mail addresses removed, rotated at
    1 MB (3 kept). The status line at the bottom of the screen shows "서버 오류 N건" when there are any since the last start.
* The automation line on the 모델 tab (US view) shows whether auto-restart is on.

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
| `docs/DATA_INPUT_SPECIFICATION.md` | approved input definitions, version `P6-20-A` (SEC timestamp eligibility, P/B cross-check, total revenue, net margin, ADV20, sector, gating); each run records its version |
| `docs/GIT_SETUP_REPORT.md` | local git setup, ignored files, secret scan, how to add a private remote later |
| `tracking/excluded_runs.json` | P6-19 exclusion list (preserved; mirrored into `tracking/ledger/events.jsonl`) |
| `runs/KR/<run_id>/` | KR runs: manifest, status, `validation_result.json`, `candidate_flow.json`, `universe_snapshot.csv.gz`, `report.md` |
| `tracking/kr/` | KR ledger, price snapshots, outcomes, `reports/latest.html` (KRW) |
| `data/kr/` | KRX KIND security-master snapshots (with source sha256) and KR OHLCV caches |
| `tracking/STORAGE_SCHEMA.json` | storage layout version 2 (additive; backup in `~/Developer/qse-backups/`) |
| `tracking/dashboard.html` | unified read-only dashboard (`python app.py dashboard`) |
| `terminal/` | personal terminal (TERMINAL-1): `services.py` data screens, `sources.py` Yahoo/SEC/FRED access, `server.py` local server, `static/` Korean UI |
| `data/lab/` | lab price panel, challenger ledger, membership cache, research cache (local, ignored by git) |
| `data/terminal/` | terminal cache, watchlist, trade journal `journal.jsonl` and risk settings (local, private, ignored by git) |
| `reports/` | phase reports, roadmap, test results |
| `reports/legacy/` | early P3 reports and outputs that used to sit at the project root |
| git tag `legacy-before-cleanup-2026-11-08` | the last commit holding the P3/P5/P6 research code (`entity/`, `providers/`, `research/`, `scripts/run_p*`, ...) and its tests, removed on 2026-11-08 because nothing the program runs used them; `git checkout <tag> -- <path>` brings a file back |

### Korean market in the terminal

A market switch at the top of the terminal (미국 | 한국) changes every tab. Typing a 6-digit code such as `005930`, or a Korean company name such as `삼성전자`, switches to Korea by itself.

- **Accounts:** the dollar and won accounts are calculated separately. Dollars can never pay for a Korean stock. Both live in the same `data/terminal/journal.jsonl`; a record of the Korean account carries `"market": "KR"`, and older records stay US. The portfolio tab also shows the total converted to won, which stays empty when a price or the exchange rate is missing.
- **Limits:** Korean long-term 1% risk and 20% weight; Korean swing 0.5% risk and 10% weight. All can be changed in 매매 보조.
- **Sell tax:** the Korean securities transaction tax (0.20% in 2026) is not added for you. Enter it with the broker fee in the fee field of a SELL record.
- **Paper trades kept by hand (모의 매매 tab):** a separate journal (`data/terminal/paper_journal.jsonl`) for trades you only want to try: put in paper money, record a buy and a sell at your own prices, and read what was paid, what came back, what the fees took and what was left. A buy or sell with an empty fee box gets Toss Securities' published fee with its own rounding (Korea 0.015% and 0.20% tax on sells; US 0.1%, none on orders of 10 dollars or less, SEC fee on sells), stored on the record with its parts. No slippage is assumed: the price is the one typed. It never reads or writes the real account, and no order is sent (`terminal/paper_trade.py`, `/api/paper-trade`). The automatic paper book under 점수 → 주문 계획·모의 장부 is a different thing: it follows the program's own plan.
- **Data:** prices from Yahoo (delayed), statements and filings from OpenDART (`OPENDART_API_KEY`), listings from KIND, macro from the Bank of Korea ECOS (`ECOS_API_KEY`).
- **ECOS key:** free from https://ecos.bok.or.kr/api/. Put it in `.env` as `ECOS_API_KEY=...` and restart the terminal. Without it the Korean macro cards read "데이터 없음"; the won/dollar card still works.
- **US only so far:** challenger models, the research lab and the P6-11B plan check. The 모델 tab shows KR-EXP-0.1 read-only, which is experimental and unvalidated.

### Long-term and swing positions

Every position is either 장기 or 스윙, and one ticker has one style at a time. Choose it on the first buy; a 구분 변경 record changes it later,
and the history stays append-only. The portfolio tab shows a table for each, and the 매매 보조 tab holds these settings:

| Setting | 장기 | 스윙 |
|---|---:|---:|
| Risk per trade | 2% | 1% |
| Maximum weight per stock | 25% | 10% |
| Suggested stop in the calculator | 5 ATR | 2 ATR |
| Target share of stock value | 70% | 30% |

* A stop is expected on both styles; a position without one raises a warning.
* The target compares tagged stock value only, so cash does not count as being off target. A gap over 10 points raises a warning.
* Each holding gets a QSF reading from its own profile. QSF is experimental, and no reading places an order.
* The daily Telegram summary carries 청산 검토, 투자 논리 무효, 비중 축소 검토, 일부 차익 실현 검토 and 시간 손절 재평가. 보유하며 재검토 stays on the screen.
* A swing's 30-session time limit counts from the day it became a swing.

### QSF 1.1 stock score (experimental)

The 점수 tab and `qsf` commands score a chosen stock from 0 to 100 under four separate profiles: `US_SWING_V1`, `US_LONG_TERM_V1`,
`KR_SWING_V2`, `KR_LONG_TERM_V1`. Each result shows the factors, coverage and confidence, hard gates, a holding plan, exit conditions
and what would change the label.

```bash
.venv/bin/python app.py qsf evaluate AAPL              # one stock, printed only
.venv/bin/python app.py --market KR qsf evaluate 005930
.venv/bin/python app.py qsf scan                       # full universe, appended to the ledger
.venv/bin/python app.py qsf validate                   # matured outcomes by score bucket
.venv/bin/python app.py qsf verify                     # ledger integrity
```

* **Not a validated signal.** A price-only historical check found no relation between score and later relative return
  (`reports/QSF_1_1_IMPLEMENTATION_REPORT.md`). A BUY label does not authorize a trade; the decision is yours.
* QSF is separate from the frozen P6-11B model. It imports nothing from the frozen core, and the two scores are never merged.
* Missing data lowers coverage and is never treated as 0. Snapshots are stored in `data/qsf/ledger/` as append-only, hash-chained
  shards. A shard recorded from bad data gets a VOID row and stays on disk.
* Exit code 3 from `qsf scan` means Yahoo has not finished the session yet; exit code 4 means price requests failed outright
  (no connection, or the Mac went to sleep mid-download), so the day may well be out. Either way nothing is recorded and the daily
  job retries at its next slot. The printed `reason`, `download` and `last_dates` say which. The daily job also notes on a failed
  step how long the Mac slept while it ran: a sleeping Mac only runs in short maintenance wakes, which on 2026-11-10 stretched a
  7-minute step to 2.5 hours and cut the US download. Keep the Mac awake (on power) around 07:10 KST.
* Korean validation (2026-11-10): the live Korean scores were replayed on 2019-2026 with point-in-time inputs
  (`terminal/qsf/research_kr_live.py`). The long score ranks stocks within the scanned universe but its top fifth did not beat the
  market; the swing score did not pass; the scanned universe itself (top 300 by traded value) lagged a market-value universe
  (`reports/QSF_KR_LIVE_REPLAY_RESULTS.md`, `reports/QSF_KR_UNIVERSE_TEST_RESULTS.md`). A swing challenger without the technical
  domain is recorded daily apart from the live score (`reports/QSF_KR_SWING_CHALLENGER_PROTOCOL.md`).
* Forward verdict of the live score (2026-11-11): `reports/QSF_LIVE_FORWARD_PROTOCOL.md` fixes, before any return exists, how the
  ledger's record will be judged: every recorded session, a Newey-West t, the five historical conditions plus a money condition,
  and the buy band's return against the index split into score effect and universe effect. One evaluation per market and strategy
  at a fixed sample (swing: 240 matured sessions; long: 756). `qsf live-forward-status` only counts sessions;
  `live-forward-evaluate-swing|long` refuses before the sample is full (`terminal/qsf/live_forward.py`). What that verdict can
  detect in a year is estimated in `reports/QSF_LIVE_FORWARD_POWER_2026_11_11.md` (strong effects only).
* Korean market-value universe challenger (2026-11-11): each session the day's 300 largest eligible stocks are scored with the
  live code by a scan that writes no live file, and stored apart (`terminal/qsf/kr_cap_universe.py`,
  `research_data/kr_cap_universe/`, inside the daily Korean forward step). One evaluation at 240 matured sessions
  (`reports/QSF_KR_CAP_UNIVERSE_PROTOCOL.md`). The avoid marks (high risk, weak fundamentals, financing) are read once at the same
  sample from records already kept (`reports/QSF_KR_AVOID_MARKS_PROTOCOL.md`, `terminal/qsf/kr_avoid_marks.py`).
* Korean technical domain, earlier window (2026-11-11): one confirmation run on 2012-2019 with the live scoring code on prices
  only (`terminal/qsf/research_kr_tech.py`). The swing technical domain's 20-session rank correlation was negative again and it
  cancelled the risk domain's ranking power (`reports/QSF_KR_TECH_EARLY_RESULTS.md`). Nothing live was changed.
* Past record next to the score (2026-11-11): the score tab shows, per strategy, what the stored one-run reports said (share of
  pairs the higher score won, top and bottom fifth, buy band, universe against market, verdict). It reads report files only
  (`terminal/qsf/track_record.py`, `/api/qsf/track-record`).
* Day-to-day stability: `qsf stability` compares consecutive sessions of one model version in the ledger (rank correlation,
  band changes, buy-band turnover). No price is read (`terminal/qsf/stability.py`).
* Fundamental inputs (QSF-1.1.9, after `reports/QSF_FUND_INPUT_AUDIT_2026_11_11.md`): every figure is the latest fiscal year's or
  empty, a ratio needs both ends in that year and growth needs the year exactly before; PER keeps reported EPS while its share
  count is today's and is market value over parent profit otherwise; EPS growth is never taken across two share bases; Korean
  EPS is read from its continuing and discontinued parts when no total line exists; statements in another currency are not set
  against the won price; holding companies of industrial groups and US exchanges, health plans, insurance brokers and real
  estate firms are scored as non-financial.  Extracted series moved to the cache keys `annual3` and `krfund3`
  (`terminal/qsf/fundamentals.py`, tests in `tests/test_qsf_fund_inputs.py`).
* Korean swing composition (QSF-1.2.0, 2026-11-11, user decision): the technical domain no longer counts in the Korean swing score.
  It ranked stocks the wrong way round in three past windows (`reports/QSF_KR_TECH_EARLY_RESULTS.md`).  Its five factors are still
  computed, shown and stored as reference rows (`scored: false`, `reference_weight`), and chart position stays in the entry
  assessment (`holding.entry_status`).  The new composite itself was never scored on a past window: the former formula is recorded
  next to it every session (`terminal/qsf/kr_swing_prior.py`, `reports/QSF_KR_SWING_PRIOR_PROTOCOL.md`, one evaluation at twelve
  separate 20-session samples).  US scores and the Korean long-term score are unchanged.  The on-screen notice and the past-record
  table now carry the second Korean long-term window (2016-2019, not confirmed) next to the first.  `reports/QSF_KR_SWING_V2_2026_11_11.md`.
* Inputs, second pass (QSF-1.2.1, after the same audit): US debt is long-term debt, its current part and short-term borrowings,
  added by what each SEC tag already holds, and a US company without a debt figure has none instead of total liabilities; annual
  figures are STALE once a newer report is overdue (12 months + 90 days + 14); financial companies have no cash-flow-to-profit
  ratio; Korean companies whose year does not end in December are read up to their newest business year.  The Korean
  `credit_liquidity` factor reads the 3-year AA- corporate spread over the treasury yield from the Bank of Korea (ECOS 817Y002).
  Extracted US series moved to the cache key `annual4` (`tests/test_qsf_inputs_2.py`, `reports/QSF_INPUTS_2_2026_11_11.md`).
* Earnings date estimate (QSF-1.3.1, 2026-11-11, user decision): when Yahoo shows no upcoming earnings date (most Korean stocks,
  about half of the US ones after a report), the date is estimated as the same quarter a year on from the company's own past
  dates: SEC 8-K item 2.02 filings, DART preliminary results or periodic reports (`terminal/qsf/earnings_estimate.py`).  An
  estimate is labelled, blocks a new swing entry from five sessions ahead and while it is overdue, and fills the
  `earnings_calendar` factor.  It was within 7 days for 96% of Korean and 90% of US events in the check; nothing says the rule
  earns anything (`reports/QSF_EARNINGS_DATE_RESEARCH_2026_11_11.md`, tests in `tests/test_earnings_estimate.py`).
* Korean universe (QSF-1.3.0, 2026-11-11, user decision): the live Korean scan scores the 300 largest companies by market value
  on the newest KRX day on file (`config.KR_UNIVERSE`, `QSF.kr_market_cap_universe`), instead of the 300 most traded.  The former
  universe lagged the market by 15 to 24 points a year in two separate past windows; the market-value figures come from one
  exploratory test and the score's rank evidence is weaker there, which the notice and the past-record table now say.  The former
  universe is still chosen by its own rule and scored every day as a separate record with one evaluation after 240 matured
  sessions (`terminal/qsf/kr_traded_universe.py`, `reports/QSF_KR_TRADED_UNIVERSE_PROTOCOL.md`), and the score tab shows its
  newest day read only (`terminal/qsf/kr_cap_view.py`, `/api/qsf/former-universe`).  `reports/QSF_KR_UNIVERSE_SWITCH_2026_11_11.md`.
* Three reliability layers (2026-11-12, user decisions).  **Look-ahead audit and walk-forward order:** every day each function that
  turns past prices into a recorded or shown value is run on the prices as they are and on copies whose later rows are wiped or
  multiplied; any difference is a read of the future, and an outcome function is run as a control that must be caught
  (`terminal/qsf/lookahead.py`, `qsf lookahead-audit`, `/api/qsf/lookahead`).  The audit also reads every forward store's hash
  chain.  `terminal/qsf/walkforward.py` holds the order in which anything fitted may learn: only from days whose outcome had ended.
  **Regime weights (challenger):** three market states from the index alone, domain weights leaning toward what ranked well in
  that state before.  The one walk-forward run was NOT_SUPPORTED in both markets (Korea difference -0.0025, t -0.49; US -0.0010,
  t -0.26), so the live score is unchanged; the frozen table is recorded every day from session 2026-11-12 and read once at 240
  matured sessions, figures only (`terminal/qsf/regime_weights.py`, `reports/QSF_REGIME_WEIGHTS_PROTOCOL.md`,
  `reports/QSF_REGIME_WEIGHTS_RESULTS.md`).  **Order plan and paper book:** no order is sent anywhere.  The plan takes the stocks
  the program reads as enterable now in score order and sizes each by the tightest of risk per trade, position weight, style
  sleeve, sector weight, cash and 1% of the stock's traded value; a held or already planned stock gets no second order
  (`terminal/qsf/order_plan.py`, `/api/qsf/order-plan` for the recorded account).  The paper book follows that plan mechanically
  on made-up accounts of 10,000,000 won and 10,000 dollars: fills at the next open unless the open is above the limit, exits by
  stop, target, 30 sessions (swing) or a long score under 40, each session written once and chained, one writer at a time
  (`terminal/qsf/paper_book.py`, `research_data/paper_book_kr|us`, `reports/PAPER_BOOK_RULES.md`).  It is a reference before any
  verdict, never evidence about the score.  **Costs** are Toss Securities' published fees (QSF-1.3.2): US 0.1% each way plus the
  SEC fee on sells, Korea 0.015% plus the 0.20% sell tax; slippage is an estimate (assumed spread plus a square-root impact by
  order size) and is labelled as one.
* Own trading method KR-M1 and the Korean risk grade (2026-11-11, user decision): a challenger kept apart from the live score.
  Stocks with an avoid mark are dropped, the top fifth of the rest by the live swing score is the pool, and seven chart entries
  plus two baselines are followed with one exit rule (stop 2 ATR, target 3 ATR, ten sessions, 0.53% round trip).  The one
  selection run on 2019-2026 named no primary: after costs every entry and both baselines sat near or below zero
  (`reports/QSF_KR_METHOD_SELECTION_RESULTS.md`).  All nine are still recorded every day from session 2026-11-11
  (`terminal/qsf/kr_method.py`, `research_data/kr_method`, `reports/QSF_KR_METHOD_PROTOCOL.md`), shown under 추적·검증 as
  "판정 전 참고", with figures reported once at 120 and at 240 matured signal days.  The risk grade answers a different question,
  which stock swings and loses more over the next 20 sessions; its one test passed (rank correlation with realized volatility
  +0.51 in the largest 300, `reports/QSF_KR_RISK_GRADE_RESULTS.md`, `terminal/qsf/kr_risk_grade.py`).  It is shown on the stock
  detail as a reference and feeds no score, rank, limit or stop.
* Statement keep-time (2026-11-11): extracted US annual statements are kept 20 hours, so a new 10-K is scored at the next
  morning's run instead of up to seven days later; a failed SEC read keeps the stored copy.  Korean statements keep seven days
  (`TTL["facts"]`, `TTL["kr_facts"]` in `terminal/qsf/service.py`, tests in `tests/test_qsf_statement_keep_time.py`).
* Korean daily bars (QSF-1.1.8): built from the KRX daily snapshots in `research_data/krx` by chaining each day's official change
  rate, which already allows for splits; Yahoo is used only for days KRX has not published yet and for its dividend ratio
  (`terminal/qsf/kr_bars.py`, cache `data/qsf/krx_panel.npz`). `qsf price-audit` checks the bars the scores read
  (`reports/QSF_PRICE_AUDIT_2026_11_09.md`).
* Korean scan safeguards (2026-11-11): a stored download of Korean bars is reused only when at least 80% of its symbols have a
  bar on the session being scored, otherwise it is downloaded again; a whole-market Korean scan with fewer than 200 stocks is not
  recorded (`UNIVERSE_TOO_SMALL`) and waits for the next run (`markets/kr/acquisition.py`, `tests/test_kr_stale_cache.py`,
  `reports/QSF_KR_PARTIAL_RECORD_2026_11_11.md`).

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
| The terminal page does not open | Run `app.py terminal-agent status`. If it is not installed, start it with `app.py terminal` or install the agent. If it is running but the page fails, read `data/terminal/logs/launchd.log` and `server_errors.log`. |
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
