# Functional regression report: workstation redesign

Agent 6 (functional regression QA), 2026-11-24. Read-only review. No code under `terminal/` or `tests/` was changed.

- New code: worktree `scratchpad/ws`, branch `ws-redesign`, commits b86d114..35f18c1 (7 stage commits) on top of main 7c8e0af.
- Baseline: main 7c8e0af, read with `git show` / `git archive`.
- Binding list: `EXISTING_UI_FEATURE_INVENTORY.md`, 421 rows. Owner decisions: `IMPLEMENTATION_SUMMARY.md` section 1.
- Diff size: 33 files, +2349/−609. Every static file changed except `calendar.js` and `forecast.js`. `terminal/server.py` is unchanged.

## 1. Summary

| Status | Rows |
|---|---|
| PASS | 381 |
| CHANGED-INTENTIONALLY | 38 |
| FAIL | **0** |
| UNVERIFIABLE | 2 |
| **Total** | **421** |

**No inventory row is broken.** Every element id, data-* hook, handler, route, `qse-*` key, API call and shortcut the baseline uses is still present and wired. Every behaviour change traces to an owner decision or a spec section.

There are two findings outside the per-row verdicts:

1. **New-code defect (fix before merge).** The new top-bar `#datatime` chip scrolls to the wrong place. Details in section 2.
2. **Spec conflict for the chief.** QR-31, the ranking's area bars. Details in section 3.

### Limits of this check

All checks read code. Nothing was rendered: the browser pane was reserved for another agent, and jsdom is not installed.

- **Layout and stickiness** need a rendered pass. These are the two UNVERIFIABLE rows.
- **Click paths** were traced in the source, not clicked.
- **Server data** was checked with GET requests only, against the scratch server on port 8799.

## 2. FAIL list

**No inventory row fails.**

### New-code defect (not an inventory row)

The `#datatime` chip opens 연구실 but never reaches the 자동 실행 line it points to.

- `terminal/static/app.js:1350`:
  ```js
  $("#datatime").onclick = () => Promise.resolve(show("lab")).then(() => { const n = $("#autoline"); if (n) n.scrollIntoView({ block: "nearest" }); });
  ```
- The chip's tooltip at `app.js:1346` promises the line: "누르면 연구실 탭의 자동 실행 줄을 봅니다".
- `#autoline` is rendered only in the **model** tab: `lab.js:44`, inside `renderComparison`, which draws into `#tab-model` (`lab.js:12`). It is US only.
- In the 연구실 tab the 자동 실행 block is `lab.js:198`, an `<h3>자동 실행</h3>` inside `#recpanel`. That block has no id.

Effect:
- If the model tab has not been opened, `$("#autoline")` is null and nothing scrolls.
- If the model tab was drawn earlier (US), `scrollIntoView` runs on an element inside a hidden tab, which does nothing useful.

No test covers this chip.

Suggested fix (one line in each file):
- Give the 연구실 block an id, for example `<h3 id="rec-auto">자동 실행</h3>` at `lab.js:198`.
- Make the handler wait until `#recpanel` has rendered, then scroll to `#rec-auto`. `renderLab` fills `#recpanel` asynchronously, so look the element up after that promise or re-try once.
- Alternatively, route the chip to `show("model")` and change the tooltip to match.

## 3. Spec conflict: QR-31 area bars

- **Baseline:** the domain bars (기술/재무/위험 관리/이벤트) were hidden when the viewport was under 1280 px.
- **New code:** they are hidden when the ranking column (container `wsmain`) is under 1184 px, at `style.css:926`. This follows WORKSTATION_LAYOUT_SPECIFICATION 2.7.
- **Consequence:** at 1920 px with the full left menu and the right panel open, the ranking column is narrower than 1184 px, so the bars are hidden. They used to show at that size.
- **Conflict:** FINANCIAL_VISUALIZATION_SPECIFICATION §9 says "unchanged visibility (hidden < 1280 px)".

I marked the row CHANGED-INTENTIONALLY because it follows the layout spec. The chief should pick one spec and record the choice.

## 4. CHANGED-INTENTIONALLY (38 rows)

Each row cites a decision in IMPLEMENTATION_SUMMARY section 1 (U-x, O-x, D-x) or a spec section. "viz" is FINANCIAL_VISUALIZATION_SPECIFICATION, "layout" is WORKSTATION_LAYOUT_SPECIFICATION and "UX" is UX_WORKFLOW_SPECIFICATION.

The changes fall into five groups:

- **confirm() replaced by `uiConfirm` (U-6):** PH-05, QT-03, AC-17, PF-14, PT-09. The sentence is kept in every case.
- **Two-column row selection into the right panel (U-5, D2):** WA-04, QR-21, QS-07, PF-06. One-column behaviour is unchanged.
- **Colour roles (viz §8):** price red/blue is no longer used for non-price meanings. Rows: S-40, QR-22, QR-30, QT-07, QC-11, FC-03, TD-18, LB-10, CH-10, CH-14, MP-05, RO-01, RO-03, PF-10, CP-08.
- **Navigation:**
  - Left menu (U-4): S-18, S-19.
  - Number keys follow the visible menu order (O-10): CM-10, CM-12.
  - Committee views in the URL (O-7): IC-02.
  - Dark default theme (U-3): S-13.
- **Placement and feedback:**
  - Rows that moved on screen: MA-04, TD-13, SP-01.
  - Rows that now give feedback: QR-08 (undo toast, phone-disabled) and AC-14 (double-submit guard, "방금 기록 취소").
  - Richer chart hover: PF-11, CP-05.
  - Container-width rule: QR-31 (see section 3).

The full reason and file:line for each row are in section 7.

## 5. UNVERIFIABLE (2 rows)

| ID | Why |
|---|---|
| S-39 Responsive breakpoints | The 640/1023 breakpoints are kept. `setTopH` (`app.js:542`) was rewritten for the top bar plus `#statusbars`, and sticky offsets now come from container queries. Correct offsets need a rendered check at 375/768/1024/1280/1600 px. |
| QR-36 Sticky rank header | The `thead` sticky rule is kept (`style.css:588`). Table overflow is now switched by container width (`style.css:934`). Whether the header still sticks beside the right panel needs a rendered check. |

## 6. Global checks

### Element ids
Every id that baseline JS queries (`$("#…")`, `getElementById`, `querySelector`) is still defined in the new HTML or JS. Two ids, `qsffcfold` and `qsftechfold`, are built at runtime by `qsfFold`, in both baseline and new code.

### API URLs
All **87** `/api/...` URLs found in the baseline static JS are still in the new code. Every one matches a route in `terminal/server.py`, which is unchanged. `/api/watchlist/` appears only as a prefix (`/api/watchlist/<ticker>`).

### localStorage
Every baseline `qse-*` key is still both read and written:

`qse-acct-unit`, `qse-chart`, `qse-compare`, `qse-fold-*`, `qse-heat-view`, `qse-keys`, `qse-market`, `qse-qsf-folds`, `qse-qsf-strategy`, `qse-qsf-view`, `qse-recent`, `qse-theme`.

- `STORE_RENAMES` (`app.js:5`) is kept.
- New keys:
  - `qse-nav`: menu width, full/rail/drawer.
  - `qse-theme-v2`: a one-time marker that moves a stored "auto" theme to dark (U-3).

### Removed calls
A token scan of baseline handlers found only two kinds of call missing from the new code. Both are intentional:
- `confirm(` calls, replaced by `uiConfirm` (U-6).
- AC-14's old success text, replaced by the U-7/O-9 text.

### Routing (app.js)
Functions: `tabHash` at 559, `show` at 577, `fromHash` at 1358. The `hashchange` listener is at 1387.

| Form | Result | Evidence |
|---|---|---|
| `#tab` | unchanged | |
| `#stock/CODE` | unchanged | |
| `#qsf/CODE` | unchanged | |
| `#qsf:view` | unchanged | |
| `#committee:view` (new, O-7) | Parsed through `IC_VIEWS`; view buttons `pushState`, so Back returns to the previous view | `committee.js:126-128` |
| `#assist:section` (new, O-7) | Parsed through `ASSIST_SECTIONS` / `assistState` / `assistScroll`. The in-page section nav uses `replaceState`; `assistGo` sets `location.hash` | `portfolio.js:257-273` |
| Right-panel row pick on the ranking | Uses `replaceState`, so a pick does not add a history step | `qsf.js:323` |

- Back/forward still goes through `hashchange` → `fromHash`. I found no case where Back leaves the URL and the screen out of step.
- The global `[data-ticker]` click handler (bubble phase, `app.js:759`) is kept. The new two-column row handlers call `stopPropagation`, so a row pick does not also open the stock screen.

### Syntax
`node --check` passes for every JS file in the new static folder. A scan for new global identifiers found none that are used without being defined.

### Scratch server (127.0.0.1:8799, GET only)
- `index.html`, `app.js`, `qsf.js`, `style.css`, `ui.js` and `theme.js` are served byte-identical to the worktree files.
- These endpoints returned 200:
  - `/api/health`
  - `/api/qsf/market-state` (US and KR)
  - `/api/automation/status`
  - `/api/overview`
  - `/api/watchlist`
  - `/api/qsf/latest`
  - `/api/committee/dashboard`
  - `/api/symbols`
  - `/api/macro`
  - `/api/rotation`

### Tests (run in the worktree, results seen)
- **Inventory-cited and UI/terminal tests:** 66 files, including every inventory-cited file that exists, `test_ws_stage7.py`, `test_ui_*` and `test_terminal_*`. Result: **908 passed in 68.19 s**.
  - Note: the inventory cites `test_account.py` and `test_automation.py`. Neither exists, in the baseline or the new code. Those citations are stale.
- **Full suite** (`pytest -q -x tests`): **2232 passed, 6 skipped, 3 xfailed, 12 warnings in 308.66 s**, with no failures (run with `-x`, `-p no:cacheprovider`).

## 7. Per-row table

Evidence is the hook found in the new code and its file:line. For non-PASS rows, the evidence is the file:line followed by the reason. Duplicate inventory IDs are labelled by section: "CO-xx (collect)" / "CO-xx (coin)" and "MO-xx (A)" / "MO-xx (C)".

| ID | Feature | Status | Evidence |
|---|---|---|---|
| TD-V1 | '사도 돼?' conclusion box: 사도 됨 / 기다림 / 사지 않음, the reason, the condition that would change... | PASS | `/api/assistant/ask` assistant.js:55 |
| TD-V2 | '결론 자세히' section: the chosen stance's line always named, half-size note on an adverse U... | PASS | `a.verdict ? { ...s` assistant.js:39 |
| TD-V3 | Duplicate lines (바뀌는 조건, 다른 전략) are hidden under the box on screen but kept in the text... | PASS | `바뀌는 조건: ` assistant.js:26 |
| S-01 | Brand "퀀트 터미널 QSF" | PASS | `ver` index.html:18 |
| S-02 | Market switch 미국/한국/코인 (`#market`) | PASS | `#market` index.html:34 |
| S-03 | Keyboard `M` cycles market US->KR->COIN->US | PASS | `qse-keys` command.js:70 |
| S-04 | Search box + 조회 button (`#search`, `#q`) | PASS | `#search` index.html:35 |
| S-05 | Search autocomplete dropdown (`#qsug`) | PASS | `#qsug` app.js:714 |
| S-06 | "혹시 이 종목인가요?" choice list (`symbolChoices`) | PASS | `#sym-raw` app.js:707 |
| S-07 | Korean search result list (`searchKr`) | PASS | `searchKr` app.js:659 |
| S-08 | 내 계좌 button (`#acctbtn`) | PASS | `#acctbtn` index.html:44 |
| S-09 | 지금 수집 button (`#collect`) -> see CO-xx | PASS | `#collect` index.html:45 |
| S-10 | 폰 연결 button (`#phonebtn`) -> see PH-xx | PASS | `#phonebtn` index.html:46 |
| S-11 | ⌘K button (`#cmdbtn`) | PASS | `#cmdbtn` index.html:47 |
| S-12 | 한 글자 단축키 끄기/켜기 (`#keysbtn`, also `#cmd-keys` in palette) | PASS | `#cmd-keys` command.js:65 |
| S-13 | Theme toggle ◐ (`#theme`) | CHANGED | app.js:804 — Default theme is now dark; stored "auto" moved to dark once (qse-theme-v2); ◐ still cycles 시스템→밝게→어둡게 and redraws (U-3, U-8) |
| S-14 | Collect progress bar (`#collectbar`) | PASS | `#collectbar` index.html:55 |
| S-15 | Phone panel (`#phonebar`) | PASS | `#phonebar` index.html:56 |
| S-16 | Server-unreachable bar (`#netbar`, role=alert) | PASS | `#netbar` index.html:57 |
| S-17 | "화면이 업데이트되었습니다" bar (`#verbar`) with 새로고침 button | PASS | `#verbar` index.html:58 |
| S-18 | Group nav (`#groups`): 오늘 / 시장 / 종목 / 차트 / 내 계좌 / 점수 / 검증·기록 / 코인 | CHANGED | app.js:397 — Horizontal group bar replaced by group headings in the left menu; .groups kept in DOM but display:none (style.css:103) for 더보기; number keys now follow visible menu order (U-4, O-10) |
| S-19 | Sub-tab row (`.tabs`) | CHANGED | app.js:381 — Sub-tab row replaced by the left vertical menu (.nav-grp), full 232 / rail 72 / drawer 264, width kept in qse-nav; phones keep one tab row (U-4, chief reconciliation §2) |
| S-20 | Tab render policy | PASS | `ALWAYS_FRESH` app.js:1279 |
| S-21 | Hash routing | PASS | app.js:1358 — All four baseline forms unchanged; #committee:view and #assist:section added (O-7). See routing section |
| S-22 | Document title + sr-only h1 (`#pagetitle`) | PASS | `#pagetitle` index.html:118 |
| S-23 | Wide-content tabs | PASS | `main.wide` style.css:603 |
| S-24 | Price colour rule | PASS | `paintColorRule` app.js:598 |
| S-25 | Bottom bar (≤640px): 오늘 / 종목 / 점수 / 코인(COIN only) / 내 계좌 / 더보기 | PASS | `#bottombar` index.html:146 |
| S-26 | 더보기 sheet (`#moresheet`) | PASS | `#moresheet` index.html:154 |
| S-27 | Footer | PASS | `#health` index.html:139 |
| S-28 | Toast (`#toast`) | PASS | `#toast` index.html:145 |
| S-29 | Hover tip (`#tip`) | PASS | `#tip` index.html:144 |
| S-30 | Touch tap-tip (`#taptip`) | PASS | `#taptip` phone.js:65 |
| S-31 | Keyable rows | PASS | `KEYABLE` app.js:762 |
| S-32 | Global `[data-ticker]` click -> `openTicker` | PASS | `openTicker` app.js:647 |
| S-33 | "지금 수집" in empty states (`.collect-now`) | PASS | `#collect` index.html:45 |
| S-34 | `plainBlock` "쉽게 설명해줘" toggle | PASS | `plainBlock` app.js:171 |
| S-35 | Error code -> Korean (`ERR_KO`, `errKo`) | PASS | `ERR_KO` app.js:136 |
| S-36 | PHONE_NOT_PAIRED handling | PASS | `location.reload` app.js:131 |
| S-37 | Recent tickers store | PASS | `pruneRecentTickers` app.js:636 |
| S-38 | localStorage key migration | PASS | `STORE_RENAMES` app.js:5 |
| S-39 | Responsive/viewport breakpoints | UNVERIFIABLE | app.js:542 — Breakpoints 640/1023 kept; setTopH rewritten to top bar + #statusbars, sticky offsets via container queries. Needs a rendered check at 375/768/1024/1280/1600 |
| S-40 | Shared canvas helpers | CHANGED | app.js:358 — sparkRange tooltip now says "가는 가로선" (baseline is a faint solid line, not dotted); gaps kept as breaks (viz spec §8 items 18-19) |
| S-41 | Number/format helpers | PASS | `tickerLabel` app.js:43 |
| S-42 | Redraw system | PASS | `redrawOn` app.js:810 |
| UI-01 | `ui.head/panel/table/notice/empty/badge/meta/kv/fold/seg` + `html`/`raw` tagged templates | PASS | `notice` ui.js:25 |
| OV-01 | Group panels of index/ETF/rate/FX cards | PASS | `/api/overview` app.js:845 |
| OV-02 | Card content | PASS | `function card(` app.js:860 |
| OV-03 | Neutral tiles | PASS | `NEUTRAL_TILE` app.js:858 |
| OV-04 | Card click -> stock | PASS | `data-ticker` app.js:646 |
| OV-05 | Status badges on a card | PASS | `장중·미확정` app.js:82 |
| OV-06 | Live-session notice | PASS | `정규장이 진행 중` app.js:851 |
| OV-07 | Source / fetch time / basis footer panel | PASS | `meta(d.source, d.cache.fetched_at` app.js:850 |
| OV-08 | Loading / error states | PASS | `errBox` app.js:186 |
| OV-09 | Sparkline redraw on theme/resize | PASS | `redrawOn` app.js:810 |
| MA-01 | Market-specific macro cards (US via FRED, KR via ECOS) | PASS | `/api/macro` app.js:1061 |
| MA-02 | Reason notice | PASS | `d.reason` app.js:1063 |
| MA-03 | CPI note + source | PASS | `전년 동월 대비` app.js:1070 |
| MA-04 | Embedded 경제 일정 panel (`#econcal`) | CHANGED | app.js:1071 — #econcal moved from above the macro cards to the right column (one column: after the cards) (layout spec 3.4, macro weakness 1) |
| MA-05 | Redraw minis | PASS | `redrawOn` app.js:810 |
| CAL-01 | 다가오는 경제 일정 table (60 days, KST) | PASS | `#econcal` app.js:1071 |
| CAL-02 | Row badges | PASS | `오래된 일정` calendar.js:17 |
| CAL-03 | Row tooltips | PASS | `발표 시각은 기관 일정표에 없습니다` calendar.js:15 |
| CAL-04 | Ticker click | PASS | `data-ticker` app.js:646 |
| CAL-05 | "공식 일정은 YYYY-MM-DD까지만 들어 있습니다" notices | PASS | `까지만 들어 있습니다` calendar.js:32 |
| CAL-06 | Basis + source links | PASS | `earnings_status` calendar.js:33 |
| CAL-07 | Empty / error / market-changed guard | PASS | `60일 안에 공식 발표된 일정이 없습니다.` calendar.js:31 |
| WA-01 | List of watched tickers for current market | PASS | `/api/watchlist` app.js:883 |
| WA-02 | Add ticker form (`#wadd`) | PASS | `#wadd` app.js:1119 |
| WA-03 | Remove (✕, title 삭제) | PASS | `watchlist` app.js:883 |
| WA-04 | Row click -> stock screen | CHANGED | app.js:1148 — One column: row click opens stock as before. Two columns (content ≥1120): row click selects into #w-side; the name button opens stock (layout spec 3.6, U-5 pattern, inventory §1 map "selected-row detail right") |
| WA-05 | Score cells (`watchScore`) | PASS | `watchScore` app.js:1168 |
| WA-06 | Footnotes | PASS | `watchlist.json 에만` app.js:1126 |
| WA-07 | Empty / error | PASS | `관심종목이 없습니다.` app.js:1123 |
| WA-08 | Count in heading | PASS | `관심종목 <span class="meta m0">${d.tickers.l` app.js:1118 |
| WA-09 | Always re-rendered | PASS | `ALWAYS_FRESH = new Set(["watch"` app.js:1279 |
| WA-10 | Empty stock tab shows watchlist chips | PASS | `/api/watchlist` app.js:883 |
| ST-01 | Empty state | PASS | `#stock` assistant.js:30 |
| ST-02 | Chips: 최근 본 종목 and 관심종목 | PASS | `qse-recent` app.js:5 |
| ST-03 | Header block (`#s-head`) | PASS | `#s-head` app.js:894 |
| ST-04 | ＋ 관심종목 button (`#addw`) | PASS | `#addw` app.js:960 |
| ST-05 | 비교 차트 button (`#addc`) | PASS | `#addc` app.js:960 |
| ST-06 | 차트분석 button (`#adda`, tooltip "이동평균·볼린저밴드·RSI·MACD와 고전 신호를 봅니다") | PASS | `#adda` app.js:960 |
| ST-07 | 점수 카드 button (`#addq`, tooltip "순위·카드 탭에서 이 종목의 점수 카드를 엽니다") | PASS | `#addq` app.js:960 |
| ST-08 | Price line (`#s-price`) | PASS | `#s-price` app.js:916 |
| ST-09 | Key-value facts | PASS | `/api/company` app.js:910 |
| ST-10 | 회사 설명 fold (`details#sum.co-sum`) | PASS | `#sum` app.js:965 |
| ST-11 | Profile source meta | PASS | `c.profile.source` app.js:964 |
| ST-12 | 가격 차트 panel | PASS | `/api/chart` app.js:637 |
| ST-13 | Range selector 3개월/1년/5년 (`#rng`) | PASS | `#rng` app.js:895 |
| ST-14 | SMA legend | PASS | `20일선` app.js:896 |
| ST-15 | Crosshair tooltip | PASS | `#tip` index.html:144 |
| ST-16 | Chart meta line (`#c-meta`) | PASS | `#c-meta` app.js:897 |
| ST-17 | Chart canvas a11y label | PASS | `가격 차트: ${b0.date}` app.js:1024 |
| ST-18 | Remember ticker after prices arrive | PASS | `rememberTicker` app.js:623 |
| ST-19 | 동종업계 비교 panel (`#s-peers`) | PASS | `#s-peers` app.js:900 |
| ST-20 | 연간 재무 요약 (`#s-fund`) | PASS | `#s-fund` app.js:901 |
| ST-21 | 최근 SEC / DART 공시 (`#s-fil`) | PASS | `#s-fil` app.js:902 |
| ST-22 | Section error states | PASS | `function sHeadError` app.js:918 |
| ST-23 | Stock re-render guard | PASS | `ticker` app.js:43 |
| ST-24 | Market auto-switch on open | PASS | `openTicker` app.js:647 |
| ST-25 | Cross-tab ticker prefill | PASS | `prefillTicker` app.js:754 |
| ST-26 | Stock tab on COIN market | PASS | `show` app.js:551 |
| PE-01 | Letter-grade table 업종 내 위치 | PASS | `/api/qsf/peers` peers.js:22 |
| PE-02 | Peer table | PASS | `id="peer-tbl"` peers.js:51 |
| PE-03 | Sortable headers | PASS | `peerState.desc` peers.js:39 |
| PE-04 | Empty columns folded | PASS | `재무 비율은 다음 자동 실행 뒤에 채워집니다` peers.js:53 |
| PE-05 | 12 rows then "N개 모두 보기" | PASS | `모두 보기` peers.js:54 |
| PE-06 | Not scanned fallback | PASS | `이 종목은 QSF 스캔 대상이 아니라 업종 비교가 없습니다.` peers.js:32 |
| PE-07 | Footnotes | PASS | `basis_note` peers.js:47 |
| PE-08 | Sector label | PASS | `sectorKo` app.js:80 |
| AL-01 | 알림 센터 add-rule form | PASS | `/api/alerts/add` alerts.js:39 |
| AL-02 | Validation messages | PASS | `추가했습니다.` alerts.js:39 |
| AL-03 | Rule list | PASS | `/api/alerts/remove` alerts.js:57 |
| AL-04 | Explanatory basis | PASS | `검증된 매매 신호가 아닙니다` alerts.js:56 |
| AL-05 | 최근 보낸 알림 log | PASS | `/api/alerts` alerts.js:39 |
| AL-06 | 지금 확인 button | PASS | `check` alerts.js:63 |
| CM-01 | Open/close | PASS | `#cmd` command.js:16 |
| CM-02 | Empty query list | PASS | `qse-recent` app.js:5 |
| CM-03 | Tab aliases | PASS | `const CMD_ALIASES` command.js:3 |
| CM-04 | Market switch commands | PASS | `시장으로 전환` command.js:28 |
| CM-05 | Ticker commands | PASS | `findSymbol` app.js:689 |
| CM-06 | Live symbol lookup | PASS | `/api/symbols` app.js:641 |
| CM-07 | Hangul search row | PASS | `findSymbol` app.js:689 |
| CM-08 | Assistant question rows | PASS | `askAssistant` assistant.js:60 |
| CM-09 | List navigation | PASS | `해당하는 이동이 없습니다.` command.js:111 |
| CM-10 | Keys help + toggle | CHANGED | command.js:75 — Help line now "1~9(메뉴 순서)" instead of "1~6" (O-10) |
| CM-11 | Focus trap | PASS | `cmd-keys` command.js:65 |
| CM-12 | Global shortcuts | CHANGED | command.js:155 — Number keys 1-9 index the visible menu groups (COIN: 1 오늘, 2 내 계좌, 3 코인) instead of DOM order incl. hidden groups (O-10) |
| CO-01 (collect) | 지금 수집 start | PASS | `automation` lab.js:49 |
| CO-02 (collect) | Progress line | PASS | `#collectbar` index.html:55 |
| CO-03 (collect) | Start-timeout error | PASS | `수집이 시작되지 않았습니다` collect.js:64 |
| CO-04 (collect) | Result lines | PASS | `다시 누르면 실패한 단계만 다시 시도합니다` collect.js:35 |
| CO-05 (collect) | 화면 새로 고침 button | PASS | `state.loaded` app.js:115 |
| CO-06 (collect) | Close ✕ | PASS | `id="collectclose"` collect.js:18 |
| CO-07 (collect) | Auto-follow on page load | PASS | `automation` lab.js:49 |
| CO-08 (collect) | Status-read failure | PASS | `수집 상태를 읽지 못했습니다.` collect.js:44 |
| PH-01 | 폰 연결 toggle panel | PASS | `#phonebar` index.html:56 |
| PH-02 | OFF state | PASS | `phone` phone.js:7 |
| PH-03 | ON state | PASS | `phone` phone.js:7 |
| PH-04 | Paired device list | PASS | `phone` phone.js:7 |
| PH-05 | 끄기 | CHANGED | phone.js:37 — confirm() replaced by in-page uiConfirm dialog, same text, OK "연결 끄기" (U-6) |
| PH-06 | Listen error + help text | PASS | `listen_error` phone.js:18 |
| PH-07 | Phone mode flag | PASS | `phone` phone.js:7 |
| PH-08 | Panel close ✕ | PASS | `id="phoneclose"` phone.js:8 |
| PH-09 | Touch tap-tip | PASS | `taptip` phone.js:65 |
| MO-01 (A) | 모델 tab (read-only model view: run summary, recommendations, 전향적 추적, 도전자 모델) | PASS | `REGIME_KO` app.js:1183 |
| MO-02 (A) | Capital input + 저장 (`#capInput`, `#capSave`, `#capNote`) | PASS | `#capInput` app.js:1260 |
| MO-03 (A) | 스캔 실행 (`#capRun`) KR | PASS | `#capRun` app.js:1260 |
| QR-01 | Status strip (summary line) | PASS | `점수 검증: 높은 점수의 수익 근거 아직 없음 · 참고용` qsf.js:221 |
| QR-02 | Market-state short text (`qsfStateShort`) | PASS | `qsfStateShort` qsf.js:55 |
| QR-03 | Market-state full block (`qsfMarketState`) | PASS | `qsfMarketState` qsf.js:44 |
| QR-04 | Caveat notice (`.qsf-caveat`) | PASS | `qsf-caveat` coin.js:15 |
| QR-05 | Track-record fold "과거 성적: 이 점수를 얼마나 믿을 수 있나" (`qsfRecordHtml`) | PASS | `qsfRecordHtml` qsf.js:152 |
| QR-06 | Per-row verdict reasons (`qsfWhyHtml`) | PASS | `qsfWhyHtml` qsf.js:128 |
| QR-07 | Stance block in strip (`qsfStanceDraw`) | PASS | `#qsfstripstance` qsf.js:220 |
| QR-08 | Stance buttons (방어/보통/공격 style segment) in nav row | CHANGED | qsf.js:681 — Stance change now shows a 6 s "되돌리기" toast (U-6); on a paired phone the buttons are disabled with "성향은 컴퓨터에서 바꿉니다" (UX spec 11.1) instead of failing with PHONE_MAC_ONLY |
| QR-09 | View switch (오늘 순위 / 스크리너 / 주문 계획·가상 장부 / 판정 일정) | PASS | `#qsf` qsf.js:18 |
| QR-10 | Strategy toggle 스윙 / 장기 | PASS | `qse-qsf-strategy` qsf.js:12 |
| QR-11 | Ticker evaluate form (`#qsfform`, `#qsfticker`, 평가) | PASS | `#qsfticker` qsf.js:233 |
| QR-12 | Evaluate status line `#qsfmsg` | PASS | `#qsfmsg` qsf.js:234 |
| QR-13 | Hash deep link `#qsf/CODE` + `qsfOpenCard` | PASS | `#qsf` qsf.js:18 |
| QR-14 | Tab return behaviour (`qsfReturn`) | PASS | `qsfReturn` qsf.js:263 |
| QR-15 | Folded-card reopen bar (`qsfFoldCard`) | PASS | `#qsfdetail` qsf.js:242 |
| QR-16 | Latest-scan cache (5 min, `qsfLatest`) | PASS | `qsfLatest` qsf.js:115 |
| QR-17 | Band edges / colours from server (`qsfBands`) | PASS | `qsfClass` qsf.js:23 |
| QR-18 | Fold-open persistence for long panels (`qsfFolds`) | PASS | `redrawAll` app.js:811 |
| QR-19 | Section-fold persistence for card (`qsfFold`/`qse-fold-<key>`) | PASS | `qsfFold` qsf.js:182 |
| QR-20 | Rank table (50 rows, one table) | PASS | `#qsfrank` qsf.js:236 |
| QR-21 | Expandable row | CHANGED | qsf.js:323 — One column: expands in place as before. Two columns: row click/Enter draws the card in the right panel (qsfPick), URL by replaceState, aria-selected (U-5) |
| QR-22 | Rank number tooltip + "상위 3" badge | CHANGED | qsf.js:738 — "상위 3" chip moved from status green (.badge.ok) to neutral .badge.rank (viz spec §8 item 15) |
| QR-23 | Name button -> stock screen | PASS | `linkish` app.js:1121 |
| QR-24 | Chip: 자료 {신뢰도} | PASS | `자료가 얼마나 있는지를 말합니다. 맞을 확률이 아닙니다.` qsf.js:389 |
| QR-25 | Chip: 자료 없는 요인 N (`qsfMissTag`) | PASS | `qsfMissTag` qsf.js:9 |
| QR-26 | Chip: 자사주 취득 · 참고 | PASS | `자사주 취득` qsf.js:403 |
| QR-27 | Stance chip: 성향 후보 / 성향 밖 · reason | PASS | `성향 후보` qsf.js:641 |
| QR-28 | Risk lines `.qr-risk` (4 kinds) | PASS | `qr-risk` qsf.js:698 |
| QR-29 | Sector column | PASS | `sectorKo` app.js:80 |
| QR-30 | Score cell: whole number + 경계 근처 badge + delta | CHANGED | qsf.js:725 (qsfDelta) — Score change colour no longer up/down: ink (.pts) at ≥1 point, grey under 1, sign kept (viz spec §8 item 2) |
| QR-31 | Domain bars (기술/재무/위험 관리/이벤트) | CHANGED | style.css:926 — Area bars now hidden when the ranking column (container wsmain) is <1184 px instead of viewport <1280 px; at 1920 with full menu they are hidden (layout spec 2.7). Note: viz spec §9 says "unchanged visibility" - spec conflict for the chief |
| QR-32 | 판단 label + 진입 text + "실행 대상 아님 · gate" | PASS | `qsfLabel` qsf.js:38 |
| QR-33 | 가점 / 감점 column (`qsfReason`) | PASS | `qsfCommonPush` qsf.js:715 |
| QR-34 | Explainer paragraphs above table | PASS | `QSF_RISK_NOTE}` qsf.js:401 |
| QR-35 | Footer lines | PASS | `종목 평가 · 생성` qsf.js:786 |
| QR-36 | Sticky header | UNVERIFIABLE | style.css:588 — thead sticky rule kept (style.css:588); table overflow now switched by container width (style.css:934). Sticky behaviour beside the right panel needs a rendered check |
| QR-37 | Empty/error states of rank | PASS | `#collect` index.html:45 |
| QR-38 | 직전 기록과 달라진 점 panel (`qsfChanges`) | PASS | `#qsfmsg` qsf.js:234 |
| QR-39 | 이전 대상(거래대금 상위 N) panel (`qsfCap`) | PASS | `#stock` assistant.js:30 |
| QC-01 | Card container header (`qsfDrawDetail`) | PASS | `#qsfdetail` qsf.js:242 |
| QC-02 | 닫기 button | PASS | `qsf-close").onclick` qsf.js:469 |
| QC-03 | 종목 화면 button | PASS | `qsf-tostock` qsf.js:452 |
| QC-04 | Notes under header | PASS | `qsfAuditLine` qsf.js:411 |
| QC-05 | Two strategy cards (`qsfCard`, one per SWING/LONG) | PASS | `qsfCard` qsf.js:306 |
| QC-06 | Summary strip | PASS | `주문 계획의 이 줄 보기` qsf.js:1109 |
| QC-07 | Link: 주문 계획의 이 줄 보기 | PASS | `planFocus` qsf.js:1114 |
| QC-08 | Link: 크기 계산기에 넣기 | PASS | `assist` portfolio.js:260 |
| QC-09 | Risk-gate notice | PASS | `위험 게이트 ${` qsf.js:594 |
| QC-10 | Earnings-unknown notice | PASS | `earnings_unknown` qsf.js:595 |
| QC-11 | Fold 근거 (open by default) | CHANGED | qsf.js:560 — 근거 균형 lists become diverging neutral bars sorted by size; labels, ±points, sum line and missing factors kept (viz spec 5.1, §8 item 1) |
| QC-12 | 쉽게 설명해줘 toggle | PASS | `쉬운 설명 닫기` app.js:184 |
| QC-13 | Stale-input notice (`qsfStaleNote`) | PASS | `qsfStaleNote` qsf.js:534 |
| QC-14 | Fund-period note (`qsfFundPeriodNote`) | PASS | `qsfFundPeriodNote` qsf.js:543 |
| QC-15 | Fold 계획 (가설) | PASS | `plan-held` qsf.js:604 |
| QC-16 | Previous-record line | PASS | `직전 기록 ` assistant.js:83 |
| QC-17 | Fold 요인별 계산 (N개) | PASS | `참고` coin.js:43 |
| QC-18 | Disclaimer line | PASS | `not_advice` qsf.js:609 |
| QC-19 | Fold 다섯 투자자와 투자위원회 | PASS | `icCardHtml` committee.js:73 |
| QC-20 | Fold 가격 범위 · 예측 층 FC-1 | PASS | `#qsffcfold` qsf.js:461 |
| QC-21 | Fold 이력과 기술 정보 | PASS | `#qsftechfold` qsf.js:466 |
| QC-22 | 당일 점검 (시세·공시·뉴스) (`qsfToday`) | PASS | `qsfToday` qsf.js:966 |
| QC-23 | 기록된 점수 이력 (`qsfHistory`) | PASS | qsf.js:499 — Tables kept; a small score plot broken at model changes added above each (U-8) |
| QC-24 | Risk grade line (`qsfRiskGradeLine`) | PASS | `qsfRiskGradeLine` qsf.js:419 |
| QC-25 | Rank-basis note | PASS | `QSF_RANK_NOTE` portfolio.js:202 |
| QC-26 | Scan-vs-now score note (`qsfScanNote`) | PASS | `qsfScanNote` qsf.js:622 |
| QS-01 | Screener panel + count line | PASS | `qsfScreenBuild` qsf.js:866 |
| QS-02 | Filter form | PASS | `/api/qsf/screen` qsf.js:901 |
| QS-03 | Checkbox filters | PASS | `/api/qsf/screen` qsf.js:901 |
| QS-04 | 초기화 button | PASS | `초기화` qsf.js:882 |
| QS-05 | CSV 저장 button (`qsfScreenCsv`) | PASS | `qsfScreenCsv` qsf.js:946 |
| QS-06 | Results table | PASS | `/api/qsf/screen` qsf.js:901 |
| QS-07 | Score button in screener row | CHANGED | qsf.js:928 — Two columns: the score button and a row click draw the card in the right panel and stay on the screener (D2, U-5). One column: switches to rank and evaluates as before |
| QS-08 | "N개 더 보기" pager | PASS | `/api/qsf/screen` qsf.js:901 |
| QS-09 | Sector spread line, formula-version notice, empty states | PASS | `조건에 맞는 종목이 없습니다.` qsf.js:912 |
| QE-01 | Order plan panel (`qsfPlanHtml`) | PASS | `qsfPlanHtml` qsf.js:1140 |
| QE-02 | Plan state: NO_SCAN / NO_ACCOUNT | PASS | `acctRecord` account.js:37 |
| QE-03 | Adverse-day size-factor notice + new-exposure cap | PASS | `size_factor` app.js:1324 |
| QE-04 | Stance note + left-out reasons; bands note; skipped-candidates line | PASS | `빠진 이유` qsf.js:1122 |
| QE-05 | Plan row highlight/jump target | PASS | `qsfPlanFocus` qsf.js:1117 |
| QE-06 | Paper book panel (`qsfPaperHtml`) | PASS | qsf.js:1236 — Panel kept; paper-book equity curve + 20-row table twin added under the tiles (U-8) |
| QE-07 | 회전율 규칙 비교 TO-1 block (`qsfTurnoverHtml`) | PASS | `qsfTurnoverHtml` qsf.js:1174 |
| QE-08 | Turnover rule switch button "이 규칙 쓰기 / 쓰지 않기" | PASS | `/api/qsf/turnover-rules` qsf.js:1198 |
| QE-09 | 순위 규칙 비교 RK-1 block + switch (`qsfRankBookHtml`) | PASS | `qsfRankBookHtml` qsf.js:1203 |
| QE-10 | Market-state line in plan | PASS | `qsfPlanState` qsf.js:1139 |
| QT-01 | 판정 일정 panel (`qsfReadings`) | PASS | `qsfReadings` qsf.js:1306 |
| QT-02 | 전체 일정 보기 | PASS | `details.qsf-readings-all` qsf.js:1323 |
| QT-03 | Fund-period switch button (연간 <-> 최근 4분기) | CHANGED | qsf.js:1330 — confirm() replaced by uiConfirm with the same sentence, OK "바꾸기" (U-6); disabled on a paired phone with a reason (UX spec 11.1) |
| QT-04 | Top-3 tracking (`qsfTop3`) | PASS | `qsfTop3` qsf.js:1355 |
| QT-05 | FC-1/FC-2 tracking panel | PASS | `fcTrack` forecast.js:144 |
| QT-06 | KR-M1 독자 매매법 panel (`qsfMethod`) | PASS | `qsfMethod` qsf.js:1007 |
| QT-07 | 시장 국면 가중치 도전자 panel (`qsfRegime`) | CHANGED | qsf.js:1054 — 충족/미달 now status colours c-ok / c-bad instead of price up/down, words kept (viz spec §8 item 12) |
| QT-08 | 미래 자료 차단 점검 panel (`qsfLookahead`) | PASS | `qsfLookahead` qsf.js:1099 |
| QT-09 | 전향 검증 panel (`qsfValidation`) | PASS | `qsfValidation` qsf.js:1338 |
| QT-10 | Fold toggles for track panels | PASS | `function qsfFolds` qsf.js:183 |
| FC-01 | Card fold "가격 범위 · 예측 층 FC-1" loader (`fcStock`) | PASS | `fcStock` forecast.js:115 |
| FC-02 | Test badge + reason line (`fcTestBadge/fcTestReason`) | PASS | `fcTestReason` forecast.js:18 |
| FC-03 | Range strip graphic (`fcStrip`) | CHANGED | style.css:341 — Stop/target marks now ink (were down/up), 50%/80% bands neutral --band-50/80 (were accent) (viz spec §8 items 6-7; CSS only, forecast.js unchanged) |
| FC-04 | Range table | PASS | `function fcStockHtml` forecast.js:115 |
| FC-05 | Level placement table (`fcLevelLines`) | PASS | `fcLevelLines` forecast.js:101 |
| FC-06 | Touch probabilities (`fcTouchLines`) FC-2 | PASS | `fcTouchLines` forecast.js:56 |
| FC-07 | Direction numbers fold `fc-fold` (`fcDirection`) | PASS | `fcDirection` forecast.js:109 |
| FC-08 | Tracking panel header + FC-1 past test table | PASS | `fcTrackHtml` forecast.js:144 |
| FC-09 | Forward record table | PASS | `fcTrack` forecast.js:144 |
| FC-10 | Direction record table | PASS | `fcTrack` forecast.js:144 |
| FC-11 | FC-2 touch grid + record | PASS | `fcTrack` forecast.js:144 |
| FC-12 | Known-limits details | PASS | `알려진 한계` forecast.js:186 |
| IC-01 | Tab header + disclaimer | PASS | `다섯 투자자 엔진과 통합 위원회` committee.js:117 |
| IC-02 | View switch (위원회 현황 / 여섯 포트폴리오 / 투자자 비교 / 가상 성과) | CHANGED | committee.js:126 — View is now in the URL (#committee:dash\|ports\|compare\|perf) and button changes push history, so Back returns (O-7) |
| IC-03 | 위원회 현황 panel (`icDash`) | PASS | `icDash` committee.js:141 |
| IC-04 | Buy-condition top table | PASS | `qsfOpenCard` qsf.js:339 |
| IC-05 | 여섯 포트폴리오 landing (not yet generated) | PASS | `여섯 포트폴리오 받아보기` committee.js:3 |
| IC-06 | Generate / "다시 받아보기" | PASS | committee.js:220 — Same flow; second press ignored while generating (icState.getting), button shows "작성 중…" |
| IC-07 | Portfolio sub-tabs + overlap line | PASS | `겹치는 종목` committee.js:198 |
| IC-08 | Portfolio detail (`icPortHtml`) | PASS | `icPortHtml` committee.js:168 |
| IC-09 | 투자자 비교 (`icCompare`) | PASS | `icCompare` committee.js:243 |
| IC-10 | 가상 성과 (`icPerf`) | PASS | `icPerf` committee.js:264 |
| IC-11 | Stock card embed (`icCardHtml`) | PASS | `icCardHtml` committee.js:73 |
| IC-12 | Investor card (`icInvestorHtml`) | PASS | `icInvestorHtml` committee.js:18 |
| IC-13 | Committee verdict (`icCommitteeHtml`) | PASS | `icCommitteeHtml` committee.js:51 |
| IC-14 | "포트폴리오 받아보기" button in card (`icPlace`) | PASS | `icPlace` committee.js:86 |
| IC-15 | Rows -> score card (`icOpenRows`) | PASS | `qsfOpenCard` qsf.js:339 |
| TD-01 | Panel title "오늘" + market badge (미국/한국/코인) | PASS | `state.market` app.js:22 |
| TD-02 | Question box (`#asst-form`, input `#asst-q` maxlength 200, button "묻기") | PASS | `#asst-form` assistant.js:106 |
| TD-03 | "물어볼 수 있는 것" button (`#asst-help`) | PASS | `#asst-help` assistant.js:107 |
| TD-04 | Answer card (`.asst-answer`) | PASS | `#asst-out` assistant.js:108 |
| TD-05 | "이어서 물어보기" follow chips and "눌러서 물어보기" example chips | PASS | `follow` assistant.js:42 |
| TD-06 | Answer's "<탭> 탭에서 보기" ghost button | PASS | `qsfOpenCard` qsf.js:339 |
| TD-07 | "사도 돼?" buy-check answer (BUY_CHECK intent) | PASS | `/api/assistant/ask` assistant.js:55 |
| TD-08 | Other stock questions (11 stock intents): STOP 손절 어디?, RANGE 얼마까지 움직일까?, EARNINGS 실적 언제... | PASS | `/api/assistant/ask` assistant.js:55 |
| TD-09 | Plain questions (11): HELP, TRUST 이 점수 믿어도 돼?, COST 수수료, ALERTS 걸어 둔 알림, VERDICTS 판정은 언... | PASS | `/api/assistant/ask` assistant.js:55 |
| TD-10 | Unknown question fallback | PASS | `/api/assistant/ask` assistant.js:55 |
| TD-11 | COIN-market questions ("코인 상위는?", "코인 시장 상태 어때?", "비트코인 분석해 줘", "솔라나 점수 왜 이래?", "이 코인 점... | PASS | `askAssistant` assistant.js:60 |
| TD-12 | Ask from elsewhere: `askAssistant(q)` (command palette, coin row click, stock-tab short... | PASS | `askAssistant` assistant.js:60 |
| TD-13 | Brief panel header (`#asst-brief` h2 = `headline_main`) + meta "<시장> 시장 · 기준 거래일 <date | CHANGED | assistant.js:154 — Headline moved from the brief h2 to .asst-headline in the top strip; h2 is now "오늘 [시장]"; meta line kept (layout spec 3.1, D5) |
| TD-14 | "읽지 못한 부분" banner | PASS | `읽지 못한 부분` assistant.js:150 |
| TD-15 | Market number tiles row (`.asst-tiles`) | PASS | `today` portfolio.js:20 |
| TD-16 | Market-state tile "시장 상태 점수 미반영" | PASS | `today` portfolio.js:20 |
| TD-17 | 오늘의 후보 (candidates) block | PASS | `today` portfolio.js:20 |
| TD-18 | Candidate row: name chip + ticker, band label, integer score with delta vs previous rec... | CHANGED | assistant.js:82 — Candidate score change and ▲▼ points use ink (.pts) / grey instead of up/down (viz spec §8 item 2) |
| TD-19 | "할 일과 알림" grouped lists: 먼저 볼 것 (ACT), 오늘 챙길 것 (DUE), 참고 (INFO), each h3 with count badge | PASS | `today` portfolio.js:20 |
| TD-20 | Item body: first sentence as title (`asstFirst`), rest folded in `<details class="asst-... | PASS | `asstFirst` assistant.js:20 |
| TD-21 | Item action buttons: ticker chip and "<탭> 탭에서 보기" (view-aware: PLAN_UNAVAILABLE/ORDERS_... | PASS | `ASST_TAB_KO` assistant.js:4 |
| TD-22 | 작업 상태 (자동 실행·기록) fold (`.asst-ops`) | PASS | `today` portfolio.js:20 |
| TD-23 | Fallback note under brief when no candidates block | PASS | `note` portfolio.js:187 |
| TD-24 | First-load states | PASS | `today` portfolio.js:20 |
| TD-25 | Return-to-tab refresh (`RETURN.today` = `asstReturn`) | PASS | `asstReturn` assistant.js:125 |
| TD-26 | Sparkline redraw (`redrawOn("today","sparks")`) | PASS | `redrawOn` app.js:810 |
| TD-27 | Coin-market brief (COIN) | PASS | `/api/assistant/today` assistant.js:141 |
| AC-01 | Entry points: header button "내 계좌" (`#acctbtn`), bottom-bar "내 계좌", group nav "내 계좌", `... | PASS | `#acctbtn` index.html:44 |
| AC-02 | Journal-integrity banner | PASS | `/api/account` account.js:151 |
| AC-03 | Panel "통합 계좌" header with 원화/달러 segmented toggle (`#acctunit`) | PASS | `#acctunit` account.js:163 |
| AC-04 | Missing-price notice and missing-FX notice | PASS | `/api/account` account.js:151 |
| AC-05 | Big total + secondary figure ("≈ $..." or "≈ ₩...") | PASS | `/api/account` account.js:151 |
| AC-06 | KV summary: 총 손익, 오늘 손익 (coloured), 현금, 주식·코인 평가액, 넣은 돈 (입금 − 출금), 환율 + date | PASS | `/api/account` account.js:151 |
| AC-07 | Per-account table (미국 주식 USD / 한국 주식 KRW / 코인 KRW): 평가액, 원화로/달러로, 비중, 현금, 주식·코인, 총 손익, ... | PASS | `/api/account` account.js:151 |
| AC-08 | "자세히" button per US/KR row (none for 코인) | PASS | `setMarket` app.js:607 |
| AC-09 | 보유 종목 table (all three accounts merged, sorted by value): 계좌, 종목 (name+code), 구분 (장기/스윙... | PASS | `/api/account` account.js:151 |
| AC-10 | Trade form "거래 기록 추가" (`#acctform`): 종류 select (9 kinds: 이미 가지고 있는 종목 추가 HOLD, 매수, 매도, ... | PASS | `#acctform` account.js:48 |
| AC-11 | HOLD kind ("이미 가지고 있는 종목 추가") | PASS | `ACCT_HOLD_HINT` account.js:6 |
| AC-12 | Per-kind hint line (`#accthint`) | PASS | `#accthint` account.js:56 |
| AC-13 | Ticker blur validation (`f.ticker.onblur`) | PASS | `#acctmsg` account.js:56 |
| AC-14 | Submit "기록 추가" | CHANGED | account.js:95 — Double submit blocked (acctBusy, button disabled until the form is redrawn); success line now "기록했습니다: <종류 종목 수량> · <계좌>. 다시 불러오는 중…" then a "방금 기록 취소" button that appends a VOID (U-7, O-9) |
| AC-15 | Prefill from other screens (`acctRecord(market, fill)`) | PASS | `#jgo` portfolio.js:76 |
| AC-16 | 거래 기록 table (last N of M; "추가만 가능, 취소는 별도 기록으로 남습니다") | PASS | `journal` portfolio.js:216 |
| AC-17 | Row "취소" button | CHANGED | account.js:126 — confirm() replaced by uiConfirm, same sentence, OK "기록 취소" (danger); shared acctVoid (U-6) |
| AC-18 | Footer notes panel + coin-price error line | PASS | `notes` portfolio.js:187 |
| AC-19 | Loading / error states | PASS | `errBox` app.js:186 |
| PF-01 | Journal-integrity notice (incl. line number, file path hint) | PASS | `/api/portfolio` portfolio.js:33 |
| PF-02 | "시작하기" empty-state panel | PASS | `/api/portfolio` portfolio.js:33 |
| PF-03 | "주식 두 계좌 합계" panel (KRW: 한국 계좌, 미국 계좌 + $ amount, 원/달러 + date; coin excluded; notice if... | PASS | `total` portfolio.js:148 |
| PF-04 | 계좌 요약 panel (한국(원화)/미국(달러)) with STALE badge, missing-price notice, big equity (+ "≈ ₩"... | PASS | `/api/portfolio` portfolio.js:33 |
| PF-05 | 경고 list ("화면 표시만 하며 주문하지 않습니다") | PASS | `화면 표시만 하며 주문하지 않습니다` portfolio.js:45 |
| PF-06 | Holdings tables split 장기 / 스윙 / 구분 없음: header summary ("N개 · 평가액 · 주식 중 %(목표 %) · 미실현 %... | CHANGED | portfolio.js:89 — One column: row click opens stock as before. Two columns: row click selects into #pf-pick (보유 점검); name button opens stock (U-5) |
| PF-07 | Empty holdings: "보유 종목이 없습니다." | PASS | `보유 종목이 없습니다.` app.js:154 |
| PF-08 | 보유 판정 (`#sigpanel`) and per-row cells (score, action, left, review) filled asynchronously | PASS | `#sigpanel` portfolio.js:179 |
| PF-09 | 섹터 비중 bars (over-limit bar styled `over`) | PASS | `sectors` committee.js:174 |
| PF-10 | 위험 분석 panel (`#risk-panel`) | CHANGED | portfolio.js:142 — Risk-share bars become diverging when any share is negative and missing shows no bar; correlation cells get a neutral \|r\| wash (viz spec §8 item 17, U-8) |
| PF-11 | 계좌 수익률 vs benchmark chart (`#eqc` canvas) + summary line "시작 <date> 이후 · 내 계좌(TWR) x% ·... | CHANGED | portfolio.js:241 — Was "no hover": now crosshair (pointer/touch/keyboard), end tags instead of the in-plot "● 내 계좌" text, month-end table twin, empty canvas hidden (viz spec V-16) |
| PF-12 | 매매 성과 panel: KV (매도 건수, 승률, 평균 이익/손실, 손익비, 실현 손익 합계), small-sample note (<20), by-style... | PASS | `stats` portfolio.js:209 |
| PF-13 | "거래 기록 추가" panel -> button "통합 계좌에서 기록하기" (`#jgo`) | PASS | `#jgo` portfolio.js:76 |
| PF-14 | 거래 기록 table with per-row "취소" | CHANGED | portfolio.js:85 — confirm() replaced by uiConfirm, same sentence (U-6) |
| PF-15 | Footer note panel (`d.note`) | PASS | `/api/portfolio` portfolio.js:33 |
| PF-16 | Loading/error and stale-market guard (`mk !== state.market`) | PASS | `errBox` app.js:186 |
| AS-01 | 포지션 크기 계산기 form (`#szform`): 종목 코드, 구분 (보유 구분 또는 공통 / 장기 / 스윙), 진입가 (blank = last close... | PASS | `#szform` portfolio.js:289 |
| AS-02 | Calculator result: big "N주", style, entry, stop (source, −x%), KV (매수 금액, 계좌 대비 비중, 손절 ... | PASS | `/api/sizing` portfolio.js:367 |
| AS-03 | "이 수량으로 매수 기록 작성" button (`#tojournal`) + "체결된 뒤에 기록하세요." | PASS | `#tojournal` portfolio.js:377 |
| AS-04 | Auto-fill from a score card (`state.sizeFill`) | PASS | `크기 계산기에 넣기` portfolio.js:327 |
| AS-05 | 알림 센터 (`#alertc`, alerts.js): form (조건: 종가 이상/이하, 하루 등락폭, QSF 점수 구간이 바뀜 (+스윙/장기), 실적 발표... | PASS | portfolio.js:319 — Alert centre still rendered into #alertc (now lower row of 매매 보조); double submit blocked; reachable by #assist:alerts |
| AS-06 | 다가오는 실적 발표 (`#earncal`) | PASS | `#earncal` portfolio.js:320 |
| AS-07 | 위험 관리 설정 form (`#stform`, 17 fields: 장기/스윙 1회 위험 %, 최대 비중 %, ATR stop multiples, 장기 목표 ... | PASS | `#stform` portfolio.js:299 |
| AS-08 | P6-11B 계획 대조 (`#plan`, US only; removed on KR) | PASS | `#plan` portfolio.js:297 |
| AS-09 | Loading/error | PASS | `errBox` app.js:186 |
| PT-01 | Title "모의 매매 기록" + badges "가상의 계좌" / "주문을 보내지 않습니다" + explainer lines (note, fee basis,... | PASS | `주문을 보내지 않습니다` paper.js:94 |
| PT-02 | Integrity-problem state | PASS | `/api/paper-trade` paper.js:51 |
| PT-03 | KV tiles: 평가액, 현금, 넣은 모의 자금, 총 손익 (+%), 끝난 거래 순손익, 낸 수수료·세금, 끝난 거래/이익 거래, 거래당 평균 순수익률 (... | PASS | `/api/paper-trade` paper.js:51 |
| PT-04 | Entry form (`#ptform`): 종류 (매수, 매도, 모의 자금 넣기, 모의 자금 빼기), 종목 코드, 수량, 가격, 금액, 수수료·세금 (bla... | PASS | paper.js:69 — Same form; second submit ignored while the first is in flight (ptBusy) |
| PT-05 | Live fee preview (`#ptpreview`) | PASS | `#ptpreview` paper.js:30 |
| PT-06 | 보유 중 table (종목, 수량, 평균 매수가 with tooltip, 최근 종가 + date, 평가액, 평가 손익 + %, 팔 때 수수료·세금 (tool... | PASS | `보유 중인 모의 종목이 없습니다.` paper.js:125 |
| PT-07 | "매도 기록" button per position | PASS | `ptPrefill` paper.js:5 |
| PT-08 | 끝난 거래 table (매도일, 종목, 수량, 매수가, 매도가, 산 금액, 판 금액, 수수료·세금 (tooltip split), 순손익, 순수익률, 보유) ... | PASS | `아직 매도까지 끝난 거래가 없습니다.` paper.js:127 |
| PT-09 | 기록 N건 table (날짜, 종류, 종목, 수량, 가격/금액, 수수료·세금 + 자동/직접, 메모) with per-row "취소" and "취소됨" bad... | CHANGED | paper.js:82 — confirm() replaced by uiConfirm, same sentence (U-6) |
| PT-10 | Loading/error and stale-market guard | PASS | `errBox` app.js:186 |
| MO-01 (C) | Baseline model panel header (name, status badge FROZEN, role) | PASS | `/api/capital` app.js:1210 |
| MO-02 (C) | 투자 자본금 input (`#capInput`) + 저장 (`#capSave`) + note line (`#capNote`) | PASS | `#capInput` app.js:1260 |
| MO-03 (C) | KR "스캔 실행" button (`#capRun`, KR only) + status note (`#capRunNote`) | PASS | `#capRunNote` app.js:1260 |
| MO-04 (C) | "더 최근 스캔 ... 채점한 종목이 없었습니다" notice | PASS | `/api/model` app.js:1236 |
| MO-05 (C) | Last-scan KV (최근 전체 스캔, 기준 거래일, 결과 REC_KO, 시장 국면 REGIME_KO, 기준 자본) | PASS | `/api/model` app.js:1236 |
| MO-06 (C) | 모델 상위 종목 table: 순위, 종목+name, 섹터, 기준가, 모델 알파 (US) or 모델 점수 (KR) (tooltip "수익률이 아닙니다"), 목... | PASS | `기록된 전체 스캔이 없습니다.` app.js:1269 |
| MO-07 (C) | 전향적 추적 panel (status badge; 기록된 실행, 관찰 건수, 집계 제외 (중복 스캔, tooltip), 최근 갱신, outcome-state... | PASS | `outKo` app.js:1186 |
| MO-08 (C) | 도전자 모델 비교 (전향적) table (`#cmp`; US only, replaces the "도전자 모델" placeholder panel) | PASS | `#cmp` compare.js:7 |
| MO-09 (C) | "데이터 갱신 + 오늘 신호 기록" button (`#labrun`) + message (`#labmsg`) | PASS | `#labmsg` lab.js:43 |
| MO-10 (C) | Automation status line (`#autoline`) | PASS | `#autoline` lab.js:44 |
| MO-11 (C) | KR variant | PASS | `if (isKR()) return;` lab.js:11 |
| LB-01 | 전향 기록 현황 panel (`#recpanel`): model-version tech id; alert list (or "문제없이 기록이 쌓이고 있습니다.") | PASS | `#recpanel` lab.js:206 |
| LB-02 | QSF 점수 기록 KV (미국/한국: 기록 거래일, 현재 버전, 마지막 기록) | PASS | `record` lab.js:154 |
| LB-03 | 판단까지 남은 기간 table (지평: 스윙/장기 N거래일, 주 지평 highlight; 필요 거래일; 미국/한국 독립 표본 x / target (만기 n)... | PASS | `record` lab.js:154 |
| LB-04 | 기준 모델 기록 KV (자본금 입력됨/미입력, 결과 확정/기준, 대기, 유효 스캔 날짜, 마지막 유효 스캔) or error "추적 기록을 읽지 못했습니다" | PASS | `record` lab.js:154 |
| LB-05 | 한국 결합 점수 기록 KV (기록 거래일, 마지막, 늦은 기록, 독립 표본 20일, 남은 기간, 시세 대조 KRX) + 재무 점수 기록 line + 공시 사... | PASS | `record` lab.js:154 |
| LB-06 | 미국 도전자 점수 기록 KV (기록 거래일, 마지막, 늦은 기록, 스윙/장기 독립 표본) + disclaimer + "첫 기록 대상은 <date>입니다" | PASS | `record` lab.js:154 |
| LB-07 | 시세 이력 점검 (`recAudit`): per market checked, flagged (+severe), reference scan, provision... | PASS | `recAudit` lab.js:158 |
| LB-08 | 자동 실행 KV (디스크 여유, 마지막 백업, 설치, 실행 시각, 마지막 실행, 기준 거래일) + step status line (완료/실패/건너뜀/자료 대... | PASS | `automation` lab.js:49 |
| LB-09 | 연구실 US-only gate: KR shows "연구실은 아직 미국 전용입니다. 위에서 미국을 선택하면 볼 수 있습니다." | PASS | `연구실은 아직 미국 전용입니다. 위에서 미국을 선택하면 볼 수 있습니다.` lab.js:86 |
| LB-10 | 과거 시뮬레이션 panel (참고용 badge): limitations notice list, 거래 비용 segmented (`#costseg`, bps f... | CHANGED | lab.js:4 — Model colours moved to series slots --s1..s4, SPY --bench (was --ok / MA colours); log-axis ticks on round %; crosshair added (viz spec 2.5, §8 item 11) |
| LB-11 | 성과 지표 table (모델, 누적, 연환산, 변동성, 샤프, 최대 낙폭, 회전율; SPY row) + 연도별 SPY 대비 초과수익 table | PASS | `/api/lab/research` lab.js:89 |
| LB-12 | 규칙 table (미리 고정, 튜닝하지 않음) | PASS | `/api/lab/research` lab.js:89 |
| LB-13 | Unavailable state: reason + "모델 탭의 '데이터 갱신' 버튼으로 가격 데이터를 먼저 받으세요." | PASS | `모델 탭의 '데이터 갱신' 버튼으로 가격 데이터를 먼저 받으세요.` lab.js:91 |
| CH-01 | Ticker form (`#cha-form`, input `#cha-q`, "보기") | PASS | `#cha-form` chart.js:48 |
| CH-02 | Shortcut chips: market indices (US ^GSPC S&P 500, ^IXIC 나스닥 종합; KR ^KS11 코스피, ^KQ11 코스닥... | PASS | `recentTickers` app.js:622 |
| CH-03 | Default ticker resolution (`chaTicker`): remembered -> open stock -> first recent -> index | PASS | `chaTicker` chart.js:27 |
| CH-04 | Range segmented: 3개월/6개월/1년/3년/5년/10년 | PASS | `chart` chart.js:34 |
| CH-05 | Chart-type segmented: 캔들 / OHLC / 선 | PASS | `qse-chart` app.js:6 |
| CH-06 | Checkboxes 볼린저밴드, 신호 표시 | PASS | `qse-chart` app.js:6 |
| CH-07 | Moving-average checkboxes (`ma_choices` with colour swatch and "N일"), max `ma_max` (ext... | PASS | `chart` chart.js:34 |
| CH-08 | Four-pane canvas stack: price (candles/OHLC/line, MA lines, Bollinger band fill + dashe... | PASS | `redrawOn` app.js:810 |
| CH-09 | Crosshair + tooltip (`#cha-x`, `#tip`) | PASS | `#cha-x` chart.js:57 |
| CH-10 | Legend line (MA colours, band, volume avg, RSI/MACD, signal glyph legend "모두 검증 안 됨") | CHANGED | chart.js:176 — Signal glyphs and RSI/MACD lines now ink, MACD histogram neutral (viz spec §8 items 3-5, 13) |
| CH-11 | Meta line (source, fetched time, status badge, live badge, date range; "가격 기록이 고른 기간보다 ... | PASS | `chart` chart.js:34 |
| CH-12 | UNAVAILABLE state: "가격 자료를 받지 못했습니다. 종목 코드를 확인하세요." (clears lines and signals); fetch e... | PASS | `가격 자료를 받지 못했습니다. 종목 코드를 확인하세요.` chart.js:96 |
| CH-13 | "지금 상태" panel: caveat notice (`settings.caveat`) + one paragraph per indicator line (na... | PASS | `lines` qsf.js:952 |
| CH-14 | "최근 신호" table: date, ▲/▼/● label (tooltip = meaning), close; latest 20 + `<details>` "나... | CHANGED | chart.js:110 — ▲/▼ glyphs in 최근 신호 no longer coloured up/down (viz spec §8 item 3) |
| CH-15 | Entry points from other screens: stock tab "차트분석" button, command palette | PASS | `chartWith` chart.js:34 |
| CH-16 | Stale-response guard (ticker/range/MA/market changed while loading) | PASS | `chaTicker` chart.js:27 |
| CP-01 | Range segmented 3개월/1년/5년 | PASS | `/api/compare` compare.js:61 |
| CP-02 | Selected chips (colour swatch + name + × remove) | PASS | `아직 없습니다.` app.js:158 |
| CP-03 | Add form (`#cmp-add`, "종목 코드 추가 (예: NVDA, 005930)", 추가) + index chips (S&P 500, 나스닥 종합,... | PASS | `#cmp-add` compare.js:46 |
| CP-04 | Defaults (first visit): SPY or ^KS11 plus recent tickers of the market (up to 3) | PASS | `qse-recent` app.js:5 |
| CP-05 | Overlay return chart (0% start, dividend-inclusive), direct end labels when <=4 series ... | CHANGED | compare.js:84 — Hover is now pointer/touch/keyboard (was mouse only); direct end labels only when the canvas is ≥520 px wide, else the legend names lines (viz spec 1.6, 1.10) |
| CP-06 | Meta line (source, fetched, date range, basis, "미국과 한국을 섞으면 두 시장이 모두 연 날만 남습니다.", "가격 없... | PASS | `compare` compare.js:32 |
| CP-07 | 기간 성과 table (기간 수익률, 연환산 only if >= 0.9y, 연 변동성, 최대 낙폭; stock rows clickable -> stock t... | PASS | `compare` compare.js:32 |
| CP-08 | 일간 수익률 상관계수 matrix (needs >= 2) | CHANGED | compare.js:156 — Cells get a neutral \|r\| wash, sign in the number (U-8 neutral \|r\| shading) |
| CP-09 | 상관계수의 변화 rolling-correlation chart vs first item (window from server) + legend "마지막 x" ... | PASS | `compare` compare.js:32 |
| CP-10 | Entry point `compareWith(list)` from other screens | PASS | `compareWith` compare.js:32 |
| MP-01 | Heatmap mode segmented: 1일 / 5일 / 1개월 / QSF 점수 | PASS | `qse-heat-view` app.js:5 |
| MP-02 | Score-style segmented: 스윙 점수 / 장기 점수 | PASS | `/api/qsf/heatmap` map.js:86 |
| MP-03 | Palette segmented: 기본 색 / 파랑·주황 (colour-blind safe pair, light and dark values), dimmed... | PASS | `파랑·주황` map.js:66 |
| MP-04 | Treemap canvas: sector groups with Korean sector names, tile size = market cap, colour ... | PASS | `/api/qsf/heatmap` map.js:86 |
| MP-05 | Legend line (size = market cap; colour meaning and span) | CHANGED | map.js:150 — Coloured-text legend replaced by a gradient key with plain text and an "값 없음" outline key; score mode uses a neutral ramp (U-8, viz spec §8 items 8, 16) |
| MP-06 | Meta line (source, scan session, model version, basis, "시가총액 없음: ...") / "UNAVAILABLE 스... | PASS | `/api/qsf/heatmap` map.js:86 |
| RO-01 | 업종 순환 그래프 (RRG approximation) canvas: 4 quadrants (선도/약화/침체/개선) tinted, axes labels "상대... | CHANGED | rotation.js:5 — Quadrant colours remapped (선도 s3, 약화 s2, 침체 grey, 개선 s7) so Korean red/blue no longer reads as phase; hover adds keyboard (viz spec 2.4, §8 item 10) |
| RO-02 | Rotation meta (source, fetched, benchmark, last week, method, missing) / UNAVAILABLE / ... | PASS | `/api/rotation` rotation.js:18 |
| RO-03 | 업종 상대 성과 table sorted by quadrant then ratio: 업종, 국면 (coloured dot), 상대강도 비율, 모멘텀, 지수 대... | CHANGED | rotation.js:5 — Quadrant dots follow the new RRG colours (viz spec 2.4) |
| SP-01 | 업종 점수 상위 종목 panel (`#rrg-picks`, initially hidden) | CHANGED | sectorpicks.js:16 — Scroll on selection is block "nearest" (was "start") so the page does not jump beside the table (layout spec 3.3) |
| SP-02 | Pick plan (`#sp-plan`): click a pick -> highlights it and loads a plan with two cards (... | PASS | `#sp-plan` sectorpicks.js:34 |
| MP-07 | Stale-market / stale-selection guards, `redrawOn("map","heat"/"rrg")` | PASS | `redrawOn` app.js:810 |
| CO-01 (coin) | Tab/group visibility: group "코인" and bottom-bar "코인" shown only in market COIN; market ... | PASS | `state.market` app.js:22 |
| CO-02 (coin) | Caveat fold (`details.notice.qsf-caveat`, summary "대상 코인끼리의 순위입니다. 오를지 내릴지를 말하지 않습니다." ... | PASS | `caveats` coin.js:14 |
| CO-03 (coin) | Mode notice for SIMPLE rank ("등록된 점수가 아닌 간이 순위입니다. ...") and title switch 코인 상대 순위 / 코인... | PASS | `간이 순위` coin.js:1 |
| CO-04 (coin) | Status badge + "<time> 마감 · 4시간봉" badge + stale warning (SIMPLE: hours old, fetch error... | PASS | `latest` lab.js:29 |
| CO-05 (coin) | UNAVAILABLE state (reason, source) | PASS | `latest` lab.js:29 |
| CO-06 (coin) | Ranking table: 순위, 코인 (+name, "1,000개 단위"), 기대 상대 폭 (+ "비용 넘음" badge) or 간이 점수, 가격(USDT... | PASS | `coin-row` coin.js:31 |
| CO-07 (coin) | "how" explainer + footer (source, version or "등록된 점수 아님") | PASS | `등록된 점수 아님` coin.js:43 |
| CO-08 (coin) | 코인 시장 panel (참고 badge): 비트코인 price, 7일, 30일, 200일 평균 대비, 1년 고점 대비, 7일 동안 내린 코인 n/N, 200... | PASS | `market` app.js:28 |
