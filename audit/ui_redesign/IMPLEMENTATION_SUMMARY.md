# Implementation summary — Institutional Research Workstation redesign

Status: implementation, regression QA, critique and one refinement round done; merged into main (fast-forward to 511e0b8) and deployed to the live terminal on 2026-11-24.

## 1. Owner decisions

| # | Question | Decision (2026-11-24) |
|---|---|---|
| U-1 | Reference image (QuantMSCI) | Did not arrive; proceed without it |
| U-2 | Up/down colours | Rule C of 2026-11-23 stays (Korean screens red up / blue down; US and unified account green up / red down); shades re-picked for the new palette |
| U-3 | Theme | Dark is the default; light theme and the ◐ toggle stay |
| U-4 | Main menu | Left vertical menu; the top bar keeps search, market state, data time and actions; drawer on narrow screens; phones keep the bottom bar |
| U-5 | Row click (O-2 / D1 / O-3) | From 1280 px a row click in ranking, screener and holdings fills the right panel; replaceState (no history entry); narrow screens expand in place as today |
| U-6 | Confirm windows (O-5 / O-6) | In-page confirm dialog replaces the five `confirm()` calls; a stance change shows an undo toast |
| U-7 | Account double-submit (O-9) | The double-submit bug is fixed; "방금 기록 취소" appends a VOID record (nothing is deleted) |
| U-8 | Extras | All applied: three new visuals (paper-book equity curve, score history broken at model changes, neutral \|r\| shading); saved "auto" theme moved to dark once; score summary on the stock screen (O-1); score heatmap on a neutral ramp |

Kept without asking: batch-6 judgement colours (purple / grey / amber) and blue as the accent.

Recommended defaults taken by the chief (from the specs, no owner question needed): O-4 "늦음" chip not now; O-7 deep links `#committee:view` and `#assist:section`; O-8 '사도 돼?' from the stock screen still opens 오늘; O-10 number keys follow the menu order; O-11 market chip hidden in COIN; D2 the screener score button stays on the screener; D3 top-bar chips read `/api/qsf/market-state` and `/api/automation/status`; D5 Today tiles in a top strip; D6 narrow-screen order changes as listed in the layout spec. Visualization owner items (a)–(c): moving-average lines use the per-market remap with direct end tags; the two lighter dark MA shades are accepted because every MA line carries an end label; the 파랑·주황 heatmap button gets a note on Korean screens.

## 2. Chief reconciliation of the four specifications

| Conflict | Design system | Layout | Decision |
|---|---|---|---|
| Left menu widths | 216 / rail 56 | 232 / rail 72 / drawer 264 | Layout spec (232 / 72 / 264). Token names from the design system (`--nav-w`, `--nav-w-rail`) carry the layout values |
| Right panel | `--right-w` 560 at ≥1600 | 360 / 420 / 480 by container query on the content column | Layout spec (container queries, because the menu width changes the space) |
| Rail range | 1024–1279 | Rail on ≥1024 by toggle; split at 1280–1439 only with the rail (D4) | Full menu by default ≥1280, rail 1024–1279, user toggle stored in `qse-nav` |
| Up/down shades | #22c55e / #f46a6a (intl), #f46a6a / #5b9cff (KR), contrast computed by hand | — | Visualization spec, validated with `validate_palette.js`: dark US #0FA05C / #E76250, dark KR #E76250 / #4C8DFF, light US #02721C / #C13A46, light KR #C13A46 / #1F5FD1 |
| Sticky offsets | warns `setTopH` breaks if the vertical menu keeps `.groups` sticky | — | `setTopH` is rewritten in stage 1 |

## 3. Implementation stages

Branch `ws-redesign` (worktree), one commit per stage after the full suite passes:

1. Tokens and shell (top bar, left menu, rail, drawer, bottom bar)
2. Shared components (workstation grid, tables, panels, confirm dialog, undo toast, chart helpers, colour-role corrections)
3. Dashboard (오늘, 시장 개요)
4. Ranking and screener with the right panel
5. Stock research
6. Market screens and charts (map, macro, chart analysis, compare) with the new visuals
7. Portfolio, account and the remaining screens
8. Responsive pass, regression, critique and refinement

Additional owner decisions in the refinement round (2026-11-24): at 1280–1439 px with no saved `qse-nav` the menu starts as the rail so two columns appear; above the ranking only the validation caveat line stays visible and the rest goes into a closed 읽는 법 fold.

## 4. Commits (branch `ws-redesign`, on top of main 7c8e0af)

| Stage | Commit | Content |
|---|---|---|
| 1 | b86d114 | Tokens, dark default (saved "auto" → dark once), top bar with market-state and data-time chips, left menu / rail / drawer, `setTopH` rewrite |
| 2 | 196cfe2 | `.ws` grid, dense tables and panels, raised-neutral segments, `uiConfirm`, stance undo toast, `viz*` chart helpers, colour-role corrections, MA end tags |
| 3 | 89cc966 | 오늘 and 시장 개요 as workstation screens |
| 4 | c6e2dad | 순위·카드 ranking and screener with the card in the right panel |
| 5 | 61e1a06 | 종목 정보 research screen with the recorded-scan score summary; 관심종목 |
| 6 | 8f955be | 시장 지도, 거시, 차트분석, 비교; shared chart hover; paper-book curve, score history, \|r\| shading |
| 7 | 35f18c1 | 통합 계좌, 시장별 자세히, 매매 보조, 모의 매매, 투자위원회, 모델, 연구실, 코인; account double-submit guard and "방금 기록 취소" |
| 8 | 511e0b8 | Refinement after FUNCTIONAL_REGRESSION_REPORT.md and VISUAL_CRITIQUE.md |

Whole branch: 35 files changed, +2738 / −639. No Python file changed; no score, ranking, regime or portfolio calculation changed; no API route added or removed (`server.py` unchanged).

## 5. Tests actually run

- Full suite after every stage, run by the chief in the worktree: 2222 passed (stages 1–6), 2232 passed (stage 7, +10 tests in `tests/test_ws_stage7.py`), 2242 passed (stage 8, +10 tests in `tests/test_ws_stage8.py`); each run also 6 skipped and 3 xfailed, 0 failed.
- `node --check` on every file in `terminal/static/` after stages 7 and 8.
- Pins changed on purpose are listed per stage in the commit messages and in the agents' reports; each keeps the old intent (e.g. native `confirm()` count → no native `confirm()` and five `uiConfirm`).

## 6. Screens actually captured and reviewed

- Chief (scratch server on port 8799 with real data, separate tab): 순위·카드 at 1440 and 1100 (rail) and 768 (drawer); 오늘 at 390, 1920 and 1280; 시장 개요 at 1440 in dark and light; 종목 정보 AAPL at 1440 (dark and light); 차트분석 KR at 1440; 순위·카드 KR at 1440; 시장 지도 at 1600 and 1440; 가상 장부 curve at 1600; 통합 계좌, 투자위원회, 매매 보조 at 1600; 순위·카드 with a card open at 1440 after the refinement.
- Agent 7 (visual critic): all 18 screens at 1440 dark; 오늘, 순위·카드 (four views) and 종목 정보 at 1440 light; 12 screens at 1920; four captures at 1280; four at 768; five at 390 — listed in VISUAL_CRITIQUE.md.
- Refinement agent: 순위·카드 with a card open at 1920, 종목 005930 at 1920, 순위·카드 with TECH card and 오늘 KR at 1440, 순위·카드 at 1280 with no saved menu choice, 순위·카드 KR at 390.

## 7. Critique and refinement cycle

VISUAL_CRITIQUE.md scored the build 6.9/10 with no P0, 8 P1 and 20 P2. All 8 P1 were fixed in stage 8 (sticky card head and folded sections in the right panel, scroll/URL reset, `#qsf:view` routing, lower section under the main column, screener mini-bars, Today candidates fitting, rail by default below 1440, 읽는 법 fold). FUNCTIONAL_REGRESSION_REPORT.md found 0 FAIL among 421 features (381 PASS, 38 changed intentionally, 2 unverifiable); its one new-code bug (data-time chip target) and the area-bar width conflict were fixed in stage 8.

## 8. Known limits

- P2 items skipped: RRG label collisions (canvas work), compact top-bar chips at 768/390, Today loading skeleton, theme toggle visibility in ⋯ at 1440, allocation bar and phone sparklines (new visuals), empty-state wording on some US panels and the Korean 관심종목 empty state, the lone VIX tile at 1440.
- The Korean 시장별 자세히 holdings table (13 columns) still scrolls sideways inside its box at 1440.
- In the screener's narrow form (main < 900 px) the four area columns cannot be sorted; they can above 900 px.
- Not verified on a real phone; the phone-only disabled stance and fund-period switches were checked by code and tests only.
- Light theme was reviewed on 오늘, 순위·카드, 시장 개요 and 종목 정보 only.
- Not built because the data is not sent: committee portfolio performance curves, hand-kept 모의 매매 equity curve, unified sector exposure, benchmark sector weights, drawdown curve, VaR histogram, market-state history, factor betas, intraday chart (see FINANCIAL_VISUALIZATION_SPECIFICATION.md).
