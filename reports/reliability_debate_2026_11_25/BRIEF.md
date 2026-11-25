# Brief: how reliable is the score, and what would honestly raise that (2026-11-25)

The owner (one private investor, Korean) asked: run a backtest of the scoring algorithm, then have several agents assess the
score's reliability and debate ways to raise it, then do the reliability work.  You are one of five debaters.  The chief will
put the outcome to the owner, who decides.

## What you are judging
- Repository `~/Developer/quant-stock-engine`, Python in `.venv`.  The score is "QSF", version `QSF-1.6.0`
  (`terminal/qsf/config.py`, `engine.py`, `factors.py`, `fundamentals.py`, `technicals.py`), four profiles (US and KR x SWING and
  LONG_TERM).  Every factor with what it measures, why, its known limit and its recorded evidence: `reports/QSF_FACTOR_INVENTORY.md`.
- **The backtest just run (BT-1):** `reports/qsf/QSF_BACKTEST_CURRENT_US.json` and `reports/qsf/QSF_BACKTEST_CURRENT_KR.json`,
  rules `reports/QSF_BACKTEST_CURRENT_PROTOCOL.md`, code `terminal/qsf/backtest_current.py`.  It is the current formula on windows
  earlier tests already read; it is a description, not new independent evidence.  A plain-language table of it:
  `reports/reliability_debate_2026_11_25/BACKTEST_SUMMARY.md`.
- **Earlier recorded tests** (read their result files and reports, do not rerun anything): `reports/qsf/*.json`,
  `reports/QSF_*RESULTS*.md`, `reports/QSF_KR_LIVE_REPLAY_RESULTS.md`, `reports/QSF_KR_UNIVERSE_TEST_RESULTS.md`,
  `reports/QSF_CORRECTED_RECHECK_RESULTS.md`, `reports/QSF_PIT_VALIDATION_RESULTS.md`, `reports/QSF_MARKET_STATE_RESULTS.md` and others.
- **Today's independent assessment** (50.9 of 100; factor and scoring 43, validation 42 after a re-check):
  `reports/maturity_assessment_2026_11_25/` (`AGENT_03`, `AGENT_06`, `RECHECK_AGENT_03`, `RECHECK_AGENT_06`, `CROSS_REVIEW_04`).
- **Standing decisions of the owner you must know:** the score is frozen at QSF-1.6.0 until the first live swing verdict, about
  December 2027 (`reports/QSF_FORMULA_FREEZE_2026_11_25.md`); live verdicts and two early readings are pre-registered
  (`reports/QSF_LIVE_FORWARD_PROTOCOL.md`); comparison books and challenger scores are recorded beside the live score
  (`terminal/qsf/readings.py` lists all 36 scheduled readings).  The owner may lift the freeze: say plainly if you think that is
  right, and what it would cost.

## Hard rules
1. READ ONLY.  Write nothing but your own files in `reports/reliability_debate_2026_11_25/`.  No git commands that write.
2. Do NOT compute any return, IC or performance figure yourself from prices, the ledger or forward records, and do not rerun or
   re-slice any backtest: the windows are used up and every extra look is another chance to fool ourselves.  You may read every
   result file, and you may simulate on random numbers (for power, false positives, the effect of a proposed rule's mechanics).
3. No requests to outside providers.  Do not read `.env`, keys, account amounts, or `data/terminal/phone_view.json`.  Never POST
   to the server.  Start no servers.  Keep scripts small (the machine has 8 GB and four other agents are working).
4. Do not invent a result.  Cite the file (and line or key) for every number.
5. A proposal that would look better on the backtest you just read is exactly how a score gets overfitted.  For every proposal
   say: what mechanism makes it more reliable, what evidence on record supports or contradicts it, how it could be wrong, how it
   would be judged WITHOUT the used history (a forward record, a pre-registered reading), and what it costs (complexity, lost
   forward sample, another version).
6. "Reliability" here means: how far the owner can trust that a higher score means a better stock, and that the labels beside it
   (buy candidate, enter now, 사도 됨) mean what they say.  Engineering quality counts only where it changes that.
7. Be concrete and brief.  No generic best-practice lists.  Korean deliverables in plain sentences.

## Round 1 (your task message names your seat)
Write `reports/reliability_debate_2026_11_25/R1_<SEAT>.md` in Korean:
1. Your reading of the backtest in five lines: what it shows, what it cannot show.
2. A reliability rating of each of the four scores (US swing, US long, KR swing, KR long) on a scale you define in one line,
   with the two facts that decide each.
3. At most five proposals to raise reliability, ranked, each with the six points of rule 5 and a label:
   NO_SCORE_CHANGE (display, labelling, recording, process), RULE_CHANGE (bands, entry, plan; not the score), or SCORE_CHANGE
   (weights, factors, inputs: needs the freeze lifted).
4. What should NOT be done, and why.
Then reply to the chief in English, under 250 words: your ratings and your proposals in one line each.
