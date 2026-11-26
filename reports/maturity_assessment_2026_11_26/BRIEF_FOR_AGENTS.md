# Brief for the specialist agents (institutional-grade maturity assessment, 2026-11-26)

You are one of eight independent specialists. The owner's master prompt asks: **"How complete and mature is this stock
recommendation platform, what level of trust does it deserve, and how far is it from becoming a genuinely professional-grade
investment research product?"** This is not a code review. Judge actual completeness, maturity, reliability, investment
intelligence, quantitative validity, operational readiness and practical usefulness. Do not assume maturity because there are many
features, a large codebase, a sophisticated-looking architecture, passing unit tests, a professional-looking dashboard, a score that
produces rankings, or completed milestones. Evaluate what exists, what works, what has been validated, what is incomplete.

Your task message holds your role, scope and deliverable. Do not produce generic feedback that any other agent would also write:
stay in your professional role and go deep on the questions that decide your score.

**The yardstick this time is a professional-grade investment research product** (what a buy-side research desk or a commercial
research terminal would accept), not "good for one hobbyist". Say plainly where the program is far from that bar. But the facts of
the program are what they are: it is one person's local tool on free public data, with no order execution. Do not recommend paid
data, cloud, multi-user features or rewrites as if they were small steps; name them as the distance to the bar, and separately
name what is achievable inside the owner's constraints (zero-cost data, one Mac, no broker).

## The system
- Repository: `~/Developer/quant-stock-engine`, commit `de1a250` plus uncommitted documentation edits (five files, numbers corrected
  after a recount; no behaviour change). Python 3.14 in `.venv` (`.venv/bin/python`). About 105,000 lines of Python and JavaScript,
  179 test files.
- A local web terminal (`terminal/server.py`, screens in `terminal/static/`) on free public data only: Yahoo (prices, company record,
  one-minute bars), SEC EDGAR (US statements, filings), DART and KRX (Korea), Bank of Korea, FRED, Binance public data.
- The score: "QSF", model version `QSF-1.6.0`, **frozen** until the first live verdict (about Dec 2027;
  `reports/QSF_FORMULA_FREEZE_2026_11_25.md`); display and rule wording version `R-2` (`reports/QSF_RULES_R2_2026_11_25.md`).
  Code: `terminal/qsf/config.py`, `engine.py`, `factors.py`, `fundamentals.py`, `technicals.py`. Four profiles: US and KR x SWING
  and LONG_TERM. Workflow A = the daily scan (`QSF.scan` in `terminal/qsf/service.py`, run by `terminal/automation.py`); workflow
  B = one ticker (`QSF.evaluate`). Records go to an append-only ledger (`terminal/qsf/ledger.py`, `data/qsf/ledger/`). The first
  sessions recorded under QSF-1.6.0 / R-2 are US and KR 2026-11-25 (written this morning).
- Beside the score: entry status and holding plan (`holding.py`), order plan and paper book (`order_plan.py`, `paper_book.py`),
  market state (`engine.market_state`), stance per market (`stance.py`), deal pin (`deal_pin.py`), figures-direction check
  (`terminal/fund_checks.py`), five investor-style rule engines with a committee and six paper portfolios (`terminal/committee/`),
  a rule-based assistant and Today screen (`terminal/assistant.py`, `analyst_extra.py`, `analyst_more.py`), plain explanations
  (`terminal/plain.py`), alerts, a journal with a unified account page (`terminal/portfolio.py`, `journal_yardstick.py`), chart
  analysis and a live minute chart, an intraday filing watch, a phone door, news headline records (no score).
- Research and validation: `terminal/qsf/validate.py`, `research_*.py`, `backtest_current.py` (BT-1), `live_forward.py`,
  `readings.py`, `calibrate.py`, `wording.py`, `lookahead.py`, `inventory.py`, comparison books (`turnover_book.py`, `rank_book.py`,
  `entry_book.py`, `fund_period.py`), `sector_archive.py`; forward records under `research_data/` and `data/qsf/`; pre-registered
  protocols `reports/*PROTOCOL*.md`; results `reports/*RESULTS*.md`, `reports/qsf/*.json`.
- An older, frozen model (P6-11B, `core/`) exists beside QSF. Out of scope except to note that it exists.

## Earlier assessments exist. Do not lean on them.
- Three "personal tool" maturity assessments: `reports/maturity_assessment_2026_11_22/` (50.7), `_2026_11_23/` (50.5),
  `_2026_11_25/` (50.9, commit `73c7886`, with a same-evening recheck). They used a different yardstick (one person's tool).
- A score audit: `reports/score_reliability_audit_2026_11_25/` (reliability 56/100, predictive accuracy 24/100) and its roadmap,
  whose P0-P3 items were then built (`git log --oneline 73c7886..HEAD`, 17 commits: formula freeze QSF-1.6.0, entry comparison
  book, early readings, BT-1 backtest of today's formula on used history with errata, a five-seat debate, rules wording R-2,
  after-verdict rules, notices cut to 15, apply buttons off, the audit's fixes, sector archive, persistence figure).
- You may read the earlier reports of your area to know what was looked at. They are NOT evidence. Score from what you verify
  today. For each earlier finding that decided an earlier score in your area, say in one line whether it is FIXED, STILL OPEN or
  CHANGED, with today's file:line. A fix that only changed wording is not a fix of the underlying limit: say which it is.
- Look just as hard at the newest code (written in the last two days): that is where new defects are.
- Orientation documents, also not evidence: `reports/RUNBOOK.md`, `reports/DECISIONS_FOR_USER.md`.

## Hard rules (the owner's standing rules; breaking one invalidates your work)
1. READ ONLY, and **write nothing inside the repository at all** (the full test suite is running and its guard fails when files
   appear under `reports/` or `data/`). Write your deliverable and every scratch script and output ONLY under
   `<scratch>/maturity_2026_11_26/`
   (deliverable in that folder, scratch files in `evidence/<your agent folder>/`). Run scripts with the repository as the working
   directory (`cd ~/Developer/quant-stock-engine; .venv/bin/python <absolute script path>`). No git command that writes. Never name a
   script `test_*.py`. Write the home directory as `~` in everything you save.
2. Do not read, print or copy `.env`, API keys, tokens, e-mail addresses or the capital amount. Do not print money amounts from the
   portfolio journal or paper trades. Do not read or print `data/terminal/phone_view.json`.
3. No requests to outside data providers and no downloads. Do not run scans, `python app.py automation ...` (except `automation
   status`, and then drop any line containing "capital"), `qsf scan`, any `*-record`, `*-evaluate`, `live-forward-*`,
   `backtest-current` or reading command, or anything else that writes records.
4. Do NOT compute any return, IC or performance figure from the ledger, the forward records or price history, and do not rerun or
   re-slice any backtest. Do not open forward-record outcome files before their reading day. You may read the recorded result
   files of tests that were already run (`reports/*RESULTS*.md`, `reports/qsf/*.json`), and you may simulate on random numbers.
5. Do not run the full test suite (the chief ran it at `de1a250`: 2,364 passed). You may run at most three individual test files:
   `.venv/bin/python -m pytest -q -p no:cacheprovider tests/<file>`.
6. The machine has 8 GB and seven other agents plus the test suite run at the same time: keep scripts small (one ledger session at
   a time), start no servers, do not use the browser pane. The terminal server runs at `http://127.0.0.1:8765`; you may send it a
   small number of GET requests (routes in `terminal/server.py`). NEVER POST. At most three calls to
   `/api/qsf/evaluate?t=<ticker>&market=<US|KR>`. Do not call `/api/committee/portfolios` or `/api/committee/place` more than once
   each. Do not call `/api/model`, `/api/qsf/top3`, `/api/account`, `/api/portfolio*`, `/api/paper*` or `/api/equity`: their
   replies carry capital, money amounts or forward-record performance that you must not see.
7. A script that builds `Terminal` or `QSF` must first run
   `from utils import runtime_config; runtime_config.load_local_env(<repo>/".env")` and must not print the environment. Prefer
   reading the ledger directly: `from terminal.qsf.ledger import Ledger; led = Ledger(repo); rows = [r for r in led._live_rows()
   if r["market"] == "US"]; snaps = led._load(rows[-1])`. To see what today's code makes of stored inputs without any provider,
   use a `QSF` whose `src` raises on every call, as `reports/maturity_assessment_2026_11_22/evidence/fixes/dump_cards.py` does
   (`scan(record=False, publish=False)`).
8. Never invent a feature, a test result, a return or a coverage figure. Classify every claim as VERIFIED, PARTIALLY VERIFIED,
   UNVERIFIED, FAILED or NOT APPLICABLE, and say how you verified it (file:line, command, output).
9. Feature existence is not maturity; passing tests are not investment validation; complexity is not quality; unknown is not
   complete. Distinguish "the infrastructure exists", "it works", "an experiment was run", "the result supports the product".

## What to deliver
- One Markdown file in KOREAN, plain sentences (labels such as VERIFIED stay in English), at the path in your task. Structure:
  (1) what you inspected and how, (2) answers to your required questions one by one, each with evidence and a classification,
  (3) confirmed strengths, (4) weaknesses and missing capabilities, each with severity and whether it affects investment outputs,
  (5) what became of earlier findings in your area and what is new since, (6) your proposed score for your category on the 0-100%
  maturity scale against the professional-grade bar, with a short justification and an evidence-confidence rating (HIGH / MEDIUM /
  LOW), and separately one line: the score you would give against the "one person's tool" bar, (7) what you could not verify,
  (8) distance to professional grade: what is missing, split into "achievable inside the owner's constraints" and "needs what the
  owner has ruled out (paid data, servers, staff)", (9) improvement priorities P0 to P3.
- Maturity scale: 0-20% fundamentally incomplete; 21-40% early; 41-60% functional; 61-80% mature; 81-90% highly mature; 91-100%
  exceptional (institutional standard). Be strict. Do not reward effort or feature count.
- Your final message to the chief (English, under 400 words): proposed score and confidence, your five most important findings
  with file:line, anything in an earlier document that you found wrong or outdated, and what you did not verify.
- Aim for about 25 minutes of work. Depth on the questions that decide your score matters more than breadth.
