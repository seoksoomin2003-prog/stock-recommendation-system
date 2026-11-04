# P6-23 Implementation Report: Independent KR Model (`KR-EXP-0.1`, EXPERIMENTAL)

Date: 2026-11-04 · Status: **IMPLEMENTED; EXPERIMENTAL (not validated)**.

Specifications:

- `KR_MODEL_RESEARCH_SPECIFICATION.md`;
- `KR_MODEL_SPECIFICATION.md`.

## Research (pre-registered; `research/kr_factor_study.py`)

- Data: 27 non-overlapping 20-session periods (2024-03 → 2026-09) on today's liquid-300.
- Kept: MOM_6_1, REV_1M, LOWVOL_60, with equal weights.
- Dropped: TREND_50, as redundant with REV_1M (rank correlation −0.85).
- **No factor had |t| > 1.** There is no evidence of predictive power, and the model is not presented as having any.
- Study runtime: 1,152 s wall; peak RSS 272 MB.

## Live run (full liquid-300): `20261104T141806Z_kr_market_scan_c4ed3d`

Status **REAL RECOMMENDATION** (full scope, data complete). Capital 10,000,000 KRW (validation figure). 74 s (universe cache from the same KST day; 300-symbol history fetched); peak RSS 213 MB.

| # | Code | Company | Market | Score | Close (KRW) | Shares |
|---|---|---|---|---|---|---|
| 1 | 001820 | 삼화콘덴서공업 | KOSPI | 1.429 | 98,700 | 10 |
| 2 | 095610 | 테스 | KOSDAQ | 1.409 | 106,100 | 9 |
| 3 | 009150 | 삼성전기 | KOSPI | 1.172 | 1,115,000 | **0** (unfunded) |
| 4 | 066570 | LG전자 | KOSPI | 1.076 | 146,300 | 6 |
| 5 | 000500 | 가온전선 | KOSPI | 1.012 | 242,500 | 4 |
| 6 | 222800 | 심텍 | KOSDAQ | 0.975 | 123,000 | 8 |
| 7 | 080220 | 제주반도체 | KOSDAQ | 0.930 | 63,200 | 15 |
| 8 | 078930 | GS | KOSPI | 0.892 | 78,900 | 12 |
| 9 | 119850 | 지엔씨에너지 | KOSDAQ | 0.858 | 32,750 | 30 |
| 10 | 036930 | 주성엔지니어링 | KOSDAQ | 0.857 | 167,100 | 5 |

- Industry exposure: at most 30% (전자부품 제조업, 3 names, which is the cap); no cap skips were needed. Cash: 1,513,500 KRW.
- **Finding:** 삼성전기 costs more per share than the 10% slice of 10M KRW. The position is kept: selection is independent of capital, and the signal is still tracked. From this run on, it is flagged `funded: false` / `unfunded_positions` and shown in the report as a capital warning (new test). The already-recorded run is unchanged, because the ledger is append-only.
- Other live runs:
  - bounded scan `…142045Z_kr_market_scan_432753` (limit 60): PARTIAL, not tracked;
  - live direct evaluation of 005930, 000660, 035720 and 999999: `…142038Z_kr_direct_evaluation_15ab1f` gave 삼성전자 rank 30, SK하이닉스 rank 26 and 카카오 rank 106 of 294 (all IN_UNIVERSE_SCORED), plus 999999 NOT_FOUND.

## Offline coverage (`tests/test_p6_23_kr_model.py`, 14 tests)

- Factor formulas, no look-ahead, NaN on insufficient history, winsorisation and constant handling.
- Reference standardisation not influenced by the evaluated row; deterministic tie-break.
- Industry cap, whole shares, cash, unfunded flag.
- End-to-end offline scan: deterministic, KR run directory only, EXPERIMENTAL label.
- Gating before normalisation; bounded runs never REAL or tracked; provider failure fails closed (state FAILED).
- Every evaluate verdict, including OUTSIDE_UNIVERSE_SCORED_AGAINST_REFERENCE.
