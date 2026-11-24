# Visual critique: Institutional Research Workstation redesign

Agent 7 (independent visual critic). Read-only on code. Reviewed 2026-11-24 against the scratch server `http://127.0.0.1:8799` (redesigned code, real data), in my own browser tab, at 1920×1080, 1440×900, 1280×800, 768×1024 and 390×844.

Method:
- Every finding below was seen on a screenshot I took.
- Widths, overflows and heights were then measured in the page (DOM read-only: `scrollWidth`/`clientWidth`, `getBoundingClientRect`, computed styles).
- The pane scales a ≥1280 px viewport down to about 800 px wide, so small text was checked by measurement rather than by eye.
- Owner decisions were not judged as defects. These are: dark default, rule-C up/down colours, purple/grey/amber judgement colours, the left vertical menu, the unified account in green/red, and the full menu by default at 1280.
- Nothing that writes data was pressed. The only interactions were market switch, theme cycle, the menu rail toggle (restored afterwards), views, row clicks, folds and the drawer.

---

## 1. Overall verdict

**The shell has reached the workstation goal, but the content inside it has not yet reached institutional density.** Score: **6.9 / 10**. No P0. **8 P1**, **20 P2**.

What is achieved:
- **Shell.** A 48 px top bar (search, market state, data time, actions), the left menu with rail and drawer, and the phone bottom bar.
- **Grid and colours.**
  - A real `.ws` main/right/lower grid that switches by container width.
  - Correct rule-C colours on every screen I checked.
  - A coherent dark palette, and a light palette that works.
  - Text contrast well above AA: meta 7.4:1, table headers 6.2:1, right-panel meta 6.5:1.
  - No page-level horizontal scroll at any width.
- **Strongest screens.** 차트분석 (Koyfin-grade), 거시 and 시장 지도 meet the bar.

What keeps it below the bar:
1. **The analytics panel on the key screen is not workable.** On 순위·카드, the score card in the right column is an 8,600–11,600 px document inside an 820–1,000 px nested scroller. Its header (name, 닫기) scrolls away, and its wide tables scroll sideways inside a 326–446 px column.
2. **Main/right imbalance leaves dead space.** The main column is often much shorter than the right column. Stock, account, assist and portfolio show 300–520 px of empty space under the main content at 1440 and 1920.
3. **Primary tables still need sideways scrolling at 1440.** This affects the screener, the Today candidates, account holdings, committee and coin.
4. **At 1280 with the default full menu, no screen splits.** At 1280×800 the stock chart starts below the fold.
5. **Routing bug.** Moving to `#qsf:<view>` from another screen ignores the view.

---

## 2. Scorecard per screen (0–10, judged mainly at 1440 and 1920)

| Screen | Score | One-line judgement |
|---|---|---|
| 오늘 | 7.0 | Strong tile strip and candidates panel. Candidate reasons column clipped at 1440/1280. The to-do list is tall and sparse at 1920. |
| 시장 개요 | 7.0 | Clean index/sector/rates split. Tiles too narrow (content overflows by 5–10 px). VIX tile orphaned on its own row at 1440. |
| 시장 지도 | 8.0 | The treemap is excellent at both widths. The RRG labels collide in the 360 px panel. |
| 거시 | 8.5 | Fits one screen at 1440. Chart cards and calendar side by side; the best balance of any screen. |
| 종목 정보 | 7.0 | Header band and score summary are institutional quality. ~300 px void under the chart at 1440 and 1920. Chart below the fold at 1280. |
| 관심종목 | 6.5 | With rows, the selection panel works well. The empty state is two near-empty panels. Notes drift far below the table when the panel grows. |
| 차트분석 | 9.0 | Best screen: four stacked panes, end tags, signal list in the right panel, rule-C volume colours. |
| 비교 | 8.0 | Good overlay chart and correlation matrix. The 기간 성과 table clips 최대 낙폭 at 1440. |
| 통합 계좌 | 6.0 | The right totals and form are good. Main is 372 px tall against a right column of 795–816 px. Holdings need sideways scroll at 1440. No allocation visual. |
| 시장별 자세히 | 6.5 | Warnings, holdings and verdict read well. The lower section is padded with empty or one-line panels. The US empty state is mostly empty panels. |
| 매매 보조 | 5.5 | The calculator (162 px) sits beside a 657 px settings column, leaving about 500 px of empty main. |
| 모의 매매 | 7.0 | Compact and honest empty state. |
| 순위·카드 (rank) | 6.0 | The table and row selection are right. The card in the right panel is unusable at length. About 400 px of explainer text sits above the table. |
| 순위·카드 (screener) | 6.0 | Filters are good. The table needs sideways scroll at 1440 (878/766), with 신뢰도/유동성 cut off. |
| 순위·카드 (exec) | 7.5 | Full-width order plan, KPI row, and an equity curve with an end label. Dense and readable. |
| 순위·카드 (track) | 7.0 | Dense. The top-3 tables do not share column positions, so the eye zig-zags. |
| 투자위원회 | 7.5 | Good KPI tiles. The table still clips at 1920 (1143/1110). |
| 모델 | 7.0 | Fine table. No screen title (shows `KR-EXP-0.1`). The 도전자 모델 panel is a placeholder. |
| 연구실 | 7.0 | Dense, tabular, single column. No screen title row. |
| 코인 | 7.5 | Good table. The last column is clipped at 1440 (869/798). The menu correctly shows only three items. |

---

## 3. Findings sorted by severity

### P0 (broken)

None found.

### P1 (clearly below the workstation goal)

**P1-1. The score card in the right panel is a nested 8,600–11,600 px scroll whose header scrolls away.**
- **Where.**
  - 순위·카드 rank view, row selected.
  - 1440 light, KR 064350: `.ws-right` scrollHeight 11,612 in an 820 client.
  - 1920 dark, US TECH: 8,609 in 1,000.
- **What is wrong.**
  - The name, 종목 화면 and 닫기 header scroll out of view. After two wheel scrolls the panel shows 요인별 계산 rows with no indication of which stock they belong to.
  - The FC-1 가격 범위 tables overflow the column: 535/443/543 px in 326 at 1440, and 535/527 in 446 at 1920.
  - The 요인별 계산 근거 cells wrap to 5 lines at 1440.
  - Two scrollbars compete: the page and the panel.
- **Why it matters.** The goal is "Screener = strongest table + analytics split". The analytics side of the split should be scannable at a glance.
- **Fix.**
  - Make the card head sticky inside the panel: `#qsfdetail .qd-head { position: sticky; top: 0; z-index: 2; background: var(--panel); }` (or whichever element holds the name and 닫기).
  - In `.ws-right`, render 근거 / 계획 / 요인별 계산 / 가격 범위 / 이력 closed by default. Keep only the score block and the diverging-bar 근거 summary open.
  - Under `@container wsright (max-width: 520px)`, give the FC-1 and 요인별 계산 tables a stacked or short form (hide 기여 and secondary columns, or switch the `.tbl-wrap` table to two-line rows).
  - Add a "카드 크게 보기" control that opens the card at main-column width for the deep read.

**P1-2. Right-panel scroll position and URL go stale between views.**
- **Where.** 순위·카드, 1440 dark.
- **What I saw.**
  - Scrolled into the card, switched to 스크리너, then came back to `#qsf`.
  - `.ws-right.scrollTop` stayed at 2000, so the panel opens mid-card with no header.
  - The hash had dropped the ticker (`#qsf`) while the card was still open.
- **Fix.**
  - In `qsfDrawDetail` and in `qsfSetView`, set `$(".ws[data-ws=qsf] .ws-right").scrollTop = 0` when a different card opens or the view changes.
  - Keep `#qsf/<ticker>` while a card is open.

**P1-3. Moving to `#qsf:<view>` from another screen ignores the view (routing bug).**
- **Where.** 1920 dark, measured three times.
- **What I saw.**
  - `#lab` → `#qsf:screen` gave `data-view="rank"`.
  - `#lab` → `#qsf:track` gave `rank`.
  - `#map` → `#qsf:exec` gave `track` (the last stored view).
  - On a full reload, `#qsf:track` correctly gave `track`. Within the 순위·카드 tab, hash changes between views also worked.
- **Why it matters.**
  - Deep links (O-7) and any command-palette or Today item that targets a view land on the wrong view.
  - The URL and the screen disagree.
- **Fix.** In the hashchange path (`fromHash` → tab already rendered), parse `:view` and call `qsfSetView(view)` even when the qsf tab is not re-rendered. Add a regression test for "different tab → #qsf:exec".

**P1-4. Main/right height imbalance leaves large dead zones (system-wide).**
- **Where (measured main vs right).**
  - 종목 정보: chart 516 px vs body 820 at 1440, and 516 vs 822 at 1920. About 300 px empty under the chart.
  - 통합 계좌: 372 vs 816 at 1440, and 372 vs 795 at 1920.
  - 매매 보조 (KR): 162 vs 657.
  - 시장별 자세히 (US, empty): 127 vs 647.
  - 관심종목 with a selection: 202 vs 557, and the source notes drift about 350 px below the table.
- **Why it matters.** Bloomberg-style density means the primary column is never mostly empty while the user scrolls only to reach the lower section.
- **Fix.**
  - Let `.ws-lower` flow into the main column whenever a right column exists. Inside the split container query:
    - `.ws { display: grid; grid-template-columns: minmax(0,1fr) var(--ws-right); }`
    - `.ws > .ws-ctx { grid-column: 1 / -1; }`
    - `.ws > .ws-body { display: contents; }`
    - `.ws-right { grid-column: 2; grid-row: 2 / span 2; }`
    - `.ws-lower { grid-column: 1; }`
  - The sticky right column is still bounded by `.ws`. Spec 2.1 assumed the lower section was full width; this changes that for split mode only.
  - For the stock chart, also let the canvas grow with the viewport: `height: clamp(420px, calc(100vh - 380px), 640px)`.

**P1-5. The screener (the "strongest table") needs sideways scroll at 1440.**
- **Where.** 순위·카드 → 스크리너, 1440 light KR. The table is 878 px in 766, and 신뢰도/유동성 are cut at the right edge.
- **Fix.** Apply the same container-query modes the rank table uses:
  - At `@container wsmain (max-width: 900px)`, collapse the four area scores (기술·재무·위험 관리·이벤트) into one mini-bar cell, or hide 이벤트/위험 관리 and show them on hover in the card.
  - Keep 종목, 업종, 점수, 판단, 신뢰도 and 유동성 visible.

**P1-6. The Today candidates (the landing screen's right panel) clip the 가점/감점 column at 1440 and 1280.**
- **Where.** 오늘, US and KR, dark and light.
- **What I measured.**
  - At 1440, the two tables are 351 and 378 px in 326. The ▲/▼ reason text is cut mid-word ("▲ 추세 구조 +6.").
  - At 1280 (single column, two tables side by side), 529 in 485.
  - Company names wrap to three lines ("West / Pharmaceutical / Services, Inc.").
- **Fix.** Under `@container wsright (max-width: 440px)`:
  - Show only the ticker chip in the 종목 cell and move the full name to `title`.
  - Set `.asst-cand td:last-child { white-space: normal; }` so the reasons wrap instead of clipping.
  - At 1920 (480 px panel) the tables fit, which confirms this is width-driven.

**P1-7. At 1280 with the default full menu, no screen gets the split; the research screen loses its chart above the fold.**
- **Where.** 1280×800 dark.
- **What I saw.**
  - 종목 정보 (TRV): header, score summary and 핵심 수치 come first. The 가격 차트 header starts at about y 700 of 800.
  - 순위·카드: single column, with the card as a button above the list.
  - The rail toggle does produce the 800/360 split (verified), so the layout works; the default does not.
- **Why it matters.** 1280–1440 is the most common laptop width. "Stock detail = research layout" and "Screener = table + analytics split" both disappear there.
- **Fix (one of the following).**
  - Default to the rail at 1280–1439 when no `qse-nav` is saved. This keeps the owner's full-menu decision available as a saved choice; the owner decides.
  - For `data-ws="stock"` only, at single column, put `#s-facts` (`.ws-first`) after the chart, or turn 핵심 수치 into a one-row kv strip under the header.

**P1-8. On a phone the ranking table starts below the first screen; on desktop about 45% of the first screen is explainer text.**
- **Where.**
  - 390×844: the `.qsf-rank-tbl` top is at y = 870, so no row is visible without scrolling.
  - 1440: the table header sits at about 400 px of 900.
  - The cause is four explanatory paragraphs plus a notice above the table (스윙 순위 50개 panel).
- **Fix.**
  - Wrap the explainer paragraphs in `<details class="fold">읽는 법</details>`, closed by default and remembered via the existing fold store.
  - Keep only the one-line common push line and the formula notice visible.
  - Apply the same treatment to the docked market-state strip in the right panel, which is a ~15-line amber prose block at rest.

### P2 (polish)

**P2-1. Korean words break mid-word in tiles.**
- **Where.**
  - 오늘 / 시장 개요 tile meta: "그래프 폭 13.0%" renders as "…2026-11-23 그래" / "프 폭 13.0%". Seen at 1440 and clearly at 390.
  - The cause: `.nw` only has a rule inside `.card .chg`, so the `.nw` span in `.card .meta` is not nowrap. The body uses `word-break: normal`.
- **Fix.** Add a global `.nw { white-space: nowrap; }` and `body { word-break: keep-all; overflow-wrap: anywhere; }`.

**P2-2. Market tiles are too narrow.**
- **Where.**
  - `.card .row` overflows (168/158 at 1440 overview; 144/137 at 1280 today).
  - `.card` overflows (180/175 at 1920 overview).
  - At 1440, main shows four index tiles per row, leaving VIX alone on row 2.
- **Fix.** Use `grid-template-columns: repeat(auto-fill, minmax(184px, 1fr))` in main, or let five index tiles share a row by dropping the sparkline below 180 px (`@container (max-width: 180px) .card canvas { display: none }`).

**P2-3. RRG labels collide in the 360 px right panel.**
- **Where.** 시장 지도, 1440: the sector names overlap in the centre cluster.
- **Fix.** At `wsright` widths below 420, label only the endpoints outside a central radius and show the rest in the legend, or move the RRG to the lower section at 1440.

**P2-4. In rail mode the menu overflows at 800 px height.**
- **Where.** 1280×800 rail: 16 items plus group headers make 956 px in 752. The active 순위·카드 is cut, and 투자위원회/모델/연구실 are hidden.
- **Fix.** In rail mode, hide the group headings and use 1 px separators (`.side.rail .group-h { display: none }`). 16 × 44 = 704 px then fits.

**P2-5. The top bar loses market state and data time at 768 and 390.** These are required top-bar elements. Show a compact "15 나쁨" chip in the bar or as the first line of the page.

**P2-6. Track-view top-3 tables do not align.** Each session's table auto-sizes, so the 점수 column jumps from about x 520 to x 468 between blocks. Fix: `table-layout: fixed` with a shared `<colgroup>`.

**P2-7. Tables clip a few pixels to a column at common widths.**

| Screen | Width | Table / column | Measured |
|---|---|---|---|
| 비교 | 1440 | 기간 성과, 최대 낙폭 | 339/326 |
| 투자위원회 | 1440 | 반대 논거 | 1067/766 |
| 투자위원회 | 1920 | 반대 논거 | 1143/1110 |
| 코인 | 1440 | last column | 869/798 |
| 통합 계좌 | 1440 | holdings, 손절가/목표가 (only one row) | 812/766 |
| 모델 | 1440 | model table | 834/766 |
| 순위·카드 rank | 390 | rank table | 341/332 |

Fix: trim or wrap the longest text column (`white-space: normal; min-width: 120px`), or hide the least-used column per container width.

**P2-8. Empty or one-line panels.** These go against spec 2.2 ("no empty panels"):
- 시장별 자세히, US empty: 계좌 수익률 vs SPY, 매매 성과 and 거래 기록 추가 are all near-empty panels.
- 시장별 자세히, KR: the 매매 성과 "아직 매도 기록이 없습니다" panel is stretched to the chart's height, and "주문 기능은 없습니다" occupies a panel of its own.
- 관심종목, KR empty: an empty main panel beside a "고른 종목" placeholder right panel. Spec 3.6 also said watch is single column.
- 모델: the 도전자 모델 placeholder.

Fix: render empty states as one line in `.ws-ctx`, and let `.ws-lower` drop panels with no data.

**P2-9. Level metrics are coloured like moves.** In 연간 재무 요약 (AAPL), 영업이익률 and 순이익률 are green. Up/down colour should mean change. Margins should be neutral, or coloured only by the year-on-year change.

**P2-10. Screen titles are inconsistent.** 연구실 starts directly with a panel. 모델 shows `KR-EXP-0.1` instead of a 모델 title. Every other screen has an 18 px `.ws-ctx > h2`.

**P2-11. Today has no skeleton while loading.** In KR at 1440 light, the screen shows only the question box and the footer for about 10 s. Fix: tile and row skeletons in `#asst-ctx` and `#asst-cands`.

**P2-12. The Today to-do items are sparse at 1920.** Each item is a card with its 탭에서 보기 button on its own line. Fix: `.asst-item { display: flex; justify-content: space-between; align-items: center; }`, which cuts height by about 40%.

**P2-13. The theme toggle is hidden in the … menu.**
- It sits next to 폰 연결 and cycles 어둡게 → 시스템 → 밝게 without saying so.
- Decision U-3 says "the ◐ toggle stays". At ≥1920 it is visible in the bar; at 1440 it is not.

**P2-14. The account has no allocation visual.** 통합 계좌 shows 비중 only as a table column. Portfolio = holdings, allocation, risk. A stacked 100% bar by account or market from the existing 비중 values would add the allocation view without new data.

**P2-15. On phones the stock chart sits 1.4 screens down** (390: canvas top at y 1180). This follows the spec's order. Consider a 120 px sparkline in the header band on phones.

---

## 4. What works well (keep)

- **Colours (rule C) are correct everywhere I looked.**
  - KR: 삼성전자 −7.01% in blue; candles and volume red/blue; holdings +red/−blue; KOSPI tiles blue for down.
  - US: green/red.
  - 통합 계좌: green/red, as the owner decided.
- **Chart quality.**
  - 차트분석: four panes, MA end tags, Bollinger fill, signal markers, signal list in the right panel.
  - Stock chart: MA end tags; the 50-day line changes colour per market so blue never reads as down.
  - Paper-book equity curve with a direct end label.
- **Shell.**
  - Sticky top bar with market-state and data-time chips at ≥1280.
  - Collapsible menu groups.
  - The drawer has a scrim at 768; the bottom bar works on the phone.
  - The rail toggle delivers the split at 1280.
- **Row selection.**
  - Selecting a row fills the right panel at ≥1440 (rank, watch).
  - The selected row is highlighted.
  - The URL is updated without a history entry.
- **Themes.** The light theme is coherent: panels, chips and charts all re-tinted. Dark default is calm and low-glare, with readable muted text (≥6.2:1).
- **Data honesty.** Sources and "실데이터" badges sit next to the data. No fabricated metric was seen. Empty states say what is missing.
- **No page-level horizontal scroll at any tested width.** Only `.tbl-wrap` scrolls sideways.

---

## 5. Screenshots reviewed (screen × width × theme)

| Width | Theme | Screens captured |
|---|---|---|
| 1440×900 | dark | 오늘 US (top, bottom/ops fold) · 시장 개요 US · 시장 지도 US (+RRG crop) · 거시 US · 종목 정보 AAPL (top, peers, financials + filings) · 종목 정보 005930 KR · 관심종목 KR (empty) · 차트분석 KR 005930 · 비교 KR (코스피 vs 005930) · 통합 계좌 KR · 시장별 자세히 KR (top, lower) · 매매 보조 KR (top, lower) · 모의 매매 KR · 순위·카드 rank KR with 064350 selected (card mid-scroll after return) · 투자위원회 KR · 모델 KR · 연구실 KR · 코인 |
| 1440×900 | light | 종목 정보 005930 KR · 오늘 KR (loading, loaded) · 순위·카드 rank KR (no selection; 064350 selected; card scrolled ×2) · 스크리너 KR · #qsf:exec KR (top, equity curve, holdings) · #qsf:track KR |
| 1920×1080 | dark | 오늘 US · 순위·카드 rank (no selection; TECH selected; card scrolled) · #qsf:screen deep link (showed rank) · 종목 정보 AAPL · 시장 지도 · 시장 개요 · 관심종목 US (no selection; MSFT selected) · 통합 계좌 · 시장별 자세히 US (empty) · 투자위원회 US · 차트분석 AAPL |
| 1280×800 | dark | 오늘 US · 순위·카드 rank (full menu) · 종목 정보 TRV (via name link) · 순위·카드 rank (rail) |
| 768×1024 | dark | 오늘 US · 순위·카드 rank · 종목 정보 AAPL · drawer open |
| 390×844 | dark | 오늘 US · 순위·카드 rank · 종목 정보 AAPL · 시장 지도 US · 통합 계좌 |

**Not captured** (no claims made about these): the 투자위원회 sub-views (미션 포트폴리오, 투자자 비교, 가상 성과); light theme on the remaining screens; 768 and 390 for 거시, 비교, 차트분석, 코인, 매매 보조, 모의 매매, 모델, 연구실; and 1280 for screens not listed above.
