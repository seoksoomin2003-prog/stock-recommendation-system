# Brief for the specialist agents (maturity assessment, 2026-11-23)

You are one of eight independent specialists assessing how mature this program is as ONE person's stock research and
decision-support tool. It is not a commercial product: do not ask for multi-user features, billing, cloud scale or
compliance certificates. Judge whether it helps its single user make better-informed decisions.

## The system
- Repository: `~/Developer/quant-stock-engine` (commit `02aed81`). Python 3.14 in `.venv` (`.venv/bin/python`). About 39,000 lines, 158 test files.
- A local web terminal (`terminal/server.py`, screens in `terminal/static/`) on free public data only: Yahoo (prices, company record),
  SEC EDGAR (US statements, filings), DART and KRX (Korea), Bank of Korea, FRED, Binance public data (coins).
- The score: "QSF", model version `QSF-1.5.1` (`terminal/qsf/config.py`, `engine.py`, `factors.py`, `fundamentals.py`, `technicals.py`).
  Four profiles: US and KR x SWING and LONG_TERM. Workflow A = the daily scan (`QSF.scan` in `terminal/qsf/service.py`, run by
  `terminal/automation.py`); workflow B = one ticker (`QSF.evaluate`). Records go to an append-only ledger (`terminal/qsf/ledger.py`,
  `data/qsf/ledger/`). The newest recorded session is 2026-11-20, recorded under QSF-1.4.1; no session has been recorded under 1.5.1 yet
  (the first will be 2026-11-23).
- Beside the score: entry status and holding plan (`holding.py`), order plan and paper book (`order_plan.py`, `paper_book.py`), market
  state (`engine.market_state`), a stance setting per market (`terminal/qsf/stance.py`), five investor-style rule engines, a committee
  and six paper portfolios (`terminal/committee/`), a rule-based assistant and analyst note (`terminal/assistant.py`,
  `analyst_extra.py`, `analyst_more.py`), plain-language explanations (`terminal/plain.py`), alerts, a portfolio journal with three
  accounts and a unified account page (`terminal/portfolio.py`, `Terminal.account`), a phone door (`terminal/phone_view.py`).
- Research and validation: `terminal/qsf/validate.py`, `research_*.py`, forward records under `research_data/`, pre-registered
  protocols `reports/*PROTOCOL*.md`, results `reports/*RESULTS*.md` and `reports/qsf/*.json`, scheduled one-time readings
  (`terminal/qsf/readings.py`, `live_forward.py`, `calibrate.py`).
- An older, frozen model (P6-11B, `core/`) exists beside QSF. It is out of scope except to note that it exists.

## An earlier assessment exists. Do not lean on it.
`reports/maturity_assessment_2026_11_22/` holds an assessment of commit `b5ca247` made one day ago (50.7 of 100). Eleven commits
followed it (`git log --oneline b5ca247..02aed81`): fixes of its P0 items and QSF-1.5.1 (`reports/QSF_1_5_1_2026_11_22.md`), the
readings, a Korean price-source label and error texts, the phone door, the stance setting and plain explanations, the unified
account and a third (coin) account, and new rules for the six portfolios. Its outcome table is at the end of
`reports/maturity_assessment_2026_11_22/PRIORITIZED_IMPROVEMENT_ROADMAP.md`.
- You may read the earlier report of your own role to know what was looked at. It is NOT evidence. Score from what you verify today.
- For each earlier finding in your area that decided the earlier score, say in one line whether it is FIXED, STILL OPEN or CHANGED,
  with today's file:line. A fix that only changed wording is not a fix of the underlying limit: say which it is.
- Look just as hard at the eleven new commits: new code written in a day is where new defects are. Do not assume it works.
- Other orientation documents, also not evidence: `reports/RUNBOOK.md`, `reports/DECISIONS_FOR_USER.md`, `reports/audit_2026_11_22_master/`.

## Hard rules (the owner's standing rules; breaking one invalidates your work)
1. READ ONLY. Do not change any file of the repository except: your own deliverable, and scratch scripts and their outputs under
   `reports/maturity_assessment_2026_11_23/evidence/<your agent folder>/`. No git commands that write (no add, commit, checkout, stash).
   Never name a script `test_*.py` (the test runner would collect it). Put any saved reply or output larger than 60 KB in your
   folder's `big/` sub-folder (it stays out of the repository).
2. Do not read, print or copy `.env`, API keys, tokens, e-mail addresses or the capital amount. Do not print money amounts from the
   portfolio journal or paper trades. Do not read or print `data/terminal/phone_view.json`.
3. No requests to outside data providers and no downloads. Do not run scans, `python app.py automation ...` (except `automation status`,
   and then drop any line containing "capital"), `qsf scan`, any `*-record` or `*-evaluate` command, or anything else that writes records.
4. Do NOT compute any return, IC or performance figure from the ledger, the forward records or price history. The project's
   pre-registration rules forbid re-testing windows already used and reading forward records before their day. You may read the
   recorded result files of tests that were already run, and you may simulate on random numbers.
5. Do not run the full test suite (the chief evaluator ran it on this commit: 2,065 passed, 6 skipped, 3 expected failures). You may
   run a few individual test files with `.venv/bin/python -m pytest -q -p no:cacheprovider tests/<file>`.
6. The machine has 8 GB and seven other agents are working at the same time: keep scripts small (read one ledger session at a time,
   never all), start no servers, do not use the browser pane. The terminal server is already running at `http://127.0.0.1:8765`; you may
   send it a small number of GET requests to see real outputs (routes are listed in `terminal/server.py`). NEVER POST: a POST can write
   the journal, the stance, the watchlist, the alert rules or open the phone door. At most three calls to
   `/api/qsf/evaluate?t=<ticker>&market=<US|KR>` (each one makes the server ask the providers). Do not call
   `/api/committee/portfolios` or `/api/committee/place` more than once each.
7. A script that builds `Terminal` or `QSF` must first run
   `from utils import runtime_config; runtime_config.load_local_env(<repo>/".env")` and must not print the environment. Prefer reading the
   ledger directly: `from terminal.qsf.ledger import Ledger; led = Ledger(repo); rows = [r for r in led._live_rows() if r["market"] == "US"];
   snaps = led._load(rows[-1])` (each snapshot has score, band, actionability, coverage, confidence, domains, factors with raw values).
   To see what today's code makes of the stored inputs without any provider: a `QSF` whose `src` raises on every call, as
   `reports/maturity_assessment_2026_11_22/evidence/fixes/dump_cards.py` does (`scan(record=False, publish=False)`).
8. Never invent a feature, a test result, a return or a coverage figure. Classify every claim as VERIFIED (you ran it or read the code
   path end to end), PARTIALLY VERIFIED, UNVERIFIED, FAILED or NOT APPLICABLE, and say how you verified it (file:line, command, output).
9. Feature existence is not maturity; passing tests are not investment validation; complexity is not quality; unknown is not complete.

## What to deliver
- One Markdown file, written in KOREAN in plain sentences (labels such as VERIFIED may stay in English), at the path given in your task.
  Structure: (1) what you inspected and how, (2) answers to your required questions, one by one, each with evidence and a
  classification, (3) confirmed strengths, (4) weaknesses and missing capabilities, each with severity and whether it affects
  investment outputs, (5) what became of the earlier assessment's findings in your area (FIXED / STILL OPEN / CHANGED) and what is new
  since, (6) your proposed score for your category on the 0-100% maturity scale below with a short justification and an
  evidence-confidence rating (HIGH / MEDIUM / LOW), (7) what you could not verify, (8) improvement priorities (P0 to P3), without
  recommending rewrites or commercial features.
- Maturity scale: 0-20% fundamentally incomplete; 21-40% early; 41-60% functional (works in ordinary cases, lacks validation or
  robustness); 61-80% mature (substantially implemented, tested, reliable for personal use); 81-90% highly mature (well validated,
  robust, consistently useful); 91-100% exceptional (strong empirical evidence). Be strict. Do not reward effort or feature count.
  A day of fixes does not by itself move a score: say what the fixes changed for the user's decisions and what they did not.
- Your final message to the chief evaluator (in English, under 400 words): the proposed score and confidence, your five most
  important findings with file:line, anything in an earlier document that you found to be wrong or outdated, and what you did not verify.
- Aim to finish in about 25 minutes of work. Depth on the questions that decide your score matters more than breadth.
