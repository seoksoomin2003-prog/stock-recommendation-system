# Existing UI feature inventory (baseline before the workstation redesign)

Written 2026-11-24, before any redesign code changes. Baseline commit: `7c8e0af` on `main`.

This document is the preservation contract for the redesign. Every row below must still exist and work afterwards. No row may disappear without the owner's explicit approval.

**Method**
- Three read-only agents covered the 22 JS files, `index.html` and `style.css`:
  - Part A: shell, market screens and the stock screen.
  - Part B: score and committee screens.
  - Part C: Today, accounts, charts, lab and coin.
- The coordinator merged the parts, checked open points against the code, and added the rows for the '사도 돼?' conclusion (merged after Part C was read).
- **Not verified:** layout descriptions come from reading the code. Rendered screenshots are part of the regression and critique phases.

## 0. Project discovery

| Item | Finding |
|---|---|
| Frontend framework | None. Vanilla JS, no build step. `index.html` loads `theme.js` in the head and 22 plain scripts at the end of the body. Global functions, `"use strict"` per file. |
| Server | Python `ThreadingHTTPServer` (`terminal/server.py`). One route table of 93 `("GET"\|"POST", "/api/...")` handlers, plus static files. Kept running by launchd (`com.quantengine.terminal`, port 8765). |
| Routing | Hash routing in `app.js` (`tabHash`, `fromHash`, `show(tab, push)`). Forms: `#tab`, `#stock/CODE`, `#qsf/CODE`, `#qsf:view`. Back and forward use `history.pushState`. |
| Navigation structure | 7 groups and 17 tab destinations (`nav.groups`, `nav.tabs`). On phones (≤640 px): a bottom bar plus a 더보기 sheet. The 코인 group appears only in the COIN market. |
| State | One global `state` object (`market`, `tab`, `ticker`, `card`, `loaded`, …) plus per-screen objects (`qsfState`, `icState`, `heat`, …). |
| Persisted UI state | localStorage `qse-*` keys: market, theme, keys, recent, qsf-view, qsf-strategy, qsf-folds, fold-*, heat-view, acct-unit, chart, compare. Old names are migrated once by `STORE_RENAMES`. |
| Styling system | One `style.css` (~600 long lines) with tokens on `:root` (colours, 7 type sizes, 4 px space grid, radii, shadows, z layers). One dark block `:root[data-theme="dark"]`. Colour rule C: `data-color="kr"` swaps up/down to red/blue. Breakpoints 640 / 1023 / 1600 px (plus 380/400). |
| Shared components | `ui.js` builders (escaped text); `esc`, `pct`, `money`, `stamp`, `tickerLabel`, `notify`, `errBox`, `DASH`; `.panel`, `.seg`, `.badge`, `.chip`, `.tbl-wrap`, `.fold` and the card fold pattern; `markKeyable` for keyboard support; `redrawOn` for redraws. |
| Charts | Hand-drawn `<canvas>`, no chart library: candles with moving averages, sparklines, equity curve, compare lines, the heatmap treemap, forecast bands, domain bars. Each carries `role=img` and a label. |
| Tests | 171 files under `tests/`. About 25 pin static-file source text, so a UI change must update its pins in the same commit. |
| Data rules carried into the UI | Missing data is never shown as 0. Stale data is labelled. Judgement labels are rule results, not advice. Scores are computed only on the server. |

## 1. Screen-level preservation map

Owner decisions of 2026-11-24 used in the "new location" column:
- Left vertical menu for groups and tabs.
- A compact top bar with search, market switch, market state, data time and settings.
- Dark theme by default, light kept.
- Colour rule C kept.
- The QuantMSCI image did not arrive, so the design proceeds from the written layout.

Every tab keeps its id, hash and render function. Only the shell and in-screen arrangement change. Per-feature rows (sections A–C) keep their screen. Where a feature moves inside its screen, the region is given in `WORKSTATION_LAYOUT_SPECIFICATION.md` and checked in `FUNCTIONAL_REGRESSION_REPORT.md`.

| Destination (tab id) | Today's place | New place | Workstation region use |
|---|---|---|---|
| Shell: brand, market switch, search, 내 계좌, 지금 수집, 폰 연결, ⌘K, keys, theme, status bars | Top header row | Top bar: brand · market · search · market state · data time · actions (collect, phone, ⌘K, theme in an overflow) | — |
| Group bar and sub-tabs | Horizontal rows under the header | Left vertical menu with groups as headings and tabs as items; collapsible; phones keep the bottom bar | — |
| today (오늘) | Group 오늘 | Same | Main: question box, answer, items · Right: market tiles, candidates · Lower: ops status |
| overview (시장 개요) | 시장 | Same | Main: index and sector tables/tiles · Right: charts · Lower: calendar/news if present |
| map (시장 지도) | 시장 | Same | Main: heatmap · Right: rotation and sector picks |
| macro (거시) | 시장 | Same | Chart-oriented panels |
| stock (종목 정보) | 종목 | Same | Research layout: header · chart + score summary · lower section tabs (fundamentals, filings, peers, description) |
| watch (관심종목) | 종목 | Same | Table main · selected-row detail right |
| chart (차트분석), compare (비교) | 차트 | Same | Chart main · controls and notes right |
| account (통합 계좌) | 내 계좌 | Same | Holdings table main · allocation/totals right · form lower |
| portfolio (시장별 자세히), assist (매매 보조), paper (모의 매매) | 내 계좌 | Same | Table main · charts right · forms lower |
| qsf (순위·카드) | 점수 | Same | **Ranking table main · score card right (from 1280 px) · plan/track views in the same tab** |
| committee (투자위원회) | 점수 | Same | Status numbers top · views main |
| model (모델), lab (연구실) | 검증·기록 | Same | Tables and records |
| coin (코인) | 코인 (COIN market only) | Same | Table main |

## 2. Rows added by the coordinator (merged after Part C was read)

| ID | Feature | Screen | Interaction | API / backend | Data | Hidden? | Writes? | Regression check |
|---|---|---|---|---|---|---|---|---|
| TD-V1 | '사도 돼?' conclusion box: 사도 됨 / 기다림 / 사지 않음, the reason, the condition that would change it, the other strategy's line, in the judgement colours | today (answer area) | Ask "X 사도 돼?" → the box appears above the sections | POST /api/assistant/ask → `assistant.buy_verdict` | ledger snapshot, stance file, market state | No | No | tests/test_buy_verdict.py, tests/test_assistant.py |
| TD-V2 | '결론 자세히' section: the chosen stance's line always named, half-size note on an adverse US day, held note, caveat | today (answer) | Same answer, below the box | same | same | No | No | tests/test_buy_verdict.py |
| TD-V3 | Duplicate lines (바뀌는 조건, 다른 전략) are hidden under the box on screen but kept in the text answer | today (answer) | — | — | — | — | No | tests/test_buy_verdict.py |

Correction to Part C:
- The rows describing the buy check as "checklist only, ending '이 점검표는 살지 말지에 대한 답이 아닙니다'" are superseded by TD-V1…V3.
- The checklist is still there, under the conclusion.

Correction to Part A:
- `GET /api/model` exists (`terminal/server.py:171`).
- `#keysbtn` is hidden in the header on purpose. It is reachable from the command palette and the phone 더보기 sheet (UI batch 5 decision).

---

# Part A — shell, market, stock

Source: `terminal/static/{index.html,app.js,command.js,collect.js,phone.js,ui.js,theme.js,calendar.js,peers.js,alerts.js,style.css}` and `terminal/server.py`. Read-only; nothing was run in a browser (all "browser step" checks are untested suggestions).
Test file shorthand: `tests/test_ui_batch_N.py` = UI batch N source-text pins; `tests/test_ui_ticker_context.py`, `tests/test_ui_groups.py`.

Notes on scope boundaries
- The stock screen has **no intraday chart panel**. Only the daily candle chart (3mo/1y/5y) and an "장중·미확정" badge exist. "Intraday" in the brief maps to `liveBadge()` and the `intraday` flag on cards/rows.
- Alerts (`alerts.js`) render into `#alertc` inside the **portfolio tab** (`portfolio.js:243`), not a tab of their own. Listed here because the file is in my scope.
- `renderModel` / `wireCapital` (모델 tab, capital box, 스캔 실행) also live in app.js lines ~700-890. Listed briefly (MO-xx) because they sit in my file; the model tab's owner agent should confirm.
- Tabs `today`, `map`, `compare`, `chart`, `account`, `portfolio`, `assist`, `paper`, `qsf`, `committee`, `lab`, `coin` are rendered by other files (other agents). The shell only routes to them.

---------------------------------------------------------------------------

## 1. Feature table

### S — App shell (index.html + app.js shell code)

| ID | Feature | Screen | Interaction | API / backend | Data dependency | Hidden/nested? | Suggested regression check |
|---|---|---|---|---|---|---|---|
| S-01 | Brand "퀀트 터미널 QSF" | top bar | Static text; `.ver` ("QSF") hidden at ≤640px, whole brand hidden ≤380px | none | none | responsive-hidden | Browser: resize to 375 and 360px, brand/ver vanish |
| S-02 | Market switch 미국/한국/코인 (`#market`) | top bar | Click button -> `setMarket(m)`: saves `qse-market` in localStorage, clears all tab HTML, resets `state.loaded`/redrawers, drops `state.ticker` if of another market, re-renders current tab; coin market only shows today+coin groups | none directly (each tab re-fetches with `market=`) | localStorage `qse-market` | no | tests/test_ui_batch_6.py, test_ui_groups.py; browser: click each market, verify groups change |
| S-03 | Keyboard `M` cycles market US->KR->COIN->US | shell | Press M when not typing, keys on | none | localStorage `qse-keys` | keyboard | tests/test_ui_batch_5.py (keysOn); browser: press M |
| S-04 | Search box + 조회 button (`#search`, `#q`) | top bar | Submit -> `findSymbol(text)`; empties and blurs input. On COIN market the same box becomes an assistant question box (`askAssistant`) with placeholder "코인에 대해 묻기 (예: 비트코인, 코인 상위는?)" | `/api/symbols`, `/api/kr/search` (Hangul fallback) | scanned symbols store (US S&P 500, KR top 300) | no | tests/test_ui_ticker_context.py; browser: type AAPL, 삼성전자, apple |
| S-05 | Search autocomplete dropdown (`#qsug`) | top bar (absolute under search) | Type (150 ms debounce) -> up to 8 items "TICKER name 시장"; Up/Down select, Enter opens selected, Esc or outside click closes; ignores same-text IME re-input; disabled in COIN | `/api/symbols?q=&market=` (cached 200 entries in `symbolCache`) | symbol universe | popover | tests/test_ui_ticker_context.py (qsug, sug-item); browser: type "app" |
| S-06 | "혹시 이 종목인가요?" choice list (`symbolChoices`) | stock tab | When typed text is not an exact scanned ticker/name: list of close tickers (`.sym-item`) + "그대로 열기" / "한국 상장 종목 전체에서 찾기" button (`#sym-raw`); if COIN market it switches to the market of the first match | `/api/symbols`, then `/api/kr/search` for Hangul | symbol universe | nested (stock tab) | tests/test_ui_ticker_context.py (sym-raw, symbolChoices); browser: type APPL |
| S-07 | Korean search result list (`searchKr`) | stock tab | Hangul text with no scan hit -> table of name/ticker/market from full KRX list; one hit or exact name opens directly | `/api/kr/search?q=` | KRX master list (can be unavailable: MASTER_UNAVAILABLE) | nested | none found in tests; browser: type 삼성 |
| S-08 | 내 계좌 button (`#acctbtn`) | top bar | Opens `show("account")` (bound in account.js, any market). Hidden ≤640px (bottom bar has 내 계좌 instead). Tooltip "미국·한국 주식과 코인을 한 페이지에서 봅니다." | none | none | responsive-hidden | tests/test_ui_batch_6.py; browser: click |
| S-09 | 지금 수집 button (`#collect`) -> see CO-xx | top bar | Starts data collection; hidden on paired phone (`.on-phone`) and ≤640px (moved to 더보기) | `/api/automation/run` | automation | responsive/phone-hidden | see CO rows |
| S-10 | 폰 연결 button (`#phonebtn`) -> see PH-xx | top bar | Hidden until `/api/phone/status` says available; label toggles "폰 연결" / "폰 연결 · 켜짐" | `/api/phone/status` | phone_view | hidden by default | see PH rows |
| S-11 | ⌘K button (`#cmdbtn`) | top bar | Opens command palette (title "명령창 (/ 또는 ⌘K)") | none | none | hidden ≤640px | see CM rows |
| S-12 | 한 글자 단축키 끄기/켜기 (`#keysbtn`, also `#cmd-keys` in palette) | top bar (hidden attr), palette footer, 더보기 sheet | Toggles one-letter shortcuts `/ ? 1-9 M`; toast "한 글자 단축키를 켰습니다/껐습니다"; saved as `qse-keys` on/off; Ctrl/⌘+K always works. Top-bar button has `hidden` attribute and is never un-hidden by JS (so it is only reachable via palette footer or 더보기) | none | localStorage `qse-keys` | yes (header button stays hidden) | tests/test_ui_batch_5.py (qse-keys, keysbtn) |
| S-13 | Theme toggle ◐ (`#theme`) | top bar | Click cycles auto -> light -> dark; title shows "화면 테마: 시스템/밝게/어둡게"; calls `redrawAll()` so canvases repaint; `auto` follows OS `prefers-color-scheme` live. `theme.js` sets `data-theme` before first paint | none | localStorage `qse-theme` | hidden ≤640px (in 더보기 as "화면 테마") | tests/test_ui_batch_5.py (theme.js, qse-theme); browser: click ◐ thrice, check charts repaint |
| S-14 | Collect progress bar (`#collectbar`) | top bar row (flex-basis 100%) | See CO-xx | | | hidden by default | |
| S-15 | Phone panel (`#phonebar`) | top bar row | See PH-xx | | | hidden by default | |
| S-16 | Server-unreachable bar (`#netbar`, role=alert) | top bar row | When any `api()` fetch throws: "터미널 서버(host)에 연결되지 않습니다…" + 다시 시도 button; polls `/api/automation/status` every 5 s; on recovery clears loaded state, re-renders the current tab and health | `/api/automation/status` (probe) | none | appears only on failure | tests/test_server_unreachable_notice.py |
| S-17 | "화면이 업데이트되었습니다" bar (`#verbar`) with 새로고침 button | top bar row | Shown when `/api/health`.screen stamp differs from first-seen stamp | `/api/health` | health.screen | appears only on change | tests/test_screen_refresh_notice.py |
| S-18 | Group nav (`#groups`): 오늘 / 시장 / 종목 / 차트 / 내 계좌 / 점수 / 검증·기록 / 코인 | below top bar (sticky under it ≥641px; hidden ≤640px) | Click -> `showGroup(g)` opens the last-visited tab of that group; active group underlined; 코인 group only in COIN market, other groups hidden in COIN except 오늘; keys 1-9 jump to the Nth visible-order group button (note: indexes DOM order including hidden 코인 = 8th, and groups hidden in COIN still count) | none | groupTab memory | responsive | tests/test_ui_groups.py, test_ui_batch_6.py |
| S-19 | Sub-tab row (`.tabs`) | below groups | Shows tabs of the active group; row hidden when group has <2 visible tabs. Tabs: 오늘 / 시장 개요, 시장 지도, 거시 / 종목 정보, 관심종목 / 차트분석, 비교 / 통합 계좌, 시장별 자세히, 매매 보조, 모의 매매 / 순위·카드, 투자위원회 / 모델, 연구실 / 코인. Account tabs are shown in every market (ANY_MARKET) | none | | tabs inside "더보기" groups on phone | tests/test_ui_groups.py |
| S-20 | Tab render policy | shell | `show(tab)`: render on first open; `ALWAYS_FRESH` tabs (watch, account, portfolio, assist, paper, model) re-render every time; stock re-renders via `renderStock`; others keep DOM and call `redrawShown` + `RETURN[tab](scrollY)` to restore scroll (tabScroll) | per-tab | | | tests/test_ui_batch_2.py; browser: switch tabs, confirm scroll restored |
| S-21 | Hash routing | URL | `#tab`, `#stock/TICKER`, `#qsf/TICKER`, `#qsf:view`; `hashchange` + `DOMContentLoaded` -> `fromHash`; unknown name -> today; no re-render if already there (keeps the "혹시 이 종목인가요?" list); opening `#stock/005930` switches market to KR | none | | | tests/test_ui_batch_2.py, test_ui_batch_6.py, test_ui_ticker_context.py |
| S-22 | Document title + sr-only h1 (`#pagetitle`) | shell | Set to "<탭 이름> · 퀀트 터미널" on every tab change; `aria-current` on the tab button | none | | a11y only | tests/test_ui_batch_5.py (paintTitle, pagetitle) |
| S-23 | Wide-content tabs | shell | `main.wide` (max 1680px) for qsf, committee, portfolio, watch, lab, model, coin; others 1280px | none | | | tests/test_ui_batch_5.py (WIDE_TABS) |
| S-24 | Price colour rule | shell | `paintColorRule`: KR market -> `data-color="kr"` (red up / blue down) except on the account tab (international pair, because it mixes markets) | none | | | tests/test_ui_batch_1.py |
| S-25 | Bottom bar (≤640px): 오늘 / 종목 / 점수 / 코인(COIN only) / 내 계좌 / 더보기 | bottom of phone screen (`#bottombar`, 56px fixed) | Tap -> `showGroup`; 내 계좌 -> `show("account")`; 더보기 highlighted when current group is not in the bar | none | | phone only | tests/test_ui_batch_3.py (bottombar) |
| S-26 | 더보기 sheet (`#moresheet`) | phone, above bottom bar | "다른 묶음" row (시장, 차트, 검증·기록, ... those not in bar) and "도구" row (지금 수집 [not on paired phone], 폰 연결, 명령창, 화면 테마, 한 글자 단축키) -> each tool clicks the hidden top-bar button; closes on outside click, Esc, or any choice; `aria-expanded` kept | none | | phone only; nested | tests/test_ui_batch_3.py (moresheet) |
| S-27 | Footer | bottom | Static disclaimer (free public data, delayed, not advice, no order function) + `#health` text: "· version · SEC 연결 설정됨/미설정 · ECOS … · 서버 오류 N건" with tooltip of last server error | `/api/health` (re-polled every 5 min, on tab change after 30 s, on visibility) | health | tooltip | tests/test_terminal_1.py, test_stability_fixes.py; browser: hover health text |
| S-28 | Toast (`#toast`) | bottom centre (above bottom bar on phone) | `notify(text, tone)`: err 9 s (role=alert), info 5 s; 닫기 button | none | | transient | browser: add a duplicate watchlist ticker over limit |
| S-29 | Hover tip (`#tip`) | floating | Used by the price-chart crosshair (candle OHLC/volume/SMA values) | none | | hover only | tests/test_ui_batch_4.py (drawPrice) |
| S-30 | Touch tap-tip (`#taptip`) | phone/coarse pointer | Tap any element with `title` (not control) -> text shown in a bar at bottom; tap elsewhere hides; titled non-controls get dotted underline on coarse pointers | none | | touch-only | none found; browser (touch emulation): tap a badge |
| S-31 | Keyable rows | all tabs | Rows/cards/spans matching `KEYABLE` (tr.click, div.card[data-ticker], b/span[data-ticker], fold h2) get tabindex=0 and role=button; Enter/Space triggers click; MutationObserver keeps aria-pressed on `.seg` buttons and aria-expanded on fold h2 | none | | a11y | tests/test_ui_batch_5.py (markKeyable, KEYABLE) |
| S-32 | Global `[data-ticker]` click -> `openTicker` | all tabs | Any element with data-ticker opens the stock screen (except `button.x`) | none | | | tests/test_ui_ticker_context.py |
| S-33 | "지금 수집" in empty states (`.collect-now`) | any tab | Delegated click triggers header `#collect` | `/api/automation/run` | | nested | tests/test_ui_batch_4.py? (P2-17) browser: find an empty state |
| S-34 | `plainBlock` "쉽게 설명해줘" toggle | cards/portfolios (other tabs call it) | Button toggles `.plain-box` (title, headed bullet lists, 낱말 풀이 dl); label flips to "쉬운 설명 닫기" | none (text built server-side in plain.py) | plain doc | folded | tests/test_ui_batch_3.py, test_assessment_fixes_2026_11_23.py, test_stance_plain.py |
| S-35 | Error code -> Korean (`ERR_KO`, `errKo`) | everywhere | Failed requests show Korean sentence; unknown code shown as "오류 코드 X"; HTTP_n generic | none | | error state | tests/test_maturity_fixes_2026_11_22.py (code needs sentence) |
| S-36 | PHONE_NOT_PAIRED handling | everywhere | 401 + PHONE_NOT_PAIRED -> `location.reload()` back to pairing page | any | phone_view | | tests/test_phone_view.py |
| S-37 | Recent tickers store | shell | `qse-recent` (12 max); a ticker is stored only if scanned or its chart returned prices; `pruneRecentTickers` (3 s after load) drops mistyped codes only when source returned no prices while probe (SPY / 005930) did | `/api/symbols`, `/api/chart?range=3mo` | localStorage | background | tests/test_recent_ticker_prune.py |
| S-38 | localStorage key migration | shell | Old keys (recentTickers, qsfView, ...) copied to `qse-*` once | none | | background | tests/test_ui_batch_5.py (STORE_RENAMES) |
| S-39 | Responsive/viewport breakpoints | shell | ≤640 phone, 641-1023 tablet, 1024-1599 desktop, ≥1600 wide; `--top-h` / `--sticky-top` CSS vars measured by ResizeObserver so table headers stick below header+groups | none | | | browser: resize |
| S-40 | Shared canvas helpers | shell | `setupCanvas` (dpr, aria-label from panel title), `spark`, `sparkRange` ("그래프 폭 x%" with tooltip), `niceTicks`/`tickLabel`, `cssVar` | none | | | tests/test_ui_batch_4.py (niceTicks, sparkRange) |
| S-41 | Number/format helpers | shell | `fmt`, `pct` (up/down/flat class), `big` (조/억/만, ₩ $), `bigInText`, `stamp` (YYYY-MM-DD HH:MM), `tickerLabel` (KR name first, US code first), missing -> "—" never 0 | none | | | tests/test_ui_batch_4.py (formats) |
| S-42 | Redraw system | shell | `redrawOn(tab, part, fn)`; resize (120 ms debounce) and theme change redraw visible tab, mark others for later | none | | | tests/test_ui_batch_5.py |

### UI — ui.js shared builders

| ID | Feature | Screen | Interaction | API | Data | Hidden | Check |
|---|---|---|---|---|---|---|---|
| UI-01 | `ui.head/panel/table/notice/empty/badge/meta/kv/fold/seg` + `html`/`raw` tagged templates | all new templates | Escape rules: title/sub/label/text escaped; body/rows/html/actions raw. `ui.fold` = `<details>` with "자세히" hint; `ui.seg` = pressed-state segmented control; `ui.table` returns `ui.empty` when no rows | none | | | tests/test_ui_batch_3.py |

### OV — 시장 개요 (tab `overview`, group 시장)

| ID | Feature | Screen | Interaction | API | Data | Hidden | Check |
|---|---|---|---|---|---|---|---|
| OV-01 | Group panels of index/ETF/rate/FX cards | overview | `/api/overview?market=` -> one panel per group (`g.title`), each a `.grid` of cards | `/api/overview` | Yahoo daily bars (cached) | no | tests/test_ui_batch_6.py (renderOverview); browser: open 시장 개요 in US and KR |
| OV-02 | Card content | overview | Name + code, last close (0 decimals for .KS/.KQ), 1일 and 1개월 change, 30-day-ish sparkline canvas, date, "그래프 폭 x%" | same | | title tooltip = symbol + date | tests/test_ui_batch_4.py |
| OV-03 | Neutral tiles | overview | VIX/VXN/VKOSPI, yields (^TNX..), DXY, FX pairs show sign without up/down colour | same | | | tests/test_ui_batch_6.py (NEUTRAL_TILE) |
| OV-04 | Card click -> stock | overview | Cards with `data-ticker` (1-5 letter US code or 6-char KR code) open stock screen; keyboard Enter/Space too; index symbols (^GSPC) not clickable | none | | | browser |
| OV-05 | Status badges on a card | overview | Non-REAL status badge (지연·오래됨, 데이터 없음...) + "장중·미확정" badge when intraday | same | | | |
| OV-06 | Live-session notice | overview | Top notice "정규장이 진행 중입니다…" if any card is intraday | same | | conditional | |
| OV-07 | Source / fetch time / basis footer panel | overview | Source, 받아온 시각, status badge, basis sentence | same | | | |
| OV-08 | Loading / error states | overview | "불러오는 중…" panel; `errBox` red panel with Korean error | | | | tests/test_server_unreachable_notice.py |
| OV-09 | Sparkline redraw on theme/resize | overview | `redrawOn("overview","sparks")` | | | | |

### MA — 거시 (tab `macro`, group 시장)

| ID | Feature | Screen | Interaction | API | Data | Hidden | Check |
|---|---|---|---|---|---|---|---|
| MA-01 | Market-specific macro cards (US via FRED, KR via ECOS) | macro | Grid of `.mcard`: label, series id, status badge if not REAL, latest value (formatted by unit: 천 명, 원, else 2 decimals + unit), date, 직전 / 1년 전 values, 90px line chart of ~260 observations with first/last month label and zero line if crossing | `/api/macro?market=` | FRED / ECOS (keys; health shows 설정됨/미설정) | no | browser: open 거시 in US and KR; no pytest pin found for renderMacro |
| MA-02 | Reason notice | macro | `d.reason` (e.g. key not configured) as top notice | same | | conditional | |
| MA-03 | CPI note + source | macro | "CPI는 전년 동월 대비 상승률…" + source meta | same | | | |
| MA-04 | Embedded 경제 일정 panel (`#econcal`) | macro | Rendered by `loadCalendar` -> see CAL rows. Sits ABOVE the macro cards | `/api/calendar?days=60&market=` | | nested | tests/test_ui_batch_4.py, test_econ_calendar.py |
| MA-05 | Redraw minis | macro | `redrawOn("macro","minis")` | | | | |

### CAL — calendar.js (inside macro tab)

| ID | Feature | Screen | Interaction | API | Data | Hidden | Check |
|---|---|---|---|---|---|---|---|
| CAL-01 | 다가오는 경제 일정 table (60 days, KST) | macro `#econcal` | Columns 날짜 (MM/DD (요일) + "오늘/내일/N일 뒤"), 시각, 나라, 일정; rows grouped per day; central-bank/statistics releases + held/watched earnings + ex-dividend dates | `/api/calendar` | official schedules (Fed, BLS, BOK); Yahoo earnings/dividends | no | tests/test_econ_calendar.py, test_ui_batch_4.py |
| CAL-02 | Row badges | macro | 보유 / 관심 / "오래된 일정" (risk-note) on earnings and dividend rows | same | holdings + watchlist | | |
| CAL-03 | Row tooltips | macro | time cell and name cell title: local time + zone, or "발표 시각은 기관 일정표에 없습니다", or Yahoo source warning | same | | hover | |
| CAL-04 | Ticker click | macro | Earnings/dividend ticker opens stock screen | none | | | |
| CAL-05 | "공식 일정은 YYYY-MM-DD까지만 들어 있습니다" notices | macro | One notice per series that runs out or is stale (with 마지막 확인 date) | same | | conditional | |
| CAL-06 | Basis + source links | macro | basis sentence, earnings status note (`earnings_status != REAL`), source links (http(s) only) with 확인 dates | same | | | |
| CAL-07 | Empty / error / market-changed guard | macro | "60일 안에 공식 발표된 일정이 없습니다."; errBox; aborts if market changed meanwhile | | | | |

### WA — 관심종목 (tab `watch`, group 종목)

| ID | Feature | Screen | Interaction | API | Data | Hidden | Check |
|---|---|---|---|---|---|---|---|
| WA-01 | List of watched tickers for current market | watch | Table: 종목 (code + name), 종가, 전일 대비, 1개월, 추세(30일) sparkline, 스윙 점수, 장기 점수, 상태 (badge + 장중·미확정 + date), ✕ | `/api/watchlist?market=` | `data/terminal/watchlist.json` (Mac only); Yahoo quotes; QSF scan | no | none found for renderWatch; browser: open 관심종목 |
| WA-02 | Add ticker form (`#wadd`) | watch | Text input (max 15) + 추가 -> POST add; switches market to ticker's market (`marketOf`), re-renders; errors (INVALID_TICKER, WATCHLIST_FULL 100) via toast | `POST /api/watchlist/add` | | | tests/test_terminal_1.py? browser |
| WA-03 | Remove (✕, title 삭제) | watch | POST remove, re-render; stops row click | `POST /api/watchlist/remove` | | | browser |
| WA-04 | Row click -> stock screen | watch | Keyable row | none | | | |
| WA-05 | Score cells (`watchScore`) | watch | Recorded SWING / LONG_TERM score (1 decimal) + coloured action label (`qsfClass`); "스캔 없음" when no scan, "스캔 밖" when not in scan | from `/api/watchlist` (qsf field) | latest QSF scan record | | |
| WA-06 | Footnotes | watch | Scan session + model version sentence, source meta, "관심종목은 이 Mac의 data/terminal/watchlist.json 에만 저장됩니다." | same | | | |
| WA-07 | Empty / error | watch | "관심종목이 없습니다."; errBox | | | | |
| WA-08 | Count in heading | watch | "미국/한국 관심종목 N개" | | | | |
| WA-09 | Always re-rendered | watch | ALWAYS_FRESH tab | | | | |
| WA-10 | Empty stock tab shows watchlist chips | stock (no ticker) | see ST-02 | `/api/watchlist` | | nested | |

### ST — 종목 정보 (tab `stock`, group 종목)

| ID | Feature | Screen | Interaction | API | Data | Hidden | Check |
|---|---|---|---|---|---|---|---|
| ST-01 | Empty state | stock, no ticker | Panel text depends on market (KR: "005930, 삼성전자"; US: "AAPL, MSFT, NVDA") | none | | | browser: open #stock |
| ST-02 | Chips: 최근 본 종목 and 관심종목 | stock, no ticker | Chip buttons per ticker (same market only); watchlist chips load async (index tickers `^` excluded) | `/api/watchlist` | `qse-recent`, watchlist | | tests/test_ui_ticker_context.py |
| ST-03 | Header block (`#s-head`) | stock | Long name, code, exchange; sector · industry (Korean sector names via `SECTOR_KO`); 웹사이트 link (http/https only, new tab) | `/api/company?t=` | Yahoo profile | | tests/test_ui_batch_1.py |
| ST-04 | ＋ 관심종목 button (`#addw`) | stock header | POST add; label becomes "✓ 추가됨"; marks watch tab stale; error -> toast | `POST /api/watchlist/add` | | | browser |
| ST-05 | 비교 차트 button (`#addc`) | stock header | `compareWith([ticker])` -> compare tab | none (compare.js) | | cross-tab | tests/test_ui_ticker_context.py |
| ST-06 | 차트분석 button (`#adda`, tooltip "이동평균·볼린저밴드·RSI·MACD와 고전 신호를 봅니다") | stock header | `chartWith(ticker)` -> chart tab | none | | cross-tab | tests/test_chart_analysis.py, test_ui_ticker_context.py |
| ST-07 | 점수 카드 button (`#addq`, tooltip "순위·카드 탭에서 이 종목의 점수 카드를 엽니다") | stock header | `qsfOpenCard(ticker)` -> qsf tab card, URL `#qsf/TICKER` | `/api/qsf/evaluate` via qsf.js | | cross-tab; not shown on COIN | tests/test_ui_batch_2.py, test_ui_batch_6.py, test_ui_ticker_context.py |
| ST-08 | Price line (`#s-price`) | stock | Big close (0 decimals KR, 2 US), 1-day %, 장중·미확정 badge, "52주 범위 lo – hi · 200일선 대비 x%" | `/api/chart` (last bar) | | | tests/test_ui_batch_1.py |
| ST-09 | Key-value facts | stock | 시가총액, PER(후행), PER(예상), PBR, 배당수익률, 베타, 평균 거래량, 상장 주식수; "—" when missing; suspicious dividend yield shows "— (원자료 이상 x%)" with tooltip (limit; not used in committee) | `/api/company` | Yahoo | tooltip | tests/test_ui_batch_1.py (dividendYieldSuspect) |
| ST-10 | 회사 설명 fold (`details#sum.co-sum`) | stock | Collapsed one-line English lead (ellipsis) + "Yahoo 영문 원문"; opens to full text; lead hidden when open | `/api/company` | Yahoo longBusinessSummary (English) | folded | tests/test_ui_batch_4.py (co-sum) |
| ST-11 | Profile source meta | stock | 출처, 받아온 시각, status badge | same | | | |
| ST-12 | 가격 차트 panel | stock | Candle chart 420px (300px ≤640px) with volume pane, 20/50/200 day SMA lines, nice price ticks on right, ~4 (phone) / 7 date labels; falls back to close line when bars too thin (bw<1.8) | `/api/chart?t=&range=` | Yahoo bars | | tests/test_ui_batch_1.py, test_ui_batch_4.py (drawPrice, goodOpen) |
| ST-13 | Range selector 3개월/1년/5년 (`#rng`) | stock | Click sets `state.range`, reloads chart only | `/api/chart` | | | browser |
| ST-14 | SMA legend | stock | 20/50/200일선 colour swatches next to title | none | | | |
| ST-15 | Crosshair tooltip | stock (desktop) | mousemove on canvas -> `#tip` with date, 시/고/저/종, 거래량, SMA values; bad open (0 from Yahoo KR) shown as "없음(원자료 이상)"; flips left near right edge; hides on leave; no touch equivalent | none | | hover only | tests/test_ui_batch_1.py (goodOpen) |
| ST-16 | Chart meta line (`#c-meta`) | stock | Source, 받아온 시각, status badge, 장중·미확정, "마지막 일봉 date"; or UNAVAILABLE empty: "가격 데이터를 받지 못했습니다. 종목 코드를 확인하세요." | `/api/chart` | | | |
| ST-17 | Chart canvas a11y label | stock | aria-label "TICKER 가격 차트: start부터 end까지, 종가 a에서 b" | | | a11y | |
| ST-18 | Remember ticker after prices arrive | stock | `rememberTicker` only for non-UNAVAILABLE chart | | | background | tests/test_recent_ticker_prune.py |
| ST-19 | 동종업계 비교 panel (`#s-peers`) | stock | See PE rows | `/api/qsf/peers` | | | |
| ST-20 | 연간 재무 요약 (`#s-fund`) | stock | Table: rows (항목 with tooltip = XBRL concept) x fiscal years; units: ratios % (debt ratio 0 decimals), USD/KRW per share, big money; "—" = not disclosed (not 0); footnote for banks; source + note; UNAVAILABLE shows reason | `/api/company` (.fundamentals) | SEC XBRL / DART | tooltip | none found; browser: AAPL and 005930 |
| ST-21 | 최근 SEC / DART 공시 (`#s-fil`) | stock | Table 제출일, 양식 (+ Korean form name via `FORM_KO`: 10-K 연간보고서, 10-Q, 8-K 주요사항, 4 내부자 거래, DEF 14A, S-3, SC 13G, 144, 11-K), 설명, 원문 "열기 ↗" (http/https only, new tab); title says SEC or DART by market | `/api/filings?t=` | SEC EDGAR / DART | | none found; browser |
| ST-22 | Section error states | stock | Each of header/fund/filings/chart shows its own red error text | | | | |
| ST-23 | Stock re-render guard | stock | `state.loaded.stock === ticker` skips re-render; stale responses dropped if ticker changed | | | | tests/test_ui_ticker_context.py |
| ST-24 | Market auto-switch on open | stock | `openTicker` sets market from code shape (6 digit/alphanumeric = KR) | | | | tests/test_ui_ticker_context.py |
| ST-25 | Cross-tab ticker prefill | other tabs | `prefillTicker(input)` fills an input in other tabs with the open ticker if same market and user hasn't typed | none | | nested | tests/test_ui_ticker_context.py |
| ST-26 | Stock tab on COIN market | stock | Not reachable (groups hidden); `show` redirects to coin | | | | tests/test_ui_groups.py |

### PE — peers.js (inside stock tab `#s-peers`)

| ID | Feature | Screen | Interaction | API | Data | Hidden | Check |
|---|---|---|---|---|---|---|---|
| PE-01 | Letter-grade table 업종 내 위치 | stock | 2 rows (스윙 점수, 장기 점수) x 5 columns (총점, 기술, 재무, 위험, 이벤트); A-F badge, tooltip "업종 n개 중 상위 x% · 값 v"; "—" with tooltip when fewer than 6 peers or no value | `/api/qsf/peers?t=&market=` | latest QSF scan, same sector | tooltip | tests/test_ui_batch_3.py, test_ui_batch_4.py |
| PE-02 | Peer table | stock | Columns 시가총액, 1개월, 스윙, 장기, PER, PBR, FCF 수익률, 영업이익률, ROE, 3년 매출성장, 부채/자본; rows clickable to open peer; own row highlighted (`.me`) | same | ratio ledger record | | tests/test_ui_batch_4.py |
| PE-03 | Sortable headers | stock | Click column header toggles desc/asc with ▼/▲; missing values always last; sort resets to market cap if the column disappears | none | | | browser |
| PE-04 | Empty columns folded | stock | Columns with no values dropped; meta lists which ones ("재무 비율은 다음 자동 실행 뒤에 채워집니다") | | | | |
| PE-05 | 12 rows then "N개 모두 보기" | stock | Shows top 12 + the current ticker; button expands all | | | | |
| PE-06 | Not scanned fallback | stock | status != REAL -> "이 종목은 QSF 스캔 대상이 아니라 업종 비교가 없습니다." | | | | |
| PE-07 | Footnotes | stock | basis, session, model version, ratio ledger version/session | | | | |
| PE-08 | Sector label | stock | `sectorKo(group)` + basis + count in heading | | | | |

### AL — alerts.js (rendered in portfolio tab `#alertc`)

| ID | Feature | Screen | Interaction | API | Data | Hidden | Check |
|---|---|---|---|---|---|---|---|
| AL-01 | 알림 센터 add-rule form | portfolio (시장별 자세히) | Select 조건 (종가 이상 / 이하 / 하루 등락폭 ≥ % / QSF 점수 구간이 바뀜 / 실적 발표 다가옴); 종목 코드 (optional; empty = all held+watched of market; prefilled with open ticker); value field (label changes: 가격($/원) / 등락폭(%) / 며칠 전); 구분 select 스윙/장기 only for BAND_CHANGE; 조건 추가 | `POST /api/alerts/add` | alert rules file | field show/hide | tests/test_alert_rules.py, test_ui_batch_5.py, test_ui_batch_3.py |
| AL-02 | Validation messages | portfolio | BAD_TYPE, TICKER_REQUIRED, BAD_VALUE (0-50 %, 1-30 days), BAD_STRATEGY, TOO_MANY_RULES (200), INVALID_TICKER; "추가했습니다." | same | | | |
| AL-03 | Rule list | portfolio | Table 조건 name, 상태 (대기 / 발동 time), buttons 다시 켜기 (only when triggered) and 삭제 | `GET /api/alerts`, `POST /api/alerts/remove`, `/rearm` | | | |
| AL-04 | Explanatory basis | portfolio | basis + "가격 조건은 한 번 발동하면 멈추고…검증된 매매 신호가 아닙니다" | | | | |
| AL-05 | 최근 보낸 알림 log | portfolio | Last 20 with time and "[한국]" prefix | `GET /api/alerts` | | | |
| AL-06 | 지금 확인 button | portfolio | Preview check: lists fired alerts (level class), "지금 발동할 조건이 없습니다", missed tickers grouped by reason (최근 확정 종가 없음, 전일 종가 없음, 실적 일정 모름, QSF 스캔 대상 아님; max 8 + 외 N개); note "미리보기일 뿐 보내지 않고 기록하지도 않습니다" | `GET /api/alerts/check` | | | |

### CM — command.js (palette)

| ID | Feature | Screen | Interaction | API | Data | Hidden | Check |
|---|---|---|---|---|---|---|---|
| CM-01 | Open/close | overlay `#cmd` | `/` or `?` (when keys on, not typing) or Ctrl/⌘+K toggles; ⌘K button; click backdrop or Esc closes; focus returns to element that had it, except when an item runs | none | | modal | tests/test_ui_batch_5.py, test_ui_batch_6.py |
| CM-02 | Empty query list | palette | All visible tab labels ("탭") + up to 6 recent tickers ("최근 본 종목") | none | `qse-recent` | | |
| CM-03 | Tab aliases | palette | Typed prefix of tab label or alias (e.g. 지도, heatmap, rrg, rsi, macd, 볼린저, calendar, 일정, portfolio, alert, lab, 기록...) -> go to tab | none | | | tests/test_ui_groups.py |
| CM-04 | Market switch commands | palette | 미국 / us / 한국 / kr / 코인 / crypto -> "X 시장으로 전환" | none | | | |
| CM-05 | Ticker commands | palette | `AAPL`, `005930`, `^GSPC`: "종목 화면" (via `findSymbol`) + "점수 카드" (non-COIN); `AAPL 비교` -> compare chart; `AAPL 차트` -> chart analysis; `AAPL 점수` -> card first; exact tab/market words beat the ticker reading | none | | | tests/test_ui_ticker_context.py, test_chart_analysis.py |
| CM-06 | Live symbol lookup | palette | Non-command text also asks `/api/symbols` (150 ms) and inserts "TICKER name · 시장" rows before 검색/질문 rows, preserving manually chosen selection | `/api/symbols` | | | tests/test_ui_ticker_context.py |
| CM-07 | Hangul search row | palette | Hangul text with no match -> "'x' 한국 종목 검색" | `/api/kr/search` via `findSymbol` | | | |
| CM-08 | Assistant question rows | palette | `help`, `?`, 도움말, 질문, 비서 -> "비서에게 물어볼 수 있는 질문 목록 보기"; sentences (with space or ending ?) -> "'…' 비서에게 묻기" (first when it contains question words) | assistant (`askAssistant`, other file) | | | tests/test_assistant.py, test_coin_bridge.py |
| CM-09 | List navigation | palette | Up/Down, Enter (not during IME composition), mouse click; `aria-activedescendant`; "해당하는 이동이 없습니다." empty | none | | | |
| CM-10 | Keys help + toggle | palette footer | Help line (↑↓ 선택 · Enter 이동 · Esc 닫기 · `/` `⌘K` · `1`~`6` · `M` · `?`) switches wording when one-letter keys are off; toggle button | none | | | tests/test_ui_batch_5.py |
| CM-11 | Focus trap | palette | Tab cycles between input and keys button only | none | | | |
| CM-12 | Global shortcuts | shell | `1`-`9` group shortcuts, `M` market, `/` and `?` open palette; disabled when typing, with modifiers, with IME, or keys off | none | | | tests/test_ui_batch_5.py |

### CO — collect.js

| ID | Feature | Screen | Interaction | API | Data | Hidden | Check |
|---|---|---|---|---|---|---|---|
| CO-01 | 지금 수집 start | top bar | Click -> POST run; disables button; "수집을 시작하는 중…"; if already running follows that run | `POST /api/automation/run` | automation lock/state | | tests/test_terminal_1.py, test_maturity_fixes_2026_11_22.py |
| CO-02 | Progress line | `#collectbar` | Polls `/api/automation/status` every 3 s: "자료 수집 중 · step name · done/total 단계 완료 · 시작 time · 15~25분 걸립니다. 맥을 깨워 두세요." | `/api/automation/status` | | | |
| CO-03 | Start-timeout error | collectbar | No result within 60 s: "수집이 시작되지 않았습니다. 기록 파일: data/automation/manual_run.log" (closable) | same | | error state | |
| CO-04 | Result lines | collectbar | UP_TO_DATE ("이미 최신입니다 · 기준 거래일 …"), ERROR (type + log path), success listing FAILED steps ("다시 누르면 실패한 단계만 다시 시도합니다") and WAITING steps ("아직 공개 전") | same | | | |
| CO-05 | 화면 새로 고침 button | collectbar | Clears rank cache and symbol cache, `state.loaded = {}`, re-renders current tab | none | | | tests/test_ui_ticker_context.py (collect), test_screen_refresh_notice.py |
| CO-06 | Close ✕ | collectbar | Hides bar | none | | | |
| CO-07 | Auto-follow on page load | collectbar | If a run is already in progress at load the bar shows it; otherwise silent | `/api/automation/status` | | | |
| CO-08 | Status-read failure | collectbar | "수집 상태를 읽지 못했습니다." only if a click or run was seen | | | | |

### PH — phone.js

| ID | Feature | Screen | Interaction | API | Data | Hidden | Check |
|---|---|---|---|---|---|---|---|
| PH-01 | 폰 연결 toggle panel | `#phonebar` | Button opens/closes panel; auto-refresh every 15 s while open (only when tab visible) | `/api/phone/status` | phone_view state (port 8766) | button hidden until available; hidden on paired phone? (see PH-07) | tests/test_phone_view.py, test_ui_batch_4.py, test_assessment_fixes_2026_11_23.py |
| PH-02 | OFF state | phonebar | "휴대폰 연결: 꺼짐" + 켜기 button + explanation | `POST /api/phone/switch {on:true}` | | | |
| PH-03 | ON state | phonebar | Addresses (`code.phone-addr`, or message if no Wi-Fi address), six-digit pairing code with minutes left / tries left / one-use, 새 코드 button, code-state messages (LOCKED, EXPIRED, none) | `POST /api/phone/code` | | | |
| PH-04 | Paired device list | phonebar | name, 연결 time, 마지막 접속, 끊기 button; "아직 연결된 기기가 없습니다."; max devices + day expiry shown | `POST /api/phone/unpair {id}` | | | |
| PH-05 | 끄기 | phonebar | `confirm()` dialog "휴대폰 연결을 끕니다. 연결된 기기도 모두 끊깁니다." then switch off | `POST /api/phone/switch {on:false}` | | native confirm | |
| PH-06 | Listen error + help text | phonebar | red message with port; explanation of what phone can/cannot do (computer-only: rule buttons, collect, settings, this toggle) | | | | |
| PH-07 | Phone mode flag | shell | `d.phone` adds `on-phone` class on `<html>`: hides 지금 수집 and `.qsf-rule-switch` | `/api/phone/status` | | | tests/test_phone_view.py |
| PH-08 | Panel close ✕ | phonebar | Hides, stops timer | | | | |
| PH-09 | Touch tap-tip | see S-30 (lives in phone.js) | | | | | |

### MO — 모델 tab (in app.js, outside my brief; brief entries only)

| ID | Feature | Screen | Interaction | API | Data | Hidden | Check |
|---|---|---|---|---|---|---|---|
| MO-01 | 모델 tab (read-only model view: run summary, recommendations, 전향적 추적, 도전자 모델) | model | ALWAYS_FRESH; shows run id, regime, outcome states (Korean via `OUT_KO`/`REC_KO`/`REGIME_KO`) | `/api/model` | model run files | | tests/test_p6_24_app.py, test_terminal_capital.py |
| MO-02 | Capital input + 저장 (`#capInput`, `#capSave`, `#capNote`) | model | Live recompute of 금액/주수 columns; save POSTs; notes about next scan | `POST /api/capital` | capital file | | tests/test_terminal_capital.py |
| MO-03 | 스캔 실행 (`#capRun`) KR | model | Starts Korean model scan; polls every 10 s; RUNNING / DONE / FAILED notes | `GET/POST /api/model/scan` | | | tests/test_model_scan_button.py |

---------------------------------------------------------------------------

## 2. Per-screen blocks

### App shell
- Components: sticky `.top` header (brand, market seg, search + suggestions, 내 계좌, 지금 수집, 폰 연결, ⌘K, [hidden 한 글자 단축키], ◐), four status bars inside the header (collect, phone, net, version), `.groups` nav, `.tabs` sub-nav, `main`, footer (+health), toast, tip, taptip, command palette overlay, bottom bar + more-sheet.
- Desktop layout: one header row (brand | market | search | 6 ghost buttons); optional full-width bars wrap below inside the header; groups row sticky under header; sub-tab row (hidden if group has one tab); content max 1280px (1680px on wide tabs); footer text.
- ≤640px: header = brand + market + search in one 48px line (buttons removed), groups row removed, fixed bottom bar (오늘/종목/점수/내 계좌/더보기; 코인 replaces 종목+점수 in COIN), more-sheet holds other groups and tools; sub-tab row remains under the header; toast raised to 64px.
- Weaknesses:
  1. Eight top-level groups plus 17 tabs in two rows on desktop; "market" is both a header switch and a group named 시장 (different meanings), which is confusing.
  2. Header crowding: six ghost buttons plus a hidden seventh, with status bars (collect/phone/net/version) stacked inside the sticky header, so a progress bar makes the sticky area taller and pushes content/table headers (`--sticky-top` is remeasured).
  3. Phone loses 지금 수집, 명령창 (⌘K), 테마, 폰 연결 to a sheet two taps deep; the sub-tab row is not sticky on phone and the groups it belongs to are only reachable through the bottom bar or sheet.
  4. Number shortcuts `1`-`9` index DOM order of group buttons (including hidden 코인 and groups hidden in COIN market), while the palette help says `1`~`6`; mismatch risk after layout changes.
  5. Two notification mechanisms (toast for errors, `.msg` inline in forms) plus native `confirm()` for phone-off; no consistent pattern.
  6. Heavy reliance on `title` tooltips for explanations (desktop hover; touch gets a separate taptip hack) -> information only reachable by hover.

### 시장 개요 (overview)
- Components: optional live notice; one panel per group, each a CSS grid of cards (name, close, 1일/1개월, sparkline, date, graph-range); source panel.
- Desktop: auto-fill grid, min 190px columns (4-6 cards per row); phone: 1-2 columns.
- Weaknesses:
  1. Every card is the same size and weight; no hierarchy between headline indices and minor tiles.
  2. Each card carries 6 text elements (name, code, price, two changes with labels, date, graph range) at small size -> dense.
  3. Cards for indices (non-clickable) look identical to clickable ones; the only cue is `title`/cursor.
  4. Neutral-vs-coloured rule (VIX, yields, FX = no colour) is invisible to users; mixed colour semantics on one grid.
  5. Source/basis sentences live in a final panel the user has to scroll to; no freshness cue near the data.
  6. Sparklines are per-card auto-scaled (hence the "그래프 폭" caption), which is hard to compare between cards.

### 거시 (macro)
- Components: reason notice; 경제 일정 panel (table + notices + sources); macro card grid (value, previous, 1y ago, 90px line chart); CPI footnote and source.
- Desktop: calendar panel on top, then 280px-min grid (3-4 per row); phone: single column, calendar table scrolls horizontally.
- Weaknesses:
  1. The calendar (a different data type, 60 days of rows) sits above the indicators the tab is named after and is long; indicator cards need a scroll.
  2. Cards use inline styles (`style="display:flex..."`, font-size 20px) -> inconsistent with token system.
  3. Charts have no axes/values except first and last month; no hover; "차트는 최근 약 260개 관측치" explained only in the footnote.
  4. Status badge and series id (e.g. FRED code) are shown on every card, adding noise to a Korean-only audience.
  5. Calendar columns (날짜/시각/나라/일정) force four columns; 나라 is redundant when a market is already chosen.
  6. No grouping of indicators (inflation / labour / rates) — flat list.

### 관심종목 (watch)
- Components: heading with count, add form, 9-column table (종목, 종가, 전일 대비, 1개월, 추세, 스윙, 장기, 상태, ✕), notes.
- Desktop: wide tab (1680px); phone: horizontal scroll inside `.tbl-wrap`.
- Weaknesses:
  1. Nine columns including a status cell with up to three items (badge + live badge + date); wide on phone with horizontal scroll and no sticky first column.
  2. Mixed alignment (`class="l"` on some headers, numbers right-aligned elsewhere) inside one table.
  3. Add form is a bare input; no autocomplete (the header search has it; this one does not), so company names fail.
  4. ✕ delete has no confirmation or undo, adjacent to the row-click target.
  5. Scores display as bare number + colour label but no link to the score card; only whole-row click goes to the stock screen, not the card.
  6. Inline `style` for sparkline canvas size; no sorting or filtering despite up to 100 rows.

### 종목 정보 (stock)
- Components (top to bottom): header panel (name, 4 action buttons, price line, sector/website, 8-fact kv grid, collapsed description, source), price chart panel (range seg, SMA legend, canvas, meta), peers panel (grade table, sortable table, expand button, notes), annual financials table, filings table.
- Desktop: single column of five full-width panels, chart 420px; phone: same stack, chart 300px, tables scroll horizontally.
- Weaknesses:
  1. Four equal-weight buttons (＋관심종목, 비교 차트, 차트분석, 점수 카드) sit right of the name with the score card — the most important cross-link — not emphasised; on phone they wrap under the title.
  2. The page contains no score/verdict summary; the user must click 점수 카드 to see anything about the model, while peers panel shows grades without the stock's own score.
  3. Order is by data source, not by importance: chart before fundamentals; 업종 비교 (5 columns of letter grades + 11-column table) sits between chart and financials, pushing financials and filings far down.
  4. Annual financials: up to many year columns, 5-10 rows, tiny `—` placeholders with explanation only in a footnote; tooltip on row label holds the XBRL concept.
  5. Chart interactions desktop-only (hover tooltip); no touch crosshair, no volume labels, no range beyond 5y, no intraday view.
  6. Loading is per-panel with identical "불러오는 중…" boxes; error text is inline red span without retry.

### Command palette / collect / phone / alerts (supporting)
- Palette: centered dialog 12vh from top, input + list (max 50vh) + help line + toggle; works on phone but only via 더보기 (no ⌘K).
- Collect: full-width bar inside header under buttons; ✕ only after finish.
- Phone: expandable panel in header; text-heavy numbered steps.
- Alerts: a form + two tables nested at the bottom of the portfolio tab.
- Weaknesses: (a) palette has 3 kinds of rows (tabs, stocks, assistant questions) with only a tiny grey hint to tell them apart; (b) collect and phone panels extend the sticky header, using vertical space on every screen; (c) alerts are far from where the user sets a price on a stock (stock screen has no alert shortcut); (d) the phone panel mixes setup, status and security info in one paragraph block; (e) result sentences in collect bar are long, mixing errors and file paths.

---------------------------------------------------------------------------

## 3. /api/ routes used by these files vs terminal/server.py

| Route | Method | Used by | server.py handler | Present? |
|---|---|---|---|---|
| /api/health | GET | app.js `loadHealth` | `t.health()` + `errors.view()` (line ~153) | yes |
| /api/overview?market= | GET | app.js `renderOverview` | `t.overview` (154) | yes |
| /api/chart?t=&range= | GET | app.js `loadChart`, `pruneRecentTickers` | `t.chart` (155) | yes |
| /api/company?t= | GET | app.js `renderStock` | `t.company` (159) | yes |
| /api/filings?t= | GET | app.js `renderStock` | `t.filings` (160) | yes |
| /api/macro?market= | GET | app.js `renderMacro` | `t.macro` (161) | yes |
| /api/watchlist?market= | GET | app.js stock empty state, `renderWatch` | `t.watchlist_quotes` (162) | yes |
| /api/watchlist/add | POST {ticker} | app.js `renderProfile`, `watchOp` | `t.watchlist_add` (163) | yes |
| /api/watchlist/remove | POST {ticker} | app.js `watchOp` | `t.watchlist_remove` (170) | yes |
| /api/symbols?q=&market= | GET | app.js `symbolSuggest`, `pruneRecentTickers` | `symbols.suggest` (197) | yes |
| /api/kr/search?q= | GET | app.js `searchKr` | `t.qsf.kr_search` (190) | yes |
| /api/calendar?days=60&market= | GET | calendar.js | `t.econ_calendar` (164) | yes |
| /api/qsf/peers?t=&market= | GET | peers.js | `t.qsf.peers` (229) | yes |
| /api/alerts | GET | alerts.js | `t.alerts_view` (165) | yes |
| /api/alerts/add | POST | alerts.js | `t.alert_add` (167) | yes |
| /api/alerts/remove | POST {id} | alerts.js | `t.alert_remove` (168) | yes |
| /api/alerts/rearm | POST {id} | alerts.js | `t.alert_rearm` (169) | yes |
| /api/alerts/check | GET | alerts.js | `t.alert_check` (166) | yes |
| /api/automation/status | GET | collect.js, app.js netDown probe | `automation.status` + `server_agent.status` (200) | yes |
| /api/automation/run | POST {} | collect.js | `automation.start_now` (240) | yes |
| /api/phone/status | GET | phone.js (also special-cased in server for phones, line ~302) | `phone.status()` (149) | yes |
| /api/phone/switch | POST {on} | phone.js | `_phone(phone).switch` (150) | yes |
| /api/phone/code | POST | phone.js | `new_code` (151) | yes |
| /api/phone/unpair | POST {id} | phone.js | `unpair` (152) | yes |
| /api/model | GET | app.js `renderModel` (MO) | present (not line-checked) | yes (route list grep showed `/api/model/plan`; `/api/model` itself exists per grep count - verify) |
| /api/capital | GET/POST | app.js MO | `t.capital` / `t.capital_set` (183-184) | yes |
| /api/model/scan | GET/POST | app.js MO | `model_scan.status` / `t.model_scan_start` (185-186) | yes |

Calls delegated to other files but triggered from my files (not routed here): `/api/qsf/evaluate` (qsfOpenCard), assistant ask endpoint (askAssistant), compare/chart endpoints (compareWith/chartWith).
No route used by these files is missing from server.py. No dead route-string found in the nine files.

---------------------------------------------------------------------------

## 4. Could not determine / caveats
- Did not run the browser; layout descriptions come from reading CSS and HTML only. "Suggested checks" that name a test file mean that the file greps matches for related strings, not that I verified the assertion covers the exact behaviour.
- No pytest pin found by grep for: `renderWatch`/`watchScore`, `renderFund`, `renderFilings`/`FORM_KO`, `renderMacro`/`fmtMacro`, `searchKr`, `#taptip`, `moreOpen`/`MORE_ACTS` (only the DOM ids `moresheet`/`bottombar` are pinned in test_ui_batch_3.py).
- `/api/model` GET: grep of server.py with my pattern did not print its line; the count shows JS calls it and the model tab is a shipped feature, but verify the route line.
- The `#keysbtn` header button has the `hidden` attribute in HTML and no code removes it; it is therefore reachable only from the palette footer and the 더보기 sheet. Whether that is intended was not determined.
- `askAssistant`, `compareWith`, `chartWith`, `qsfOpenCard`, `qsfClass`, `RENDER.today`, `RETURN.*` are defined in other files (assistant.js, compare.js, chart.js, qsf.js) and not inventoried here.
- Alerts' exact placement (`#alertc` in portfolio tab) comes from `portfolio.js:243` only.

---

# Part B — score (순위·카드) and committee

Source: terminal/static/qsf.js (1170 lines), forecast.js (195), committee.js (277); routes cross-checked in terminal/server.py. Read-only pass. Test names are existing files in tests/ found by grep (pins by source-text or function name); "browser step" = manual check where no test pins it.

Conventions: "Tab" = tab id. qsf views = rank / screen / exec / track (QSF_VIEWS). Shared helpers defined elsewhere (not in my files but used): `plainBlock` (app.js:168, "쉽게 설명해줘" toggle), `.collect-now` handler (app.js:402), `acctRecord()`, `tickerLabel/nameFirst`, `notify`, `api`, `RETURN.qsf`, `RENDER.qsf`, `redrawAll`, `show`, `setMarket`.

## Part 1: Feature rows

### QR: orientation, strip, navigation (tab qsf)

| ID | Feature | Screen | Interaction | API / backend | Data dependency | Hidden/nested? | Writes? | Regression check |
|---|---|---|---|---|---|---|---|---|
| QR-01 | Status strip (summary line) | qsf, top | One `<details id=qsfstrip>`; summary shows market-state short text + stance label + fixed "점수 검증: 높은 점수의 수익 근거 아직 없음 · 참고용" + "자세히" hint. Click toggles. | GET /api/qsf/market-state | state.market; ms.status REAL | Yes (folded details below) | No | test_ui_batch_2.py (qsfStrip), test_score_split.py |
| QR-02 | Market-state short text (`qsfStateShort`) | qsf strip, order plan, plan line | Shows "시장 상태 N/100 [label]" + badge "새 주문 크기 X%" on bad day; "읽지 못함"/"자료 없음" fallbacks. Same function reused in plan/paper book. | /api/qsf/market-state, market_state embedded in /api/qsf/order-plan | ms.score_100, state, size_factor | No | No | test_ui_batch_2.py, test_score_split.py |
| QR-03 | Market-state full block (`qsfMarketState`) | qsf strip (expanded) | Score/100, label, size cut badge, "점수 미반영 · N 미만이면 나쁨", per-factor 0-100 line (VIX, VIX term, HY spread, VKOSPI, USDKRW...), note. Empty state "시장 상태를 불러오지 못했습니다." | /api/qsf/market-state | ms.factors | Yes (strip fold) | No | test_ui_batch_2.py, test_ui_audit_2026_11_23.py |
| QR-04 | Caveat notice (`.qsf-caveat`) | qsf strip (expanded) | Static long paragraph: no evidence high score pays, US/KR test summaries, "참고용", not advice. | none (static text) | none | Yes (strip fold) | No | browser step: expand strip, text present |
| QR-05 | Track-record fold "과거 성적: 이 점수를 얼마나 믿을 수 있나" (`qsfRecordHtml`) | qsf strip (expanded) -> nested details.qsf-record | Table per strategy x horizon: pair-win (with range), top/bottom fifth or net spread, 70+ excess, universe/market return, verdict label; tooltips on every header; forward-record paragraph; what/caveats/sources. Silent empty on error. | GET /api/qsf/track-record?market | report files (reports/) | Yes, 2 levels | No | test_track_record.py (backend); no JS pin (qsfRecordHtml untested) |
| QR-06 | Per-row verdict reasons (`qsfWhyHtml`) | qsf record table, extra row | "판정 근거 자세히 (다섯 조건 중 N개 충족)" details: checks table (조건/기준/실제/결과), per-domain table (pair win, t, early/late IC), band table, notes. | /api/qsf/track-record | r.why, checks, domains, bands | Yes, 3 levels | No | test_track_record.py; browser step |
| QR-07 | Stance block in strip (`qsfStanceDraw`) | qsf strip (expanded) | Heading "{시장} 성향 · {level}", description, nested details "단계마다 달라지는 것" (6 rows x 3 levels table), adverse note, damaged-note notice. Also fills strip label `#qsfstripstance`. | GET /api/qsf/stance?market | per-market stance level | Yes, 2 levels | No (read) | test_ui_batch_6.py, test_ui_batch_2.py, test_stance_plain.py |
| QR-08 | Stance buttons (방어/보통/공격 style segment) in nav row | qsf nav row (always visible) | Click a level -> POST stance, drop latest-scan cache, `renderQsf(true)` (keeps open card). Tooltip lists what each level changes. Disabled no-op if already on. Error -> notify. | POST /api/qsf/stance {market, level} | per-market setting | No | YES (stance setting) | test_stance_plain.py, test_ui_batch_6.py |
| QR-09 | View switch (오늘 순위 / 스크리너 / 주문 계획·가상 장부 / 판정 일정) | qsf nav row | Seg buttons; `qsfSetView(v, push=true)` pushes `#qsf:view` history entry; remembered in localStorage `qse-qsf-view`; hides other `[data-view]`; lazy-loads view once (fresh flags). | none | localStorage | No | localStorage only | test_ui_batch_6.py (deep links), test_ui_batch_2.py; browser step: back button returns to prior view |
| QR-10 | Strategy toggle 스윙 / 장기 | qsf nav row | Sets `qsfState.strategy`, localStorage `qse-qsf-strategy`, clears fresh flags, reloads current view (rank, screen filter query, changes, cap, top3, former universe all follow). | none directly | localStorage | No | localStorage | browser step; test_ui_batch_5.py |
| QR-11 | Ticker evaluate form (`#qsfform`, `#qsfticker`, 평가) | qsf / rank | Enter ticker/code (placeholder differs per market), upper-cased, `setMarket(marketOf(t))`, switch to rank view, `qsfEvaluate`. `prefillTicker` pre-fills from context. | GET /api/qsf/evaluate?t&market | t.qsf_evaluate (may read filings: "수십 초") | No | No (evaluation may warm caches server-side) | test_ui_ticker_context.py, test_ui_batch_2.py |
| QR-12 | Evaluate status line `#qsfmsg` | qsf / rank | aria-live: "T 평가 중… (처음에는 공시를 읽느라 수십 초 걸릴 수 있습니다)", "평가할 수 없습니다: reason", "평가 실패: err". Token guards stale replies. | /api/qsf/evaluate | - | No | No | browser step: evaluate bad ticker |
| QR-13 | Hash deep link `#qsf/CODE` + `qsfOpenCard` | qsf / rank | Opening a card from any tab (종목 화면 "점수 카드", other tabs, committee rows) sets market, view=rank, evaluates, pushes hash; back/forward restores card without re-evaluating (`kept`). | /api/qsf/evaluate | state.card, history | No | history entry | test_ui_batch_6.py, test_ui_batch_2.py, test_ui_ticker_context.py |
| QR-14 | Tab return behaviour (`qsfReturn`) | qsf | Returning to the tab in same market keeps expanded rows/scroll; folds the card to a one-liner (unless opened by link); re-reads plan/paper book only; re-renders once if a newer scan was recorded. | /api/qsf/latest | scanMark | No | No | test_ui_batch_2.py, test_ui_ticker_context.py |
| QR-15 | Folded-card reopen bar (`qsfFoldCard`) | qsf / rank | After "닫기" or tab re-entry, `#qsfdetail` shows one "{name} 카드 다시 열기" ghost button; hash reset to #qsf. | none (cached detail) | qsfState.detail | No | history replace | test_ui_batch_2.py (qsfFoldCard) |
| QR-16 | Latest-scan cache (5 min, `qsfLatest`) | qsf | One /api/qsf/latest per market shared by swing/long; dropped on collect finish / "화면 새로 고침" / stance change; failures not cached. | /api/qsf/latest | server ledger | No | No | test_ui_ticker_context.py (qsfLatest) |
| QR-17 | Band edges / colours from server (`qsfBands`) | qsf (all band colour use) | Fetch once at load; bands drive `qsfClass` colour (AVOID above lowest band shows orange). Null -> neutral colour. | GET /api/qsf/bands | config.BANDS | No | No | test_ui_batch_5.py |
| QR-18 | Fold-open persistence for long panels (`qsfFolds`) | qsf (cap/changes/readings/top3/fcast/method/regime/look/valid) | Click `<h2>` of a `.fold` panel toggles; open set stored in localStorage `qse-qsf-folds`; default only "readings" open; opening calls `redrawAll()`. | none | localStorage | Yes | localStorage | browser step |
| QR-19 | Section-fold persistence for card (`qsfFold`/`qse-fold-<key>`) | qsf card | Each card section `<details data-fold>` saves open/closed per kind via capture-phase `toggle` listener. | none | localStorage | Yes | localStorage | test_ui_batch_3.py, test_ui_batch_5.py, test_ui_groups.py |

### QR: ranking table (view rank)

| ID | Feature | Screen | Interaction | API / backend | Data dependency | Hidden/nested? | Writes? | Regression check |
|---|---|---|---|---|---|---|---|---|
| QR-20 | Rank table (50 rows, one table) | qsf / rank | `#qsfrank` panel "{스윙/장기} 순위 N개 [session badge]"; rows sorted by score as recorded (no client sort). Columns: 순위, 종목, 업종, 점수 (whole), 점수 변화(전일), 기술/재무/위험 관리/이벤트 bars, 판단, 진입, 가점/감점. | GET /api/qsf/latest + /api/qsf/rank-notes | scan record; notes only if same session | No | No | test_ui_batch_1.py, test_ui_batch_5.py, test_ui_batch_6.py (rank_notes), test_qsf_stored_rank.py |
| QR-21 | Expandable row | qsf / rank | Click (not on a/button) or Enter/Space on `.qsf-rrow` toggles `aria-expanded`; first open fetches card via `qsfFillRow` (cached in `qsfState.evals`). Nested content: scan-vs-now score note, price-audit notice, full `qsfCard`, "당일 점검" details. Loading "불러오는 중…", error "불러오지 못했습니다", "평가할 수 없습니다". | /api/qsf/evaluate | evals cache cleared when scan mark changes | Yes | No | test_ui_batch_2.py; browser step |
| QR-22 | Rank number tooltip + "상위 3" badge | qsf / rank | Rank cell: tooltip "상위 N%"; badge 상위 3 on first 3 ACTIONABLE rows. | latest | actionability | No | No | test_ui_batch_1.py |
| QR-23 | Name button -> stock screen | qsf / rank (also screener, changes) | `.linkish` button opens 종목 화면 (chart/financials/filings) via data-ticker (global handler, not here). Rest of row toggles card. | none (navigation) | - | No | No | test_ui_ticker_context.py |
| QR-24 | Chip: 자료 {신뢰도} | rank row | Shown when confidence != HIGH; tooltip "자료가 얼마나 있는지... 맞을 확률이 아닙니다". | latest | confidence | No | No | browser step |
| QR-25 | Chip: 자료 없는 요인 N (`qsfMissTag`) | rank row, card | Tooltip explains missing factors computed from remainder; extra sentence if band held back. | latest (missing_factors, band_held_back) | - | tooltip | No | none found (qsfMissTag unpinned) |
| QR-26 | Chip: 자사주 취득 · 참고 | rank/screener row | KR filing buyback tag; tooltip = QSF_FILING_NOTE. | latest filing_events | KR only | tooltip | No | test_ui_batch_2.py |
| QR-27 | Stance chip: 성향 후보 / 성향 밖 · reason | rank row | "성향 후보" when stance ok; "성향 밖 · {why}" only for BUY_CANDIDATE bands. | latest (r.stance) | stance level | tooltip | No | test_ui_batch_6.py, test_stance_plain.py |
| QR-28 | Risk lines `.qr-risk` (4 kinds) | rank, screener rows (under name) | Sentence lines: 합병 절차 공시, 자금조달 결정 공시, 변동성 상위 20%, 시세 이력 확인 필요; full explanation in title (touch tap via phone.js). | latest | deal, filing_events, high_risk, price_audit | tooltip | No | test_ui_batch_2.py (qsfRiskLines) |
| QR-29 | Sector column | rank row (hidden <=640px) | Korean sector via `sectorKo` from rank-notes sectors; empty if notes missing. | /api/qsf/rank-notes | notes.sectors | hidden on phone | No | test_ui_batch_1.py |
| QR-30 | Score cell: whole number + 경계 근처 badge + delta | rank row | `qsfInt` whole score, badge when within 1pt of band edge (edges from rank-notes), delta under score on narrow screens / own column on wide (`qr-dcol`). Delta "새로" if no prev, up/down/flat colour classes (arrows = ± glyph). | rank-notes (band_edges, prev) | prev session | tooltip | No | test_ui_batch_1.py (qsfNear), test_ui_batch_6.py |
| QR-31 | Domain bars (기술/재무/위험 관리/이벤트) | rank row (wide only) | `qd-bar` mini bar + number; tooltips on headers (RISK "높을수록 위험이 낮고..."). Hidden <1280px and hidden when the card is beside the table (>=1600). | latest r.domains | - | hidden by CSS | No | test_ui_batch_6.py |
| QR-32 | 판단 label + 진입 text + "실행 대상 아님 · gate" | rank row | `qsfLabel` colour+text; entry text via `qsfEntry` (long ENTRY_NOW renamed "진입을 막는 조건 없음"); gates / actionability line in orange. On narrow screens the label+entry move under the name (`qr-m2`). | latest | gates, entry_status | - | No | test_ui_batch_3.py (qsfEntry) |
| QR-33 | 가점 / 감점 column (`qsfReason`) | rank row | "▲ factor +x.x" / "▼ factor −x.x"; skips factor common to >=80% (and >=5) rows, which is moved to a line above the table (`qsfCommonPush`). Fallback "두드러진 요인 없음". | rank-notes plus/minus/_more | notes | - | No | test_ui_batch_6.py (qsfCommonPush), test_ui_batch_2.py (qsfReason) |
| QR-34 | Explainer paragraphs above table | rank | Static intro; conditional lines: stance line, high-risk note, filing note, deal note, formula-version notice (recorded scan version != live), common-push line. | latest (live_model_version, model_version), stance | - | No | No | browser step |
| QR-35 | Footer lines | rank | Notes line (or "가점·감점... 원장에서 읽지 못해 비워 둡니다"), scan counts "N종목 평가 · 생성 ... UTC", stale-input count "N종목은 새 재무·공시 자료를 받지 못해...". | latest, rank-notes | stale_inputs | No | No | browser step |
| QR-36 | Sticky header | rank table | CSS `position: sticky; top: var(--sticky-top)` on `thead th`; `.tbl-wrap` overflow visible for this table (style.css 558-559). | none | CSS | No | No | browser step: scroll 50 rows |
| QR-37 | Empty/error states of rank | rank | Failure: "순위를 불러오지 못했습니다: ... 스캔 기록이 없다는 뜻이 아닙니다." (sets loaded.qsf=false so next entry retries). No scan: "아직 스캔 기록이 없습니다..." + 지금 수집 button (`.collect-now`, clicks global #collect). Empty rows: "순위에 올릴 종목이 없습니다." | /api/qsf/latest | - | No | Triggers collect job (app.js, outside my scope) | browser step; test_screen_refresh_notice.py |
| QR-38 | 직전 기록과 달라진 점 panel (`qsfChanges`) | qsf / rank, below table (fold "changes") | Tables: 새로 매수 후보가 된 종목, 매수 후보에서 빠진 종목; nested details "점수가 크게 움직인 종목" (오른/내린); counts of new/gone in scan; model-changed notice; empty reason panel. Name -> stock screen; score button -> opens card (scrolls to #qsfmsg unless beside). | GET /api/qsf/changes?market&strategy | previous scan record | Yes (nested details) | No | test_qsf_changes.py (backend) |
| QR-39 | 이전 대상(거래대금 상위 N) panel (`qsfCap`) | qsf / rank, KR only, fold "cap" | Notice with notes, counts, table rank/종목 link (#stock/…)/점수/거래대금 순위/라이브 대상 여부/상태. Hidden for US; empty when unavailable. | GET /api/qsf/former-universe?strategy | KR cap-universe record | folded | No | test_kr_cap_view.py |

### QC: score card

| ID | Feature | Screen | Interaction | API / backend | Data dependency | Hidden/nested? | Writes? | Regression check |
|---|---|---|---|---|---|---|---|---|
| QC-01 | Card container header (`qsfDrawDetail`) | qsf / rank `#qsfdetail` (beside table >=1600px, sticky) | Panel h2: name+ticker (name-first for KR), market badge, tags (변동성 높음, 자금조달, 자사주, 시세 이력 확인 필요), buttons 종목 화면 and 닫기. | /api/qsf/evaluate | d.name, flags | No | No | test_ui_batch_2.py, test_ui_batch_6.py |
| QC-02 | 닫기 button | card header | Folds card to reopen bar; resets hash. | none | - | No | history | test_ui_batch_2.py |
| QC-03 | 종목 화면 button | card header | `.qsf-tostock` opens chart/financials/filings (global handler). | none | - | No | No | browser step |
| QC-04 | Notes under header | card | high-risk note + date; filing-events note + date; deals notice (SEC M&A, up to 3); price-audit line/notice (`qsfAuditLine`: ok line vs notice with examples, provisional-bar remark). | evaluate | price_audit, deals | No | No | test_ui_batch_3.py (qsfAuditLine) |
| QC-05 | Two strategy cards (`qsfCard`, one per SWING/LONG) | card | Each: score/100, profile tech-id, "보유 중" marker, action label + band, 신뢰도(자료의 양), 데이터 반영률, optional 요인 안 수치 반영률, 시세 date+price (tooltip provenance), model version. | evaluate cards | c.* | tooltips | No | test_ui_batch_3.py |
| QC-06 | Summary strip | card (`.qsf-sum`) | 진입 {status}; links "주문 계획의 이 줄 보기" (only ENTRY_NOW) and "크기 계산기에 넣기"; swing 손절/목표 기준; 보유 종목 exit state. | evaluate | entry, holding, exit | No | No | test_ui_batch_6.py (qsfCardGo) |
| QC-07 | Link: 주문 계획의 이 줄 보기 | card summary | Sets market, `planFocus`, view=exec, jumps to plan row, highlights it (`hl`, scroll center); if absent -> notify "오늘 주문 계획에 없습니다...". | order-plan | plan rows | No | No | test_ui_batch_6.py (qsf-toplan, qsfPlanFocus) |
| QC-08 | Link: 크기 계산기에 넣기 | card summary | Sets `state.sizeFill {t, style, stop}` and opens tab `assist` (size calculator, other module). Swing passes stop price. | none | - | No | state only | test_ui_batch_6.py (qsf-tosize) |
| QC-09 | Risk-gate notice | card | "위험 게이트 N건: ... 점수는 진단용..." | evaluate | gates | No | No | browser step |
| QC-10 | Earnings-unknown notice | card | c.earnings_unknown text. | evaluate | - | No | No | browser step |
| QC-11 | Fold 근거 (open by default) | card | `<details data-fold=basis>`: why_summary, 근거 균형 two columns (올린/깎은 요인, +/- points, sum line, missing factors), plain explanation, surface note ("엇갈림"), stale-input notice, fund-period note, 영역별 점수 bars (REGIME hidden, reference flag, RISK "높을수록 좋음"), 진입 reason + zone, 보유 종목 판단. | evaluate | balance, domains, plain | folded (default open) | localStorage fold state | test_ui_batch_3.py, test_ui_audit_2026_11_23.py (qsfBalance) |
| QC-12 | 쉽게 설명해줘 toggle | card basis, committee block, portfolios | `.plain-btn` shows/hides `.plain-box`; label changes to "쉬운 설명 닫기"; aria-expanded. Defined in app.js. | none (rule-built text from backend) | doc.parts/words | hidden box | No | test_stance_plain.py |
| QC-13 | Stale-input notice (`qsfStaleNote`) | card basis | "오래된 자료로 채점": what, age, reason code mapped (SEC paused, empty response, connection, timeout). | evaluate provenance | stale | No | No | test_ui_batch_3.py |
| QC-14 | Fund-period note (`qsfFundPeriodNote`) | card basis | Shows basis date (연간/최근 4분기, days old) and alternative-basis score with diff; "이보다 새로운 분기 보고서가 없습니다". | evaluate fund_period | - | No | No | test_ui_batch_3.py, test_fund_period.py |
| QC-15 | Fold 계획 (가설) | card (`plan`/`plan-held`, open if held) | 보유 계획: entry date; swing: expected sessions, first review, time stop, stop/target + methods, reward-risk; long: months, milestones, scenarios; 무효화 조건, 이 기간의 이유; 판단이 바뀌는 조건 list. | evaluate | holding | folded | localStorage | test_ui_batch_3.py |
| QC-16 | Previous-record line | card | "직전 기록 date score → 변화 (큰 변화)". | evaluate stability | ledger | No | No | browser step |
| QC-17 | Fold 요인별 계산 (N개) | card | Factor table: 요인(tooltip raw key)/배점 ("참고" if unscored)/기여/근거 text; status suffixes (오래된 데이터/해당 없음/점수 미반영); "빠진 요인 N개". | evaluate factors | - | folded | localStorage | test_ui_batch_3.py |
| QC-18 | Disclaimer line | card bottom | c.not_advice. | evaluate | - | No | No | - |
| QC-19 | Fold 다섯 투자자와 투자위원회 | card (only if d.committee) | Embeds `icCardHtml` (see IC-10..IC-13) + "엇갈림" note. | evaluate.committee | committee module | folded | No | test_committee.py, test_ui_audit_2026_11_23.py |
| QC-20 | Fold 가격 범위 · 예측 층 FC-1 | card (`#qsffcfold`) | Lazy: on first open calls `fcStock` (see FC-01..FC-12). Id used by tests. | /api/qsf/forecast-stock | forecast record | folded, lazy | No | test_forecast.py, test_ui_batch_3.py |
| QC-21 | Fold 이력과 기술 정보 | card (`#qsftechfold`) | Contains risk-grade line (KR test numbers), rank-basis note, P6-11B reference line, nested details "당일 점검", nested "기록된 점수 이력". Lazy-loads history on open. | /api/qsf/history, /api/today | risk_grade, rank_basis, p6_reference | folded, 2nd-level nested | No | test_ui_batch_3.py, test_score_split.py |
| QC-22 | 당일 점검 (시세·공시·뉴스) (`qsfToday`) | card tech fold; also expanded rank row | Nested details; on first open fetch. Sections: 시세 kv (price, change, gap, same-day market, volume ratio, intraday/stale/behind-market remarks), 공시 경고 list, 최근 공시 links (safeUrl, new tab), 뉴스 제목 links with source/time, provider and fetched time. Loading text; error with "다시 시도" button; offline (TypeError) message. | GET /api/today?t&market | live Yahoo/EDGAR/DART/RSS | Yes, nested | No (may populate server caches) | test_ui_audit_2026_11_23.py (qsfToday), test_today_news.py |
| QC-23 | 기록된 점수 이력 (`qsfHistory`) | card tech fold, nested | Tables per strategy newest first: 거래일, 점수, 판단, 신뢰도, 기록 가격, 모델 (* marks model change + note). Empty message with reason. | GET /api/qsf/history | ledger | nested | No | test_qsf_history.py, test_ui_batch_3.py |
| QC-24 | Risk grade line (`qsfRiskGradeLine`) | card tech fold (KR) | 위험 등급 name, risk score, top-fifth flag, past-test numbers (pair win, loss share, drawdown). | evaluate | KR test report | folded | No | test_score_split.py |
| QC-25 | Rank-basis note | card tech fold | QSF_RANK_NOTE: NO_SCAN / OUTSIDE_UNIVERSE / SHORT_HISTORY text. | evaluate.rank_basis | - | folded | No | - |
| QC-26 | Scan-vs-now score note (`qsfScanNote`) | expanded rank row | "순위표는 스캔 시점 x점, 이 카드는 조회 시점 y점" if differs >=0.05. | evaluate | - | nested | No | test_ui_batch_3.py |

### QS: screener (view screen)

| ID | Feature | Screen | Interaction | API / backend | Data dependency | Hidden/nested? | Writes? | Regression check |
|---|---|---|---|---|---|---|---|---|
| QS-01 | Screener panel + count line | qsf / screen | `qsfScreenBuild`: header, explainer, count "{전략} total개 중 matched개 · 기준 date · 값이 없어 뺀 종목 N · 기술 열은 참고(KR swing)". | GET /api/qsf/screen | latest scan rows | No | No | test_qsf_screen.py (backend) |
| QS-02 | Filter form | qsf / screen | Fields: 검색(q), 업종 select (filled from first response with counts), 판단 (전체/매수 후보/관찰/회피), 진입 (all QSF_ENTRY), 신뢰도 (전체/보통 이상/높음), 점수/기술/재무/위험 관리 이상 (0-100 number). Debounced 250 ms live re-run on input; Enter also. | /api/qsf/screen (q, sector, action, entry, confidence, min_*) | - | No | No | test_qsf_screen.py |
| QS-03 | Checkbox filters | screen | 게이트 통과만 (both markets); KR only: 자금조달 결정 제외, 변동성 높음 제외, 자사주 취득만. | /api/qsf/screen (actionable, no_financing, no_high_risk, buyback) | KR flags | No | No | test_qsf_screen.py |
| QS-04 | 초기화 button | screen | Clears form state and rebuilds. | none | - | No | No | browser step |
| QS-05 | CSV 저장 button (`qsfScreenCsv`) | screen | Fetches up to 2000 rows with current filter, builds UTF-8 BOM CSV (formula-injection guard via `qsfCsvCell`), downloads `screen_{market}_{strategy}_{session}.csv`. Errors/empty shown in count line. | /api/qsf/screen?limit=2000 | - | No | Writes a file download (client) | none found (qsfScreenCsv/qsfCsvCell unpinned); browser step: download and open |
| QS-06 | Results table | screen | Columns: 종목 (link + 자사주 chip + risk lines), 업종 (tooltip industry), sortable 점수/기술/재무/위험 관리/이벤트 headers (aria-sort, arrows), 판단, 신뢰도, 진입과 게이트. Sort toggles desc/asc. | /api/qsf/screen (sort, order) | - | No | No | test_qsf_screen.py |
| QS-07 | Score button in screener row | screen | `.qs-open` -> switch to rank view, evaluate, scroll #qsfmsg. | /api/qsf/evaluate | - | No | No | browser step |
| QS-08 | "N개 더 보기" pager | screen | Adds 100 per click (limit grows; re-queries). | /api/qsf/screen | - | No | No | browser step |
| QS-09 | Sector spread line, formula-version notice, empty states | screen | "결과의 업종 분포" top 6; notice when scan formula != live; "조건에 맞는 종목이 없습니다."; "조건을 읽지 못했습니다"; "아직 스캔 기록이 없습니다". | /api/qsf/screen | - | No | No | test_screen_refresh_notice.py |

### QE: order plan and paper book (view exec)

| ID | Feature | Screen | Interaction | API / backend | Data dependency | Hidden/nested? | Writes? | Regression check |
|---|---|---|---|---|---|---|---|---|
| QE-01 | Order plan panel (`qsfPlanHtml`) | qsf / exec | Title "오늘 진입 후보의 주문 계획 [내 계좌 기준][주문을 보내지 않습니다]", rule explainer, equity/cash/candidates line, orders table (종목+deal tag, 스타일, 점수/band, 수량, 기준 종가, 지정가 상한 (tick-rounded, tooltip), 손절, 목표, 금액(비중), 위험, 묶인 한도, 슬리피지 추정 (tooltip spread+impact), 수수료 매수/매도, 왕복 예상 비용), cost footnote, timing note. | GET /api/qsf/order-plan?market | account (unified account), latest scan, market-state | No | No | test_order_plan_paper_book.py, test_audit_fixes_2026_11_22.py, test_assessment_fixes_2026_11_23.py |
| QE-02 | Plan state: NO_SCAN / NO_ACCOUNT | exec | "기록된 스캔이 없습니다"; NO_ACCOUNT reason + candidate count + button "통합 계좌에서 기록하기" (inline `acctRecord('US'|'KR')`). | order-plan | account | No | Navigates to account entry | test_order_plan_paper_book.py |
| QE-03 | Adverse-day size-factor notice + new-exposure cap | exec | "시장 상태가 나쁘거나 읽을 수 없는 날이라 ... X%로 계산..." plus cap % and plan total. | order-plan | size_factor, new_exposure_cap | No | No | test_audit_fixes_2026_11_22.py |
| QE-04 | Stance note + left-out reasons; bands note; skipped-candidates line | exec | Notice "빠진 이유: ..." ; band note; "계획에서 빠진 후보: reason N종목". | order-plan | stance | No | No | test_stance_plain.py |
| QE-05 | Plan row highlight/jump target | exec | `data-plan` rows; `qsfPlanFocus` scroll+highlight, notify if missing. | order-plan | planFocus | No | No | test_ui_batch_6.py |
| QE-06 | Paper book panel (`qsfPaperHtml`) | exec `#qsfpaper` | "가상 체결 장부 [판정 전 참고][가상의 금액]"; empty state "아직 기록이 없습니다 ..."; header line (sessions, integrity, fills, unfilled counts); 9 tiles (평가액, 수익률, benchmark, 최대 낙폭, 현금, 끝난/이긴, 평균 순수익, 수수료, 슬리피지); 보유 N종목 table (pending-exit badge); 다음 거래일 시가의 주문 계획 (same order table + market-state line + skip line); 최근 매도 table; 최근 체결 table; rules paragraph (start cash, fill rule, PB-2 adverse-day halving, exits). | GET /api/qsf/paper-book?market | paper_book store | No | No | test_order_plan_paper_book.py, test_paper_trade.py (different: hand-kept 모의 매매 is another tab) |
| QE-07 | 회전율 규칙 비교 TO-1 block (`qsfTurnoverHtml`) | exec, inside paper book | Status DECIDED/RECORDING/pre-first/DAMAGED text, rule counts, own trade volume, rule description, `.env` force badge, damaged/unknown-switch warnings. | GET /api/qsf/turnover-book | comparison book | No | No | test_turnover_book.py |
| QE-08 | Turnover rule switch button "이 규칙 쓰기 / 쓰지 않기" | exec | Appears only when DECIDED and `.env` mode is auto; disables, POSTs `{market,on}`, shows reason inline on failure, notify note, reloads paper book. Before decision: explanatory line instead. | POST /api/qsf/turnover-rules | verdict file | No | YES (rules on/off, setting) | test_turnover_book.py; browser step |
| QE-09 | 순위 규칙 비교 RK-1 block + switch (`qsfRankBookHtml`) | exec | Same pattern as QE-07/08 for rank rules (entry top %, long exit outside top %). Button class `qsf-rule-switch`. | GET /api/qsf/rank-book, POST /api/qsf/rank-rules | rank book | No | YES | test_rank_book.py |
| QE-10 | Market-state line in plan | exec | `qsfPlanState`: "이 계획이 읽은 시장 상태 ... 자세한 설명은 맨 위 띠". | order-plan | - | No | No | test_ui_batch_2.py |

### QT: tracking / verdict schedule (view track)

| ID | Feature | Screen | Interaction | API / backend | Data dependency | Hidden/nested? | Writes? | Regression check |
|---|---|---|---|---|---|---|---|---|
| QT-01 | 판정 일정 panel (`qsfReadings`) | qsf / track, fold "readings" (open by default) | Header "읽음 n / total"; summary sentence (read / due / waiting, nearest verdict); table of non-waiting readings: 판정 + 주된 판정/참고/스스로 적용 badges, 기록 n / wanted, state (읽음 + verdict + meaning + reasons; 읽을 때가 됨 + attempts; 기다리는 중 + days left + ~date), 결과가 나오면, 문서. | GET /api/qsf/readings | automation state, reading files | No | No | test_readings.py |
| QT-02 | 전체 일정 보기 | qsf / track | Nested `details.qsf-readings-all` (open state kept across refresh) with all readings. | readings | - | Yes | No | test_readings.py |
| QT-03 | Fund-period switch button (연간 <-> 최근 4분기) | qsf / track, in fund-period reading row | Visible only when switch.can_switch; `confirm()` dialog ("... 바꿉니다. 다음 스캔부터 스윙과 장기 점수 모두에 적용됩니다. 바꿀까요?"); POST; notify OK/err; reload. Else explanatory text (.env controls / appears after verdict). | POST /api/qsf/fund-period {market, period} | verdict, .env | row inside table | YES (score input setting) | test_assessment_fixes_2026_11_23.py (qsf-fund-switch), test_fund_period.py |
| QT-04 | Top-3 tracking (`qsfTop3`) | track, fold "top3" | Per-day blocks (last 10): session score -> entry session; table rank/종목/점수/post-entry return net with relative; "개장 뒤 고정이라 집계에서 뺌"; aggregate table by model (days, picks, beat-benchmark %, mean relative, vs-universe, rank corr, verdict + window note); small-sample notice. NO_RECORD/failed states. | GET /api/qsf/top3?market | frozen top-3 record | No | No | test_readings.py, test_assistant.py |
| QT-05 | FC-1/FC-2 tracking panel | track, fold "fcast" | `fcTrack` (FC-07..FC-12). | GET /api/qsf/forecast | forecast record | No | No | test_forecast.py, test_forecast_touch.py |
| QT-06 | KR-M1 독자 매매법 panel (`qsfMethod`) | track, KR only, fold "method" | Table R1,R2,R3,T1-T4,B0,B00: latest signals, cumulative signals, closed, open, net per trade, win rate, payoff, vs B0; 주력 badge; rules and selection-result text. Empty "아직 기록이 없습니다". Hidden for US. | GET /api/qsf/kr-method | method record | No | No | test_kr_method.py (backend); JS unpinned |
| QT-07 | 시장 국면 가중치 도전자 panel (`qsfRegime`) | track, fold "regime" | Badge 기준 충족/미달 (n/m)/시험일 부족; walk-forward summary; condition table; weight table per state with "최근 기록일의 상태"; record counts; nested details "한계 N가지". | GET /api/qsf/regime-weights | report files | Yes (limits) | No | test_regime_weights.py, test_order_plan_paper_book.py |
| QT-08 | 미래 자료 차단 점검 panel (`qsfLookahead`) | track, fold "look" | Status badge; function table (days, moved, verdict), control row; record-store table (hash chain, before-next-open, late, span); walk-forward line; note. NO_RECORD empty. | GET /api/qsf/lookahead | audit file | No | No | test_lookahead.py, test_order_plan_paper_book.py |
| QT-09 | 전향 검증 panel (`qsfValidation`) | track, fold "valid" | Table per cohort (US/KR x swing/long): snapshots, sessions, independent samples, verdict; integrity badge; mixed-model-version notice. Silent skip on error. | GET /api/qsf/validation | validation | No | No | none found for JS |
| QT-10 | Fold toggles for track panels | track | Click h2 to fold; persisted (see QR-18). | none | - | Yes | localStorage | browser step |

### FC: forecast.js

| ID | Feature | Screen | Interaction | API / backend | Data dependency | Hidden/nested? | Writes? | Regression check |
|---|---|---|---|---|---|---|---|---|
| FC-01 | Card fold "가격 범위 · 예측 층 FC-1" loader (`fcStock`) | qsf card (fold `range`) | On first open fetch stock forecast; guards stale card. Statuses: NO_RECORD, BROKEN (hash fail), NOT_IN_RECORD, no data (<120 sessions), fetch error "가격 범위를 불러오지 못했습니다." | GET /api/qsf/forecast-stock?t&market | forecast record | folded | No | test_forecast.py, test_ui_batch_3.py |
| FC-02 | Test badge + reason line (`fcTestBadge/fcTestReason`) | FC-01 and FC-07 | "범위 폭 점검 통과 · 방향 근거 없음" / "과거 점검 미달" / "과거 점검 없음", failed-cell list with band. | forecast | test file | tooltip | No | test_forecast.py |
| FC-03 | Range strip graphic (`fcStrip`) | card range fold | CSS bars: 50% and 80% ranges for 5 and 20 sessions, marks for swing stop/target, tags, axis (±%), legend; aria-label describes ranges. | forecast-stock | ranges, swing card levels | - | No | test_forecast.py |
| FC-04 | Range table | card range fold | Rows 5/20거래일: 50% and 80% price ranges (and % vs close), past coverage 50/80; vol-third text, bias note, stress note. | forecast-stock | - | - | No | test_forecast.py |
| FC-05 | Level placement table (`fcLevelLines`) | card range fold | Stop/target price, % from price, per horizon "50% 범위 폭 안쪽 / 50% 범위 밖 · 80% 범위 안 / 80% 범위 밖" + how-to-read paragraph. Only if swing card has stop/target. | forecast-stock + card levels | - | - | No | test_forecast.py |
| FC-06 | Touch probabilities (`fcTouchLines`) FC-2 | card range fold | Table: level, price, distance in vol multiples (tooltip), probability per horizon ("약 N%" / "이미 기준을 지남" / "가까워서 대부분 닿음" / "멀어서 표 밖"), same-vol-group past actual; note, failed cells, formula-source note. Before first record: "닿을 가능성은 date 거래일 기록부터 보입니다...". | forecast-stock (touch) | touch table | - | No | test_forecast_touch.py |
| FC-07 | Direction numbers fold `fc-fold` (`fcDirection`) | card range fold and track panel | Details "방향 쪽 숫자: 근거 기준으로 초과 수익 0, 확률 50%": per strategy alpha, win prob, reason, assumed values, z. | forecast-stock / forecast | ic evidence | Yes | No | test_forecast.py |
| FC-08 | Tracking panel header + FC-1 past test table | qsf / track fold "fcast" (`fcTrackHtml`) | Title with badge, how-paragraph, integrity notice, past-test table (80% / 50% all/early/late, by vol third, stress share). Empty "아직 기록이 없습니다." | GET /api/qsf/forecast?market | - | - | No | test_forecast.py |
| FC-09 | Forward record table | track | Per horizon: current 80% width median, past median, matured/needed, actual coverage 80/50, reading verdict ("띠 안/밖") or "끝난 기록일 N개에서 한 번 읽음". | forecast | - | - | No | test_forecast.py |
| FC-10 | Direction record table | track | Per strategy: IC evidence, reason for 0, matured, high/mid/low win share, Brier assumed vs half. | forecast | - | - | No | test_forecast.py |
| FC-11 | FC-2 touch grid + record | track | Calibration grid forecast -> real per distance and horizon, latest table, record table with verdict "허용 차이 안/밖"; protocol line. | forecast (touch) | touch | - | No | test_forecast_touch.py |
| FC-12 | Known-limits details | track | `details.fc-fold` "알려진 한계 N가지" + path note + protocol code line. | forecast | - | Yes | No | test_forecast.py |

### IC: committee.js (tab committee)

| ID | Feature | Screen | Interaction | API / backend | Data dependency | Hidden/nested? | Writes? | Regression check |
|---|---|---|---|---|---|---|---|---|
| IC-01 | Tab header + disclaimer | committee | Title "투자위원회 [market] · 다섯 투자자 엔진과 통합 위원회 · 규칙 IC-1"; paragraph (not real investors, not validated, not mixed with QSF, no orders). Market comes from global market switch. | none | state.market | No | No | test_committee.py (renderCommittee) |
| IC-02 | View switch (위원회 현황 / 여섯 포트폴리오 / 투자자 비교 / 가상 성과) | committee | `icSetView` toggles seg buttons; not remembered in storage (icState only); renders body. | none | - | No | No | test_committee.py |
| IC-03 | 위원회 현황 panel (`icDash`) | committee / dash | Four big stats (판정한 종목, 매수 조건으로 본 종목, 의견 일치 평균, 시장 상태); nested details "분포와 국면 자세히": market state + regimes (확신) + unread regimes, decision distribution chips, disagreement kinds, frequent risks. Loading, error `errBox`, empty reason. | GET /api/committee/dashboard?market | scan record | Yes (details) | No | test_committee.py |
| IC-04 | Buy-condition top table | committee / dash | "위원회가 매수 조건으로 본 종목 N종목 가운데 매력 순 K종목": 종목 (opens score card via `qsfOpenCard`), 업종, 판정, 매력, 자료·일치 (tooltip with weights), 찬성한 관점, 찬성 논거, 반대 논거; empty "억지로 채우지 않습니다". | dashboard | - | No | No | test_committee.py |
| IC-05 | 여섯 포트폴리오 landing (not yet generated) | committee / ports | Description of six portfolios + primary button "여섯 포트폴리오 받아보기" (generates only on click, per market cached in `icState.ports`). | none until click | - | No | No | test_committee.py (icPortsGet) |
| IC-06 | Generate / "다시 받아보기" | committee / ports | Loading "여섯 포트폴리오를 작성하고 있습니다…"; error box; reason empty. Not stored server-side (computed on request). | GET /api/committee/portfolios?market | scan record | No | No (compute only) | test_committee.py |
| IC-07 | Portfolio sub-tabs + overlap line | committee / ports | Seg of six names with counts; "겹치는 종목" pairs; remembered `icState.port`. | portfolios | - | No | No | test_committee.py |
| IC-08 | Portfolio detail (`icPortHtml`) | committee / ports | h2 name/objective, plain block "쉽게 설명해줘", fatal-exit notices ("치명적 훼손으로 전량 제외"), overweight notices ("비중 과다 알림 · 오늘 처음"), 6 stat tiles (종목 수, 투자 비중, 현금, 가장 큰 종목, HHI, 이번 교체), sizing rules, limits, held-weights text, cash reasons, sector line, holdings table (종목 -> card, 업종/category, 비중 + 비중 과다 badge, 판정, 점수, 자료 확인, 상태, nested details with thesis/entry/exit/sizing/vol/as-of), exits list, moves-together list; empty "전부 현금입니다". | portfolios | - | Yes (per-row details) | No | test_committee.py |
| IC-09 | 투자자 비교 (`icCompare`) | committee / compare | Search form (comma-separated codes, up to 12 server-side) -> `비교`; default top-20 by committee attractiveness; matrix: 종목, five engine badges+scores (tooltip valuation+horizon), 위원회, 매력, 일치, 성장, 하방 위험; not-found notice; second panel tally per engine; notes. | GET /api/committee/compare?market&t=a,b | scan record | tooltips | No | test_committee.py (api route); JS unpinned |
| IC-10 | 가상 성과 (`icPerf`) | committee / perf | Title with "가상 기록" badge, kind/method/cost lines; when records exist a 16-column table (거래일, 수익, 지수, 최대 낙폭, 오른 날, 연환산, 변동성, 샤프, 소르티노, 칼마, 알파, 베타, 하루 교체, 평균 보유일, 비용 합), ratios line; "한 번의 읽기" verdict block; empty: reason + record count. | GET /api/committee/performance?market | daily paper-record | No | No | test_committee.py |
| IC-11 | Stock card embed (`icCardHtml`) | qsf card fold 다섯 투자자와 투자위원회 | Five investor cards in `.ic-grid` + committee block + plain block + button + result slot + note. Non-OK shows reason panel. | evaluate.committee | - | folded | No | test_committee.py, test_ui_audit_2026_11_23.py |
| IC-12 | Investor card (`icInvestorHtml`) | IC-11 | Name, "규칙 엔진" badge, philosophy, recommendation badge (colour tokens), score, 자료 확인, opinion, 근거/우려/할 일, optional alternative-profile line (Graham profiles side by side). Nested details "자세히": alt profile opinion/buy, question/horizon, valuation, approximate return/downside (tooltip bases), component scores, category/profile/method/loss risk/regimes/unread regimes, reverse-risk ways, positives/negatives, six condition lines (매수/보유/추가 매수/축소/매도/생각이 틀렸다고 볼 때), missing data, coverage + suggested weight. | evaluate | - | Yes | No | test_committee.py |
| IC-13 | Committee verdict (`icCommitteeHtml`) | IC-11 | Decision badge, 9 score chips (매력, 신뢰, 일치, 품질, 가치, 성장, 국면, 하방, 자료), thesis, reasons list, strongest for/against; nested details "위원회 토론 자세히": 함께 좋게/나쁘게 본 것, 의견이 갈린 곳, 따로 본 위험 (중대/주요), 들어갈/나올 조건, 따르지 않은 의견. | evaluate | - | Yes | No | test_committee.py |
| IC-14 | "포트폴리오 받아보기" button in card (`icPlace`) | qsf card committee fold | Click: disables, label "작성 중…", GET place, renders table "여섯 포트폴리오에서 이 종목" (포트폴리오, 이 종목의 비중 or 없음, count + cash, why) with link to committee tab; label becomes "다시 받아보기"; error notice. Invalidates `icState.ports[market]` cache. Global click listener. | GET /api/committee/place?t&market | scan record | result slot | No (compute only) | test_committee.py (ic-place, icPlace) |
| IC-15 | Rows -> score card (`icOpenRows`) | dash/ports/compare tables | `.qs-open` buttons call `qsfOpenCard(ticker)` (switches tab to qsf). | none | - | No | history | test_committee.py |

## Part 2: Per-view blocks

### View: qsf / 오늘 순위 (rank)
- Components: strip (details), nav row (view seg, strategy seg, stance seg), ticker form + status line, split container (`#qsfdetail` + `#qsfrank`), fold panels `#qsfcap` (KR) and `#qsfchanges`; table `qsf-rank-tbl` with expandable rows embedding the full card; card = two article cards + three/five folds.
- Layout desktop >=1600px: `.qsf-split:has(> #qsfdetail > .panel)` becomes grid `minmax(0,1fr) 560px`; card sticky at right (top = `--sticky-top` + gap), rank on left, domain-bar columns and delta column hidden (delta moves under score). 1280-1599: single column, card above table; domain bars hidden <1280px. Phone <=640px: `.w/.w2` columns (sector, 판단, 진입) hidden, 판단+진입 moved under the name (`qr-m2`), tighter padding; table header sticky; nav row wraps.
- Weaknesses:
  1. Information density: each rank row can stack name, 4 chip kinds, up to 4 risk sentences and label+entry under name; the same label+entry is rendered twice in the DOM (`qr-m2` and `w`/`w2` columns) toggled by CSS.
  2. Hierarchy: the strip always says "근거 아직 없음 · 참고용" but the same warning repeats in 4 other places (caveat, rank intro, risk notes, card notes); user-facing disclaimers outweigh data.
  3. Card appears in three different positions (above table <1600, beside >=1600, inline in expanded row) with different widths; expanded-row card and the main card are two different render paths (`qsfFillRow` vs `qsfDrawDetail`) causing inconsistency (e.g., expanded row has no 이력과 기술 정보 / 가격 범위 / committee folds, but has its own 당일 점검).
  4. Two entry paths for the same action: tapping a name opens the stock screen, tapping elsewhere opens the card; the intent split is only explained by a tooltip.
  5. Controls row mixes three unrelated concepts (view, strategy, stance) in one wrap line with identical `.seg` styling; stance (market-wide config) looks like a filter.
  6. Table has 12 columns with 5 breakpoints (1280, 1600-with-card, 640, 400) controlling visibility, so the same feature set shows differently per width; phone loses sector and domain bars entirely.

### View: qsf / 스크리너
- Components: form (`qs-form`) with 9 inputs + checkbox row + two buttons, count line, results table `qs-table`, "더 보기".
- Layout: desktop single panel, form is a wrapped grid; phone relies on the generic form wrap; table scrolls inside `.tbl-wrap` (no sticky header unlike the rank table).
- Weaknesses: (1) live-filter with debounce but also a no-op submit path, no visible "applied filters" summary; (2) sector select starts almost empty until first response (options appear late); (3) result table lacks the rank table's chips/domain bars/delta, so the same stock looks different here; (4) opening a card from here switches views, the user loses the filter position (state kept but scroll not); (5) CSV button sits in the form next to reset with no export hint of row limit (2000); (6) no sticky header, no column for 업종 on phone adaptation.

### View: qsf / 주문 계획·가상 장부
- Components: order plan panel, paper book panel (tiles, 4 tables), TO-1 and RK-1 blocks with switch buttons, rules paragraph.
- Layout: two stacked panels; 14-column order table inside scroll wrapper on both desktop and phone (used twice: plan and "다음 거래일 시가의 주문 계획").
- Weaknesses: (1) 14-column table is horizontally scrolled on phone with no priority columns; (2) the same order table is rendered in two places with different titles; (3) TO-1/RK-1 are buried between 최근 매도 and 최근 체결 tables, yet carry the only buttons that change behaviour; (4) very long explanatory sentences before data (how/rules) push the table below the fold; (5) money/percent tiles use inline styles (`font-size:16px`) not tokens; (6) "주문을 보내지 않습니다" and "가상의 금액" badges both present, and the paper book vs the 모의 매매 tab (other module) naming is easily confused.

### View: qsf / 판정 일정
- Components: seven fold panels (readings, top3, forecast, KR-M1, regime weights, look-ahead, validation).
- Layout: all stacked, headings clickable to fold; only readings open by default; same on desktop and phone.
- Weaknesses: (1) seven unrelated audit/validation panels in one flat list with no grouping or summary of "what needs my attention"; (2) fold affordance is the h2 only (no chevron, delegated click handler), so discoverability depends on CSS; (3) many tables of 6-9 columns at phone width; (4) verdict text is raw strings from reports; (5) Korean-only jargon (IC, Brier, walk-forward) with minimal glossary; (6) the one real action in this view (fund-period switch + confirm) is inside a table cell.

### View: committee / 위원회 현황
- Components: stats tiles (4), details "분포와 국면 자세히", buy-conditions table.
- Layout: two panels; table 8 columns with long text cells (찬성 논거/반대 논거) wraps wide on desktop; phone scrolls horizontally.
- Weaknesses: (1) text columns are wide and dominate numeric columns; (2) row activation only through the ticker button (the hint "줄을 누르면 점수 카드" says row but only the button is wired); (3) 매력 / 자료·일치 numbers have no bars or scale; (4) stats tiles use `ic-stat` custom style not shared with qsf tiles; (5) market state number duplicates the qsf strip; (6) no sorting.

### View: committee / 여섯 포트폴리오
- Components: landing with primary button, six-button segment with counts, overlap line, per-portfolio panel (tiles, notices, table with nested details per row).
- Layout: single column; portfolio panel long; table 8 columns with a details cell containing the thesis as the summary.
- Weaknesses: (1) empty-landing explanation is a dense paragraph and the CTA is the only element; (2) after generation, "다시 받아보기" is a ghost button inside an h2; (3) six segment buttons wrap on phone; (4) per-row thesis is the `<summary>` text so long text acts as the toggle; (5) sector/category line cramming; (6) fatal/overweight notices precede tiles, pushing the data down.

### View: committee / 투자자 비교
- Components: search form, comparison matrix (5 engines + committee + 4 numbers), tally panel.
- Layout: matrix of up to 12 columns, horizontal scroll.
- Weaknesses: (1) 12 columns at phone width; (2) tooltips are the only place valuation/horizon appear (not touch friendly except phone.js taptip); (3) cell mixes badge + score, no colour/size encoding of score; (4) form markup (`.search` with inline style) differs from `.qsf-form`; (5) no way to clear/return to default top-20 except empty submit; (6) `not_found` handled but no input validation.

### View: committee / 가상 성과
- Components: head lines, 16-column metrics table, ratio line, reading block.
- Weaknesses: (1) 16 columns with finance jargon (샤프, 소르티노, 칼마, 알파, 베타) and no explanation inline; (2) no chart of the paper curves although records exist; (3) the verdict block sits under the table instead of leading; (4) empty state mostly text; (5) sample-length warning is a footer; (6) abbreviations without tooltips.

### Card (cross-view): score card
- Components: header, notes, two strategy articles, folds (근거 open, 계획, 요인별 계산, 위원회, 가격 범위, 이력과 기술 정보).
- Weaknesses: (1) two strategy cards stacked each with its own 3-4 folds -> the fold keys are per kind, not per strategy, so opening one opens both; (2) 근거 fold nests plain block, balance, domains, entry; (3) status of "referencing" parts (committee, range, tech) is separated from the scoring parts only by section title tags; (4) summary strip packs 5 facts and 2 action links in one line; (5) beside-mode sticky panel has a fixed 560px width and its own scroll; (6) card disclaimers repeat at top and bottom.

## Part 3: API routes used (cross-check with terminal/server.py)

All routes below exist in server.py (line = route dict entry):

| Route | Method | server.py line | Used by |
|---|---|---|---|
| /api/qsf/bands | GET | 228 | qsf.js (load) |
| /api/qsf/market-state | GET | 225 | strip |
| /api/qsf/track-record | GET | 208 | strip record fold |
| /api/qsf/stance | GET 216, POST 217 | 216-217 | stance block, stance buttons |
| /api/qsf/latest | GET | 204 | rank, return check |
| /api/qsf/rank-notes | GET | 227 | rank |
| /api/qsf/evaluate | GET | 201 | evaluate form, expanded rows, links |
| /api/qsf/history | GET | 203 | card tech fold |
| /api/today | GET | 233 | 당일 점검 |
| /api/qsf/changes | GET | 206 | changes panel |
| /api/qsf/former-universe | GET | 209 | KR cap panel |
| /api/qsf/screen | GET | 205 | screener + CSV |
| /api/qsf/order-plan | GET | 224 | plan |
| /api/qsf/paper-book | GET | 215 | paper book |
| /api/qsf/turnover-book | GET | 221 | TO-1 |
| /api/qsf/turnover-rules | POST | 220 | TO-1 switch |
| /api/qsf/rank-book | GET | 223 | RK-1 |
| /api/qsf/rank-rules | POST | 219 | RK-1 switch |
| /api/qsf/readings | GET | 222 | 판정 일정 |
| /api/qsf/fund-period | POST | 218 | fund-period switch |
| /api/qsf/top3 | GET | 226 | top-3 tracking |
| /api/qsf/forecast | GET | 213 | FC tracking |
| /api/qsf/forecast-stock | GET | 214 | card range fold |
| /api/qsf/kr-method | GET | 210 | KR-M1 |
| /api/qsf/regime-weights | GET | 211 | regime panel |
| /api/qsf/lookahead | GET | 212 | look-ahead panel |
| /api/qsf/validation | GET | 207 | validation panel |
| /api/committee/dashboard | GET | 195 | IC dash |
| /api/committee/portfolios | GET | 193 | IC ports |
| /api/committee/place | GET | 192 | IC-14 |
| /api/committee/compare | GET | 194 | IC compare |
| /api/committee/performance | GET | 196 | IC perf |

Count: 32 distinct paths, 35 method+path pairs with POST variants counted (stance/turnover/rank/fund-period POSTs). No missing route, no dead route found in my three files. Routes in server.py with `/api/qsf/` that these files do NOT call (belong elsewhere or unused here): none observed among those I grepped; I did not enumerate server.py's remaining qsf routes beyond the used ones.

Write endpoints (all POST, all via `api(...)`): stance (QR-08), turnover-rules (QE-08), rank-rules (QE-09), fund-period (QT-03). Everything committee-related is GET and computes on request; nothing persists. Client-side writes: localStorage keys `qse-qsf-strategy`, `qse-qsf-view`, `qse-qsf-folds`, `qse-fold-<kind>`; history `pushState/replaceState/hash`; CSV download.

## Part 4: Things not determined / caveats
- CSS rules for `.qsf-split` were read (style.css 575-581) but I did not read the full stylesheet, so exact paddings/tokens and the `ic-*` styles are not reviewed.
- Row counts of server responses (e.g. how many rows `rank-notes` covers) were not verified against data files (kept out per instructions).
- Global handlers outside my files that affect behaviour (stock-screen `.linkish[data-ticker]`, `.qsf-tostock`, `plain-btn`, `collect-now`, phone.js taptip, `prefillTicker`, `redrawAll`, `RETURN`) were located only partly; their exact behaviour belongs to other inventories.
- Test coverage claims are by grep of function/string names in tests/; a test that exercises the behaviour without naming the symbol would show as "none found".
- Untested in JS (no grep hit): qsfScreenCsv/qsfCsvCell, qsfTurnoverHtml/qsfRankBookHtml markup, qsfMethod, qsfRecordHtml/qsfWhyHtml, qsfChanges, icDash/icCompare/icPerf, qsfMissTag, qsfValidation.

---

# Part C — Today, accounts, charts, lab, coin

Scope: `terminal/static/{assistant,account,portfolio,paper,lab,chart,compare,map,rotation,sectorpicks,coin}.js`, plus the pieces of `app.js` that these screens depend on (`renderModel`, `wireCapital`, `card()`, `show()`, `RETURN`/`ALWAYS_FRESH`) and `alerts.js` (rendered into the assist tab). Read-only inspection; no file in the project was touched. `.env`, `phone_view.json`, `horizon_bot_beta` were not read.

Conventions
- "Test pin" = existing pytest file. Most JS pins are text assertions on the JS/CSS source (not behaviour), so a browser step is suggested where behaviour matters. File names are under `tests/`.
- `GLOBAL` behaviours that apply to every row below: any element with `data-ticker` (chips, cards, `b[data-ticker]`, `tr.click[data-ticker]`) opens the stock tab through the document-level click handler in app.js (`openTicker`); `tr.click`, `tr[data-coin]`, `tr[data-fund]`, `div.card[data-ticker]`, `b/span[data-ticker]` are made keyboard-operable (Enter/Space) by `markKeyable` (pinned by test_ui_batch_5.py); `.seg` buttons get `aria-pressed`; `[title]` attributes are shown on phone by the tap-tip (`#taptip`) and on desktop as native tooltips; `#tip` is the shared hover tooltip for canvases.
- Market switch (`setMarket`) clears every tab's HTML and `state.loaded`, so every screen redraws for the new market. The `account` tab is the only tab open in all markets (`ANY_MARKET`); in market COIN only groups `today` and `coin` (plus account) are shown (`groupShown`).
- Colour rule: on KR market screens (except account) `html[data-color=kr]` swaps to red-up/blue-down (test_ui_batch_1.py).
- Tab host layout: `main` max-width `--content-max`; `WIDE_TABS` (qsf, committee, portfolio, watch, lab, model, coin) use `--content-max-wide` (test_ui_batch_5.py `test_table_screens_widen...`). `account`, `today`, `assist`, `paper`, `chart`, `compare`, `map` stay narrow.
- Phone (<=640px): top-bar group nav hidden, fixed bottom bar (오늘/종목/점수/코인/내 계좌/더보기) + "더보기" sheet; `body` gets 56px bottom padding; tables scroll horizontally inside `.tbl-wrap` with the first column sticky.

---------------------------------------------------------------------------

## 1. Feature rows

### 1.1 오늘 (tab `today`, assistant.js)

| ID | Feature | Screen | Interaction | API / backend | Data dependency | Hidden/nested? | Writes data? | Suggested regression check |
|---|---|---|---|---|---|---|---|---|
| TD-01 | Panel title "오늘" + market badge (미국/한국/코인) | today / top panel | Display only; badge follows market switch | none (state.market) | `state.market` | no | no | Browser: switch 미국/한국/코인, badge text changes |
| TD-02 | Question box (`#asst-form`, input `#asst-q` maxlength 200, button "묻기") | today / top panel | Type a question, Enter or 묻기; placeholder differs by market (US: "AAPL 점수 왜 낮아?...", KR: "삼성전자 ...", COIN: "코인 상위는? ..."); shows loading, then the answer card; empty input ignored; error shown as red `.msg.err` | POST `/api/assistant/ask` `{q, market}` -> `assistant.answer` (COIN -> `coin_answer`) | stored scan ledger, order plan, market state; coin file/Binance data in COIN | no | no (read only) | test_assistant.py (answer intents); test_ui_batch_5.py (asstBrief); Browser: ask "help" |
| TD-03 | "물어볼 수 있는 것" button (`#asst-help`) | today / top panel | Click asks the literal word `help`; answer lists all fixed questions as chips | POST `/api/assistant/ask` | `EXAMPLES` (22 fixed questions: 11 plain + 11 stock-bound; COIN has 5 `COIN_EXAMPLES`) | no | no | test_assistant.py (help lists examples) |
| TD-04 | Answer card (`.asst-answer`) | today / `#asst-out` | Renders: echoed question (`.asst-q`), title h3, bold one-line `summary`, h4-titled sections each a bullet list, basis meta, note meta; `status != REAL` -> grey left border ("unknown"); each new ask replaces the previous card (one card at a time) | `/api/assistant/ask` | answer JSON: title, summary, sections[], lines[], basis, follow[], examples[], tab, ticker, note, status | no | no | test_assistant.py; Browser: ask an unknown phrase -> grey card with examples |
| TD-05 | "이어서 물어보기" follow chips and "눌러서 물어보기" example chips | today / inside answer | Click a chip -> its text is put in the box and asked again (delegated click on `.asst-ex`) | `/api/assistant/ask` | `follow`, `examples` | nested in answer | no | test_assistant.py (`_others` follow list); Browser: click a chip |
| TD-06 | Answer's "<탭> 탭에서 보기" ghost button | today / inside answer | Click -> `asstGo(tab, ticker)`: stock -> `openTicker`; qsf + ticker -> `qsfOpenCard`; else `show(tab)` + scroll top. Tab names mapped by `ASST_TAB_KO` | none (client nav) | `a.tab`, `a.ticker` | nested in answer; not shown when tab is `today` | no | test_ui_batch_6.py `test_deep_links_and_the_view_in_the_address` |
| TD-07 | "사도 돼?" buy-check answer (BUY_CHECK intent) | today / answer card | Ask "<종목> 사도 돼?" (keywords 사도/살까/사면/매수/들어가/진입/담아). Shows summary "N개 중 M개가 걸림 없이 통과 ... 이 점검표는 살지 말지에 대한 답이 아닙니다", section "점검표 (○ 통과 · ✕ 걸림 · – 확인 못 함)" with 7 rows (점수 구간, 진입 판단, 차단 조건, 실적 발표, 회피 표시, 시장 상태, 보유 여부), section 참고, section 다음에 볼 것, follow chips (분석/왜/손절/위험) | POST `/api/assistant/ask` -> `stock_answer` BUY_CHECK | stored scan row + snapshot, market state, holdings | nested checklist lines | no | test_assistant.py (search "BUY_CHECK"/"점검표"). **Note**: the memory index describes a 사도 됨/기다림/사지 않음 verdict start; the current code (assistant.py ~line 1487) is a checklist and the strings 사도 됨/기다림/사지 않음 occur nowhere in terminal/ or tests (only an unrelated 기다림 hit in a test fixture). There is no separate "verdict box" component in JS: it is the generic answer card. |
| TD-08 | Other stock questions (11 stock intents): STOP 손절 어디?, RANGE 얼마까지 움직일까?, EARNINGS 실적 언제?, SELL_CHECK 팔아야 해?, RISK 위험해?, RANK 몇 등이야?, WHY 점수 왜 낮아?, ANALYZE 분석해 줘 (analyst note), FIVE 다섯 관점은? (committee), PORTFOLIO 포트폴리오 받아보기 | today / answer card | Same answer card; stock found by ticker or (KR) name from stored scan names; each has follow chips to the other intents | `/api/assistant/ask` -> `stock_answer`, `analyst_note`, `five_answer`, `portfolio_answer` | scan ledger, forecast (RANGE), committee service, peers | nested | no (PORTFOLIO only reads; "portfolios only on a button" rule) | test_assistant.py |
| TD-09 | Plain questions (11): HELP, TRUST 이 점수 믿어도 돼?, COST 수수료, ALERTS 걸어 둔 알림, VERDICTS 판정은 언제?, JOB 오늘 수집 됐어?, CHANGES 어제와 뭐가 달라졌어?, MARKET 시장 상태, HOLDINGS 내 보유 종목, TOP 오늘 상위 종목, TODAY 오늘 뭐 해야 해? | today / answer card | Same card; no stock needed | `/api/assistant/ask` -> `plain_answer` | readings, automation state, account, top3 | nested | no | test_assistant.py |
| TD-10 | Unknown question fallback | today / answer card | Unrecognised text -> "unknown" styled card saying only fixed questions are understood, with example chips | `/api/assistant/ask` | `EXAMPLES` | nested | no | test_assistant.py |
| TD-11 | COIN-market questions ("코인 상위는?", "코인 시장 상태 어때?", "비트코인 분석해 줘", "솔라나 점수 왜 이래?", "이 코인 점수 믿어도 돼?") | today / answer card when market=COIN | Placeholder switches; coin found by name/symbol in coin table | `/api/assistant/ask` -> `coin_answer` | `coin_bridge.read` (registered score file if present, else Binance simple rank) | nested | no | test_coin_bridge.py (`askAssistant`) |
| TD-12 | Ask from elsewhere: `askAssistant(q)` (command palette, coin row click, stock-tab shortcuts) | today | If already on today: asks immediately and scrolls top; otherwise stores `asstPending`, switches to today, asks after render/return | same | `asstPending` | no | no | test_assistant.py, test_coin_bridge.py, test_ui_ticker_context.py (grep `askAssistant`); Browser: coin tab row click lands on Today with the answer |
| TD-13 | Brief panel header (`#asst-brief` h2 = `headline_main`) + meta "<시장> 시장 · 기준 거래일 <date|기록 없음> · <time> 기준" | today / brief panel | Display; headline includes the market-state clause | GET `/api/assistant/today?market=` -> `assistant.briefing` (COIN -> `coin_briefing`) | order plan session, items, market state | no | no | test_assistant.py (briefing) |
| TD-14 | "읽지 못한 부분" banner | today / brief | Red `.msg.err` listing parts whose builder raised (e.g. 시장 숫자, 오늘의 후보); their items are missing from the list | same (`unread_parts`) | server-side `part()` failures | conditional | no | test_assistant.py (unread_parts) |
| TD-15 | Market number tiles row (`.asst-tiles`) | today / brief | Grid of the overview cards (index/FX/VIX etc. with 1일/1개월 change, sparkline, date); click a tile whose code is a stock/ETF -> stock tab; neutral tiles (VIX, rates, DXY, FX) show sign only, no colour; phone: 2 columns, sparklines hidden | `/api/assistant/today` -> `tiles()` from `overview` | overview cache (Yahoo), source string + fetched_at via `meta()` | no | no | test_ui_audit_2026_11_23.py (`test_tiles_keep_a_fixed_order...`, `test_the_screens_read_the_new_fields`); test_ui_batch_6.py (neutral tiles) |
| TD-16 | Market-state tile "시장 상태 점수 미반영" | today / tiles row | Shows score_100 / 100, label badge, and (when adverse and size_factor < 1) "새 주문 크기 N%", plus "<session> 기록"; tooltip "어떤 종목 점수에도 들어가지 않는 값입니다"; `risk-note` badge when not FAVOURABLE | `/api/assistant/today` (`tiles.market_state`) -> `terminal.market_state` | MKT-1 market state record | tooltip | no | test_ui_audit_2026_11_23.py |
| TD-17 | 오늘의 후보 (candidates) block | today / brief | h3 + session badge, optional notice (rank-note), two side-by-side tables (스윙 "지금 진입 가능", 장기 "진입을 막는 조건 없음") with up to 5 rows each, header text "N종목 · 그중 매수 후보 구간(70점 이상) M"; footer note; empty -> "...인 종목이 없습니다" | `/api/assistant/today` -> `candidates()` from `qsf.screen_rows` + `rank_notes` | stored scan rows, band edges | no | no | test_ui_audit_2026_11_23.py (`test_candidates_are_the_enter_now_rows...`, `test_the_briefing_adds_figures_and_candidates...`); test_ui_batch_1.py / batch_2 (asstCands) |
| TD-18 | Candidate row: name chip + ticker, band label, integer score with delta vs previous record day (green/red only if >=1 point, tooltip "직전 기록 거래일과의 차이"), "경계 근처" marker (`qsfNear`), band, sector (Korean), 가점/감점 (+pts / −pts) | today / candidate tables | Click name chip -> stock tab. KR/US name-first rule (`nameFirst`). Phone: band and sector columns hidden, band shown under name (`.qr-m2`); tables stack to 1 column | none | `r.plus/minus`, `prev`, `band_edges` | no | no | test_ui_audit_2026_11_23.py, test_ui_batch_6.py (judgement colours); Browser at 390px: columns collapse |
| TD-19 | "할 일과 알림" grouped lists: 먼저 볼 것 (ACT), 오늘 챙길 것 (DUE), 참고 (INFO), each h3 with count badge | today / brief | Display; coloured left stripe 4px (red/amber/grey); empty groups omitted; if nothing: "보여 줄 항목이 없습니다." | `/api/assistant/today` items[] (kinds incl. ORDER, MY_ALERT, HELD_LEFT_BUY, IC_INTERRUPT, MARKET_ADVERSE, TOP3, MACRO_DATE, NEW_VERDICT, VERDICT_STUCK, FUND_GAP, FINANCIAL_SHARE, STANCE, ...) | account, plan, signals, alerts, readings, committee, calendar | no | no | test_assistant.py; test_ui_batch_6.py `test_today_items_fold_after_the_first_sentence` |
| TD-20 | Item body: first sentence as title (`asstFirst`), rest folded in `<details class="asst-more">` | today / list item | Click summary to expand the remainder; single-sentence items render plain | none | item `text` | folded `<details>` | no | test_ui_batch_6.py (`asstItem`) |
| TD-21 | Item action buttons: ticker chip and "<탭> 탭에서 보기" (view-aware: PLAN_UNAVAILABLE/ORDERS_MORE/NO_ORDERS -> qsf "exec"; NEW_VERDICT/VERDICT_STUCK -> "track"; IC_* -> committee "ports") | today / list item | Chip -> stock tab; button -> `asstGo(tab, ticker, view)` sets `qsfState.view` / `icState.view` then `show(tab)` | none | `ASST_VIEW`, `ASST_TAB_KO` | no | no | test_ui_batch_6.py `test_deep_links_and_the_view_in_the_address` |
| TD-22 | 작업 상태 (자동 실행·기록) fold (`.asst-ops`) | today / bottom of brief | `<details>` with count badge; open by default only when an ops item is ACT; holds JOB_*, NEWS_FAILED, RECORD_ALERT items | `/api/assistant/today` (`OPS_KINDS`) | automation status, record status | folded | no | test_ui_audit_2026_11_23.py (`...mark the job lines`) |
| TD-23 | Fallback note under brief when no candidates block | today / brief | Shows server `note` ("비서는 ... 투자 자문이 아니고 주문을 실행하지 않습니다 ...") | same | `NOTE` | no | no | test_assistant.py |
| TD-24 | First-load states | today / brief | Loading placeholder; on failure red "오늘 목록을 만들지 못했습니다: <reason>" | `/api/assistant/today` | network | no | no | Browser: stop server, reload |
| TD-25 | Return-to-tab refresh (`RETURN.today` = `asstReturn`) | today | Leaving and coming back does not redraw: previous list is kept, dimmed (`.refreshing`, 55% opacity), a "갱신 중… 아래는 <time>에 만든 목록입니다." line is inserted, then replaced; on failure "새 목록을 받지 못했습니다: ... 아래는 <time>에 만든 목록입니다."; scroll position restored; stale-response guard by token and market | GET `/api/assistant/today` | `brief.dataset.at` | transient | no | test_ui_batch_5.py `test_today_shows_the_previous_list_while_it_refreshes` |
| TD-26 | Sparkline redraw (`redrawOn("today","sparks")`) | today / tiles | Redrawn on theme change/resize; deferred via `redrawLater` when the tab is hidden | none | canvas size | no | no | test_ui_batch_5.py `test_redraws_are_keyed_and_hidden_tabs_wait` |
| TD-27 | Coin-market brief (COIN) | today / brief | Same layout fed by `coin_briefing` (items COIN_TOP, COIN_MARKET, COIN_COST, COIN_SIMPLE, COIN_CAVEAT, COIN_STALE, COIN_UNAVAILABLE); no tiles/candidates | GET `/api/assistant/today?market=COIN` | `coin_bridge.read` | no | no | test_coin_bridge.py |

### 1.2 통합 계좌 (tab `account`, account.js)

| ID | Feature | Screen | Interaction | API / backend | Data dependency | Hidden/nested? | Writes data? | Suggested regression check |
|---|---|---|---|---|---|---|---|---|
| AC-01 | Entry points: header button "내 계좌" (`#acctbtn`), bottom-bar "내 계좌", group nav "내 계좌", `acctRecord()` from other screens | header / bottom bar | Click -> `show("account")`; works in any market; "내 계좌" bar button always visible | none | none | `#acctbtn` is hidden at <=640px; the bottom bar carries "내 계좌" there | no | test_ui_groups.py / test_ui_batch_3.py (bottombar); Browser: click on each market |
| AC-02 | Journal-integrity banner | account / top | If integrity != OK: notice "거래 기록 무결성 오류: <reason>. 새 기록 추가가 중단됩니다." | GET `/api/account` (`integrity`) | `journal.jsonl` chain | conditional | no | test_account.py (integrity) |
| AC-03 | Panel "통합 계좌" header with 원화/달러 segmented toggle (`#acctunit`) | account / top panel | Click 원화/달러 -> `acctUnit`, saved in localStorage `qse-acct-unit`, page re-fetched/redrawn; totals converted with the day's USD/KRW rate | GET `/api/account` | `localStorage qse-acct-unit`, fx rate | no | local only (browser storage) | test_ui_batch_5.py `test_old_setting_names_move_to_the_qse_prefix_once`; Browser: toggle, reload keeps choice |
| AC-04 | Missing-price notice and missing-FX notice | account / top panel | "가격을 받지 못한 종목이 있어 합계를 확정할 수 없습니다: ..." and "환율을 받지 못해 ... 합계가 비어 있을 수 있습니다." | `/api/account` (`total.missing`, `usdkrw`) | Yahoo prices, FX, Binance | conditional | no | test_account.py |
| AC-05 | Big total + secondary figure ("≈ $..." or "≈ ₩...") | account / top panel | Display; `—` when unknown | `/api/account` | total.krw/usd | no | no | test_account.py |
| AC-06 | KV summary: 총 손익, 오늘 손익 (coloured), 현금, 주식·코인 평가액, 넣은 돈 (입금 − 출금), 환율 + date | account / top panel | Display | `/api/account` | journal + prices | no | no | test_account.py |
| AC-07 | Per-account table (미국 주식 USD / 한국 주식 KRW / 코인 KRW): 평가액, 원화로/달러로, 비중, 현금, 주식·코인, 총 손익, "기록 없음" tag, STALE badge when incomplete | account / top panel | Display | `/api/account` (`accounts[]`) | per-market books | no | no | test_account.py |
| AC-08 | "자세히" button per US/KR row (none for 코인) | account / accounts table | Click -> `setMarket(m,false)` + `show("portfolio")` (시장별 자세히) | none | none | no | no | Browser: click 자세히 on KR -> portfolio tab with KR |
| AC-09 | 보유 종목 table (all three accounts merged, sorted by value): 계좌, 종목 (name+code), 구분 (장기/스윙/미지정), 수량, 평균 단가, 지금 가격, 평가액 (own currency), 원화로/달러로, 전체 비중 (title tooltip), 손익 %, 손절가, 목표가; status badge when price not REAL; empty message pointing to the form | account / holdings panel | Display; tickerLabel is clickable (global data-ticker) | `/api/account` (`holdings[]`) | journal, prices, coin prices (Binance USDT x USD/KRW) | tooltip on 전체 비중 | no | test_account.py |
| AC-10 | Trade form "거래 기록 추가" (`#acctform`): 종류 select (9 kinds: 이미 가지고 있는 종목 추가 HOLD, 매수, 매도, 입금, 출금, 배당, 비용, 손절·목표 설정, 구분 변경), 계좌 select, 날짜 (max today; "(미국 기준)" for US), 종목 코드 (uppercase, datalist of coins for COIN), 구분, 수량, 가격/산 가격, 수수료, 금액, 손절가, 목표가, 메모 (500) | account / form panel | Fields shown per kind (`KIND_FIELDS`); changing 종류 or 계좌 redraws the form (keeps date); currency symbol follows account | none until submit | `KIND_FIELDS`, `ACCT_CUR`, `d.coins` | fields toggled with `hidden` | no | test_ui_batch_6.py `test_one_trade_form_in_the_unified_account` |
| AC-11 | HOLD kind ("이미 가지고 있는 종목 추가") | account / form | Default kind when opened from the account tab; hint text `ACCT_HOLD_HINT` ("...입금 기록이 없어도 되고 현금은 바뀌지 않습니다...") plus coin-price caveat; label "산 날짜", "산 가격" | POST `/api/journal/add` kind HOLD | journal | no | yes (journal.jsonl append) | test_account.py (HOLD), test_terminal_2.py |
| AC-12 | Per-kind hint line (`#accthint`) | account / form | Text under the button: coins -> "코인은 원화로 적습니다 ... 바이낸스 달러 가격에 환율을 곱한 값..."; others -> "실제로 체결된 내용만 적으세요. 이 화면은 주문을 내지 않습니다." | none | none | no | no | Browser |
| AC-13 | Ticker blur validation (`f.ticker.onblur`) | account / form | Auto-switches 계좌 select to the market implied by the code shape; warns (in `#acctmsg`): Korean name instead of code, 6-digit code on COIN, coin not in priced list, stock code that is also a coin name | none | `d.coins` | no | no | Browser: type 005930 with 계좌 미국 -> switches to 한국 |
| AC-14 | Submit "기록 추가" | account / form | Builds body from the fields of the kind; requires 구분 for BUY/HOLD of a not-yet-held ticker and for STYLE ("구분(장기 또는 스윙)을 선택하세요."); on success "기록했습니다. 다시 불러오는 중…" then re-render; on error `errKo` message | POST `/api/journal/add` | journal, held set | no | yes (journal append) | test_account.py, test_terminal_2.py |
| AC-15 | Prefill from other screens (`acctRecord(market, fill)`) | account / form | Called by portfolio's "통합 계좌에서 기록하기" (`#jgo`), assist "이 수량으로 매수 기록 작성", qsf no-account plan button; scrolls to the form panel and focuses ticker (or qty if filled) | none | `acctForm` | no | no | test_ui_batch_6.py (`acctRecord`) |
| AC-16 | 거래 기록 table (last N of M; "추가만 가능, 취소는 별도 기록으로 남습니다") | account / journal panel | Columns 날짜, 계좌, 종류, 종목, 수량, 가격, 금액, 메모 (with style/stop/target text, "(기록 X 취소)"); voided rows struck/grey with "· 취소됨" | `/api/account` (`journal`, `journal_count`) | journal | no | no | test_account.py |
| AC-17 | Row "취소" button | account / journal table | Click -> `confirm("이 기록을 취소합니다. 지우지 않고 '취소' 기록을 덧붙입니다.")`; on OK posts a VOID record and re-renders; error -> toast | POST `/api/journal/void` `{ref}` | journal | confirm() dialog | yes (VOID record appended) | test_account.py, test_kr_terminal.py (`journal_void`) |
| AC-18 | Footer notes panel + coin-price error line | account / bottom | `d.notes` lines; "코인 가격을 새로 받지 못했습니다(...)" | `/api/account` (`notes`, `coin_error`) | Binance | conditional | no | test_account.py, test_coin_source.py |
| AC-19 | Loading / error states | account | "loading" placeholder when empty; `errBox(e)` on failure | `/api/account` | network | no | no | Browser |

### 1.3 시장별 자세히 (tab `portfolio`, portfolio.js; follows market switch US/KR; WIDE)

| ID | Feature | Screen | Interaction | API / backend | Data dependency | Hidden/nested? | Writes data? | Suggested regression check |
|---|---|---|---|---|---|---|---|---|
| PF-01 | Journal-integrity notice (incl. line number, file path hint) | portfolio / top | Display | GET `/api/portfolio` (`integrity`) | journal.jsonl | conditional | no | test_terminal_2.py |
| PF-02 | "시작하기" empty-state panel | portfolio / top | Shown when journal empty: 1) 입금 기록 2) 매수·매도 기록 guidance | `/api/portfolio` | journal empty | conditional | no | Browser: fresh data dir |
| PF-03 | "주식 두 계좌 합계" panel (KRW: 한국 계좌, 미국 계좌 + $ amount, 원/달러 + date; coin excluded; notice if unknown) | portfolio / top | Display; mentions 위의 '내 계좌' | `/api/portfolio` (`total`) | fx, prices | no | no | test_terminal_2.py |
| PF-04 | 계좌 요약 panel (한국(원화)/미국(달러)) with STALE badge, missing-price notice, big equity (+ "≈ ₩" for US), KV: 총 손익, 오늘 손익, 미실현, 실현, 현금 (+%), 주식 평가액, 순입금, 배당 / 비용, 손절 시 손실 합계 (+% of account); unprotected-ticker line; source/fetched meta + FX | portfolio / summary | Display | `/api/portfolio` (`summary`, `fx`, `cache`) | journal, prices | no | no | test_terminal_2.py |
| PF-05 | 경고 list ("화면 표시만 하며 주문하지 않습니다") | portfolio / alerts panel | Display, class by level | `/api/portfolio` (`alerts`) | settings (near-stop %, sector limit, style drift) | conditional | no | test_portfolio_style.py, test_portfolio_interrupts.py |
| PF-06 | Holdings tables split 장기 / 스윙 / 구분 없음: header summary ("N개 · 평가액 · 주식 중 %(목표 %) · 미실현 %"), columns 종목, 비중, 점수, 판정, 손절가(거리), 목표가+남은 기간 (swing) or 다음 점검 (long), 미실현 손익 + %, 오늘, 수량, 평균단가, 현재가, 평가액, 섹터; 'live' badge, status badge; `미설정` for missing stop | portfolio / holdings panels | Row click -> stock tab (`tr.click[data-ticker]`) | `/api/portfolio` | journal, prices, sector map | no | no | test_portfolio_style.py, test_ui_batch_6.py |
| PF-07 | Empty holdings: "보유 종목이 없습니다." | portfolio / holdings | Display | `/api/portfolio` | none | conditional | no | Browser |
| PF-08 | 보유 판정 (`#sigpanel`) and per-row cells (score, action, left, review) filled asynchronously | portfolio / holdings + panel | Loading text "계산 중… (처음에는 공시를 읽느라 시간이 걸릴 수 있습니다)"; each row gets score, action chip (EXIT/THESIS_INVALIDATED = red; REDUCE/PARTIAL_TAKE_PROFIT/TIME_STOP_REVIEW = amber; HOLD), "N거래일 (date)" or "실적 date"/"분기 실적 공시 후"; "구분 필요" / "계산 불가"; below the list: alert list of non-HOLD reasons, server note, financing-filing note, "not in scan" note; error "판정을 계산하지 못했습니다" | GET `/api/portfolio/signals` | QSF scan ledger, filings | async; failure isolated | no | test_assistant.py (`portfolio_signals`), test_portfolio_style.py |
| PF-09 | 섹터 비중 bars (over-limit bar styled `over`) | portfolio / sector panel | Display; limit shown | `/api/portfolio` (`sectors`, `settings.max_sector_pct`) | sector map | conditional | no | test_portfolio_style.py |
| PF-10 | 위험 분석 panel (`#risk-panel`) | portfolio / risk panel | Loads async: 시장 베타, 연 변동성 (vs index), VaR 95% (+amount), ES 95%, 최악의 하루, 최악의 20거래일, 최대 낙폭, 실질 종목 수 + 평균 상관; per-holding table (비중, 위험 기여 bar, 변동성, 베타; row click -> stock); 종목 간 상관계수 matrix; short-history exclusions; explanation + source; reasons table `RISK_WHY` when not REAL; not drawn when no holdings | GET `/api/portfolio/risk` | 1y price history of holdings | async | no | test_portfolio_risk.py |
| PF-11 | 계좌 수익률 vs benchmark chart (`#eqc` canvas) + summary line "시작 <date> 이후 · 내 계좌(TWR) x% · <bench> y%" + method meta | portfolio / equity panel | Canvas redraw on theme/resize (`redrawOn("portfolio","equity")`); no hover; empty -> "거래 기록이 생기면 계좌 가치 곡선을 그립니다." | GET `/api/portfolio/equity` | journal, benchmark history | async | no | test_terminal_2.py (`.equity(`); Browser |
| PF-12 | 매매 성과 panel: KV (매도 건수, 승률, 평균 이익/손실, 손익비, 실현 손익 합계), small-sample note (<20), by-style table (장기/스윙), closed-trade table (last 50: 매도일, 종목, 구분, 수량, 평균단가, 매도가, 실현 손익, 수익률, 보유 일수) | portfolio / performance panel | Display; empty "아직 매도 기록이 없습니다." | `/api/portfolio` (`stats`, `stats_by_style`, `closed`) | journal | no | no | test_portfolio_style.py |
| PF-13 | "거래 기록 추가" panel -> button "통합 계좌에서 기록하기" (`#jgo`) | portfolio / form panel | Click -> `acctRecord(mk)` (account form with this market preselected) | none | none | no | no | test_ui_batch_6.py (`$("#jgo").onclick = () => acctRecord(mk)`) |
| PF-14 | 거래 기록 table with per-row "취소" | portfolio / journal panel | Click 취소 -> `confirm("이 기록을 취소할까요? 원래 기록은 남고, 취소 기록이 추가됩니다.")`; POST then re-render | POST `/api/journal/void` | journal | confirm() | yes | test_terminal_2.py (`api/journal/void`) |
| PF-15 | Footer note panel (`d.note`) | portfolio / bottom | Display | `/api/portfolio` | none | no | no | - |
| PF-16 | Loading/error and stale-market guard (`mk !== state.market`) | portfolio | Placeholder; `errBox` | `/api/portfolio` | network | no | no | Browser |

### 1.4 매매 보조 (tab `assist`, portfolio.js `renderAssist`; follows market)

| ID | Feature | Screen | Interaction | API / backend | Data dependency | Hidden/nested? | Writes data? | Suggested regression check |
|---|---|---|---|---|---|---|---|---|
| AS-01 | 포지션 크기 계산기 form (`#szform`): 종목 코드, 구분 (보유 구분 또는 공통 / 장기 / 스윙), 진입가 (blank = last close), 손절가 (blank = ATR suggestion by style), 계좌 금액 (blank = journal-based) , 계산 | assist / calculator | Ticker is prefilled from the open stock (`prefillTicker`), calculation only on button; wrong-market code -> red "위의 시장 스위치를 ... 바꾼 뒤 입력하세요."; "계산 중…" state | GET `/api/sizing?t&style&entry&stop&equity&market` | prices (ATR14), settings, journal equity/cash | no | no | test_terminal_2.py (`api/sizing`), test_ui_ticker_context.py (`szform`) |
| AS-02 | Calculator result: big "N주", style, entry, stop (source, −x%), KV (매수 금액, 계좌 대비 비중, 손절 시 손실 + %, 수량을 정한 한도 = RISK/WEIGHT/CASH), per-limit max shares line, context line (last close, ATR(14), stop suggestion, current held qty); no-result reason message | assist / calculator | Display | `/api/sizing` | same | no | no | test_terminal_2.py |
| AS-03 | "이 수량으로 매수 기록 작성" button (`#tojournal`) + "체결된 뒤에 기록하세요." | assist / calculator result | Shown when shares>0 and ticker given; click -> `acctRecord(market, {kind:BUY, ticker, style, qty, price, stop})` | none (navigates to account form) | result | conditional | no (prefill only) | test_ui_batch_6.py (`acctRecord(marketOf(d.ticker), {`) |
| AS-04 | Auto-fill from a score card (`state.sizeFill`) | assist / calculator | Coming from qsf card "크기 계산기에 넣기": fills code, style, swing stop, scrolls and auto-submits once | none | `state.sizeFill` | transient | no | test_ui_batch_6.py (`if (state.sizeFill)`) |
| AS-05 | 알림 센터 (`#alertc`, alerts.js): form (조건: 종가 이상/이하, 하루 등락폭, QSF 점수 구간이 바뀜 (+스윙/장기), 실적 발표가 다가옴; 종목 코드 blank = all held+watched; 값), "조건 추가", "지금 확인" button | assist / alert panel | Add -> "추가했습니다."; errors mapped by `AL_ERR`; rules table with 상태 (대기/발동), "다시 켜기", "삭제"; "지금 확인한 결과" preview (not sent/recorded, unchecked tickers note); "최근 보낸 알림" log (20) | POST `/api/alerts/add`, `/api/alerts/remove`, `/api/alerts/rearm`; GET `/api/alerts`, `/api/alerts/check` | `alert_rules`, scan ledger, prices | partly (preview section) | yes (alert rules file: add/remove/rearm; check is read-only) | test_alert_rules.py, test_terminal_4.py |
| AS-06 | 다가오는 실적 발표 (`#earncal`) | assist / earnings panel | 14-day list of "보유/관심/스윙·장기 매수 후보" tags, "오래된 일정" badge; ticker click -> stock; fold "그 밖의 스캔 종목 N개"; footer says dateless tickers are omitted; empty/unavailable message | GET `/api/qsf/earnings?market&days=14` | stored next-earnings dates | folded `<details>` | no | test_qsf_earnings_calendar.py |
| AS-07 | 위험 관리 설정 form (`#stform`, 17 fields: 장기/스윙 1회 위험 %, 최대 비중 %, ATR stop multiples, 장기 목표 비중, 목표 이탈 경고, 한국 장기/스윙 위험·비중, 한국 장기 목표 비중, 구분 없는 종목 위험/비중, 섹터당 최대, 손절 근접 경고) + 저장 | assist / settings panel | Submit -> "저장했습니다." or error; values feed calculator and warnings | GET/POST `/api/settings` | `settings.json` | no | yes (settings) | test_terminal_2.py (`api/settings`), test_phone_view.py |
| AS-08 | P6-11B 계획 대조 (`#plan`, US only; removed on KR) | assist / plan panel | Table: 순위, 종목 (click -> stock), 기준가 + bar date, 목표 비중, 목표 수량, 1차 진입 수량, 모델 손절가, 보유, 기간, "계산기" button (fills calculator and scrolls); badges FROZEN/STALE; UNAVAILABLE reason; disclaimer + 2nd-entry rule text | GET `/api/model/plan` | frozen model scan + account | no | no | test_terminal_2.py (`model/plan`) |
| AS-09 | Loading/error | assist | placeholders / `errBox` | `/api/settings` | network | no | no | Browser |

### 1.5 모의 매매 (tab `paper`, paper.js; follows market; always re-fetched)

| ID | Feature | Screen | Interaction | API / backend | Data dependency | Hidden/nested? | Writes data? | Suggested regression check |
|---|---|---|---|---|---|---|---|---|
| PT-01 | Title "모의 매매 기록" + badges "가상의 계좌" / "주문을 보내지 않습니다" + explainer lines (note, fee basis, pointer to qsf paper book) | paper / top panel | Display | GET `/api/paper-trade` | `paper_journal.jsonl` | no | no | test_paper_trade.py; test_ui_batch_6.py (`"모의 매매 기록" in paper.js`) |
| PT-02 | Integrity-problem state | paper / top | If status != REAL: only the notice with file path and no form | `/api/paper-trade` (`integrity`) | file | conditional | no | test_paper_trade.py |
| PT-03 | KV tiles: 평가액, 현금, 넣은 모의 자금, 총 손익 (+%), 끝난 거래 순손익, 낸 수수료·세금, 끝난 거래/이익 거래, 거래당 평균 순수익률 (each with title tooltip) | paper / top panel | Shown only when records exist | `/api/paper-trade` | prices | tooltips | no | test_paper_trade.py |
| PT-04 | Entry form (`#ptform`): 종류 (매수, 매도, 모의 자금 넣기, 모의 자금 빼기), 종목 코드, 수량, 가격, 금액, 수수료·세금 (blank = automatic Toss fees, title tooltip), 날짜 (max today; "(미국 기준)"), 메모 (200), "기록" | paper / form panel | Fields toggled per kind; first use: heading "시작하기: 모의 자금을 먼저 넣으세요" with DEPOSIT preset to `start_hint`; submit -> POST, resets prefill, switches market if ticker is of the other market, re-renders; error shown red in `#ptmsg` | POST `/api/paper-trade/add` | paper journal | no | yes (paper_journal append) | test_paper_trade.py |
| PT-05 | Live fee preview (`#ptpreview`) | paper / form | Debounced 250ms on ticker/qty/price/fee input: "거래 금액 ... · 수수료 X + 거래세 Y + SEC Z (자동) · 나가는 돈 / 들어오는 돈 ..." or "(직접 입력)"; helper text for DEPOSIT / missing qty-price | GET `/api/paper-trade/fee?market&side&qty&price` | Toss fee schedule | no | no | test_paper_trade.py (`paper-trade/fee`) |
| PT-06 | 보유 중 table (종목, 수량, 평균 매수가 with tooltip, 최근 종가 + date, 평가액, 평가 손익 + %, 팔 때 수수료·세금 (tooltip), 첫 매수일) + note on delayed quotes | paper / positions panel | Display; empty "보유 중인 모의 종목이 없습니다." | `/api/paper-trade` | prices | tooltips | no | test_paper_trade.py |
| PT-07 | "매도 기록" button per position | paper / positions table | Click -> prefill SELL with ticker, full qty, last close; re-render and scroll form to centre | none (then add) | `ptPrefill` | no | no (prefill only) | Browser |
| PT-08 | 끝난 거래 table (매도일, 종목, 수량, 매수가, 매도가, 산 금액, 판 금액, 수수료·세금 (tooltip split), 순손익, 순수익률, 보유) + totals line + small-sample caution (<20) | paper / closed panel | Display; empty "아직 매도까지 끝난 거래가 없습니다." | `/api/paper-trade` | journal | tooltips | no | test_paper_trade.py |
| PT-09 | 기록 N건 table (날짜, 종류, 종목, 수량, 가격/금액, 수수료·세금 + 자동/직접, 메모) with per-row "취소" and "취소됨" badge/dim | paper / journal panel | Click 취소 -> `confirm("이 기록을 취소할까요? 기록은 지워지지 않고 '취소됨'으로 남습니다.")`; POST `/api/paper-trade/void` then re-render; error -> toast | POST `/api/paper-trade/void` | paper journal | confirm() | yes (VOID appended) | test_paper_trade.py (`paper_void`) |
| PT-10 | Loading/error and stale-market guard | paper | placeholder / `errBox` | `/api/paper-trade` | network | no | no | Browser |

### 1.6 모델 (tab `model`, app.js `renderModel` + lab.js wrapper + `wireCapital`)

| ID | Feature | Screen | Interaction | API / backend | Data dependency | Hidden/nested? | Writes data? | Suggested regression check |
|---|---|---|---|---|---|---|---|---|
| MO-01 | Baseline model panel header (name, status badge FROZEN, role) | model / panel 1 | Display | GET `/api/model?market`, GET `/api/capital?market` | `model` record | no | no | test_terminal_1.py, test_kr_terminal.py |
| MO-02 | 투자 자본금 input (`#capInput`) + 저장 (`#capSave`) + note line (`#capNote`) | model / panel 1 | Typing previews amount/share columns client-side ("저장 전 미리보기입니다."), invalid -> "0보다 큰 숫자로 입력하세요."; 저장 posts amount (empty clears); messages for saved/not saved/invalid stored value; "금액과 주수만 환산했습니다..." when differing from scan capital | POST `/api/capital` `{market, amount}` | `capital.json` | no | yes (capital file) | test_terminal_capital.py, test_phone_view.py |
| MO-03 | KR "스캔 실행" button (`#capRun`, KR only) + status note (`#capRunNote`) | model / panel 1 | Requires saved amount (else message); POST starts KR model scan; polls every 10s showing running/DONE/FAILED text (time of start, "40분쯤", log path); on DONE re-renders the tab | POST/GET `/api/model/scan` | background job, capital | no | yes (starts job, writes scan records) | test_model_scan_button.py |
| MO-04 | "더 최근 스캔 ... 채점한 종목이 없었습니다" notice | model / panel 1 | Conditional | `/api/model` (`newer_empty_scan`) | scan run | conditional | no | test_stability_second.py |
| MO-05 | Last-scan KV (최근 전체 스캔, 기준 거래일, 결과 REC_KO, 시장 국면 REGIME_KO, 기준 자본) | model / panel 1 | Display | `/api/model` | latest run | no | no | test_terminal_1.py |
| MO-06 | 모델 상위 종목 table: 순위, 종목+name, 섹터, 기준가, 모델 알파 (US) or 모델 점수 (KR) (tooltip "수익률이 아닙니다"), 목표 비중, 목표 금액, 주수 (both recomputed from capital box), 손절가, 보유 기간; row click -> stock | model / panel 1 | Display; empty "추천 종목 없음" / "기록된 전체 스캔이 없습니다."; execution id footer | `/api/model` | latest run | tooltip | no | test_terminal_1.py, test_terminal_capital.py |
| MO-07 | 전향적 추적 panel (status badge; 기록된 실행, 관찰 건수, 집계 제외 (중복 스캔, tooltip), 최근 갱신, outcome-state counts via `outKo`; "표본이 충분히 쌓이기 전에는 성과를 판단할 수 없습니다.") or error | model / panel 2 | Display | `/api/model` (`tracking`) | tracking files | tooltip | no | test_terminal_1.py |
| MO-08 | 도전자 모델 비교 (전향적) table (`#cmp`; US only, replaces the "도전자 모델" placeholder panel) | model / panel 3 | Columns: 모델 (tooltip rule, FROZEN badge), 성격, 코호트, per horizon "N일 평균 초과수익 vs SPY" (cell tooltip: matured/independent/hit rate; "대기 N" or "—" when unmatured) , 최근 선정 종목 (first 10 tickers clickable, "외 N", 진입 date); notice about independent-sample minimum; method + panel_last + signal session | GET `/api/lab/compare` | challenger records | tooltips | no | test_terminal_3.py (`comparison(`) |
| MO-09 | "데이터 갱신 + 오늘 신호 기록" button (`#labrun`) + message (`#labmsg`) | model / panel 3 | Click -> background job; button disabled; polls every 3s "가격 받는 중… done/total"; DONE -> "<session> 신호 N개 모델 기록 완료 (진입 date)." or "이미 기록되어 있습니다."; FAILED -> red error; then re-renders comparison after 0.8s | POST `/api/lab/run`; GET `/api/lab/status` | price panel, recorded cohorts | no | yes (downloads prices, appends challenger records) | test_terminal_3.py, test_phone_view.py (`lab/run`) |
| MO-10 | Automation status line (`#autoline`) | model / panel 3 | Text: 자동 실행 켜짐 (한국 시간 hh:mm)/꺼짐, 서버 자동 재시작, 텔레그램 연결됨/미설정/설정 오류, last run time + session, missing sessions | GET `/api/automation/status` | launchd state, run log | no | no | test_automation.py (backend) |
| MO-11 | KR variant | model | KR skips challenger comparison (US only); shows capital + scan button | - | - | - | - | test_kr_terminal.py |

### 1.7 연구실 (tab `lab`, lab.js; groups 검증·기록)

| ID | Feature | Screen | Interaction | API / backend | Data dependency | Hidden/nested? | Writes data? | Suggested regression check |
|---|---|---|---|---|---|---|---|---|
| LB-01 | 전향 기록 현황 panel (`#recpanel`): model-version tech id; alert list (or "문제없이 기록이 쌓이고 있습니다.") | lab / top | Display | GET `/api/record` -> `record_status.build` | ledgers, automation | no | no | test_record_status.py |
| LB-02 | QSF 점수 기록 KV (미국/한국: 기록 거래일, 현재 버전, 마지막 기록) | lab / record | Display | `/api/record` | ledgers | no | no | test_record_status.py |
| LB-03 | 판단까지 남은 기간 table (지평: 스윙/장기 N거래일, 주 지평 highlight; 필요 거래일; 미국/한국 독립 표본 x / target (만기 n); 남은 기간 via `SPAN`) + explanatory meta | lab / record | Display | `/api/record` | progress | no | no | test_record_status.py |
| LB-04 | 기준 모델 기록 KV (자본금 입력됨/미입력, 결과 확정/기준, 대기, 유효 스캔 날짜, 마지막 유효 스캔) or error "추적 기록을 읽지 못했습니다" | lab / record | Display | `/api/record` (`baseline`) | tracking | no | no | test_record_status.py |
| LB-05 | 한국 결합 점수 기록 KV (기록 거래일, 마지막, 늦은 기록, 독립 표본 20일, 남은 기간, 시세 대조 KRX) + 재무 점수 기록 line + 공시 사건 기록 line | lab / record | Display | `/api/record` (`kr_forward`) | KR forward ledgers | no | no | test_record_status.py |
| LB-06 | 미국 도전자 점수 기록 KV (기록 거래일, 마지막, 늦은 기록, 스윙/장기 독립 표본) + disclaimer + "첫 기록 대상은 <date>입니다" | lab / record | Display | `/api/record` (`us_challenger`) | US challenger ledger | no | no | test_record_status.py |
| LB-07 | 시세 이력 점검 (`recAudit`): per market checked, flagged (+severe), reference scan, provisional last bars (US), issue kinds, common-wrong days, window note | lab / record | Display; "점검 결과 없음" when none | `/api/record` (`price_audit`) | price audit | no | no | test_price_audit.py |
| LB-08 | 자동 실행 KV (디스크 여유, 마지막 백업, 설치, 실행 시각, 마지막 실행, 기준 거래일) + step status line (완료/실패/건너뜀/자료 대기) + note | lab / record | Display | `/api/record` (`automation`, `disk`, `backup`) | launchd, run log | no | no | test_record_status.py, test_review_2026_11_17.py |
| LB-09 | 연구실 US-only gate: KR shows "연구실은 아직 미국 전용입니다. 위에서 미국을 선택하면 볼 수 있습니다." | lab / body | Display (the record panel above still shows) | none | market | no | no | Browser |
| LB-10 | 과거 시뮬레이션 panel (참고용 badge): limitations notice list, 거래 비용 segmented (`#costseg`, bps from server), log-scale NAV canvas (`#labc`) with legend, method + universe size + panel_last + 지수 편입일 적용 예/아니오 (red when 아니오) | lab / sim panel | Loading text "과거 시뮬레이션 계산 중… (처음에는 수십 초 걸릴 수 있습니다)"; click a bps button -> `labCost`, updates button state, table, chart; canvas redraw on resize/theme | GET `/api/lab/research` | cached price panel, membership file | no | no | test_terminal_3.py (`research(`) |
| LB-11 | 성과 지표 table (모델, 누적, 연환산, 변동성, 샤프, 최대 낙폭, 회전율; SPY row) + 연도별 SPY 대비 초과수익 table | lab / tables | Re-filled on cost change | `/api/lab/research` | same | no | no | test_terminal_3.py |
| LB-12 | 규칙 table (미리 고정, 튜닝하지 않음) | lab / bottom | Display | `/api/lab/research` | models_meta | no | no | test_terminal_3.py |
| LB-13 | Unavailable state: reason + "모델 탭의 '데이터 갱신' 버튼으로 가격 데이터를 먼저 받으세요." | lab / body | Display | `/api/lab/research` (`status != REAL`) | no panel | conditional | no | Browser: empty data dir |

### 1.8 차트분석 (tab `chart`, chart.js)

| ID | Feature | Screen | Interaction | API / backend | Data dependency | Hidden/nested? | Writes data? | Suggested regression check |
|---|---|---|---|---|---|---|---|---|
| CH-01 | Ticker form (`#cha-form`, input `#cha-q`, "보기") | chart / top panel | Type code, submit -> `chartWith(code)`; market inferred from code; remembered per market | GET `/api/chart/analysis` | localStorage `qse-chart` (ticker per market) | no | local storage | test_chart_analysis.py (`chartWith`), test_ui_batch_5.py (`qse-chart`) |
| CH-02 | Shortcut chips: market indices (US ^GSPC S&P 500, ^IXIC 나스닥 종합; KR ^KS11 코스피, ^KQ11 코스닥) + up to 6 recent tickers of the market; current one highlighted | chart / top panel | Click chip -> `chartWith` | same | `recentTickers()` (localStorage `qse-recent`) | no | local only | test_chart_analysis.py |
| CH-03 | Default ticker resolution (`chaTicker`): remembered -> open stock -> first recent -> index | chart | Implicit | - | state.ticker, recent | no | no | Browser |
| CH-04 | Range segmented: 3개월/6개월/1년/3년/5년/10년 | chart / controls | Click -> saves, re-renders, re-fetches | `/api/chart/analysis?range=` | `qse-chart` | no | local | test_ui_batch_5.py |
| CH-05 | Chart-type segmented: 캔들 / OHLC / 선 | chart / controls | Click -> redraw only; bars narrower than 2.2px fall back to line; bars without trustworthy open drawn as high-low line (grey) | none | `qse-chart` | no | local | test_chart_analysis.py |
| CH-06 | Checkboxes 볼린저밴드, 신호 표시 | chart / controls | Toggle -> redraw; band breaks hidden with the band | none | `qse-chart` | no | local | Browser |
| CH-07 | Moving-average checkboxes (`ma_choices` with colour swatch and "N일"), max `ma_max` (extra click reverted with toast "이동평균은 한 번에 N개까지 그립니다."), "기본(…)" reset button, "최대 N개" | chart / MA row | Toggle -> saved per market, re-fetch; 기본 deletes the market's choice | `/api/chart/analysis?ma=` | server settings, `qse-chart` | no | local | test_chart_analysis.py |
| CH-08 | Four-pane canvas stack: price (candles/OHLC/line, MA lines, Bollinger band fill + dashed lines, up/down signal triangles), 거래량 (+ N-day average line, spike dots), RSI (Wilder, band shading, reference lines, markers), MACD (line, signal, histogram, markers); pane captions include settings ("RSI(14, 와일더 방식) · 기준선 30/70", "MACD(12, 26, 9)...") ; date axis; nice-tick price axis | chart / stack | Canvas redraw on theme/resize (`redrawOn("chart","main")`); phone uses shorter heights (300/70/80/90) | `/api/chart/analysis` | Yahoo daily bars, `chart_analysis.py` | no | no | test_chart_analysis.py |
| CH-09 | Crosshair + tooltip (`#cha-x`, `#tip`) | chart / stack | Pointer move/down (mouse or finger drag; `touch-action: pan-y`) shows vertical line and tooltip: date, OHLC, volume (x of 20-day avg), MA values, Bollinger range, RSI, MACD/signal, signals of that day; hides outside plot | none | `cha.data` | transient | no | Browser: hover and touch-drag at 390px |
| CH-10 | Legend line (MA colours, band, volume avg, RSI/MACD, signal glyph legend "모두 검증 안 됨") | chart / below stack | Display | none | settings | no | no | - |
| CH-11 | Meta line (source, fetched time, status badge, live badge, date range; "가격 기록이 고른 기간보다 짧아 ..." ) | chart / panel | Display | `/api/chart/analysis` | cache | no | no | test_chart_analysis.py |
| CH-12 | UNAVAILABLE state: "가격 자료를 받지 못했습니다. 종목 코드를 확인하세요." (clears lines and signals); fetch error in red | chart | Display | same | network | conditional | no | Browser: enter bogus code |
| CH-13 | "지금 상태" panel: caveat notice (`settings.caveat`) + one paragraph per indicator line (name + text) + "마지막 일봉(...) 기준 ... 골든·데드크로스는 N일선과 M일선" | chart / panel 2 | Display | same (`lines`) | analysis | no | no | test_chart_analysis.py |
| CH-14 | "최근 신호" table: date, ▲/▼/● label (tooltip = meaning), close; latest 20 + `<details>` "나머지 N건 보기"; `<details open>` "신호의 관습적인 뜻"; footer disclaimer (no outcome stats, never feeds score); count "이 기간 N건"; empty "이 기간에 고전 신호가 없었습니다." | chart / panel 3 | Folds | same (`signals`) | analysis | folded | no | test_chart_analysis.py |
| CH-15 | Entry points from other screens: stock tab "차트분석" button, command palette | chart | `chartWith(t)` clears `state.loaded.chart` and shows tab | none | - | no | local | test_chart_analysis.py |
| CH-16 | Stale-response guard (ticker/range/MA/market changed while loading) | chart | Implicit | - | - | no | no | - |

### 1.9 비교 (tab `compare`, compare.js)

| ID | Feature | Screen | Interaction | API / backend | Data dependency | Hidden/nested? | Writes data? | Suggested regression check |
|---|---|---|---|---|---|---|---|---|
| CP-01 | Range segmented 3개월/1년/5년 | compare / top | Click -> re-render and re-fetch | GET `/api/compare?t=a,b,c&range=` | - | no | no | Browser |
| CP-02 | Selected chips (colour swatch + name + × remove) | compare / top | × removes (colour slot kept for others); at most 8; empty "아직 없습니다." | none | localStorage `qse-compare` | no | local | test_ui_batch_6.py (compare), test_chart_analysis.py |
| CP-03 | Add form (`#cmp-add`, "종목 코드 추가 (예: NVDA, 005930)", 추가) + index chips (S&P 500, 나스닥 종합, 코스피, 코스닥) | compare / top | Add -> dedupe, max 8 else toast "비교는 최대 8개까지입니다."; US and KR may be mixed | none | `qse-compare` | no | local | Browser |
| CP-04 | Defaults (first visit): SPY or ^KS11 plus recent tickers of the market (up to 3) | compare | Implicit | - | `qse-recent` | no | no | Browser |
| CP-05 | Overlay return chart (0% start, dividend-inclusive), direct end labels when <=4 series (nudged apart, kept inside bounds), 5 horizontal ticks, zero line; legend with total return; hover tooltip sorted by value | compare / chart panel | Mouse hover tooltip (mouse only: `onmousemove`, no touch handler); redraw on theme/resize | `/api/compare` | Yahoo history | no | no | test_ui_batch_6.py `test_compare_labels_stay_inside_and_the_range_axis_has_five_ticks` |
| CP-06 | Meta line (source, fetched, date range, basis, "미국과 한국을 섞으면 두 시장이 모두 연 날만 남습니다.", "가격 없음: ...") / UNAVAILABLE | compare / chart panel | Display | `/api/compare` (`missing`, `mixed_markets`) | - | conditional | no | test_chart_analysis.py (`compare(`) |
| CP-07 | 기간 성과 table (기간 수익률, 연환산 only if >= 0.9y, 연 변동성, 최대 낙폭; stock rows clickable -> stock tab, index rows not) | compare / stats panel | Row click | `/api/compare` | - | no | no | Browser |
| CP-08 | 일간 수익률 상관계수 matrix (needs >= 2) | compare / corr panel | Display; empty text | `/api/compare` (`correlation`) | - | no | no | Browser |
| CP-09 | 상관계수의 변화 rolling-correlation chart vs first item (window from server) + legend "마지막 x" + hover tooltip + explanation; hidden canvas + empty text when < 2 items or short period | compare / roll panel | Mouse hover | `/api/compare` (`rolling`, `rolling_window`) | - | conditional | no | Browser |
| CP-10 | Entry point `compareWith(list)` from other screens | compare | Adds tickers then shows the tab | none | `qse-compare` | no | local | test_maturity_fixes_2026_11_22.py (grep compare.js) |

### 1.10 시장 지도 (tab `map`, map.js) with rotation.js and sectorpicks.js rendered into the same tab

| ID | Feature | Screen | Interaction | API / backend | Data dependency | Hidden/nested? | Writes data? | Suggested regression check |
|---|---|---|---|---|---|---|---|---|
| MP-01 | Heatmap mode segmented: 1일 / 5일 / 1개월 / QSF 점수 | map / heatmap panel | Click -> redraw; saved in `qse-heat-view`; colour scale full at ±3% / ±8% / ±15% | none (data loaded) | localStorage | no | local | test_ui_batch_5.py (`qse-heat-view`) |
| MP-02 | Score-style segmented: 스윙 점수 / 장기 점수 | map / heatmap panel | Click -> re-fetch `strategy=`; dimmed (`.idle`, tooltip "등락 보기에서는 쓰지 않습니다...") in change modes | GET `/api/qsf/heatmap?strategy=&market=` | stored scan | tooltip | local | test_ui_batch_6.py `test_heatmap_colour_choice_and_idle_toggle` |
| MP-03 | Palette segmented: 기본 색 / 파랑·주황 (colour-blind safe pair, light and dark values), dimmed in 점수 mode; tooltip | map / heatmap panel | Click -> redraw; saved | none | localStorage | tooltip | local | test_ui_batch_6.py |
| MP-04 | Treemap canvas: sector groups with Korean sector names, tile size = market cap, colour = change or score (grey = no value; score scale 40 -> 80), tile label (KR name, US ticker) + value shown by size; phone height 520 / 620 desktop | map / heatmap panel | Hover tooltip (name, ticker, sector, market cap, 1일/5일/1개월, style score + band); click tile -> stock tab; pointer cursor | `/api/qsf/heatmap` | scan market caps, price changes | no | no | test_qsf_heatmap.py; Browser |
| MP-05 | Legend line (size = market cap; colour meaning and span) | map / heatmap panel | Display | none | mode | no | no | - |
| MP-06 | Meta line (source, scan session, model version, basis, "시가총액 없음: ...") / "UNAVAILABLE 스캔 결과가 없습니다." / error box | map / heatmap panel | Display | `/api/qsf/heatmap` | scan | conditional | no | test_qsf_heatmap.py |
| RO-01 | 업종 순환 그래프 (RRG approximation) canvas: 4 quadrants (선도/약화/침체/개선) tinted, axes labels "상대강도 비율 →" / "모멘텀 →", 8-week tail per sector ETF, head dot coloured by quadrant, names beside dots with overlap avoidance; legend + path explanation | map / `#map-more` panel 1 | Hover head dot -> tooltip (name, symbol, quadrant, ratio, momentum, 4w/13w vs index); click head -> `loadSectorPicks` | GET `/api/rotation?market=` | sector ETF prices (US sector funds; KR 16 rotation funds) | no | no | test_sector_picks.py, test_terminal_1.py (rotation) |
| RO-02 | Rotation meta (source, fetched, benchmark, last week, method, missing) / UNAVAILABLE / error | map / panel 1 | Display | `/api/rotation` | - | conditional | no | test_terminal_1.py |
| RO-03 | 업종 상대 성과 table sorted by quadrant then ratio: 업종, 국면 (coloured dot), 상대강도 비율, 모멘텀, 지수 대비 4주/13주; row click -> sector picks; selected row highlighted (`me`); disclaimer "QSF 점수에 쓰이지 않으며, 검증된 매매 신호가 아닙니다." | map / panel 2 | Click row | `/api/rotation` | - | no | no | test_sector_picks.py |
| SP-01 | 업종 점수 상위 종목 panel (`#rrg-picks`, initially hidden) | map / panel 3 | Appears and scrolls into view on selection; two columns 스윙 / 장기 "점수 상위 3": rank, name + ticker (+ industry on KR), score, band badge, gate badges, "고위험 표시"; header text "ETF 보유 N종목 중 스캔 대상 M개" or "업종 N개 중 · 매수 후보 K개"; rule/basis footer; empty "점수가 있는 종목이 없습니다."; UNAVAILABLE reason | GET `/api/qsf/sector-picks?fund=&market=` | scan + KR ETF holdings (`kr_etf_holdings`) | hidden until chosen | no | test_sector_picks.py, test_kr_etf_holdings.py |
| SP-02 | Pick plan (`#sp-plan`): click a pick -> highlights it and loads a plan with two cards (스윙/장기): score, label, band, confidence, price date; risk-gate notice; 매수 시기 (entry status, reason, entry date, zone), 매도 시기 (swing: target/stop, expected sessions, exit date, time-stop review; long: months, review dates, invalidation list), 계획상 수익률 table (swing: 목표가까지, 손절가까지, 손익비; long: scenarios "1년 뒤") with disclaimer, button "종목 화면에서 자세히" | map / panel 3 | Click pick; button -> stock tab | GET `/api/qsf/evaluate?t=&market=` (via `qsfEval` in qsf.js) | live re-evaluation (may take seconds for unscanned names) | nested | no | test_sector_picks.py, test_assessment_fixes_2026_11_23.py |
| MP-07 | Stale-market / stale-selection guards, `redrawOn("map","heat"/"rrg")` | map | Implicit | - | - | no | no | - |

### 1.11 코인 (tab `coin`, coin.js; market COIN only; ALWAYS_FRESH)

| ID | Feature | Screen | Interaction | API / backend | Data dependency | Hidden/nested? | Writes data? | Suggested regression check |
|---|---|---|---|---|---|---|---|---|
| CO-01 | Tab/group visibility: group "코인" and bottom-bar "코인" shown only in market COIN; market switch "코인" button | coin | Implicit | none | `state.market` | conditional | no | test_ui_groups.py |
| CO-02 | Caveat fold (`details.notice.qsf-caveat`, summary "대상 코인끼리의 순위입니다. 오를지 내릴지를 말하지 않습니다." + "자세히") | coin / top | Click to expand caveat list | GET `/api/coin/latest` (`caveats`) | `coin_bridge.read` | folded | no | test_coin_bridge.py |
| CO-03 | Mode notice for SIMPLE rank ("등록된 점수가 아닌 간이 순위입니다. ...") and title switch 코인 상대 순위 / 코인 간이 순위 | coin / panel 1 | Display | `/api/coin/latest` (`mode`, `mode_note`) | registered score file present or not (not read here) | conditional | no | test_coin_bridge.py, test_coin_source.py |
| CO-04 | Status badge + "<time> 마감 · 4시간봉" badge + stale warning (SIMPLE: hours old, fetch error; registered: "예측기가 멈췄거나 맥이 잠들어 있었습니다") | coin / panel 1 | Display | `/api/coin/latest` | `age_hours`, `fetch_error` | conditional | no | test_coin_bridge.py |
| CO-05 | UNAVAILABLE state (reason, source) | coin | Display | `/api/coin/latest` | - | conditional | no | test_coin_bridge.py |
| CO-06 | Ranking table: 순위, 코인 (+name, "1,000개 단위"), 기대 상대 폭 (+ "비용 넘음" badge) or 간이 점수, 가격(USDT), 1일/7일/30일, 자금조달비 (+ "낮은 순 p/n"), 변동성, 베타 (headers with tooltips) | coin / panel 1 | Row click -> `askAssistant("<coin> 분석해 줘")` (lands on Today); Enter/Space also works (keyable) | `/api/coin/latest` | Binance public data / registered score | tooltips | no | test_coin_bridge.py |
| CO-07 | "how" explainer + footer (source, version or "등록된 점수 아님") | coin / panel 1 | Display | same | - | no | no | - |
| CO-08 | 코인 시장 panel (참고 badge): 비트코인 price, 7일, 30일, 200일 평균 대비, 1년 고점 대비, 7일 동안 내린 코인 n/N, 200일 평균 위 n/N, 평균 자금조달비 + note | coin / panel 2 | Display | same (`market`) | - | no | no | test_coin_source.py |

---------------------------------------------------------------------------

## 2. Per-screen blocks (components, layout, weaknesses)

### 오늘 (today)
- Components: 2 panels. Panel 1 = title + question form + `#asst-out`. Panel 2 = `#asst-brief`: h2 headline, meta, `.grid.asst-tiles` of `.card` tiles + one state tile, candidates (`.asst-cands` 2-column grid of tables), grouped `.asst-list` of `.asst-item`, `.asst-ops` fold.
- Desktop: single column at 1280px max; tiles auto-fill grid (min 190px); candidates side by side; items full-width with 4px severity stripe. Phone (<=640): tiles 2 columns without sparklines, candidates stack to one column with band/sector columns hidden, bottom bar navigation; question form wraps (input flex 260px).
- Weaknesses:
  1. The question box and its answer sit above the daily list, so a long answer pushes the day's must-do items far down; no way to dismiss/collapse the answer card.
  2. The brief mixes five kinds of things in one scroll (headline, numeric tiles, candidates, action list, ops fold) with similar visual weight; only the stripe colour distinguishes ACT/DUE/INFO and there is no summary of counts at the top (counts exist in the data but only appear as small badges).
  3. The 22 fixed questions are discoverable only through the "물어볼 수 있는 것" button or the empty-state placeholder; there is no persistent shortcut row, and the "사도 돼?" answer is rendered with the same generic card as every other answer, so the ○/✕ checklist is plain bullets with glyphs, not a scannable table.
  4. Candidate tables are dense (5 columns, +/- factor text) and the phone version drops the sector and band columns silently; score delta colouring only when >=1 point is a subtle rule with no legend.
  5. Item text is a flat sentence with the first sentence as title and the rest hidden in a `<details>`: no icon/type tag per item kind, so 30+ different kinds look identical.
  6. Refresh-on-return dims the whole panel to 55% opacity, which also dims the tiles and candidates for several seconds; loading and refreshing states differ from every other tab.

### 통합 계좌 (account)
- Components: 5 panels (summary with unit toggle + KV + account table; holdings; trade form; journal; notes), integrity notice.
- Desktop: single column, narrow (not WIDE) although the holdings table has 12 columns (horizontal scroll inside `.tbl-wrap`). Form is auto-fill grid (min 140px). Phone: tables scroll sideways with sticky first column; form becomes 1-2 columns.
- Weaknesses:
  1. The trade form (9 kinds, up to 12 fields) sits below two large tables, so recording a trade requires scrolling past the holdings and the form redraws completely when 종류/계좌 changes (fields hide/show via `hidden`, no grouping).
  2. The 12-column holdings table in a narrow container forces sideways scrolling on desktop and phone; numeric columns repeat own-currency and converted values side by side.
  3. Currency handling is split: per-account rows in native currency, a global 원화/달러 toggle for totals, and the form uses another symbol; there is no single indicator of which currency a number is in apart from the symbol.
  4. Journal table has an unlabelled, always-visible "취소" button per row with a browser `confirm()`; destructive-ish action next to data with no undo affordance in UI.
  5. Warnings (missing prices, missing FX, integrity) are plain `.notice` blocks stacked above the figure, and the hint text under the submit button is a long grey sentence the user must read to understand HOLD semantics.
  6. Colour convention is forced to international red/green on this tab even in KR market (`INTL_COLOR_TABS`), differing from every other KR screen.

### 시장별 자세히 (portfolio)
- Components: up to 10 panels: notice, start-guide, two-account total, summary + KV, alerts, three holdings tables, 보유 판정, sector bars, risk analysis, equity chart, performance, form pointer, journal, note. WIDE tab.
- Desktop: vertical stack of full-width panels; holdings tables have 13-14 columns. Phone: horizontal scroll tables.
- Weaknesses:
  1. Very long vertical page: 10+ panels with no in-page navigation or folding; important actions (판정 per holding) are 4 panels below the holdings that they describe, and the 판정 results are patched into holding rows asynchronously (cells jump from "—" to values).
  2. The tab duplicates the account summary shown in 통합 계좌 (totals, journal) and carries its own journal table and a button that merely forwards to the account form.
  3. Holding rows hold 13+ columns, including both 판정 and 다음 점검/남은 기간 whose column set differs between 장기 and 스윙 tables, so tables are not aligned with each other.
  4. Market-dependent currency/format via `isKR()` inside shared helpers (`money`), while the account tab uses a different formatter (`acctCur`), a consistency risk.
  5. Equity chart has no hover/crosshair and no legend beyond two text labels drawn on the canvas.
  6. Loading states are uneven: risk panel says "불러오는 중…", signals "계산 중…", equity "불러오는 중…"; no skeletons.

### 매매 보조 (assist)
- Components: calculator form + result, alert center (form, rules table, preview, log), earnings calendar, 17-field settings form, P6-11B plan table (US).
- Desktop: single narrow column; forms use auto-fill grid. Phone: same, forms 1-2 columns.
- Weaknesses:
  1. Four unrelated tools (sizing, alerts, earnings calendar, risk settings, model plan) share one tab with no sub-navigation; the calculator is first but the settings that drive it are four panels down.
  2. The settings form is 17 undifferentiated number inputs (US/KR/long/swing mixed), labels are long Korean phrases, and a single "저장" button with a grey explanation underneath.
  3. The calculator result is a mix of big number, kv and a dense limits sentence; the binding limit (the key insight) is one of four kv cells.
  4. The alert center is a full feature embedded in a tab named "매매 보조", with its own mini-nav (add/check/log) and a floated "지금 확인" button using inline `style="float:right"`.
  5. Table of the plan (P6-11B) has 10 columns and a small "계산기" button that scrolls the page up; the relationship to the calculator is only implied.
  6. Calculator is US/KR-market-bound (wrong-market code error), requiring the user to switch the market switch first.

### 모의 매매 (paper)
- Components: header panel with KV tiles, entry form + live fee preview, positions, closed trades, journal.
- Desktop: narrow single column. Phone: scroll tables.
- Weaknesses:
  1. "가상의 계좌" is indicated only by two small badges; layout and wording nearly mirror the real account, risking confusion between real and paper books.
  2. Form fields toggle per kind like the account form, and the fee preview is a plain text line that reflows as the user types.
  3. Two tables (positions and closed) and the journal repeat the same columns with different scales; the "매도 기록" button redraws the whole tab and scrolls (state restored only via `ptPrefill`).
  4. Native `confirm()` for cancel, same as account.
  5. KPIs show 8 tiles with long labels; no emphasis on the one number (총 손익).

### 모델 (model)
- Components: baseline panel (capital form, scan button, KV, top-5 table), tracking panel, challenger comparison panel (US).
- Desktop: WIDE, stacked. Phone: scrolling tables.
- Weaknesses:
  1. The first panel mixes configuration (capital input + save + scan button + two note lines) with results (KV, ranking), so the primary content starts after a form.
  2. The challenger comparison table puts value and verdict in one cell with a `<br>` and information in a tooltip only (matured count, independent samples, hit rate) -> invisible on touch.
  3. Capital note, run note and automation line are three separate grey text areas whose states (saved/preview/running) are easy to miss.
  4. Model lives in a different JS file (app.js base + lab.js override that mutates DOM by finding an h2 with the text "도전자 모델"), a structural fragility for any redesign.
  5. KR and US share a tab but differ greatly (KR has a scan button and no challengers).

### 연구실 (lab)
- Components: record panel (many KV groups, tables) and simulation panels (chart, cost segmented, tables).
- Desktop: WIDE stack. Phone: scroll.
- Weaknesses:
  1. The "전향 기록 현황" panel is a very long vertical sequence of h3 + KV + meta paragraphs (9 subsections) with no folding; numbers like "독립 표본 x / target" repeat in different forms.
  2. KR shows an empty-state for the simulation but the record panel still loads, so the screen looks half empty with an apologetic message.
  3. The simulation chart is a log-scale NAV with y labels in % and a legend; there is no hover/tooltip and no per-series toggle.
  4. Terminology-heavy (독립 표본, TWR-like, 회전율) with no inline help beyond meta sentences.
  5. Loading message ("몇십 초") is a plain empty panel; no progress.

### 차트분석 (chart)
- Components: control panel (form, chips, range/type segmented, MA checkboxes, four canvases, legend, meta), 지금 상태 panel, 최근 신호 panel.
- Desktop: narrow column; canvases 400/90/100/110 px. Phone: 300/70/80/90 px, finger crosshair.
- Weaknesses:
  1. Controls are spread in three rows (form+chips, range/type/toggles, MA row) before the chart, pushing the chart down on phone.
  2. The four stacked canvases are separate elements with captions; crosshair line is a DOM overlay, tooltip is a global floating `#tip` that can cover the data.
  3. Chip row mixes index shortcuts and recent tickers with no separator; names for KR codes depend on a lookup table (`CMP_INDEX`) that only covers indices.
  4. The "지금 상태" text lines and signal tables are long prose; reading the current state requires scanning paragraphs.
  5. State is spread over `localStorage` keys (range, type, MA per market, ticker per market, toggles) with no visible "reset".

### 비교 (compare)
- Components: controls panel (range, chips, add form, chart), stats panel, correlation matrix, rolling correlation chart.
- Desktop: narrow column; chart 380 px (phone 280). Phone: tables scroll.
- Weaknesses:
  1. Hover tooltips only on mouse events (`onmousemove`); on touch there is no way to read values at a date.
  2. Colour slots (8) are assigned per ticker and persisted nowhere; direct end labels disappear above 4 series, leaving legend-only identification.
  3. Add form and index chips duplicate chart.js's chip row; entry via text only (no search/autocomplete of names, KR names need codes).
  4. Rolling-correlation panel is conditional and shows an empty text when conditions are not met.
  5. 4 panels with identical styling; the stats table is the most useful output but sits under the chart.

### 시장 지도 (map) + 업종 순환 (rotation) + 업종 상위 종목 (sectorpicks)
- Components: heatmap panel (three segmented controls, canvas, legend, meta), `#map-more` host: RRG panel, relative-performance table panel, hidden picks panel with plan cards.
- Desktop: stacked panels; heatmap 620 px tall; RRG at most 560 px square. Phone: heatmap 520, RRG square at full width, `.sp-cols` stacked.
- Weaknesses:
  1. Three segmented controls in the panel `h2` row (mode, score style, palette) wrap awkwardly on narrow widths and their dependencies (style idle in change mode, palette idle in score mode) are expressed only as 50% opacity.
  2. The heatmap is canvas-only (no DOM): no keyboard access, no screen-reader text, labels truncated by tile width; tile click is the only drill-down, and touch devices have no hover tooltip.
  3. The RRG and treemap are on one tab with unrelated data sources (scan vs sector ETFs) and the RRG selection result appears three panels down with auto-scroll (`scrollIntoView`), which can disorient.
  4. The picks panel nests another fully-fledged score card (with entry/exit, scenario tables) inside a map tab, replicating the 순위·카드 card in a different layout.
  5. Quadrant names and colours are drawn on canvas using palette variables `--s1/--s3/--s4/--s8` that are not colour-blind aware (unlike the heatmap palette option).
  6. Header text wording differs: 시장 지도 vs 시장 히트맵 vs 업종 순환 그래프.

### 코인 (coin)
- Components: panel 1 (title, badges, mode notice, caveat fold, stale warning, explainer, table, source), panel 2 (market KV).
- Desktop: WIDE; table 10 columns. Phone: table scrolls; header badges wrap.
- Weaknesses:
  1. The ranking table has 10 columns of small numerics with tooltips on header cells only (invisible on touch); rank of funding/vol/beta shown as a second small line.
  2. Two mode variants (registered vs simple) change column heading, formatting, notices and footer text, making the screen's meaning shift under the same title.
  3. Caveat fold is closed by default and carries the most important epistemic message (ranking, not direction).
  4. The only interaction (row -> ask the assistant) leaves the tab and lands on Today, with no in-place detail view; users must discover that rows are clickable from one grey sentence.
  5. No chart/sparkline; prices shown in USDT while the account page converts to won, so currency context differs between screens.

---------------------------------------------------------------------------

## 3. `/api/` routes used by these files (cross-checked against `terminal/server.py` route dict)

| Method + path | Used by | In server.py? |
|---|---|---|
| POST `/api/assistant/ask` | assistant.js (TD-02..) | yes (line 235) |
| GET `/api/assistant/today?market=` | assistant.js | yes (234) |
| GET `/api/account` | account.js | yes (182) |
| POST `/api/journal/add` | account.js | yes (176) |
| POST `/api/journal/void` | account.js, portfolio.js | yes (181) |
| GET `/api/portfolio` | portfolio.js | yes (172) |
| GET `/api/portfolio/equity` | portfolio.js | yes (173) |
| GET `/api/portfolio/risk` | portfolio.js | yes (174) |
| GET `/api/portfolio/signals` | portfolio.js | yes (175) |
| GET `/api/sizing` | portfolio.js (calculator) | yes (189) |
| GET `/api/settings`, POST `/api/settings` | portfolio.js (assist) | yes (187, 188) |
| GET `/api/model/plan` | portfolio.js (assist) | yes (198) |
| GET `/api/qsf/earnings` | portfolio.js (assist) | yes (202) |
| GET `/api/alerts`, GET `/api/alerts/check`, POST `/api/alerts/add`, POST `/api/alerts/remove`, POST `/api/alerts/rearm` | alerts.js (rendered in assist) | yes (165-169) |
| GET `/api/paper-trade`, GET `/api/paper-trade/fee`, POST `/api/paper-trade/add`, POST `/api/paper-trade/void` | paper.js | yes (177-180) |
| GET `/api/model` | app.js `renderModel` | yes (171) |
| GET `/api/capital`, POST `/api/capital` | app.js `renderModel`/`wireCapital` | yes (183, 184) |
| GET `/api/model/scan`, POST `/api/model/scan` | app.js `wireCapital` (KR scan button) | yes (185, 186) |
| GET `/api/lab/compare` | lab.js | yes (237) |
| POST `/api/lab/run`, GET `/api/lab/status` | lab.js | yes (239, 199) |
| GET `/api/lab/research` | lab.js | yes (238) |
| GET `/api/automation/status` | lab.js (`automationLine`) | yes (200) |
| GET `/api/record` | lab.js | yes (232) |
| GET `/api/chart/analysis` | chart.js | yes (157) |
| GET `/api/compare` | compare.js | yes (156) |
| GET `/api/qsf/heatmap` | map.js | yes (231) |
| GET `/api/rotation` | rotation.js | yes (158) |
| GET `/api/qsf/sector-picks` | sectorpicks.js | yes (230) |
| GET `/api/qsf/evaluate` | sectorpicks.js via `qsfEval` (qsf.js) | yes (201) |
| GET `/api/coin/latest` | coin.js | yes (236) |

Routes in server.py that none of these files call: `/api/chart` (stock tab), `/api/today`, `/api/watchlist*`, `/api/qsf/*` other than above, `/api/committee/*`, `/api/phone/*`, etc. (belong to other agents' screens). All routes used by these files exist in the server dict; no dangling client route found.

---------------------------------------------------------------------------

## 4. Could not determine / caveats
- The "사도 돼?" 사도 됨 / 기다림 / 사지 않음 verdict described in the memory index (buy-check-verdict) is not present in the repository code or tests: `assistant.py` BUY_CHECK still emits a ○/✕/– checklist with the sentence "이 점검표는 살지 말지에 대한 답이 아닙니다". Either the change is unmerged or the memory entry is out of date. The redesign should be based on the checklist as it exists.
- Server-side answer shapes for the 22 fixed questions were enumerated from `STOCK_INTENTS`/`PLAIN_INTENTS`; the full text of each answer's sections was not read exhaustively (only BUY_CHECK).
- I did not run the app or take screenshots: layout descriptions (desktop vs phone) come from CSS/JS, not from a rendered page; no real-phone check was possible.
- Test pins named above were found by grepping function names/strings; many are source-text assertions and do not prove behaviour. Where grep found nothing (e.g. `renderPortfolio`, `loadSignals`, `renderLab`, `renderCompare`, `cmpAdd`, `heat` drawing, `coin-row`), a browser step is given instead.
- `alerts.js` is outside the nominal scope but renders inside the assist tab, so it was included (AS-05); `calendar.js` and `peers.js` were not inspected (other screens).
