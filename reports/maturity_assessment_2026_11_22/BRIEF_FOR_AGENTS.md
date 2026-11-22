# Brief for the specialist agents (maturity assessment, 2026-11-22)

You are one of eight independent specialists assessing how mature this program is as ONE person's stock research and
decision-support tool. It is not a commercial product: do not ask for multi-user features, billing, cloud scale or
compliance certificates. Judge whether it helps its single user make better-informed decisions.

## The system
- Repository: `~/Developer/quant-stock-engine` (commit `b5ca247`). Python 3.14 in `.venv` (`.venv/bin/python`). About 35,000 lines.
- A local web terminal (`terminal/server.py`, screens in `terminal/static/`) on free public data only: Yahoo (prices, company record),
  SEC EDGAR (US statements, filings), DART and KRX (Korea), Bank of Korea, FRED.
- The score: "QSF", model version `QSF-1.5.0` (`terminal/qsf/config.py`, `engine.py`, `factors.py`, `fundamentals.py`, `technicals.py`).
  Four profiles: US and KR x SWING and LONG_TERM. Workflow A = the daily scan (`QSF.scan` in `terminal/qsf/service.py`, run by
  `terminal/automation.py`); workflow B = one ticker (`QSF.evaluate`). Records go to an append-only ledger (`terminal/qsf/ledger.py`,
  `data/qsf/ledger/`). The newest recorded session is 2026-11-20, recorded under QSF-1.4.1; the first session under 1.5.0 will be 2026-11-23.
- Beside the score: entry status and holding plan (`holding.py`), order plan and paper book (`order_plan.py`, `paper_book.py`), market
  state (`engine.market_state`), five investor-style rule engines and a committee (`terminal/committee/`), a rule-based assistant and
  analyst note (`terminal/assistant.py`, `analyst_extra.py`, `analyst_more.py`), alerts, portfolio journal (`terminal/portfolio.py`).
- Research and validation: `terminal/qsf/validate.py`, `research_*.py`, forward records under `research_data/`, pre-registered
  protocols `reports/*PROTOCOL*.md`, results `reports/*RESULTS*.md` and `reports/qsf/*.json`, scheduled one-time readings
  (`terminal/qsf/readings.py`, `live_forward.py`, `calibrate.py`).
- An older, frozen model (P6-11B, `core/`) exists beside QSF. It is out of scope except to note that it exists.
- Earlier documents you may read for orientation, NOT as evidence: `reports/audit_2026_11_22_master/` (an audit of commit `6aec1f1`,
  earlier today; many of its findings were fixed afterwards, see its `REMEDIATION_ROADMAP.md` section 6), `reports/QSF_1_5_0_2026_11_22.md`,
  `reports/RUNBOOK.md`, `reports/DECISIONS_FOR_USER.md`, `reports/AUDIT_5_TERMINAL_ENGINEER_2026_11_22.md`. Verify everything you
  rely on in the current code. Say explicitly when something an earlier document reported is now different.

## Hard rules (the owner's standing rules; breaking one invalidates your work)
1. READ ONLY. Do not change any file of the repository except: your own deliverable, and scratch scripts and their outputs under
   `reports/maturity_assessment_2026_11_22/evidence/<your agent folder>/`. No git commands that write (no add, commit, checkout, stash).
2. Do not read, print or copy `.env`, API keys, tokens, e-mail addresses or the capital amount. Do not print money amounts from the
   portfolio journal or paper trades (the terminal has no account recorded, keep it that way in your notes).
3. No requests to outside data providers and no downloads. Do not run scans, `python app.py automation ...` (except `automation status`,
   and then drop any line containing "capital"), `qsf scan`, any `*-record` or `*-evaluate` command, or anything else that writes records.
4. Do NOT compute any return, IC or performance figure from the ledger, the forward records or price history. The project's
   pre-registration rules forbid re-testing windows already used and reading forward records before their day. You may read the
   recorded result files of tests that were already run, and you may simulate on random numbers.
5. Do not run the full test suite (the chief evaluator runs it once and shares the result). You may run a few individual test files
   with `.venv/bin/python -m pytest -q -p no:cacheprovider tests/<file>`.
6. The machine has 8 GB and seven other agents are working at the same time: keep scripts small (read one ledger session at a time,
   never all), start no servers, do not use the browser pane. The terminal server is already running at `http://127.0.0.1:8765`; you may
   send it a small number of GET requests to see real outputs (routes are listed in `terminal/server.py`). Never POST. At most three
   calls to `/api/qsf/evaluate?t=<ticker>&market=<US|KR>` (each one makes the server ask the providers).
7. A script that builds `Terminal` or `QSF` must first run
   `from utils import runtime_config; runtime_config.load_local_env(<repo>/".env")` and must not print the environment. Prefer reading the
   ledger directly: `from terminal.qsf.ledger import Ledger; led = Ledger(repo); rows = [r for r in led._live_rows() if r["market"] == "US"];
   snaps = led._load(rows[-1])` (each snapshot has score, band, actionability, coverage, confidence, domains, factors with raw values).
8. Never invent a feature, a test result, a return or a coverage figure. Classify every claim as VERIFIED (you ran it or read the code
   path end to end), PARTIALLY VERIFIED, UNVERIFIED, FAILED or NOT APPLICABLE, and say how you verified it (file:line, command, output).
9. Feature existence is not maturity; passing tests are not investment validation; complexity is not quality; unknown is not complete.

## What to deliver
- One Markdown file, written in KOREAN in plain sentences (labels such as VERIFIED may stay in English), at the path given in your task.
  Structure: (1) what you inspected and how, (2) answers to your required questions, one by one, each with evidence and a
  classification, (3) confirmed strengths, (4) weaknesses and missing capabilities, each with severity and whether it affects
  investment outputs, (5) your proposed score for your category on the 0-100% maturity scale below with a short justification and an
  evidence-confidence rating (HIGH / MEDIUM / LOW), (6) what you could not verify, (7) improvement priorities (P0 to P3), without
  recommending rewrites or commercial features.
- Maturity scale: 0-20% fundamentally incomplete; 21-40% early; 41-60% functional (works in ordinary cases, lacks validation or
  robustness); 61-80% mature (substantially implemented, tested, reliable for personal use); 81-90% highly mature (well validated,
  robust, consistently useful); 91-100% exceptional (strong empirical evidence). Be strict. Do not reward effort or feature count.
- Your final message to the chief evaluator (in English, under 400 words): the proposed score and confidence, your five most
  important findings with file:line, anything in an earlier document that you found to be wrong or outdated, and what you did not verify.
- Aim to finish in about 25 minutes of work. Depth on the questions that decide your score matters more than breadth.
