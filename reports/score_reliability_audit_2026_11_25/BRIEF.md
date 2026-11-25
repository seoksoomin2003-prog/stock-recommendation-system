# Brief for every agent — score reliability and predictive accuracy audit (2026-11-25)

You are one specialist of an independent quantitative research team auditing the scoring system of a personal stock recommendation
program.  The chief (the session that started you) coordinates.  Read this whole file before anything else.

## What is being audited
- Repository: `~/Developer/quant-stock-engine` (Python 3.14 in `.venv`, vanilla JS terminal in `terminal/static/`).  Start every shell
  command with `cd ~/Developer/quant-stock-engine;`.  Code version: commit `a77dbd2` (main).
- The score: QSF, four profiles (US/KR × SWING/LONG_TERM), `config.MODEL_VERSION = "QSF-1.6.0"`, wording rules `RULES_VERSION = "R-2"`.
  Code under `terminal/qsf/` (`config.py`, `factors.py`, `engine.py`, `service.py`, `fundamentals.py`, `technicals.py`, `holding.py`,
  `ledger.py`, `validate*.py`, `live_forward.py`, `calibrate.py`, `lookahead.py`, `inventory.py`, `backtest_current.py`, ...).
- A second, separate frozen model (P6-11B, "MODEL_RANK_E") exists in the repository.  It is NOT the subject.  Do not audit it, and
  never merge the two.
- One user, personal use, no order execution.  No SaaS, no live trading.

## The user's decision on returns (2026-11-25, binding)
**No new return is computed in this audit.**  The stored history has been read eight times (US 2014-2026) and four times (Korea
2019-2026); no untouched window is left; the user decided today that the backtest is not rerun or sliced further and that candidate
formulas are not tried on the historical replay (`reports/QSF_AFTER_VERDICT_RULES_2026_11_25.md` section 3).  Therefore:
- You may NOT compute a return, an IC, a spread, a hit rate or any outcome statistic from prices, from the stored research panels
  (`data/qsf/research/*.npz`, `research_data/**`) or from the forward records (the ledger's outcomes, `research_data/*` stores,
  comparison books).  You may not rerun or re-slice any backtest.  You may not peek at forward records' outcomes.
- You MAY: read every recorded result file and document (`reports/*.md`, `reports/qsf/*.json`) and do arithmetic on the numbers in
  them (say so); run experiments that need no return (score, rank, weight, normalisation, missing-data, redundancy, reproducibility,
  stability experiments on stored scores and recorded factor values); run random-number simulations (say the assumptions); read code.
- Where the master prompt asks for something that needs a new return (walk-forward of an alternative, a new baseline backtest, a
  holdout test), write `UNVERIFIED` with the exact reason and what forward record or protocol would settle it.  Never invent a figure.

## Material that needs no return
- Recorded factor values per stock and day: the QSF ledger (`terminal/qsf/ledger.py`; `Ledger(Path("."))._live_rows()` and
  `_load(row)` give each session's snapshots with `factors` rows: factor, domain, weight, status, raw, normalized, contribution).
  `terminal/qsf/order_plan.session_snaps(led, market, session)` reads one session.  Sessions exist from 2026-11-03.  Read-only.
- The day's stored scan: `data/qsf/latest_US.json`, `latest_KR.json`.
- Scores of the current formula on the historical dates (scores only, no returns inside): `data/qsf/research/scores_current_us.json.gz`,
  `research_data/krx_live/scores_current_cap.json.gz`.  You may use the scores (distributions, stability over time, turnover of the
  top group, sector make-up) but not join them to prices.
- Recorded results: BT-1 `reports/qsf/QSF_BACKTEST_CURRENT_{US,KR}.json`, its protocol and `reports/QSF_BACKTEST_CURRENT_ERRATA.md`;
  earlier tests `reports/QSF_*RESULTS*.md`, `reports/qsf/*.json`; the factor inventory `reports/QSF_FACTOR_INVENTORY.md`
  (`terminal/qsf/inventory.py`); the freeze `reports/QSF_FORMULA_FREEZE_2026_11_25.md`; today's rules
  `reports/QSF_RULES_R2_2026_11_25.md`, `reports/QSF_AFTER_VERDICT_RULES_2026_11_25.md`; live verdict protocol
  `reports/QSF_LIVE_FORWARD_PROTOCOL.md`; earlier audits `reports/maturity_assessment_2026_11_25/`, `reports/audit_2026_11_22_master/`;
  today's debate `reports/reliability_debate_2026_11_25/`.
- **Earlier audits and the debate are hypotheses, not findings.**  Check what you use against code and result files.  Where you
  agree after checking, cite the primary file, not the earlier audit.

## Hard rules
1. Read-only on the system: change no file outside `reports/score_reliability_audit_2026_11_25/`.  Your scripts and outputs go in
   `reports/score_reliability_audit_2026_11_25/scratch_<YOUR_AGENT_NUMBER>/`.  No commit, no push, no server restart, no daily job,
   no `python app.py ... evaluate`/`record`/`scan` command (many of them write records).  No network download.
2. Never read or print `.env`, `data/terminal/phone_view.json`, any API key or token, the Telegram token, or the SEC user-agent email.
   Do not print the user's capital or money amounts from portfolio, journal or order-plan data.  Write `~` for the home directory.
3. Do not run the whole test suite (it takes 18 minutes and its guard reacts to files written under `reports/`).  Single test files
   are fine when they prove a point.
4. Forward record files are not edited, deleted or read for outcomes.
5. Not investment advice; labels are rule results.  Do not present the committee's five investor engines as real investors' opinions.
6. Every material finding is classified `VERIFIED` / `PARTIALLY VERIFIED` / `UNVERIFIED` / `FAILED` / `NOT APPLICABLE`, with the file
   and line or the result file and key it rests on.  Say which numbers are (a) read from a file, (b) arithmetic on file values,
   (c) your own count or no-return experiment, (d) random-number simulation.

## Output
- Write your report in **Korean** (plain, short sentences; the reader is the owner, not a quant) to
  `reports/score_reliability_audit_2026_11_25/<the file name the chief gave you>`.  Aim for 2,000-3,500 words; tables for figures.
- End the report with a section "점수표 제안": for each scorecard category in your area (the chief's message names them), a point
  proposal as a range out of the category's maximum, the two facts that decide it, and your confidence in the evidence
  (높음 / 보통 / 낮음).  A category that cannot be judged is `UNVERIFIED`, not a number.
- Hand back a short summary (under 250 words): the three most important findings, your scorecard proposals, and anything you could
  not do.

## Two scorecards (the chief fills them; you propose only your categories)
A. Score reliability /100: mathematical and implementation correctness 20 · factor economic and statistical validity 20 · weighting
and normalisation reliability 15 · score and ranking stability 15 · data quality and point-in-time integrity 20 · reproducibility
and interpretability 10.
B. Predictive accuracy /100: historical data and backtest integrity 20 · cross-sectional ranking power 20 · forward return
performance 20 · out-of-sample and walk-forward robustness 20 · risk-adjusted and benchmark-relative performance 10 · statistical
significance and stability 10.  No points for a backtest module existing; points for valid method and reproducible evidence.
