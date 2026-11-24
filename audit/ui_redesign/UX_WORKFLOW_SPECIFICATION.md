# UX and investment workflow specification (workstation redesign)

Written 2026-11-24 by Agent 4 (UX and investment workflow designer). Read-only pass on baseline `7c8e0af`. No code was changed and nothing was clicked in a browser.

Inputs:
- the shared design brief and its binding owner decisions 1–6;
- `audit/ui_redesign/EXISTING_UI_FEATURE_INVENTORY.md` (feature IDs used below: S-, CM-, CO-, ST-, QR-, QC-, QS-, QE-, QT-, IC-, TD-, AC-, PF-, AS-, AL-, …);
- `reports/ui_ux_assessment_2026_11_23/UX_WORKFLOW_ASSESSMENT.md` and `UI_UX_REMEDIATION_ROADMAP.md`;
- the code in `terminal/static/`: `app.js` (show, fromHash, tabHash, findSymbol, symbolSuggest, openTicker, markKeyable), `qsf.js`, `assistant.js`, `command.js`, `collect.js`, `account.js`, `portfolio.js`, `committee.js`, plus `terminal/automation.py` (`status()`) and `terminal/phone_view.py` (`PHONE_WRITES`).

**What this document decides and what it leaves to others**
- It specifies **flows**: which region shows what, in what order, what a click does, where focus goes, what the URL becomes, and the states (loading, empty, error, stale).
- **Geometry** (widths, heights, tokens, colours) belongs to `WORKSTATION_LAYOUT_SPECIFICATION.md` and the design-system spec. Where a number appears here, it is only what the flow needs. If the two documents disagree, the layout spec wins on geometry and this one wins on behaviour.
- **Owner decisions** are marked **[O-n]** and collected in section 13. Everything else is a display or flow change. None of it changes a score, band, gate, rule, stored value or server computation.

**Measurement caveat**
- Click counts come from following the event handlers in the code. They were not measured in a browser.
- Counting rules:
  - a click, tap, or Enter/Space on a focused control counts 1;
  - typing a code and pressing Enter is written "T⏎" and not counted as a click;
  - ⌘K counts as 1;
  - scrolling is noted separately.

---

## 0. Vocabulary used in every workflow

### 0.1 Regions

| Code | Region | Hosts (existing elements) |
|---|---|---|
| **T** | Top bar (sticky, one line) | Left to right: `≡` menu button (≤1023 px only) · brand `.brand` · market switch `#market` · search `#search`/`#q` (+ `#qsug`) · **MS chip** (market state, new host of existing data) · **DT chip** (data time, new host of existing data) · actions: `#acctbtn` 내 계좌, `#collect` 지금 수집, `#phonebtn` 폰 연결, `#cmdbtn` ⌘K, `#theme` ◐ (exact grouping and overflow are in the layout spec) |
| **NR** | Notice rail directly under T, inside the sticky header | `#netbar` (first, role=alert), `#verbar`, `#collectbar`, `#phonebar`. Today these sit inside `.top` and make the header taller (S-14…S-17). They keep their ids, texts and behaviour; only their container moves. |
| **N** | Left navigation | Replaces `#groups` + `.tabs` on screens ≥641 px. Group names are headings, the 17 tabs are items. `data-group`/`data-tab` stay on the items, so `groupOf`, `paintGroups`, `show` and the command palette's `cmdTabs()` keep working. |
| **PH** | Page header row (top of the workspace) | Page title (the visible one; `#pagetitle` stays sr-only), page-level controls (view segments, strategy, stance), and the screen's **basis stamp** (기준 거래일 / 받아온 시각 / scan session). |
| **M** | Main (left) | The screen's table or primary content |
| **R** | Right | Analytics that complement M: the selected row's card, charts, totals |
| **L** | Lower | Supporting sections: compact panels or section tabs |
| **SN** | Section nav | Sticky in-page tabs (stock research screen and 매매 보조) |
| **BB** | Phone bottom bar | `#bottombar` + `#moresheet`, unchanged by owner decision 4 |

### 0.2 Breakpoints (from the existing tokens; the layout spec may refine them)

| Name | Width | N | R |
|---|---|---|---|
| wide | ≥1600 | docked, expanded | beside M |
| desktop | 1024–1599 | docked; collapsible to a rail | beside M from 1280. Below 1280, R stacks under PH, above M. |
| tablet | 641–1023 | drawer opened by `≡` | stacks under M |
| phone | ≤640 (390 is the reference) | hidden; BB + 더보기 | stacks; most R content becomes inline or a fold |

### 0.3 The five investor questions

The owner's prompt asks five questions. Each workflow says where on screen each one is answered:

1. **Q1** What is happening in the market?
2. **Q2** Which stocks are attractive under the program's rules?
3. **Q3** Why does a stock rank highly?
4. **Q4** What are its major risks?
5. **Q5** What should I investigate next?

Every answer is a rule result. The wording stays as it is ("참고용", "프로그램 규칙 기준", "점수 미반영") and adds no advice.

---

## 1. Summary: clicks before vs after

| # | Task (start point) | Before | After | Where the gain comes from |
|---|---|---|---|---|
| 1a | See whether today's collection ran and its session, from any screen | 1 (go to 오늘) + read; failed steps 1 more (작업 상태 fold) or 2 + scroll (검증·기록 → 연구실) | **0** (DT chip), failed steps **1** (chip popover) | DT chip in T |
| 1b | Start collection and watch progress | 1 desktop / 2 phone | 1 / 2 | Progress also in the DT chip; NR no longer grows the header |
| 2a | Typed ticker → its score | T⏎ + 1 (점수 카드) + evaluate wait | T⏎ + **0** (score summary from the recorded scan) [O-1]; full card 1 | Score summary in the stock screen's R |
| 2b | Typed ticker → size calculator | T⏎ + 2 | T⏎ + **1** | `크기 계산기에 넣기` in the score summary |
| 2c | Typed ticker → account form prefilled | T⏎ + 3 | T⏎ + **2** | Same |
| 2d | Stock screen → '사도 돼?' verdict | 1 + typing on 오늘 | **1** (button, asks by itself) | `사도 돼? 묻기` button |
| 3a | 오늘 → a ranking row's card | 2 (+1 if another qsf view was remembered) | 2 | Same count. The card opens in R and the table does not move [O-2]. |
| 3b | Screener result → its card, keeping the filters | 1, but it leaves the screener (QS-07 switches to the rank view) | **1**, screener stays | R card shared by the qsf views [O-2] |
| 4 | Put 3 ranked stocks on the compare chart | 10 through the stock screens, or 2 + 3×T⏎ on the compare tab | **4** (`+비교` ×3, then `비교 열기`) | Row action + add without navigating |
| 5 | Stock screen → forecast range / committee / 당일 점검 | 2 / 2 / 3 (+ evaluate wait) | **1 / 1 / 1** | Quick links that open the card with that fold open |
| 6a | 내 계좌 → one holding's sell check | 2 + scroll ~4 panels (보유 판정 sits under the holdings) | **3**, no scroll | Holding row selects into R [O-2] |
| 6b | Stock screen → price alert for this stock | 2 + scroll past the calculator + form | **1** + form | `알림 걸기` deep link to `#assist:alerts` [O-7] |
| 7a | Market-state detail from any screen | 2 (점수 → strip 자세히) | **1** (MS chip) | MS chip in T |
| 7b | Reach 시장 개요 / 시장 지도 / 거시 from another group | 2 (group, then sub-tab) | **1** | Left nav lists the tabs themselves |
| 8 | Any tab from any tab (desktop) | 1–2 | **1** | Left nav |

---

## 2. Workflow 1: automated scanning (did today's scan run, how fresh, '지금 수집')

### 2.1 Today (baseline)
- **Whether the job ran** has no permanent indicator.
  - The Today brief shows "기준 거래일 … · … 기준" (TD-13).
  - Job items (JOB_FAILED, JOB_NOT_INSTALLED, JOB_NEVER, JOB_NOTE, JOB_RUNNING from `assistant.py:job_items`) go into the 작업 상태 fold (TD-22). That fold opens by itself only when an item is ACT.
- **The full step list** is on 연구실 → 자동 실행 (LB-08), two group hops away.
- **지금 수집** (`#collect`):
  1. It starts a run (CO-01).
  2. `#collectbar` shows progress every 3 s (CO-02).
  3. When the run ends it shows the result and `화면 새로 고침` (CO-04, CO-05).
  - The bar lives inside the sticky header. It makes the header taller and pushes every sticky table header down (`--sticky-top` is measured again).
  - The bar appears by itself only when a run is already in progress at load (CO-07).

### 2.2 After: step by step

**Step 1. See freshness on any screen (0 clicks).** The **DT chip** in T reads `GET /api/automation/status`. `collect.js` already calls it at load (`collectPoll()`); reuse that one response. Refresh it:
- every 5 min (together with `loadHealth`);
- on tab change when the last read is older than 30 s (same rule as health);
- on `visibilitychange`;
- every 3 s while `running`;
- when `collectPoll` finishes a run.

Chip text, chosen in this order of precedence. Every input is an existing server field; nothing is computed on the client.

| Server state | Chip text (desktop) | Phone text | Tone |
|---|---|---|---|
| `running` set | `수집 중 {done}/{total}` (or `수집 중` when total is missing) | `수집 {done}/{total}` | accent; a 1.2 s opacity pulse that is off under `prefers-reduced-motion` |
| `installed=false` | `자동 실행 꺼짐 · 기준 {latest_session}` | `자동 꺼짐` | `--warn` + "!" glyph |
| `steps` empty / no `latest_session` | `수집 기록 없음` | `기록 없음` | `--warn` + "!" |
| any step `FAILED` that is not a news step (same split as `job_items`: NEWS_STEPS → info only) | `기준 {latest_session} · 실패 {n}` | `{MM-DD} · 실패` | `--warn` + "!" |
| otherwise | `기준 {latest_session}` | `{MM-DD}` | neutral `--muted` |
| status unreadable | `수집 상태 모름` | `상태 모름` | neutral, dotted border |

- The chip never says "최신" or "늦음". Whether a session is behind the expected one is decided by `markets/session_data.py`, which is not exposed to the screen. Adding a "늦음" state needs a server-provided flag **[O-4]**. Until then the chip shows only the session stamp, and the Today brief's job items remain the judgement.
- The chip shows the automation session, not each screen's data basis. Each analytical screen also keeps its **own basis stamp in PH** (section 2.4).

**Step 2. Open the details (1 click).** Clicking the chip opens a popover anchored under it. It is `role="dialog"`, not modal. Esc or an outside click closes it and focus returns to the chip. Content, all from the same response:
- `자동 실행 {schedule_text}` · `등록됨` / `등록 안 됨`;
- `마지막 실행 {stamp(last_run.at)} · 기준 거래일 {last_run.session}`;
- `마지막 시도: {UP_TO_DATE→이미 최신 / ERROR→오류 / DONE→완료}`;
- the step list of `latest_session`: name from `step_names` with status 완료 / 실패 / 건너뜀 / 자료 대기 (same words as LB-08), plus `detail`;
- `notes` lines;
- buttons:
  - **[지금 수집]**: calls `$("#collect").click()`. It is hidden when `html.on-phone`, like the top-bar button (PH-07).
  - **[자동 실행 기록 보기]**: `show("lab")`, then scrolls to the 자동 실행 KV (LB-08).
  - **[오늘 수집 됐어? 묻기]**: `askAssistant("오늘 수집 됐어?")`, the existing JOB intent.

**Step 3. Start a collection (1 click on desktop: `#collect` in T, or the popover button).**
- Behaviour, texts, the 60 s start timeout and file paths stay exactly as CO-01…CO-08.
- The progress line renders in **NR** (`#collectbar`), not inside T. The DT chip shows `수집 중 n/N` at the same time.
- When the run ends, `#collectbar` shows the result line with `화면 새로 고침` (CO-05). The chip changes to the new `기준 {session}`.

**Step 4. Refresh the screens.**
- `화면 새로 고침` (CO-05) stays the only full refresh. It clears the rank cache and symbol cache, sets `state.loaded = {}` and re-renders the current tab.
- It is not automatic, so a table never changes under the reader's eyes.

### 2.3 Phone (390)
- The DT chip sits in the 48 px top bar as a short label (`11-23` or `수집 7/12`).
- A tap opens the same content as a bottom sheet above BB.
- 지금 수집 stays in 더보기 → 도구 (S-26) and in the sheet. It is hidden on a paired phone (PH-07; the server refuses `/api/automation/run` with `PHONE_MAC_ONLY`).
- `#collectbar` renders as one line under the top bar. Its long result sentences wrap to at most three lines; the rest is reached by tapping the line, which expands it.

### 2.4 Basis stamps that move into PH (same text, earlier on the page)

| Screen | Stamp | Today's position | New position |
|---|---|---|---|
| 오늘 | `{시장} 시장 · 기준 거래일 … · … 기준` (TD-13) | under the headline | PH, right side |
| 순위·카드 rank | session badge in the `#qsfrank` title, stale-input count line (QR-35) | panel title; footer | PH: session badge. The stale-input count becomes a PH warning line when > 0; the footer keeps the full sentence. |
| 스크리너 | `기준 date` in the count line (QS-01) | count line | unchanged (it is already at the top of M) |
| 시장 개요 | source / 받아온 시각 panel (OV-07) | last panel | PH shows `받아온 시각`. The footer panel stays for the source and the basis sentence. |
| 시장 지도 | scan session, model version (MP-06) | under the map | PH shows the scan session; the rest stays |
| 종목 정보 | chart meta `마지막 일봉 …` (ST-16), profile meta (ST-11) | under the chart / head | unchanged; also mirrored as `마지막 일봉 …` next to the price line |
| 통합 계좌 / 시장별 자세히 | fetched + FX date (AC-06, PF-04) | inside the totals | R totals panel header |

### 2.5 States
- **Loading:** the chip shows `수집 상태…` in grey, never an empty box.
- **Error:** `수집 상태 모름`.
- **Server down:** `#netbar` takes over (S-16). The chip turns grey and keeps the last value with the suffix `(마지막으로 읽은 값)`.

### 2.6 Five questions
| Q | Where |
|---|---|
| Q1 market | Not this workflow's job. The DT chip only says whether today's data arrived. The market answer is in workflow 7. |
| Q2 attractive | After a run: `화면 새로 고침` → 순위·카드 (workflow 3) |
| Q3 why | — (workflow 5) |
| Q4 risks | Data risk: the chip's `실패 {n}`, the rank PH stale-input line (QR-35), the formula-version notice (QR-34) |
| Q5 next | Popover links: 자동 실행 기록 보기, 오늘 수집 됐어? 묻기 |

### 2.7 Friction and fixes
| ID | Friction | Fix |
|---|---|---|
| UXW-01 | No permanent "did it run" indicator; failures sit in a fold on one tab | DT chip + popover (above) |
| UXW-02 | Status bars inside the sticky header grow it and push sticky table heads | NR under T; `--sticky-top` is measured on T + NR (keep the existing `setTopH` ResizeObserver, observe the new container) |
| UXW-03 | The collect result line mixes errors and file paths in one long sentence | Keep the text (tests pin it). Show it in NR with the `.err` part first and the path in `meta` style on a second line. |

---

## 3. Workflow 2: direct ticker analysis (search / ⌘K / '사도 돼?' → research → score → plan / size / account form)

### 3.1 Entry points (all kept)
| Entry | Today's behaviour (kept) | After |
|---|---|---|
| T search `#q` + `#qsug` (S-04, S-05) | 150 ms suggestions; Enter → `findSymbol` → exact code or name opens `#stock/CODE`; otherwise "혹시 이 종목인가요?" (S-06); Hangul with no hit → KRX search (S-07) | Unchanged. The visible hint inside the field becomes `종목 코드·회사명 · ⌘K`. |
| ⌘K palette (CM-05, CM-06) | `AAPL` → 종목 화면, then 점수 카드; `AAPL 점수` → card first; `AAPL 차트`, `AAPL 비교` | Unchanged |
| '사도 돼?' (TD-07, TD-V1…V3) | Typed on 오늘, or as a palette sentence → `askAssistant` → 오늘 answer area | Also a **button on the stock screen** (step 3) that calls the same `askAssistant("{T} 사도 돼?")` |
| COIN market | The search box asks the assistant (S-04) | Unchanged |

### 3.2 After: step by step (desktop ≥1280)

1. **T⏎ in `#q`.**
   - `openTicker(T)` sets `#stock/T`, switches the market by code shape (ST-24) and shows the stock research screen (layout in section 6).
   - Focus moves to the page title in PH (`tabindex="-1"`, `focus({preventScroll:true})`), so a screen reader announces the stock.
2. **Read the score summary in R (0 clicks) [O-1].** The first R panel, titled `점수 요약 · 스캔 기록 {session}`, is filled from the row for T in `qsfLatest(market)`. That is the cached `/api/qsf/latest` the ranking already uses; no evaluate call is made.
   - Shown for **스윙** and **장기** side by side:
     - whole score `qsfInt`;
     - the `경계 근처` badge (`qsfNear`);
     - band label in the judgement colours (`qsfLabel`);
     - entry text `qsfEntry` (long ENTRY_NOW stays "진입을 막는 조건 없음");
     - `실행 대상 아님 · {gate}` when blocked;
     - rank `{rank}위 / {N}` with "상위 x%";
     - the four domain bars (neutral colour);
     - the risk lines `qsfRiskLines(r)` (합병 절차 공시, 자금조달 결정, 변동성 상위 20%, 시세 이력 확인 필요);
     - confidence chip when not HIGH.
   - **Not in the scan** (ETF, index, or outside the universe): `이 종목은 {date} 스캔 대상이 아닙니다. 점수 카드에서 지금 평가할 수 있습니다(처음에는 수십 초).` + **[점수 카드 열기]**. Missing values are `—`, never 0.
   - **Scan unavailable:** `스캔 기록을 읽지 못했습니다. 스캔 기록이 없다는 뜻이 아닙니다.` (same wording as QR-37) + retry.
   - Fixed caption under the panel (existing strip text, shortened): `점수 검증: 높은 점수의 수익 근거 아직 없음 · 참고용`.
   - Buttons in this panel:
     - **[점수 카드 열기]** (primary, accent blue): `qsfOpenCard(T)` → `#qsf/T`, the full card (QC-01…QC-26);
     - **[사도 돼? 묻기]**: `askAssistant(T + " 사도 돼?")`;
     - **[크기 계산기에 넣기]**: same delegated handler as QC-08 (`.qsf-tosize`, `data-style` = the strategy whose band is higher, or SWING when equal; no stop passed, so the calculator uses its ATR suggestion as AS-01 already does);
     - **[주문 계획의 이 줄 보기]**: only when that strategy's `entry_status === ENTRY_NOW`, same handler as QC-07.
3. **'사도 돼?' (1 click).**
   - The button navigates to 오늘. The question is asked at once (`asstPending`, TD-12) and the verdict box (TD-V1) sits at the top of M.
   - Browser Back returns to `#stock/T` without reloading: `state.loaded.stock === ticker` guard (ST-23).
   - Hosting the verdict inside the stock screen's R would be a second host of TD-V1. It is offered as **[O-8]**; the recommendation is no for now.
4. **Full card (1 click from step 2).**
   - At ≥1280 px the card renders in the 순위·카드 screen's R beside the ranking (owner's batch-5 layout, now from 1280 instead of 1600; the breakpoint is in the layout spec).
   - The card's `종목 화면` button (QC-03) returns to the research screen, and so does Back.
5. **Size (1 click).** `크기 계산기에 넣기` → 매매 보조, SN section `크기 계산기`, with the code, style and (from the card) swing stop filled in and computed once (AS-04).
6. **Account form (1 more click).**
   - `이 수량으로 매수 기록 작성` (AS-03) → `acctRecord(market, {BUY…})` → 통합 계좌 L form, scrolled and focused (AC-15).
   - The user checks the fields and presses `기록 추가` (section 11, write safety).

### 3.3 Click table
| Goal | Before | After |
|---|---|---|
| See the score of a typed ticker | T⏎ + 1 + wait (evaluate can take tens of seconds) | T⏎ + 0 (recorded scan); full card + 1 |
| Size calculator | T⏎ + 2 | T⏎ + 1 |
| Account form prefilled with the computed quantity | T⏎ + 3 | T⏎ + 2 |
| Order-plan row | T⏎ + 2 (card → link) | T⏎ + 1 |
| '사도 돼?' verdict | 1 (to 오늘) + typing | 1 |

### 3.4 Five questions
| Q | Where |
|---|---|
| Q1 | MS chip in T (always visible) |
| Q2 | R score summary: band label + entry + `실행 대상 아님` gate line |
| Q3 | R domain bars. The full "why" is in the card's 근거 fold (QC-11), 1 click. |
| Q4 | R risk lines (from the scan row); the card's risk-gate notice (QC-09); filings in the L tab `공시` |
| Q5 | R buttons (카드, 사도 돼?, 크기 계산기, 주문 계획 줄) + header actions (차트분석, 비교에 추가, 알림 걸기) |

### 3.5 States
- **Stock not found:** "혹시 이 종목인가요?" (S-06) renders in M with no R panel.
- **KRX master list unavailable:** existing MASTER_UNAVAILABLE text.
- **Wrong market for the calculator:** AS-01's red message is kept. Because `크기 계산기에 넣기` calls `setMarket(marketOf(t))` first, it no longer happens on this path.

### 3.6 Friction and fixes
| ID | Friction | Fix |
|---|---|---|
| UXW-04 | The stock screen says nothing about the model; the score is one click and a slow evaluate away | R score summary from the cached scan row [O-1] |
| UXW-05 | Four equal ghost buttons in the stock header; the score card is not emphasised (ST-04…ST-07) | `점수 카드 열기` is the one primary button (in R); header actions become a compact action group (section 6.2) |
| UXW-06 | '사도 돼?' is reachable only by typing on 오늘 or in the palette | Button on the stock screen |

---

## 4. Workflow 3: stock discovery (ranking → screener → candidate row → right-panel card → stock detail)

### 4.1 Layout of 순위·카드 after the change
- **PH, line 1:**
  - the status strip `#qsfstrip`, kept as is (QR-01…QR-07). Its summary line shows market state, stance and `점수 검증: … 참고용`; its expanded content is the full market state, caveat, past record and stance explanation;
  - the session badge;
  - the stale-input line when present.
- **PH, line 2** (the `.qsf-nav` row, always visible):
  - view segment `#qsfview` (오늘 순위 / 스크리너 / 주문 계획·가상 장부 / 판정 일정);
  - strategy `#qsfstratseg` 스윙/장기;
  - `{시장} 성향` + `#qsfstanceseg`, always visible (owner request 2026-11-24).
  - The three groups are separated by a 1 px divider and a small label, so the stance setting no longer looks like a filter (inventory weakness QR §5).
- **PH, line 3:** the evaluate form `#qsfform` + `#qsfmsg` (rank view only). It is kept because the evaluate path also serves stocks outside the scan.
- **M:** the active view's table (`#qsfrank`, `#qsfscreen`, `#qsfplan`/`#qsfpaper`, track panels).
- **R (≥1280):** `#qsfdetail`, the card of the selected stock, **shared by all four views** [O-2]. When nothing is selected, R shows the folded reopen bar (QR-15) if a card was open, or one line: `줄을 고르면 그 종목의 점수 카드가 여기에 열립니다.` No empty panel.
- **L (rank view):** `#qsfcap` (KR, fold "cap") and `#qsfchanges` (fold "changes"). They keep their fold persistence (QR-18).

### 4.2 Steps
1. **Open 순위·카드: 1 click.**
   - Left nav item 순위·카드. On the phone: BB 점수.
   - The remembered view (`qse-qsf-view`) and strategy (`qse-qsf-strategy`) apply.
   - The view segment shows which view is on (`aria-pressed`). Its label stays visible in PH, so a remembered 판정 일정 view cannot hide the ranking unnoticed.
2. **Scan the ranking (M).**
   - Sticky table header (QR-36) under T + NR.
   - The first 3 actionable rows carry `상위 3` (QR-22).
   - The common factor line sits above the table (QR-33).
3. **Select a row (1 click), ≥1280 [O-2].**
   - A row click (not on the name button) marks the row selected (`aria-selected="true"`, accent left border; the colour comes from the layout spec).
   - It calls `qsfEvaluate(ticker, market, push=false)`, and `qsfDrawDetail` renders in R.
   - The URL becomes `#qsf/T` through `history.replaceState` [O-3]. Back leaves the screen instead of walking back through every row looked at.
   - The table does not scroll. The R card is sticky under T + NR with its own scroll.
   - **Inline expansion is kept.** Each row gets a trailing disclosure button `▸` (`aria-expanded`, title `줄 안에 펼치기`). It toggles the existing `qsf-exp-row` with the scan-vs-now note (QC-26), price-audit notice, `qsfCard` and 당일 점검 (QR-21).
   - Below 1280 px, a row click still expands inline, as today. Nothing is lost at any width.
4. **Read the card in R:**
   - header: name, tags, `종목 화면`, `닫기`;
   - the two strategy cards with the summary strip (진입, `주문 계획의 이 줄 보기`, `크기 계산기에 넣기`);
   - 근거 open by default;
   - folds 계획 (가설), 요인별 계산, 다섯 투자자와 투자위원회, 가격 범위 · 예측 층 FC-1, 이력과 기술 정보.
   - Fold states are remembered per kind (`qse-fold-*`, QC-19).
5. **Go to the stock detail (1 click):** the name button in the row (`.linkish[data-ticker]`, QR-23) or `종목 화면` in the card header (QC-03). Back returns to the ranking with the scroll position and the selected row (RETURN.qsf).
6. **Screener (view switch, 1 click):**
   - Filters in PH line 3 (replacing the evaluate form for this view); results table in M.
   - A row click selects the row and renders the card in R **without leaving the screener** [O-2]. Today `.qs-open` switches to the rank view (QS-07). The `.qs-open` score button becomes the same action as the row click. The filter state (`qsfScreenState`) and scroll stay.
   - CSV 저장 (QS-05) moves next to the count line, with the hint `최대 2,000줄` (the existing limit, now stated).
   - Below 1280 the screener row click opens the card **inline under the row**, using the same expandable-row component as the ranking. Today it jumps to the rank view.
7. **Changes panel (L):** names → stock screen; score buttons → card in R, without the current `scrollIntoView(#qsfmsg)` jump.

### 4.3 Click table
| Goal | Before | After |
|---|---|---|
| 오늘 → 순위 → a card | 2 (+1 if another view was remembered) | 2; the card is beside the table and the page does not move |
| Card → stock screen | 1 | 1 |
| Screener result → card, filters kept | 1, filters left behind | 1, filters stay |
| Card → order-plan row | 1 (only ENTRY_NOW) | 1 |
| 오늘 candidate chip → card | chip → stock screen (1) → 점수 카드 (2) | 2 (chip → stock screen with the R score summary → card), or **1** from the candidate's score cell (see below) |

The 오늘 candidate table follows the batch-6 rule "code or name → 종목 화면, score or judgement → 점수 카드". Today the score cell of a candidate row is not clickable. After the change, the score number becomes a `.linkish` button that calls `qsfOpenCard` (the same rule the ranking already follows).

### 4.4 Five questions (순위·카드)
| Q | Where |
|---|---|
| Q1 | PH strip summary (`시장 상태 n/100 {label}` + `새 주문 크기 x%` on adverse days); MS chip in T |
| Q2 | M ranking: 판단 label (judgement colours), 진입, `상위 3`, `성향 후보 / 성향 밖` chip; screener filters (판단, 진입, 게이트 통과만) |
| Q3 | M: 가점/감점 column (QR-33) and domain bars (≥1280, hidden while the card is beside them per QR-31). R card: 근거 fold (QC-11: 근거 균형, 영역별 점수), 요인별 계산 (QC-17) |
| Q4 | M: risk lines under the name (QR-28), `실행 대상 아님 · gate`; R card: tags, deals notice, risk-gate notice (QC-09), price-audit line (QC-04), 이력과 기술 정보 → 위험 등급 (QC-24) |
| Q5 | L 직전 기록과 달라진 점 (QR-38); R card links (주문 계획, 크기 계산기, 종목 화면); 판정 일정 view for whether the score is working (QT-01) |

### 4.5 States
| State | Text (existing unless marked new) | Region |
|---|---|---|
| Loading ranking | `불러오는 중…` → **new:** 8 skeleton rows at final row height so the sticky header does not jump | M |
| Ranking fetch failed | `순위를 불러오지 못했습니다: … 스캔 기록이 없다는 뜻이 아닙니다.` (QR-37) + **new** `다시 시도` button that calls `renderQsf(true)` | M |
| No scan yet | `아직 스캔 기록이 없습니다…` + `.collect-now` | M |
| Empty | `순위에 올릴 종목이 없습니다.` | M |
| Card evaluating | `#qsfmsg` text (QR-12) mirrored as a one-line placeholder at the top of R | R |
| Card failed / cannot evaluate | `평가 실패: …` / `평가할 수 없습니다: reason` in R | R |
| Stale scan formula | formula-version notice (QR-34) | PH warning line |
| A newer scan arrived while away | `qsfReturn` re-renders once (QR-14); **new** NR-style info line `새 스캔({session})으로 순위를 다시 그렸습니다.` so the change is not silent | M top |

### 4.6 Phone (390)
- BB 점수 → rank view.
- The `.qsf-nav` row wraps into two lines: (1) the view segment as a horizontally scrollable chip row, with whole Korean words kept (P3-2); (2) strategy + stance.
- Rows are two lines (rank, name and score / judgement and entry); see the batch-2 phone rule.
- A tap on a row expands it inline (no R). The name tap → stock screen.
- After an inline card is opened, a `맨 위로` floating button (40×40, above BB) appears once the page has scrolled more than two screens.

### 4.7 Friction and fixes
| ID | Friction | Fix |
|---|---|---|
| UXW-07 | The card has three positions (above the table, beside it, inline) and two render paths | R is the one host ≥1280; inline stays below 1280 and as a disclosure. Both keep their current content (no feature dropped). Merging the two render paths is left to engineering; not required. |
| UXW-08 | Screener → card leaves the screener (QS-07) | Row → R card in place [O-2] |
| UXW-09 | View, strategy and stance look like one filter row | Grouped with labels and dividers in PH line 2 |
| UXW-10 | Evaluate re-reads filings for tens of seconds with only a text line | Keep the text; R shows the same line plus the ticker name, and the selected row shows a small busy marker (`aria-busy`) |

---

## 5. Workflow 4: stock comparison (비교 tab; adding from the ranking and the stock screen)

### 5.1 Today
- `compareWith([t])` (CP-10) adds the ticker and **navigates** to 비교. It is used by the stock header `비교 차트` (ST-05) and the palette `AAPL 비교`.
- The compare add form `#cmp-add` takes typed codes only, with no name suggestions (CP-03).
- Max 8 tickers; the selection is kept in `qse-compare`.

### 5.2 After: step by step
1. **Add without leaving (1 click per ticker).** A `+비교` action:
   - in the ranking row's action cell (visible on row hover/focus; always visible on coarse pointers);
   - in the screener rows;
   - in the R card header;
   - in the stock screen header group (`비교에 추가`, replacing the label `비교 차트`; `#addc` keeps its id).

   It calls a new non-navigating helper (working name `compareAdd(t)`). The helper uses the same dedupe and max-8 rule as `compareWith`, then shows the toast `비교에 넣었습니다 ({n}/8)` with a **[비교 열기]** button (`notify` with an action; toast info tone, 5 s). At 8: the existing toast `비교는 최대 8개까지입니다.`
2. **Open 비교 (1 click):** the toast button, the left nav item 비교, or ⌘K `비교`.
3. **On the 비교 tab:**
   - M: overlay return chart (CP-05) with the range segment (CP-01) in PH.
   - R: selected chips with × and their colour swatch (CP-02); add form with **name suggestions** (reuse `symbolSuggest` + the `#qsug` listbox pattern; Hangul names allowed); index chips (CP-03).
   - L, two tabs: `기간 성과` (CP-07, the most useful output, now the default tab) | `상관계수` (CP-08 matrix + CP-09 rolling chart).
   - Meta lines (CP-06) under the chart.
4. **Cross-link to the committee's investor comparison:** a ghost button `다섯 투자자 관점으로 비교` under the chips. It opens committee view `compare` with the current stock tickers (indices dropped) in the `icCompare` form, then runs it. It is a link only; IC-09 is unchanged.

### 5.3 Click table
| Goal | Before | After |
|---|---|---|
| 3 ranked stocks on the compare chart | 10 (name → 비교 차트 → Back → Back per ticker) or 2 + 3×T⏎ | 4 |
| Add the open stock | 1 (navigates) | 1 (stays) + 1 to open |
| Add by company name | not possible (codes only) | T + pick a suggestion |

### 5.4 Five questions
| Q | Where |
|---|---|
| Q1 | index chips (S&P 500, 코스피 …) on the same chart |
| Q2 | — (comparison is descriptive). R chips can show each stock's band label when the ticker is in the cached scan row. That is optional, existing data only, and needs no decision. |
| Q3 | — |
| Q4 | L `기간 성과`: 연 변동성, 최대 낙폭; `상관계수` |
| Q5 | row click in `기간 성과` → stock screen (CP-07); `다섯 투자자 관점으로 비교` |

### 5.5 States
- Under 2 series: the correlation tab keeps its existing empty texts (`두 개 이상일 때 보입니다.` / `두 개 이상이고 기간이 상관을 잴 만큼 길 때 보입니다.`).
- UNAVAILABLE series: listed in meta `가격 없음: …` (CP-06).
- Mixed markets: the existing note `미국과 한국을 섞으면 두 시장이 모두 연 날만 남습니다.` moves from meta to directly under the chart title, because it changes how the chart reads.

### 5.6 Friction and fixes
| ID | Friction | Fix |
|---|---|---|
| UXW-11 | Adding to the comparison always navigates away | `compareAdd` + toast action |
| UXW-12 | Code-only add form | Name suggestions (reuses search) |
| UXW-13 | Hover tooltips are mouse-only (CP-05, CP-09) | Pointer events with `touch-action: pan-y`, the same pattern chart.js already uses (CH-09) |
| UXW-14 | Two "비교" (price compare vs committee 투자자 비교) | Keep both names. Left nav item `비교` gets the sub-label `수익률·상관`; the committee view keeps `투자자 비교`. The cross-link makes the relation explicit. |

---

## 6. Workflow 5: individual stock research (종목 정보 layout and how each topic is reached)

### 6.1 Section order (desktop ≥1280)
```
PH   name · code · exchange · sector·industry · 웹사이트            [action group]
     price line: close · 1-day % (with sign/arrow) · 장중·미확정 · 52주 범위 · 200일선 대비 · 마지막 일봉 date
SN   개요 · 재무 · 공시 · 동종업계 · 회사 설명            (sticky under T+NR)
M    가격 차트 panel (range 3개월/1년/5년, SMA legend, canvas 420 px, meta)          R  1 점수 요약 · 스캔 기록 [O-1]
                                                                                      2 핵심 수치 (8-fact kv, ST-09)
                                                                                      3 더 보기 (quick links, 6.3)
L    section tabs: 재무 (ST-20, default) | 공시 (ST-21) | 동종업계 (ST-19, PE-01…08) | 회사 설명 (ST-10)
     footer meta: profile source (ST-11)
```
- **SN behaviour:**
  - `개요` scrolls to the top.
  - The other three select the L tab and scroll L into view.
  - The chosen L tab is remembered in `qse-stock-sec` (new key, try/catch like the others).
  - L tabs are a `role="tablist"`. Arrow keys move between tabs and Enter selects.
- **Peers** sits in L, not between the chart and the financials. Its 11-column table needs full width, and today it pushes the financials and filings far down.
- **The 8 facts** move from the header block to R panel 2. Dividend-yield suspicion handling (ST-09) is unchanged.
- **Below 1280:** R stacks above M (score summary first, because that is the screen's verdict). L stays below M.
- **Phone:**
  - the price line wraps to two lines;
  - the action group shows the two most-used actions (`점수 카드`, `사도 돼?`) and a `⋯` button. `⋯` opens a sheet with `＋ 관심종목`, `비교에 추가`, `차트분석`, `알림 걸기`;
  - the chart is 300 px (existing);
  - L tabs become a horizontally scrollable segment.

### 6.2 Header action group (all existing features kept)
| Action | Element | Behaviour | Change |
|---|---|---|---|
| ＋ 관심종목 | `#addw` | POST watchlist add → `✓ 추가됨` (ST-04) | none |
| 비교에 추가 | `#addc` | was `compareWith` (navigates) | `compareAdd` + toast (workflow 4) |
| 차트분석 | `#adda` | `chartWith(T)` (ST-06) | none |
| 점수 카드 | `#addq` | `qsfOpenCard(T)` (ST-07) | Kept in the header for muscle memory. The primary styling moves to R's `점수 카드 열기`. |
| 알림 걸기 (new link) | — | `show("assist")`, SN section `알림 센터`; `prefillTicker` already fills the alert form's code field (AL-01) | new link to an existing feature |

### 6.3 R panel 3 "더 보기" quick links
These links open the card with a fold already open. Mechanism: `qsfOpenCard(T, true, {fold})` sets `qsfState.openOnce = fold`. `qsfDrawDetail` opens that `<details>` and fires its lazy loader, without writing `qse-fold-*`, so the user's remembered fold states are not changed.

| Link text | Opens | Inventory |
|---|---|---|
| 가격 범위 · 예측 층 | fold `range` (`#qsffcfold`) | QC-20, FC-01…06 |
| 다섯 투자자와 투자위원회 | fold `committee` | QC-19, IC-11…14 |
| 당일 점검 (시세·공시·뉴스) | fold `tech` + `#qsftodayfold` | QC-21, QC-22 |
| 기록된 점수 이력 | fold `tech` (history loads on open) | QC-23 |
| 다섯 관점은? (질문) | `askAssistant(T + " 다섯 관점은?")` | TD-08 FIVE |
| 손절 어디? / 실적 언제? / 위험해? | `askAssistant(T + " …")` | TD-08 STOP / EARNINGS / RISK |

### 6.4 How each topic is reached
| Topic | Before (from the stock screen) | After |
|---|---|---|
| Score and band | 1 + evaluate wait (점수 카드) | 0 (R summary, scan record); full card 1 |
| Why (factors) | 1 (card; 근거 open by default) | 1 |
| Risk | 1 (card tags and gates); none on the stock screen | 0 (R summary risk lines); gates 1 |
| Filings | 0 clicks, ~3–4 screens of scrolling | 1 (SN `공시`), no long scroll |
| Peers | 0 clicks, ~1–2 screens of scrolling | 1 (SN `동종업계`) |
| Financials | 0 clicks, scroll | 0 (default L tab), or 1 |
| Forecast range | 2 (card → fold) | 1 |
| Committee opinion | 2 (card → fold) | 1 |
| 당일 점검 | 3 | 1 |
| Score history | 2 | 1 |

### 6.5 Five questions
| Q | Where |
|---|---|
| Q1 | MS chip (T); `200일선 대비` in the price line (stock-level trend, existing) |
| Q2 | R score summary (band + entry + gate) |
| Q3 | R domain bars; card 근거 (1 click) |
| Q4 | R risk lines; L 공시; facts (베타); card risk gate and 위험 등급 |
| Q5 | R quick links; L 동종업계 (rows open peers, PE-02) |

### 6.6 States (per panel; today each panel says `불러오는 중…` and shows an inline red error with no retry, ST-22)
| Panel | Loading | Empty / unavailable | Error | Stale |
|---|---|---|---|---|
| PH head | name from the cached scan row if known, else the code; the price line shows `—` | — | red sentence + **new** `다시 시도` (re-runs `renderStock` after clearing `state.loaded.stock`) | profile status badge (ST-11) |
| 가격 차트 | canvas area with a fixed height and `불러오는 중…` centred (no layout jump) | `가격 데이터를 받지 못했습니다. 종목 코드를 확인하세요.` (ST-16) | red + 다시 시도 (`loadChart`) | `장중·미확정`, status badge |
| 점수 요약 | 2 skeleton lines | not scanned / no scan (3.2) | QR-37 wording + 다시 시도 | session in the title; **new** `스캔 기록 {session} · 지금 시세와 다를 수 있음` when the chart's last bar date is newer than the scan session (both dates already on screen; comparison only) |
| 재무 | skeleton table | `UNAVAILABLE` reason (ST-20) | red + 다시 시도 | `—` = not disclosed |
| 공시 | skeleton | the server's reason text (`f.reason`, existing) | red + 다시 시도 | — |
| 동종업계 | skeleton | `이 종목은 QSF 스캔 대상이 아니라 업종 비교가 없습니다.` (PE-06) | red | ratio ledger note (PE-04) |

---

## 7. Workflow 6: portfolio monitoring (통합 계좌 → 시장별 자세히 → alerts → sell check)

### 7.1 통합 계좌 (`account`) after
- **PH:** `통합 계좌 · 미국 주식 · 한국 주식 · 코인`; 원화/달러 toggle `#acctunit` (AC-03); fetched time + FX date.
- **R (totals):**
  - integrity notice (AC-02) at the top;
  - missing-price and missing-FX notices (AC-04);
  - big total + secondary figure (AC-05);
  - kv (AC-06);
  - per-account table with `자세히` per US/KR row (AC-07, AC-08).
- **M:** 보유 종목 table (AC-09). The ticker label opens the stock screen (global `data-ticker`).
- **L:** `거래 기록 추가` form (AC-10…AC-15), then `거래 기록` (AC-16, AC-17), then notes (AC-18).
  - The form gets an anchor id `acctform-panel` (already present). `acctRecord()` keeps scrolling there and focusing.
- **Colours:** the international pair on this tab stays (S-24, `INTL_COLOR_TABS`), as owner decision 2 confirms.

### 7.2 시장별 자세히 (`portfolio`) after
- **PH:** market (follows the switch), fetched time; `주식 두 계좌 합계` (PF-03) as a one-line summary with a `통합 계좌` link.
- **M:** holdings tables 장기 / 스윙 / 구분 없음 (PF-06), each with its header summary. The 보유 판정 cells fill in asynchronously (PF-08) and are reserved at final width, showing `계산 중…` in grey, so columns do not jump.
- **R:**
  1. 계좌 요약 (PF-04);
  2. 경고 list (PF-05);
  3. **보유 점검 for the selected holding** [O-2].
     - Default (nothing selected): the `#sigpanel` summary (PF-08 explanation lines).
     - When a row is selected (row click; the ticker label still opens the stock screen), R shows for that holding:
       - action chip (EXIT/THESIS_INVALIDATED amber, REDUCE… amber, HOLD grey; judgement colours, decision 5);
       - score;
       - 손절가 and distance; 목표가 and 남은 기간 (swing) or 다음 점검 (long);
       - 미실현 손익;
       - buttons **[팔아야 해? 묻기]** (`askAssistant(T + " 팔아야 해?")`, TD-08 SELL_CHECK), **[점수 카드]**, **[종목 화면]**, **[알림 걸기]**.
     - All values are already on the row; nothing new is computed.
  4. 섹터 비중 bars (PF-09).
- **L tabs:** `위험 분석` (PF-10, async) | `수익률 곡선` (PF-11) | `매매 성과` (PF-12) | `거래 기록` (PF-14 table with 취소) | `기록 추가` (PF-13, the `통합 계좌에서 기록하기` button). The empty-journal `시작하기` panel (PF-02) replaces the L tabs when the journal is empty.

### 7.3 Alerts (매매 보조 `assist`, not 시장별 자세히)
- **Inventory correction:** the alert center `#alertc` is rendered by `renderAssist` (`portfolio.js:204, 243`), so it is on the **매매 보조** tab (AS-05). Part A's rows AL-01…AL-06 name "portfolio tab"; their screen should read **assist**. The regression check must look for alerts on 매매 보조.
- **매매 보조 after:** SN with five sections, each an existing panel:
  - `크기 계산기` (AS-01…AS-04)
  - `알림 센터` (AS-05 / AL-01…AL-06)
  - `실적 발표` (AS-06)
  - `위험 관리 설정` (AS-07)
  - `P6-11B 계획 대조` (AS-08, US only)

  The calculator's result panel sits in R beside the form at ≥1280; the other sections stack in M.
- **Deep link `#assist:alerts`** (and `:size`, `:earn`, `:settings`, `:plan`) **[O-7]**: `fromHash` already splits `tab:view`. It extends to scroll to the section after render. `알림 걸기` from the stock screen and from 보유 점검 uses it.

### 7.4 Sell check paths (all existing logic)
1. **Rule state per holding:** the 보유 판정 cell (PF-08) in M, plus R 보유 점검 for the selected row.
2. **Question:** `팔아야 해?` (TD-08 SELL_CHECK) from R 보유 점검 or typed on 오늘.
3. **Today list:** held-stock items (ACT/DUE such as stop or exit items) on 오늘, linking to 시장별 자세히.
4. **Alerts:** price and band-change rules on 매매 보조 → 알림 센터; `지금 확인` preview (AL-06) does not send or record.

### 7.5 Click table
| Goal | Before | After |
|---|---|---|
| 내 계좌 → market detail | 2 | 2 |
| … → one holding's rule state with stop/target | +0 clicks but scroll to 보유 판정 4 panels down, then match the row | +1 (row select), no scroll |
| … → '팔아야 해?' | +1 (go to 오늘) + typing | +1 (R button) |
| Alert for the open stock | 2 + scroll + form | 1 + form |
| Record a trade from 시장별 자세히 | 1 (`통합 계좌에서 기록하기`) | 1 (L tab `기록 추가` → same button; or `acctRecord`) |

### 7.6 Five questions
| Q | Where |
|---|---|
| Q1 | MS chip; 오늘 tiles |
| Q2 | — (holdings are owned; the band label per holding is in the 보유 판정 cell) |
| Q3 | R 보유 점검 → 점수 카드 |
| Q4 | R 경고 (PF-05), `손절 시 손실 합계` (PF-04), 섹터 비중 over-limit bars, L `위험 분석` (VaR, ES, correlation) |
| Q5 | R 보유 점검 buttons; 오늘 할 일 items for holdings; 알림 센터 |

### 7.7 States
| Screen | Loading | Empty | Error | Stale / partial |
|---|---|---|---|---|
| 통합 계좌 | skeleton totals + table | `보유 종목이 없습니다` + pointer to the form (AC-09); journal `기록이 없습니다.` | `errBox` (AC-19) | STALE badge per account; missing price / FX notices; coin price error line (AC-18) |
| 시장별 자세히 | skeleton; 보유 판정 cells `계산 중…`; risk `불러오는 중…` | `시작하기` (PF-02); `보유 종목이 없습니다.` | `errBox`; market-changed guard (PF-16) | STALE badge; unprotected-ticker line |
| 매매 보조 | per section | calculator: no-result reason (AS-02); earnings: empty/unavailable text (AS-06) | `errBox` | `오래된 일정` badges (AS-06) |
| 모의 매매 | — | first-use `시작하기: 모의 자금을 먼저 넣으세요` (PT-04) | integrity state (PT-02) | delayed-quote note (PT-06) |

### 7.8 Friction and fixes
| ID | Friction | Fix |
|---|---|---|
| UXW-15 | 보유 판정 lives 4 panels below the holdings it describes; cells jump from — to values | R 보유 점검 per selected row; reserved cell width |
| UXW-16 | Alerts are far from where a price is decided | `알림 걸기` on the stock screen and in 보유 점검; `#assist:alerts` |
| UXW-17 | 매매 보조 holds five tools with no sub-navigation | SN |
| UXW-18 | The trade form sits below two large tables (AC weakness 1) | Form in L directly under M; the `acctRecord` scroll stays. On the phone the form comes **before** the holdings table when the screen is reached through `acctRecord()` (scroll target already does this). |

---

## 8. Workflow 7: market analysis (시장 개요 / 시장 지도 / 거시 / market-state strip)

### 8.1 MS chip in T (owner decision 4)
- **Source:** `GET /api/qsf/market-state?market={US|KR}`. This is the same call `qsfStrip` makes; cache it per market for 5 min and share it with the strip. Refresh on market switch and on collect finish.
- **Text:** `qsfStateShort(ms)` exactly (`시장 상태 {n}/100 {label}` + `새 주문 크기 x%` badge when `size_factor < 1`). Fallbacks: `시장 상태 읽지 못함` / `시장 상태 자료 없음`.
  - Korea has no brake (owner decision 2026-11-16). The server's `size_factor` already reflects that, so the client adds no rule.
- **Tone:** neutral when FAVOURABLE; `--warn` border when not. Never price colours.
- **Click → popover:** `qsfMarketState(ms)` (score, label, size-cut badge, `점수 미반영 · {mid} 미만이면 나쁨`, factor line, note) + link `순위·카드에서 자세히` (`show("qsf")`, opens `#qsfstrip`).
- **COIN market:** no market-state score exists, so the chip is hidden **[O-11]**. The coin market panel (CO-08) stays on the 코인 tab.
- **Hosts:** the qsf strip (QR-01…03), the 오늘 tile (TD-16), the plan line (QE-10) and the committee stat (IC-03) all stay. The chip is an extra entry point, not a replacement.

### 8.2 시장 개요 (`overview`) after
- **PH:** live-session notice (OV-06) when intraday; `받아온 시각`.
- **M:** one compact table per group instead of equal cards. Columns: 이름 · 코드 · 종가 · `1일` · `1개월` (both labelled, per P0-3) · status. Index rows are not clickable; stock and ETF rows are (`data-ticker`, OV-04). Neutral rows (VIX, yields, DXY, FX) show the sign without up/down colour (OV-03).
- **R:** the sparkline cards of the selected group (OV-02), using the existing `spark()` and "그래프 폭 x%". Hovering or focusing a row highlights its card.
- **L:** source/basis panel (OV-07).
- **Feature check:** every card field stays (OV-02); only the arrangement changes. Clicking a card still opens the stock screen.
- *This M/R split is a proposal for the layout spec. If the layout agent keeps cards, the flow above is unchanged.*

### 8.3 시장 지도 (`map`) after
- **PH:** the three segments (MP-01 mode, MP-02 score style, MP-03 palette) with text labels `보기`, `점수`, `색`. Disabled segments carry `aria-disabled` and the existing tooltip text shown as a visible caption under the segment (`등락 보기에서는 쓰지 않습니다…`), not only 50 % opacity.
- **M:** treemap canvas (MP-04). Click → stock screen.
  - **New, keyboard and touch:** a visually hidden list of the drawn tiles (name, value) after the canvas, so Tab or a screen reader can reach each tile. It is the same data, already in memory.
- **R:** 업종 순환 그래프 (RO-01) at ≥1280. Below that it moves to L.
- **L:** 업종 상대 성과 table (RO-03). Clicking a sector shows 업종 점수 상위 종목 (SP-01) in **R under the RRG**, instead of a panel three panels down with `scrollIntoView`. The pick plan (SP-02) renders in the same place. `종목 화면에서 자세히` → stock screen.

### 8.4 거시 (`macro`) after
- **M:** macro indicator cards (MA-01), first, because the tab is named after them.
- **R:** 경제 일정 (CAL-01…07, `#econcal`), a scrollable panel of 60 days with today's rows first. Held and watched badges are kept (CAL-02).
- **PH:** reason notice (MA-02) when a key is missing.
- **L:** CPI note and source (MA-03).
- **Phone:** the cards come first and the calendar follows as a fold, open by default when any row is `오늘` or `내일`.

### 8.5 Click table
| Goal | Before | After |
|---|---|---|
| Market state number, from any screen | 0 if on 오늘 or 순위·카드, otherwise 1–2 | 0 (chip) |
| Market state factors | 2 | 1 |
| 시장 지도 / 거시 from another group | 2 | 1 |
| Sector → its top stocks | 1 + automatic scroll | 1, no scroll (R) |

### 8.6 Five questions
| Q | Where |
|---|---|
| Q1 | MS chip; 오늘 headline + tiles; 시장 개요 M; 시장 지도 M (breadth by colour); 거시 M |
| Q2 | 시장 지도 in score mode (MP-01 `QSF 점수`); R sector top picks (SP-01) |
| Q3 | Pick plan (SP-02) → 종목 화면 / 점수 카드 |
| Q4 | 거시 calendar (events ahead, CAL-02 held badges); MS chip `새 주문 크기` |
| Q5 | Sector rotation (RO-03) → picks; calendar rows → stock screen (CAL-04) |

### 8.7 States
| Screen | Loading | Empty | Error | Stale |
|---|---|---|---|---|
| 시장 개요 | `불러오는 중…` → skeleton table | — | `errBox` (OV-08) | non-REAL status badge per row (OV-05) |
| 시장 지도 | canvas placeholder at final height | `UNAVAILABLE 스캔 결과가 없습니다.` (MP-06) | `errBox` | scan session in PH |
| RRG | placeholder | `UNAVAILABLE` (RO-02) | error | last week in meta |
| 거시 | per card | `60일 안에 공식 발표된 일정이 없습니다.` (CAL-07) | `errBox` | `오래된 일정`; `공식 일정은 … 까지만` notices (CAL-05) |

---

## 9. Workflow 8: navigation between sections

### 9.1 Left navigation (N)
- **Structure:** group headings (`오늘`, `시장`, `종목`, `차트`, `내 계좌`, `점수`, `검증·기록`, `코인`) with their tabs as items, in today's order.
  - Groups with one tab (오늘, 코인) are a single item without a heading.
  - `groupShown()` hides groups exactly as today: COIN shows 오늘 and 코인, and 통합 계좌 stays reachable in every market (ANY_MARKET).
- **Active item:** `aria-current="page"` on the item; the group heading gets a marker. The existing `paintGroups`/`paintTitle` set these.
- **Collapse (≥1024):**
  - a `«` button at the foot of N collapses it to a rail;
  - the rail shows two-syllable group labels (`오늘 시장 종목 차트 계좌 점수 검증 코인`), so no icon set is needed;
  - hover or focus on a rail group opens a flyout with its tabs;
  - remembered in `qse-nav` (`open`/`rail`, new key).
- **641–1023:** N is a drawer opened by `≡` in T, with focus trapped while open. Esc, an outside click or choosing an item closes it, and focus returns to `≡`.
- **Group click behaviour:** the old group bar opened the group's last-visited tab (`groupTab`). In N the heading is not a link; items are. `showGroup(g)` stays for the bottom bar, the more sheet and the number keys.

### 9.2 Hash links and back/forward

| Hash | Opens | Status |
|---|---|---|
| `#today`, `#overview`, … (17 tabs) | the tab | existing |
| `#stock/CODE` | stock screen; market from the code shape | existing |
| `#qsf/CODE` | 순위·카드, rank view, card for CODE | existing |
| `#qsf:rank\|screen\|exec\|track` | 순위·카드 view | existing (pushState on user choice) |
| `#committee:dash\|ports\|compare\|perf` | committee view | **new [O-7]**: `icSetView(v, push)` mirrors `qsfSetView`; `tabHash("committee")` returns `committee:{view}` when not `dash` |
| `#assist:size\|alerts\|earn\|settings\|plan` | 매매 보조 scrolled to that section | **new [O-7]** |

| Move | Back returns to | Scroll | Status |
|---|---|---|---|
| tab → tab | previous tab | restored for kept tabs (`RETURN`, `tabScroll`); **new:** ALWAYS_FRESH tabs also restore `tabScroll[tab]` after their render resolves (best effort, clamped to page height) | partly new |
| stock A → stock B | stock A (re-rendered) | top | existing |
| qsf view change | previous view | kept | existing |
| card opened from a link (`qsfOpenCard` push) | origin screen | origin's | existing |
| ranking/screener row selection [O-3] | the screen before 순위·카드 (selection uses replaceState) | — | new |
| palette, popovers, sheets, drawer | never create history | — | existing rule, extended |
| market switch | not in the hash, except through `#stock/` and `#qsf/` codes | — | existing; documented in the T market switch tooltip: `시장 전환은 뒤로 가기로 되돌아가지 않습니다` |

### 9.3 Keyboard

| Keys | Where | Action | Status |
|---|---|---|---|
| ⌘K / Ctrl+K | anywhere | toggle palette | existing, always on |
| `/` `?` | not typing, single keys on | open palette | existing |
| `1`–`9` | single keys on | **Nth visible group** in N order | **changed:** today it indexes DOM order including hidden groups (S-18). The palette help says `1~6`; it becomes the computed count, `1`~`7` in US/KR and `1`~`2` in COIN. Minor behaviour change in COIN (8 → 2). |
| `M` | single keys on | cycle market US → KR → COIN | existing |
| Esc | layered | closes the topmost of: palette > popover (DT/MS chip) > drawer > more sheet > suggestions | existing parts + new layers |
| Tab | page | order: skip link `본문으로 건너뛰기` (**new**, first focusable, jumps to PH title) → T → N → PH → M → R → L | new skip link |
| Enter / Space | focused `tr.click`, `.qsf-rrow`, keyable cards, fold headings | activate (markKeyable) | existing |
| ↑ / ↓ | a focused row in a table | move focus to the previous or next row of the same `tbody` (`preventDefault` only when a sibling exists) | **new**, active only while a row has focus, so it is not a single-key shortcut |
| ← / → | L section tabs, SN, view segments | move between tabs (tablist pattern) | new for SN/L |

**Single-key switch** (S-12, CM-10): unchanged.
- It is stored in `qse-keys`.
- The header button `#keysbtn` stays `hidden` by decision. It is reachable from the palette footer and 더보기, and is added to the DT/settings overflow if the layout spec gives T an overflow menu.

### 9.4 Focus return rules
| Closing … | Focus goes to |
|---|---|
| palette (Esc or backdrop) | the element focused before (existing `cmdBack`) |
| palette (item run) | the new screen's PH title (`tabindex=-1`, `preventScroll`) |
| left-nav item | the new screen's PH title |
| DT/MS popover, drawer, more sheet | the button that opened it |
| R card `닫기` | the selected row in M (if still in the DOM), else the PH title |
| inline row expansion collapse | the row |
| toast action (`비교 열기`) | the new screen's PH title |
| after a write (stance, rules, form) | the control that was pressed; the result is announced in an `aria-live="polite"` region (form `.msg`, `#toast`) |

### 9.5 Remembered state
| Key | Remembers | Status |
|---|---|---|
| `qse-market` | market | existing |
| `qse-theme` | auto/light/dark (dark default per decision 3: `theme.js` default changes from `auto` to `dark`; layout spec) | existing key |
| `qse-keys` | single-key shortcuts on/off | existing |
| `qse-recent` | 12 recent tickers | existing |
| `qse-qsf-view`, `qse-qsf-strategy`, `qse-qsf-folds`, `qse-fold-*` | qsf view, strategy, panel folds, card section folds | existing |
| `qse-heat-view`, `qse-acct-unit`, `qse-chart`, `qse-compare` | map toggles, account currency, chart settings, compare list | existing |
| `qse-nav` | left nav open/rail | **new** |
| `qse-stock-sec` | stock screen L tab | **new** |

Committee view and 매매 보조 section are carried by the hash [O-7], not by storage. Every new key is read and written inside try/catch, like the existing ones.

### 9.6 Phone navigation (≤640)
- **BB** (unchanged, S-25): 오늘 / 종목 / 점수 / [코인] / 내 계좌 / 더보기.
- **더보기 sheet** (S-26), two changes:
  - (a) groups are listed **with their tabs**, so `시장 › 시장 개요 · 시장 지도 · 거시` is one tap from the sheet instead of group-then-sub-tab;
  - (b) the 도구 row is unchanged (지금 수집 hidden on a paired phone, 폰 연결, 명령창, 화면 테마, 한 글자 단축키).
- **Sub-tab strip:** a 40 px horizontally scrollable strip of the current group's tabs, sticky under the 48 px top bar. It appears only when the group has ≥2 tabs (today the row is not sticky on the phone).
- **Phone top bar:** market switch · search · DT short label. The MS chip moves to the first line of the 오늘 and 순위·카드 PH on the phone, because 390 px cannot hold it in T.

---

## 10. Loading / empty / error / stale states for every screen

Shared rules (new as a pattern; the texts are the existing ones):
1. **Loading** keeps the final geometry: skeleton rows for tables, a fixed-height placeholder for canvases, and `불러오는 중…` only where no shape is known. No spinner that shifts content.
2. **Error** is a panel-level `errBox` with the Korean `errKo` sentence. It adds a **`다시 시도`** button that re-runs only that panel's loader. Server-down still goes to `#netbar` (S-16).
3. **Empty** says what is missing and the next action (existing sentences; `.collect-now` where a collection fixes it).
4. **Stale or partial:** STATUS_KO badge `지연·오래됨` / `데이터 없음` next to the value it qualifies, plus the screen's basis stamp in PH. **Missing data is `—`, never 0.**
5. **Market switch** clears every tab (`setMarket`). Every async render keeps its `mk !== state.market` guard; skeletons show at once on the new market.
6. **Return refresh** (TD-25 on 오늘) keeps its wording. The dimming applies only to the panel being refreshed (`#asst-brief`), not to the answer area (it already does this). A `갱신 중…` line is the only indicator.

| Screen | Loading | Empty | Error | Stale / partial |
|---|---|---|---|---|
| Shell | DT `수집 상태…`; MS `시장 상태 불러오는 중…` | — | `#netbar` (S-16); `#verbar` on a new screen version (S-17) | DT `(마지막으로 읽은 값)` |
| 오늘 | brief skeleton (headline line, 6 tiles, 2×5 candidate rows) | `보여 줄 항목이 없습니다.`; candidates `…인 종목이 없습니다` | `오늘 목록을 만들지 못했습니다: …` + 다시 시도 | `읽지 못한 부분: …` (TD-14); refresh-on-return line (TD-25) |
| 시장 개요 / 지도 / 거시 | section 8.7 | | | |
| 종목 정보 | section 6.6 | | | |
| 관심종목 | skeleton rows | `관심종목이 없습니다.` | `errBox` | `스캔 없음` / `스캔 밖` cells (WA-05) |
| 차트분석 | canvas placeholders at phone/desktop heights | `이 기간에 고전 신호가 없었습니다.` | `가격 자료를 받지 못했습니다…` (CH-12) | `가격 기록이 고른 기간보다 짧아…` (CH-11) |
| 비교 | chart placeholder | chips `아직 없습니다.`; chart `비교할 종목을 추가하세요.` | `비교할 가격을 받지 못했습니다.` (UNAVAILABLE) | `가격 없음: …` |
| 통합 계좌 / 시장별 자세히 / 매매 보조 / 모의 매매 | section 7.7 | | | |
| 순위·카드 (rank) | section 4.5 | | | |
| 순위·카드 (screen) | skeleton rows | `조건에 맞는 종목이 없습니다.` | `조건을 읽지 못했습니다` | formula-version notice (QS-09) |
| 순위·카드 (exec) | per panel | `기록된 스캔이 없습니다`; NO_ACCOUNT + `통합 계좌에서 기록하기` (QE-02); paper book `아직 기록이 없습니다…` | `errBox` | `판정 전 참고`, `가상의 금액` badges (QE-06) |
| 순위·카드 (track) | per fold | per panel `아직 기록이 없습니다` | silent skip today for record/validation (QR-05, QT-09). **Change:** a one-line `불러오지 못했습니다` instead of silence, so a missing panel is visible. | integrity badges (QT-08, QT-09) |
| 투자위원회 | `불러오는 중…` | `억지로 채우지 않습니다` (IC-04); ports landing (IC-05) | `errBox` | — |
| 모델 | per panel | `추천 종목 없음` / `기록된 전체 스캔이 없습니다.` | error line | `더 최근 스캔…` notice (MO-04) |
| 연구실 | `과거 시뮬레이션 계산 중… (처음에는 수십 초…)` | KR gate (LB-09); unavailable (LB-13) | `추적 기록을 읽지 못했습니다` | `점검 결과 없음` |
| 코인 | skeleton | UNAVAILABLE (CO-05) | `errBox` | stale warning (CO-04) |

---

## 11. Actions that write data: how each stays safe

There are five `confirm(` calls today; `tests/test_ui_batch_4.py:116` pins the count at 5: three record voids, phone off, and the fund-period basis. Paired phones may only POST to `PHONE_WRITES` (journal add/void, paper add/void, watchlist add/remove, alerts add/remove/rearm, assistant ask). Every other POST is refused with `PHONE_MAC_ONLY` (`server.py:305`).

### 11.1 The five actions named in the brief

| Action | Control → endpoint | What it changes | Today's guard | Specified guard |
|---|---|---|---|---|
| **Stance** 방어/보통/공격 | `#qsfstanceseg button[data-level]` → `POST /api/qsf/stance {market, level}` | the per-market stance setting: candidate marks and real-plan sizes, never the score | no confirm; clicking the current level is a no-op; **not disabled while in flight**; on a phone the server refuses (toast) | (1) Disable the segment and set `aria-busy` while in flight. (2) On success, an info toast `{시장} 성향을 '{label}'(으)로 바꿨습니다. 후보 표시와 주문 크기가 달라집니다. 점수는 그대로입니다.` with **[되돌리기]** for 9 s. It POSTs the previous level, the same endpoint. (3) On `html.on-phone` the segment renders disabled with the caption `성향은 컴퓨터에서 바꿉니다`. **No modal confirm** [O-5]: the owner asked for the stance in plain sight, one click away. |
| **Rules switches** TO-1 / RK-1 `이 규칙 쓰기 / 쓰지 않기` | `.qsf-rule-switch` → `POST /api/qsf/turnover-rules` / `/api/qsf/rank-rules {market, on}` | whether the rule set is used (a setting) | appears only when DECIDED and the `.env` mode is auto; disabled in flight; reason inline on failure; hidden on a phone | Add an **inline two-step confirm** [O-5]. The first click replaces the button with `{규칙 이름}을(를) {쓰기/끄기}로 바꿉니다. 다음 주문 계획부터 적용됩니다. [바꾸기] [취소]`, focus on `취소`, auto-revert after 15 s. The existing in-flight disable, inline reason and `notify(r.note)` stay. In the redesigned exec view the TO-1 and RK-1 blocks move out from between the paper-book tables into their own L section `규칙 비교`, so the only buttons that change behaviour are not buried (inventory weakness QE §3). |
| **Fund period** 연간 ↔ 최근 4분기 | `.qsf-fund-switch` → `POST /api/qsf/fund-period` | the score input basis from the next scan (both strategies) | `confirm()` with the verbatim text; result toast; table re-read | Keep the `confirm()` text verbatim. If [O-6] is accepted, the same text goes into the in-page dialog (section 11.3). Move the button out of the table cell into a row footer line under its reading, so it is not inside a 5-column cell on the phone. Hidden on a phone (server refuses; add `on-phone` hiding like `.qsf-rule-switch`). |
| **Portfolios button** `여섯 포트폴리오 받아보기` / card `포트폴리오 받아보기` | IC-05/06 → `GET /api/committee/portfolios`; IC-14 `.ic-place` → `GET /api/committee/place` | **nothing stored.** It computes on request and caches in the page only (`icState.ports`) | the card button disables and shows `작성 중…` | No confirm needed. State it: a meta line under both buttons `계산만 하고 저장하지 않습니다.` The landing button also disables while computing. The double-request guard on `다시 받아보기` matches `icPlace`. |
| **Account form** `기록 추가` | `#acctform` submit → `POST /api/journal/add` | appends one journal record (append-only; corrections are VOID records) | client checks (style required, code-shape warnings, AC-13/14); **the submit button is not disabled while in flight** (`account.js:81-91`), so a double click can append two records | (1) Disable `기록 추가` and set `aria-busy` while posting (same for `#ptform` paper add and the alert add). (2) **No pre-submit confirm** [O-9]: the form is the confirmation, and voids exist. (3) The success line becomes `기록했습니다: {종류} {종목} {수량}주 · {계좌}. 다시 불러오는 중…`, built from the submitted fields, not from data files. Next to it, **[방금 기록 취소]** calls the existing void route with the existing confirm text. (4) The form never auto-submits: `acctRecord()` prefill only fills and focuses (AC-15); AS-04's auto-submit is the calculator, which is read-only. |

### 11.2 Other writes (kept; listed so the regression pass checks them)
| Action | Guard |
|---|---|
| Record void ×3 (account, portfolio, paper) | `confirm()` verbatim (AC-17, PF-14, PT-09) |
| 폰 연결 끄기 | `confirm()` verbatim (PH-05) |
| 지금 수집 | no confirm (re-running skips finished steps); disabled while running; hidden on a paired phone |
| 관심종목 ✕ | no confirm today. **Add** an undo toast `삭제했습니다 · [되돌리기]` (re-adds through the existing add route). The ✕ keeps `button.x` so a row click does not fire. |
| 위험 관리 설정 저장 (AS-07), 투자 자본금 저장 (MO-02), 한국 스캔 실행 (MO-03), 데이터 갱신 + 오늘 신호 기록 (MO-09) | unchanged; each shows its result line. They are server-refused on a phone; hide them under `html.on-phone`, like the rule switches. |
| Alerts add/remove/rearm | unchanged; `지금 확인` stays a preview that does not send or record (AL-06) |

### 11.3 In-page confirm dialog [O-6] (if accepted)
- **Component:** `ui.confirm(text, okLabel)` returns a Promise. It renders a `role="alertdialog"`, `aria-modal="true"` box in the z-dialog layer.
  - The text is verbatim. Buttons: `[취소]` (default focus) and `[{okLabel}]`.
  - Esc or a backdrop click means 취소. Focus returns to the invoking control.
- **Use it for exactly the five existing `confirm()` calls.** Update `test_ui_batch_4.py:116` in the same commit; the count moves to `ui.confirm(`.
- **Why:** native dialogs look different on the phone, cannot be styled for dark mode, and block the page's live regions (roadmap P3-5).

---

## 12. Phone (390 px) essentials

1. **Top bar 48 px:** market switch · search · DT short label. Brand hidden ≤380 (existing). 내 계좌, 지금 수집, ⌘K, theme and 폰 연결 stay in BB and 더보기 (S-08…S-13).
2. **Bottom bar 56 px** (unchanged) and the 더보기 sheet listing tabs per group (section 9.6).
3. **Sticky sub-tab strip** 40 px for groups with ≥2 tabs.
4. **R and L stack:**
   - R content renders before M only where it is the verdict: the stock screen's score summary, and 통합 계좌 totals;
   - everywhere else R follows M;
   - L section tabs become a scrollable segment.
5. **Tables keep the decision columns:** rank rows two lines with 판단 + 진입 always visible (roadmap P1-10, built); 오늘 candidates the same; holdings rows show 종목, 판정, 손익 % and fold the rest into a tap-to-expand row.
6. **Tap targets ≥ 40 px** (existing coarse-pointer rule). Title-only explanations reach the touch user through `#taptip` (S-30). Every risk sentence that matters (합병, 자금조달) is a visible text line (QR-28), not only a title.
7. **The stance segment** stays visible in the qsf view row (owner request) and is disabled on a paired phone (section 11.1).
8. **`맨 위로`** button on long pages (rank with an open inline card, 시장별 자세히).
9. **No hover-only information:** chart crosshairs work by finger drag (chart.js already does; compare charts get the same, UXW-13).

---

## 13. Decisions needed from the owner

| ID | Question | Recommendation | What it changes |
|---|---|---|---|
| **O-1** | Show a **score summary from the recorded scan** in the stock screen's right column (existing `/api/qsf/latest` row: score, band, entry, gate, rank, domain bars, risk lines), with `점수 카드 열기` for the full card? | Yes | The stock screen shows scan-time values without a slow evaluate. They are labelled `스캔 기록 {session}`. No new number. |
| **O-2** | On workstation screens (순위·카드 rank and screener ≥1280, 시장별 자세히 holdings, 관심종목), should a **row click select the row and fill the right panel** (card, or 보유 점검) instead of expanding inline or navigating? The name/code still opens the stock screen; inline expansion stays as a `▸` button and below 1280. | Yes | Changes what a row click does on four tables. Screener → card no longer leaves the screener. |
| **O-3** | Row selection writes `#qsf/CODE` with **replaceState** (Back leaves the screen) instead of pushState (Back walks through every selected row)? | replaceState | Back-button behaviour on the ranking |
| **O-4** | Add a **"늦음" (behind) state** to the data-time chip? It needs a server field from `markets/session_data.py`. | Not now; show stamps only | No client-side freshness threshold is invented |
| **O-5** | Confirmation for the **stance** and **rules switches**: stance = no modal, an undo toast instead; rules = an inline two-step confirm? | As stated | One extra click on the rules switch; none on stance |
| **O-6** | Replace the five native `confirm()` dialogs with one **in-page dialog** using the same texts? | Yes | Look and dark mode only; a test pin moves |
| **O-7** | Extend the hash to **`#committee:view`** and **`#assist:section`** (deep links and Back for committee views and 매매 보조 sections)? | Yes | Back now returns to the previous committee view; `알림 걸기` deep link |
| **O-8** | Should '사도 돼?' on the stock screen **answer inside the stock screen** (second host of the verdict box) or keep navigating to 오늘? | Keep navigating to 오늘 for now | One host for TD-V1 |
| **O-9** | Account form: keep **no pre-submit confirm**, and add in-flight disable + `방금 기록 취소`? | Yes | Prevents duplicate records from a double click |
| **O-10** | Number shortcuts `1`–`9` follow the **visible** group order (fixes the help text `1~6`; in COIN, 코인 becomes `2` instead of `8`)? | Yes | Minor shortcut change in COIN |
| **O-11** | Hide the market-state chip in the **COIN** market (no coin market-state score exists)? | Yes | T shows no chip in COIN |

---

## 14. Friction register (all workflows) and feature-location changes

### 14.1 Friction found and fix (every feature kept)
| ID | Workflow | Friction | Fix | Decision |
|---|---|---|---|---|
| UXW-01 | 1 | no permanent run/freshness indicator | DT chip + popover | O-4 for "늦음" |
| UXW-02 | 1 | status bars grow the sticky header | NR rail | — |
| UXW-03 | 1 | collect result sentence mixes errors and paths | two-line layout, same text | — |
| UXW-04 | 2, 5 | stock screen has no model view | R score summary | O-1 |
| UXW-05 | 2, 5 | four equal header buttons | primary `점수 카드 열기` in R; action group | — |
| UXW-06 | 2 | '사도 돼?' only by typing | stock-screen button | O-8 (host) |
| UXW-07 | 3 | card in three positions | R host ≥1280; inline kept | O-2 |
| UXW-08 | 3 | screener → card leaves the screener | R card in place | O-2 |
| UXW-09 | 3 | view/strategy/stance look alike | grouped PH line 2 | — |
| UXW-10 | 3 | slow evaluate shows only a text line | R placeholder + row busy marker | — |
| UXW-11 | 4 | adding to the comparison always navigates | `compareAdd` + toast | — |
| UXW-12 | 4 | code-only compare add | name suggestions | — |
| UXW-13 | 4, 12 | mouse-only chart tooltips | pointer events | — |
| UXW-14 | 4 | two "비교" | sub-label + cross-link | — |
| UXW-15 | 6 | 보유 판정 far from holdings; cells jump | R 보유 점검; reserved widths | O-2 |
| UXW-16 | 6 | alerts far from the stock | `알림 걸기` + `#assist:alerts` | O-7 |
| UXW-17 | 6 | 매매 보조 has no sub-navigation | SN | — |
| UXW-18 | 6 | trade form below big tables | L under M | — |
| UXW-19 | 7 | market state only on two screens | MS chip | O-11 |
| UXW-20 | 7 | sector picks appear three panels down with auto-scroll | R under RRG | — |
| UXW-21 | 7 | calendar above the indicators on 거시 | indicators M, calendar R | — |
| UXW-22 | 8 | two-step group → sub-tab navigation | left nav items | — |
| UXW-23 | 8 | number keys index hidden groups; help says 1~6 | visible order, computed help | O-10 |
| UXW-24 | 8 | phone sub-tab row not sticky | sticky strip | — |
| UXW-25 | 8 | ALWAYS_FRESH tabs lose scroll on Back | restore after render | — |
| UXW-26 | 10 | panel errors have no retry (stock, ranking) | `다시 시도` per panel | — |
| UXW-27 | 10 | track panels fail silently | one-line `불러오지 못했습니다` | — |
| UXW-28 | 11 | account / paper / alert submit not disabled in flight (duplicate append) | in-flight disable | O-9 |
| UXW-29 | 11 | stance not disabled in flight; stance and fund switch shown on a phone that the server refuses | in-flight disable; `on-phone` hiding with caption | O-5 |
| UXW-30 | 11 | rules switches buried between paper-book tables | own L section `규칙 비교` | O-5 |
| UXW-31 | 11 | watchlist ✕ deletes with no undo | undo toast | — |
| UXW-32 | 3 | 오늘 candidate score not clickable (breaks the batch-6 click rule) | score → card | — |

### 14.2 Features whose location changes (within their screen unless noted)
| Inventory IDs | From | To |
|---|---|---|
| S-14…S-17 (`#collectbar`, `#phonebar`, `#netbar`, `#verbar`) | inside `.top` | NR under T (same ids) |
| S-18, S-19 (`#groups`, `.tabs`) | horizontal rows | left nav N (same `data-*`) |
| S-26 more sheet | groups only | groups with their tabs |
| ST-03…ST-11 | one header panel | PH (name, price) + R (facts) + L (description) |
| ST-19…ST-21 | stacked panels | L section tabs |
| OV-01/02 | card grids | M tables + R sparkline cards (proposal for the layout spec) |
| MA-04 / CAL-* | above the macro cards | R beside them |
| RO-01, SP-01/02 | stacked; picks far below | R (RRG + picks) |
| QS-05 CSV | in the form | beside the count line |
| QS-07 score button | switches to the rank view | R card in place (O-2) |
| QE-07/08, QE-09 rules blocks | between paper-book tables | own L section `규칙 비교` |
| QT-03 fund switch | inside a table cell | row footer line |
| PF-08 `#sigpanel` | 4 panels below the holdings | R 보유 점검 |
| PF-10…PF-14 | stacked panels | L tabs |
| AS-01…AS-08 | stacked panels | SN sections |
| AL-01…AL-06 | inventory says the portfolio tab | **correct screen is 매매 보조** (no move; inventory correction) |
| CP-07/08/09 | under the chart | L tabs (`기간 성과` default) |
| TD-13…TD-23 | one column | PH (headline, stamp) · M (question, answer, 할 일과 알림) · R (tiles, market state, candidates) · L (작업 상태, note), as in the inventory's screen map |

Nothing in this specification removes a feature, a text that tests pin, an endpoint call, or a stored value.
