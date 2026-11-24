# Chief evaluator's decisions (2026-11-25, commit 73c7886)

Inputs: AGENT_01..08 and CROSS_REVIEW_01..06 in this folder. The full suite on 73c7886 was run by the chief: 2,270 passed,
6 skipped, 3 expected failures. Earlier totals: 50.7 (11-22), 50.5 (11-23).

## Final category scores (chief, after cross review)

| Category | Weight | Agent proposal | Chief score | Weighted | Confidence |
|---|---:|---:|---:|---:|---|
| Software architecture & engineering | 10 | 65 | 63 | 6.30 | MEDIUM |
| Data integrity & reliability | 15 | 67 | 63 | 9.45 | MEDIUM |
| Fundamental research quality | 15 | 48 | 46 | 6.90 | HIGH |
| Factor & scoring methodology | 20 | 42 | 41 | 8.20 | HIGH |
| Market regime & risk awareness | 10 | 57 | 55 | 5.50 | MEDIUM |
| Quantitative validation | 15 | 40 | 40 | 6.00 | HIGH |
| Investment decision usefulness | 10 | 58 | 55 | 5.50 | MEDIUM |
| Personal user experience | 5 | 60 (revised from 62 in CR-06) | 60 | 3.00 | MEDIUM |
| **Total** | 100 | | | **50.85 -> 50.9** | |

Level 2 (FUNCTIONAL RESEARCH TOOL, 40-54). Verdict: **BASICALLY FUNCTIONAL**.

Why the chief is lower than agents 1, 5, 4, 7:
- Architecture 65 -> 63: the new code of 11-24/25 added three filing-list paths with different cache lives (score 20 h, screen 1 h,
  filing watch uncached), a deal pin that switches off silently when the SEC list is missing (service.py:763-767, 815-819), a band rule
  changed inside version QSF-1.5.2, and a UTC-date bug in the Korean filing screen (service.py:668, the chief's own code of 11-24,
  confirmed). One real recorded session under 1.5.2 is weak evidence.
- Data 67 -> 63: Agent 5's own probe FAILED: quotes, chart, price fill and alerts call a bar REAL within 5 calendar days
  (services.py:18, 201-205, 707; price_fill.py:37); live case on KR Today tiles (KOSPI/KOSDAQ 11-23 beside KOSPI 200 11-24, all REAL,
  CR-06). Korean index input one session late in 7 of 8 sessions (Agent 4) and a KR card a session behind (Agent 1). Backup on the same disk.
- Regime 57 -> 55: new false statement on screen (Korean stance note stance.py:94 vs 157, confirmed by chief and CR-06), the Korean
  REGIME_SEVERE/REDUCE holding warning driven by a value MKT-1 found meaningless for Korea (holding.py:245-247).
- Decision 58 -> 55: CR-05 shows the score structure decides what the user sees: all 21 US swing buy-band cards are "wait" (reward/risk
  2 ATR / 3 ATR cap, CR-01 CONFIRMED), the only US swing "사도 됨" is a 보유·관찰 card, KR swing "enter now" cards are in downtrends;
  low-confidence KR cards get buy wording and "사도 됨" (CR-06); buyer described as the bought company (plain.py:151-160, confirmed);
  held-back cards stay ENTRY_NOW and in the order plan (CR-01).

## Cross-review corrections the reports must carry
- Rank stability under weight changes is NOT evidence of validity (CR-04 SUPPORTED by a rerun on random factors).
- Sector-neutral scoring: UNSUPPORTED (US recorded sector-neutral IC lower). Do not recommend it.
- Blocking long entry on PROFITABILITY_DOWN, value-trap / cyclical-peak rules, ROIC caps: UNSUPPORTED (CR-02). Display flags only.
- US capex tags and Korean missing fields (gross profit, interest, average shares, buybacks never extracted, fundamentals.py:140-143):
  MEASUREMENT FIXES, but they move scores, so they need the user's decision and a version bump; their direction is mixed (CR-02).
- "Dropping reward/risk gives 81 not 23 at 70+" is DESCRIPTIVE ONLY: it says the fixed 70 line has no defined meaning (CR-04).
- KR swing "picks downtrends": mechanism SUPPORTED, defect-for-returns UNSUPPORTED (recorded KR tests lean toward reversal) (CR-04).
- Agent 6's conclusions stand on point-in-time data; its "past figures optimistic" holds for returns and bands, not IC (CR-03).
- Protocol contradiction confirmed: QSF_LIVE_FORWARD_PROTOCOL.md:129/141 says blocked stocks leave the sample; live_forward.py:47 keeps them (CR-03).
- System Test A (CR-01): same inputs give the same output across scan and direct ticker; differences are revised bars (<=0.003),
  TECH (deal pin added after the scan, same version label) and EOG swing +2.13 (earnings date missing at scan time, found later).
  KOSPI close 4869.96 vs 4708.54 for "11-23" sits in index_trend (weight 0): market-state input only, likely the KR index lag.
- System Test E (CR-05): PARTIALLY VERIFIED, close to a pass; flaws: LOW-confidence DB손해보험 "no worries", 140410 growth 0/100 without
  figures, identical long invalidation conditions on every card. The ledger keeps no explanation text or entry reason.
- System Test G (CR-06): strong/stale/valuation-doubt handled; conflicting (005930) and insufficient-data (005830) fall short; missing
  data never stated as a strength but changes no conclusion.

## P0 (fix: output says something false or shows stale as current; no user decision needed unless noted)
1. Korean filing screen uses the UTC date (service.py:668): use the Korean date. (chief's own bug)
2. Price status by calendar days (services.py:18, 201-205, 707; price_fill.py:37): judge REAL/STALE by the market's last expected
   session, as the score path already does; KR Today tiles with different dates must say so.
3. Korean stance note (stance.py:94) says aggressive 1.5x is not used on adverse days; Korea has no brake (user decision 2026-11-16), so
   the sentence is false for Korea: fix the wording per market. (Whether Korea should hold 1.5x on its "나쁨" days is a user decision.)
4. plain.py:151-160 describes any deal filer as the company being bought: read the deal pin (and the assistant's wording in
   analyst_more.py:151-152) instead.
5. Deal pin follow-through: what_would_change (holding.py:283-301) and the swing plain stop/target ignore the pin; '사도 돼?' gives a generic
   reason; a missing SEC list switches the pin off silently (say "확인 못 함"); bands changed without a version label (ledger/version notice).
6. QSF_LIVE_FORWARD_PROTOCOL.md:129/141 contradicts live_forward.py:47: correct the document to the code (no verdict change).
7. Held-back cards stay ENTRY_NOW and in the order plan while '사도 돼?' says 기다림 (CR-01): the two must agree. USER DECISION which way.
8. LOW-confidence cards: plain.py never reads confidence ("걱정 없음"), buy verdict says 사도 됨, Today candidate list has no confidence
   column. Wording/display fix needs no decision; changing the verdict needs one.

## P1 (decision quality; most need the user's decision)
- Formula freeze rule before the first live verdict (Agent 6): 8 versions in 14 sessions; a version change mid-sample destroys power. USER DECISION.
- Reward/risk cap (2 ATR stop / 3 ATR target with no resistance) contradicts the swing entry rule by construction (CR-01): USER DECISION, score change.
- US capex tags (37 companies) and Korean missing statement fields: measurement fixes, version bump. USER DECISION.
- Korean REGIME_SEVERE/REDUCE on swing holdings driven by FX/credit (holding.py:245-247): USER DECISION.
- Filing list: one cache life for score, screen and watch; the watch should cover days the Mac slept (filing_watch.py:157).
- Show annual vs trailing-4-quarter gap and committee disagreement where the decision is made (card head, '사도 돼?').
- Backup on another disk (user's hands). Records on time (Mac asleep 4 of 14 KR sessions; none since 11-19).

## Do NOT build
Sector-neutral scoring; new sentiment indicators; value-trap or cyclical-peak rules without a test; more investor engines or portfolios;
any new score input before the formula-freeze decision; commercial features.
