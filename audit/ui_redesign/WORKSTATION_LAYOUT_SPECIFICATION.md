# Workstation layout specification

Written 2026-11-24 by the workstation layout designer (agent 2), before any redesign code changes.
Baseline commit: `7c8e0af` on `main`.

Inputs:
- The shared brief (owner decisions 1-6).
- `EXISTING_UI_FEATURE_INVENTORY.md` (421 rows).
- `terminal/static/index.html`, `style.css`, and the screen scripts (`app.js`, `qsf.js`, `assistant.js`, `account.js`, `portfolio.js`, `paper.js`, `committee.js`, `map.js`, `rotation.js`, `sectorpicks.js`, `peers.js`, `chart.js`, `compare.js`, `lab.js`, `coin.js`, `calendar.js`, `alerts.js`, `command.js`, `collect.js`, `phone.js`, `theme.js`, `ui.js`).

This document covers layout only: shell, grid, regions, ordering and widths. Colour values, type scale and table styling are named here as tokens. Where a separate design-token or table spec gives values, those values win. Where none exists, the values in section 1.2 apply.

**Nothing in this spec changes a score, a rule, an API call's meaning or a stored value.**
- Every inventory row keeps its screen.
- Rows only change region inside their screen.
- Section 4 lists every prefix.
- Section 6 lists the places that need the owner's decision.

---

## 0. Conventions and two inventory corrections

**Region names.** Every analytical screen is one `.ws` (workstation) block with up to four regions:

| Region | Class | Role |
|---|---|---|
| Context bar | `.ws-ctx` | Screen title, freshness line, notices, the screen's own controls. Full width. Scrolls away. Not a card. |
| Main | `.ws-main` | The primary table or chart. Left column. |
| Right | `.ws-right` | Analytics or tools that complement the main region and never duplicate it. Sticky column with its own scroll. |
| Lower | `.ws-lower` | Supporting panels (risk, records, notes, folds). Full width under main and right. |

**ID collisions in the inventory.** Two prefixes are used twice. This spec names them apart:
- `CO-01..08` in Part A is the collect bar; written **CO-a-xx** here. `CO-01..08` in Part C is the coin tab; written **CO-c-xx**.
- `MO-01..03` in Part A and `MO-01..11` in Part C both describe the model tab. Part C's numbering is used here (**MO-xx**). Part A's MO-01..03 equal Part C's MO-01/MO-06 (tab), MO-02 (capital) and MO-03 (scan button).

**Correction to Part A.**
- The AL rows (alert centre, `alerts.js`) are rendered into `#alertc` inside **`renderAssist`** (`portfolio.js:204`, `:243`). That means the **매매 보조 (assist)** tab, not 시장별 자세히.
- AL-01..06 and AS-05 are the same feature. Both are placed in the assist tab.

**Breakpoints.** Viewport media queries stay at the existing four widths: 640/641, 1023/1024 (and 380/400 for phone fine-tuning). The `1279/1600` rank-table rules are replaced; see section 2.7.

Workstation columns are decided by **container queries on the content column**, not by the viewport. This is needed because the left menu's width (232 / 72 / 0 px) changes the space available.

---

## 1. Application shell

### 1.1 DOM skeleton (index.html after the change)

```html
<header class="top">
  <button id="navtoggle" class="ghost nav-toggle" type="button" aria-controls="side" aria-expanded="true" aria-label="메뉴 접기">☰</button>
  <div class="brand">퀀트 터미널 <span class="ver">QSF</span></div>
  <span class="seg" id="market" role="group" aria-label="시장">…unchanged 미국/한국/코인…</span>
  <form id="search" class="search" autocomplete="off">…unchanged #q + 조회…</form>
  <span class="top-chips">
    <button type="button" id="mstate" class="top-chip" hidden></button>     <!-- market state (new view of existing data) -->
    <button type="button" id="datatime" class="top-chip" hidden></button>   <!-- data time (new view of existing data) -->
  </span>
  <span class="top-acts">
    #acctbtn #collect #phonebtn #cmdbtn #keysbtn(hidden, unchanged) #theme   <!-- same elements, same ids, same titles -->
  </span>
  <button id="topmore" class="ghost" type="button" aria-haspopup="true" aria-expanded="false" aria-controls="topmenu" aria-label="도구 더 보기">⋯</button>
</header>
<div class="topmenu" id="topmenu" role="dialog" aria-label="도구" hidden></div>
<div class="statusbars" id="statusbars">#collectbar #netbar #verbar #phonebar</div>   <!-- moved out of <header>, ids unchanged -->
<div class="shell">
  <aside class="side" id="side" aria-label="메뉴">
    <nav class="groups" id="groups" aria-label="묶음">…unchanged 8 buttons…</nav>   <!-- kept for keys 1-9 and 더보기; never shown -->
    <nav class="tabs" aria-label="탭">                                               <!-- the left menu; `hidden` attribute removed -->
      <div class="nav-grp" data-group="today" role="group" aria-labelledby="nh-today">
        <span class="nav-h" id="nh-today">오늘</span>
        <button data-tab="today" data-group="today" class="on">오늘</button>
      </div>
      <div class="nav-grp" data-group="market" role="group" aria-labelledby="nh-market">
        <span class="nav-h" id="nh-market">시장</span>
        <button data-tab="overview" data-group="market">시장 개요</button>
        <button data-tab="map" data-group="market">시장 지도</button>
        <button data-tab="macro" data-group="market">거시</button>
      </div>
      …종목 (stock, watch) · 차트 (chart, compare) · 내 계좌 (account, portfolio, assist, paper) · 점수 (qsf, committee) ·
      검증·기록 (model, lab) · 코인 (coin)…
    </nav>
  </aside>
  <div class="content">
    <main>…17 unchanged <section id="tab-*" class="tab"> + #pagetitle…</main>
    <footer class="foot">…unchanged text… <span id="health"></span></footer>
  </div>
</div>
<div class="scrim" id="navscrim" hidden></div>
#tip #toast #bottombar #moresheet (unchanged, body level)
```

Rules for this structure:
1. Every tab button keeps the exact attribute order `<button data-tab="X" data-group="Y">` (pinned by `test_ui_groups.py`). Tab order inside `.tabs` stays the groups' order.
2. Group headings are `<span>`, never `<button>`. Two reasons:
   - `app.js:400` binds every `.tabs button` to `show(b.dataset.tab)`.
   - `command.js:17` lists every `.tabs button` as a tab.
3. Nothing with `position: fixed` may live inside `.content`. `.content` is a size container, and container queries apply layout containment, which would trap fixed descendants. Today, `#tip`, `#toast`, `#taptip`, `#cmd`, `#moresheet` and `#topmenu` are all body-level, and `#phonebar` is in `.statusbars`, which is outside `.content`.

### 1.2 Layout tokens (added to `:root`)

```css
:root {
  --top-h-min: 48px;                 /* top bar height at every width ≥ 641 px and the phone header's min-height */
  --nav-full: 232px; --nav-rail: 72px; --nav-drawer: 264px;
  --nav-cur: var(--nav-full);        /* set by html[data-nav] below; 0 at ≤ 1023 px */
  --page-pad: 16px;                  /* 24px at ≥ 1600 px, 12px at ≤ 640 px */
  --gutter: 16px;                    /* between main and right, between lower panels; 12px at ≤ 640 px */
  --ws-gap: 12px;                    /* between stacked panels inside one region */
  --ws-right: 360px;                 /* 420 / 480 by content width (2.3) */
  --ws-max: 1760px;                  /* widest workstation block; centred in the content column */
  --ws-narrow: 1280px;               /* single-column form screens (stock without a ticker) */
  --z-scrim: 12; --z-drawer: 13;     /* between --z-header (10) and --z-popover (20) */
}
html[data-nav="rail"] { --nav-cur: var(--nav-rail); }
@media (min-width: 1600px) { :root { --page-pad: 24px; } }
@media (max-width: 1023px) { :root { --nav-cur: 0px; } }
@media (max-width: 640px)  { :root { --page-pad: 12px; --gutter: 12px; } }
```

**Colour tokens.** The layout uses these colour tokens. Dark is the default per owner decision 3.
- Values follow the brief's starting palette unless the token spec says otherwise.
- The light block keeps the same names.

| Token | Dark | Light | Used by |
|---|---|---|---|
| `--bg` | `#0B1018` | `#F4F6F9` | page, `.ws-ctx` background (transparent over `--bg`) |
| `--bg-2` (new) | `#101722` | `#FFFFFF` | top bar, side menu, status bars, bottom bar |
| `--panel` | `#151E2B` | `#FFFFFF` | `.panel` in every region |
| `--panel-2` (new) | `#1B2635` | `#F8FAFC` | popovers (`#topmenu`, `#phonebar`, `.sug`), drawer |
| `--line` | `#273446` | `#DDE3EA` | region and panel borders, nav separators |
| `--accent` | `#3B82F6` | `#2457D6` | active nav bar, focus ring |
| `--nav-active` (new) | `color-mix(in srgb, var(--accent) 16%, transparent)` | same formula | active nav item background |

The owner decides only the default. The cycle stays `auto → light → dark`.

**Theme default.** In `theme.js` and `app.js`, `localStorage.getItem("qse-theme") || "auto"` becomes `|| "dark"`. The ◐ cycle and the `qse-theme` key stay.

`theme.js` also sets the menu state before first paint, so the page does not jump:

```js
var n = null; try { n = localStorage.getItem("qse-nav"); } catch (e) {}
document.documentElement.setAttribute("data-nav", n === "rail" ? "rail" : "full");
```

### 1.3 Top bar

**Base box (≥ 641 px).**
- `position: sticky; top: 0; z-index: var(--z-header)`.
- Height exactly 48px: `min-height: var(--top-h-min)`, `flex-wrap: nowrap`.
- Background `--bg-2`, bottom border `--line`.
- Padding `0 var(--page-pad)` (at 1600+ that is 24px).
- `display: flex; align-items: center; gap: 8px`, plus an extra 8px margin between clusters: brand | market | search | chips | actions.

**Element sizes.**

| Element | Size and style |
|---|---|
| `#navtoggle` | 32×32, glyph ☰. Hidden at ≤ 640 px. |
| Brand | 15px/700. `.ver` 12px muted. Unchanged hide rules (S-01). |
| `#market` seg | Buttons 30px high, padding `0 10px`. |
| Search | Input 32px high. `flex: 1 1 320px; min-width: 220px; max-width: 320px` (440px at ≥ 1600). Suggestions `#qsug` unchanged (absolute under the input, z popover). |
| `.top-chip` | Height 26px, `border-radius: var(--r-pill)`, `background: var(--chip)`, `font: 12px/1 tabular-nums`, padding `0 10px`, `white-space: nowrap`. A chip is a button (focusable, `title` gives the long text). |
| Action buttons | `.ghost`, height 32px, padding `0 10px`, 13px. |
| `#topmore` | 32×32, glyph ⋯. |

**Left → right order.**

`☰ · 퀀트 터미널 QSF · [미국|한국|코인] · [search ……][조회] · (market state chip) (data time chip) · ⟶ · 내 계좌 · 지금 수집 · 폰 연결 · ⌘K · ◐ · ⋯`

**Market state chip `#mstate`.** This is the owner-required "market state" (decision 4). It shows existing data only.
- Source: `GET /api/qsf/market-state?market=` (the same endpoint the qsf strip uses), via the existing `qsfStateShort(ms)`.
- Shows, for example, `시장 상태 62/100 · 보통`, plus the amber `새 주문 크기 50%` badge when `size_factor < 1` (QR-02 wording).
- If the read fails: `시장 상태 읽지 못함`, never 0.
- Hidden in the COIN market (there is no coin market-state record).
- Click: `show("qsf")`, then `$("#qsfstrip").open = true` (the strip sits in the qsf right panel at workstation widths; see 3.13).
- Loaded on boot, on `setMarket`, and after `collect.js` "화면 새로 고침" (CO-a-05).

**Data time chip `#datatime`.**
- Source: `GET /api/automation/status`, already read by `collect.js` on load and by `lab.js automationLine()`.
- Text: `기준 거래일 {last_run.session} · 수집 {stamp(last_run.at)}`.
- Plus an amber `빠진 거래일 N` when `last_run.missing_sessions.length`.
- If there is no run record: `실행 기록 없음`.
- `title` = the full `automationLine()` sentence.
- Click: `show("lab")`, where the 자동 실행 key-value group (LB-08) is.
- Re-read when `collect.js` sees a run finish.

**Collapse ladder.** Collapsed controls go into the `⋯` menu. They are never removed.

| Width | Visible in the bar | In `⋯` (`#topmenu`) |
|---|---|---|
| ≥ 1440 | everything above; `⋯` hidden | — |
| 1280–1439 | ☰, brand, market, search, both chips (data chip short form: `{session} 기준`), 내 계좌, 지금 수집, ⌘K, ⋯ | 폰 연결, 화면 테마 ◐, 한 글자 단축키 |
| 1024–1279 | ☰, brand, market, search, state chip short form (`상태 62`), ⌘K, ⋯ | data time line, 내 계좌, 지금 수집, 폰 연결, 화면 테마, 한 글자 단축키 |
| 641–1023 | ☰, brand (`.ver` hidden), market, search (`flex: 1; min-width: 160px; max-width: none`), ⋯ | market state line, data time line, 내 계좌, 지금 수집, 폰 연결, 명령창, 화면 테마, 한 글자 단축키 |
| ≤ 640 | Unchanged phone header (brand, market, search in one 48px line). ☰ and ⋯ hidden. | — (the existing 더보기 sheet carries the tools; its "도구" row gains the two status lines as `.meta` text above it) |

**`⋯` menu `#topmenu`.**
- Built by the same code that builds the phone's 더보기 "도구" row. Generalise `moreOpen()` into `toolsHtml(where)`, reusing `MORE_ACTS`.
- Each item clicks the original hidden header button, so `#collect`, `#phonebtn`, `#cmdbtn`, `#theme` and `#keysbtn` stay the only implementations.
- Same rules as the more-sheet: `지금 수집` omitted on a paired phone (`.on-phone`); the label of 폰 연결 / 한 글자 단축키 is read from the button.
- The two chip texts appear at the top as `.meta` lines when the chips are hidden.
- Popover:
  - `position: fixed; top: calc(var(--top-h) + 4px); right: var(--page-pad); width: 280px`.
  - Background `--panel-2`, `--shadow-2`, `z-index: var(--z-popover)`.
  - Closes on Esc, outside click and any choice. Focus returns to `#topmore`.
  - `aria-expanded` is kept on `#topmore`.
- CSS hides the original buttons at the widths where they sit in the menu, in the same way the phone block does today (`#phonebtn, #theme { display: none }` etc.). The elements stay in the DOM, so `.click()` from the menu works.

### 1.4 Left vertical menu (`aside.side` holding `nav.tabs`)

**States.**

| Viewport | State | Width | How it shows |
|---|---|---|---|
| ≥ 1024 | `html[data-nav="full"]` (default) | 232px | In-flow grid column, sticky |
| ≥ 1024 | `html[data-nav="rail"]` | 72px | In-flow grid column, sticky |
| 641–1023 | drawer, closed by default | 0 in flow / 264px when open | Fixed overlay over the content, scrim behind |
| ≤ 640 | phone | — | The aside becomes the existing sub-tab strip under the header (current phone behaviour); the bottom bar and 더보기 sheet stay |

**Shell grid (≥ 1024).**

```css
.shell { display: grid; grid-template-columns: var(--nav-cur) minmax(0, 1fr); align-items: start; }
.side  { position: sticky; top: var(--sticky-top); height: calc(100vh - var(--sticky-top)); overflow-y: auto;
         overscroll-behavior: contain; background: var(--bg-2); border-right: 1px solid var(--line); z-index: var(--z-header); }
.content { container: content / inline-size; min-width: 0; padding: var(--page-pad) var(--page-pad) 0; }
main { max-width: none; margin: 0; padding: 0; }          /* replaces main { max-width: var(--content-max) } */
.groups { display: none !important; }                     /* replaces the sticky group bar; the element stays */
```

`main.wide` keeps its JS toggle (`WIDE_TABS`, pinned by tests) but no longer limits width. The `.ws` block carries the maximum (`--ws-max`).

**Expanded menu (232px).**

Group heading `.nav-h`:
- `display: block; padding: 14px 16px 4px`.
- `font: 600 11px/16px` system font, `letter-spacing: .02em`, `color: var(--muted)`.
- The first group has `padding-top: 8px`.

Item `.tabs button`:
- `display: flex; align-items: center; width: calc(100% - 16px); margin: 0 8px; height: 32px; padding: 0 12px`.
- `border: 0; border-radius: var(--r-md); background: none; color: var(--muted); font-size: 13px; text-align: left; white-space: nowrap`.

States:
- Hover: `background: var(--hover); color: var(--ink)`.
- Active (`.on` + `aria-current="page"`, set today by `show()` and `paintTitle()`): `background: var(--nav-active); color: var(--ink); font-weight: 600; box-shadow: inset 3px 0 0 var(--accent)`.
- Focus: `outline: 2px solid var(--accent); outline-offset: -2px`.

Single-item groups:
- A group that has one visible item in the current market shows **no heading**. Today that is 오늘 and 코인 always, and 내 계좌 in COIN.
- `paintGroups` sets `data-single` on the `.nav-grp`. Its heading is then `display: none`, and a 1px `--line` separator (`margin: 8px 16px`) sits above the item instead.
- This avoids "오늘 / 오늘".

**Rail (72px).**
- Headings become `.sr-only`; the group label is still read through `aria-labelledby`. A visible 1px separator (`margin: 6px 12px`) sits between groups.
- Items: `height: auto; min-height: 44px; margin: 2px 6px; width: calc(100% - 12px); padding: 4px 6px; justify-content: center; text-align: center`.
- `font-size: 11px; line-height: 1.25; white-space: normal; word-break: keep-all`.
- The full Korean label stays visible on at most two lines. The longest are 시장별 자세히 and 투자위원회, and both fit 60px at 11px.
- Active marker and colours are the same as expanded.
- The rail scrolls vertically when 17 items exceed the height.

**Toggle `#navtoggle` (≥ 1024).**
- Flips `data-nav` between `full` and `rail`.
- Saves `qse-nav` (`"full" | "rail"`); unreadable storage means `full`.
- Sets `aria-expanded` (`true` = full) and `aria-label` (`메뉴 접기` / `메뉴 펼치기`).
- Calls `setTopH()` and `redrawAll()` once in the next animation frame, because every canvas width changes.
- No width animation: grid-column transitions reflow every frame.

**Drawer (641–1023).**
- `#navtoggle` opens it: `html[data-drawer="open"]`; label `메뉴 열기` / `메뉴 닫기`.
- `.side` becomes `position: fixed; top: var(--sticky-top); left: 0; bottom: 0; width: var(--nav-drawer)`.
- `transform: translateX(-100%)` → `0` with a 160ms `ease-out` transition (`none` under `prefers-reduced-motion`).
- `z-index: var(--z-drawer)`. Shows the expanded layout.
- `#navscrim`: `position: fixed; inset: var(--sticky-top) 0 0 0; background: rgba(0,0,0,.45); z-index: var(--z-scrim)`.
- Opening moves focus to the active item.
- Closes on any of the following, and focus returns to `#navtoggle`:
  - Esc,
  - a scrim click,
  - choosing an item,
  - `show()`,
  - resizing past 1023.
- The open state is not saved.

**Phone (≤ 640).**
- `#navtoggle` and the drawer are disabled.
- The `.side` element is shown as today's sub-tab row, not sticky, under the header:
  - `.side { position: static; height: auto; border: 0; border-bottom: 1px solid var(--line); background: var(--bg); overflow-x: auto }`.
  - `.nav-h, .nav-grp:not(.cur) { display: none }`.
  - `.nav-grp.cur { display: flex; gap: 2px; padding: 0 12px }`.
  - Items get today's sub-tab look: 13px, 2px accent underline when `.on`.
- When the current group has fewer than two visible tabs, the strip is hidden: `.tabs[data-single-cur] { display: none }` (S-19 behaviour).
- `#bottombar` and `#moresheet` are unchanged (S-25, S-26).

**`paintGroups(tab)` rewrite.** This is required, because today it hides every tab outside the current group and hides `.tabs` when the group has one tab, which would empty the left menu.

```js
function paintGroups(tab) {
  const g = groupOf(tab); if (!g) return;
  groupTab[g] = tab;
  document.querySelectorAll(".groups button").forEach((b) => { b.classList.toggle("on", b.dataset.group === g); b.toggleAttribute("aria-current", b.dataset.group === g); b.hidden = !groupShown(b.dataset.group); });
  document.querySelectorAll(".tabs .nav-grp").forEach((w) => {
    const items = [...w.querySelectorAll("button[data-tab]")];
    items.forEach((b) => (b.hidden = !groupShown(b.dataset.group) && !ANY_MARKET.has(b.dataset.tab)));   // market rule only
    const n = items.filter((b) => !b.hidden).length;
    w.hidden = n === 0; w.toggleAttribute("data-single", n === 1); w.classList.toggle("cur", w.dataset.group === g);
  });
  const cur = document.querySelector(`.tabs .nav-grp[data-group="${g}"]`);
  document.querySelector(".tabs").toggleAttribute("data-single-cur", !cur || cur.querySelectorAll("button[data-tab]:not([hidden])").length < 2);
  paintBar(g);
}
```

**Keyboard and aria.**
- The nav keeps `aria-label="탭"`. Each group is `role="group"` labelled by its heading.
- The active item carries `aria-current` (as today). In the drawer, the toggle carries `aria-expanded`.
- Roving focus:
  - Only the active item has `tabindex="0"`; the others have `-1`.
  - ArrowDown/ArrowUp move to the next/previous visible item across groups; Home/End go to the first/last.
  - Enter/Space activate (native button).
  - This keeps one Tab stop for 17 items.
- The `1`–`9` shortcuts (CM-12) are unchanged. They read `.groups button` order, which stays the side menu's group order.

### 1.5 Status bars

`#collectbar`, `#netbar` and `#verbar` move out of `<header>` into `<div class="statusbars" id="statusbars">`, placed right after the header (full viewport width, above the menu and content).
- `.statusbars`: `position: sticky; top: var(--top-h); z-index: var(--z-header)`.
- Each visible bar:
  - `display: flex; align-items: center; gap: 10px; min-height: 32px; padding: 4px var(--page-pad)`.
  - `border-bottom: 1px solid var(--line)`, 13px.
  - Text may wrap; nothing is cut.
- Bar colours:
  - collect: `--bg-2` with `inset 3px 0 0 var(--accent)`.
  - net: `inset 3px 0 0 var(--bad)`, text `--bad`.
  - ver: `inset 3px 0 0 var(--accent)`.
- Their contents and behaviour (CO-a-01..08, S-16, S-17) are unchanged.
- `setTopH()` sets two values, and observes both `.top` and `.statusbars` with the existing `ResizeObserver`:
  - `--top-h` = header height.
  - `--sticky-top` = header height + `.statusbars` height. The menu (at ≥ 1024) is never counted, because it is a column, not a row.

**Phone panel `#phonebar`.** It stays inside `.statusbars` in the DOM, but is drawn as a popover anchored under the 폰 연결 button, so its tall content no longer pushes the page:
- `position: fixed; top: calc(var(--top-h) + 4px); right: var(--page-pad); width: min(440px, calc(100vw - 2 * var(--page-pad)))`.
- `max-height: calc(100vh - var(--top-h) - 24px); overflow-y: auto`.
- `background: var(--panel-2); border: 1px solid var(--line); border-radius: var(--r-lg); box-shadow: var(--shadow-2); z-index: var(--z-popover); padding: 12px 16px`.
- At ≤ 640 px: `left: 8px; right: 8px; width: auto; top: auto; bottom: 64px` (a bottom sheet above the bottom bar).
- Its open/close (PH-01, PH-08), states and buttons (PH-02..06) are unchanged. It does not count toward `--sticky-top`.

### 1.6 Footer, toast, tooltips, palette

- **Footer `.foot`.** Inside `.content` after `main`: `max-width: var(--ws-max); margin: 0 auto; padding: var(--sp-3) 0 var(--sp-5)`. The text and `#health` are unchanged (S-27). On phone, `body { padding-bottom: 56px }` is unchanged.
- **Toast `#toast`.** The existing styles stay. `left: calc(var(--nav-cur) + (100vw - var(--nav-cur)) / 2)` centres it over the content column instead of the window. At ≤ 640, `bottom: 64px` is unchanged (S-28).
- **`#tip`, `#taptip`, command palette `#cmd`.** Unchanged (S-29, S-30, CM-*). The palette stays centred in the viewport.
- **Bottom bar and 더보기.** Unchanged, except the two status lines added to the sheet's "도구" heading (1.3).

### 1.7 Where every existing header control goes

| Control (ID) | ≥ 1440 | 1280–1439 | 1024–1279 | 641–1023 | ≤ 640 |
|---|---|---|---|---|---|
| Brand (S-01) | bar | bar | bar | bar (no `.ver`) | bar (≤ 380 hidden, unchanged) |
| Market switch `#market` (S-02, S-03) | bar | bar | bar | bar | bar |
| Search + suggestions (S-04, S-05) | bar | bar | bar | bar | bar |
| 내 계좌 `#acctbtn` (S-08) | bar | bar | ⋯ | ⋯ | bottom bar 내 계좌 (unchanged) |
| 지금 수집 `#collect` (S-09) | bar | bar | ⋯ | ⋯ | 더보기 (unchanged) |
| 폰 연결 `#phonebtn` (S-10) | bar | ⋯ | ⋯ | ⋯ | 더보기 (unchanged) |
| ⌘K `#cmdbtn` (S-11) | bar | bar | bar | ⋯ | 더보기 (unchanged) |
| 한 글자 단축키 `#keysbtn` (S-12) | palette footer + ⋯ menu (button stays `hidden` in the bar) | ⋯ | ⋯ | ⋯ | 더보기 (unchanged) |
| Theme ◐ `#theme` (S-13) | bar | ⋯ | ⋯ | ⋯ | 더보기 (unchanged) |
| Collect / net / version bars (S-14, S-16, S-17) | `.statusbars` (sticky band) | same | same | same | same |
| Phone panel (S-15) | popover under the bar | same | same | same | bottom sheet |
| Group row `#groups` (S-18) | never shown; replaced by the side menu (group heading + items); keys 1-9 still use it | same | same | drawer | bottom bar (unchanged) |
| Sub-tab row `.tabs` (S-19) | is the side menu | same | same | drawer | strip under the header (unchanged) |

---

## 2. Shared workspace grid (`.ws`)

### 2.1 DOM contract

```html
<div class="ws [ws--single] [ws--right-first]" data-ws="qsf" [data-view="rank"]>
  <div class="ws-ctx">…title, meta, notices, controls…</div>                  <!-- optional -->
  <div class="ws-body">
    <div class="ws-main">…</div>
    <div class="ws-right" role="complementary" aria-label="…">…panels…</div>   <!-- optional -->
  </div>
  <div class="ws-lower">…panels…</div>                                        <!-- optional -->
</div>
```

`.ws-body` is a separate box, so the sticky right column is bounded by `.ws-body` and never slides over `.ws-lower`. A sticky grid item's constraint box is its grid container.

Modifiers:
- **`.ws--single`**: one column at every width. The right panel's content stacks per the order rules below.
- **`.ws-right > .ws-first`**: in single-column mode, this right-panel child is placed **before** `.ws-main`. Other right children go after it.
  - This keeps today's reading order on tablet and phone (for example, the qsf card above the ranking, the account totals above the holdings).
- **`[data-view]` on `.ws`**: set by screens with views. qsf `exec` and `track` force single column (3.13).

### 2.2 CSS

```css
.ws { max-width: var(--ws-max); margin: 0 auto var(--sp-5); display: flex; flex-direction: column; gap: var(--gutter); }
.ws--narrow { max-width: var(--ws-narrow); }
.ws-ctx { display: flex; flex-wrap: wrap; align-items: center; gap: var(--sp-2) var(--sp-4);
          padding-bottom: var(--sp-3); border-bottom: 1px solid var(--line); }
.ws-ctx > h2 { margin: 0; font-size: var(--fs-xl); }                              /* the visible screen title */
.ws-ctx .ws-tools { margin-left: auto; display: flex; flex-wrap: wrap; gap: var(--sp-2); align-items: center; }
.ws-ctx > .notice, .ws-ctx > .msg, .ws-ctx > .meta, .ws-ctx > details { flex-basis: 100%; margin: 0; }
.ws-body { display: grid; grid-template-columns: minmax(0, 1fr); gap: var(--gutter); align-items: start; }
.ws-main { container: wsmain / inline-size; min-width: 0; display: flex; flex-direction: column; gap: var(--ws-gap); }
.ws-main > .panel, .ws-right .panel, .ws-lower > .panel { margin-bottom: 0; }    /* region gaps replace panel margins */
.ws-right { display: contents; }                                                   /* single column: children join .ws-body */
.ws-right > * { order: 1; min-width: 0; }
.ws-right > .ws-first { order: -1; }
.ws-lower { display: grid; gap: var(--gutter); grid-template-columns: repeat(auto-fit, minmax(min(100%, 520px), 1fr)); }
.ws-lower > .span-all, .ws-lower > .fold, .ws-lower > :only-child { grid-column: 1 / -1; }
.ws-lower:empty, .ws-ctx:empty { display: none; }

@container content (min-width: 1120px) {
  .ws:not(.ws--single) > .ws-body:has(> .ws-right > :not([hidden]):not(:empty)) {
    grid-template-columns: minmax(0, 1fr) var(--ws-right); }
  .ws:not(.ws--single) > .ws-body:has(> .ws-right > :not([hidden]):not(:empty)) > .ws-main { grid-column: 1; grid-row: 1; }
  .ws:not(.ws--single) > .ws-body:has(> .ws-right > :not([hidden]):not(:empty)) > .ws-right {
    display: flex; flex-direction: column; gap: var(--ws-gap); grid-column: 2; grid-row: 1; min-width: 0;
    position: sticky; top: calc(var(--sticky-top, 0px) + var(--gutter)); z-index: var(--z-raise);
    max-height: calc(100vh - var(--sticky-top, 0px) - 2 * var(--gutter)); overflow-y: auto; overscroll-behavior: contain;
    container: wsright / inline-size; }
}
@container content (min-width: 1320px) { .ws { --ws-right: 420px; } }
@container content (min-width: 1560px) { .ws { --ws-right: 480px; } }
```

With container queries, an empty right panel never takes a column. A right panel whose children are all empty or hidden gives a single-column page, which is the "no empty panels" rule.

Without container-query support, every screen stays single column. That is safe, and it is today's layout at < 1600 px.

**Helpers (app.js, next to `setTopH`).**

```js
const wsCanSplit = () => { const c = $(".content"); if (!c) return false; const s = getComputedStyle(c);
  return c.clientWidth - parseFloat(s.paddingLeft) - parseFloat(s.paddingRight) >= 1120; };
let wsRz; new ResizeObserver(() => { clearTimeout(wsRz); wsRz = setTimeout(() => { setTopH(); if (typeof qsfDockStrip === "function") qsfDockStrip(); redrawAll(); }, 120); }).observe($(".content"));
```

`redrawAll()` on content resize is required. A menu toggle changes canvas widths without a window `resize` event.

### 2.3 Proportions per breakpoint

Content width W = viewport − menu − 2 × page padding.
- The ws block is capped at 1760px.
- Two columns appear at W ≥ 1120px.
- The right panel is 360px for W < 1320, 420px for W < 1560, and 480px above.
- The main/right gutter is 16px.

| Viewport | Menu | Page pad | W | Mode | Right | Main |
|---|---|---|---|---|---|---|
| 1920 | full 232 | 24 | 1640 | two columns | 480 | 1144 |
| 1920 | rail 72 | 24 | 1800 → cap 1760 | two columns | 480 | 1264 |
| 1440 | full 232 | 16 | 1176 | two columns | 360 | 800 |
| 1440 | rail 72 | 16 | 1336 | two columns | 420 | 900 |
| 1280 | full 232 | 16 | 1016 | single column | — | 1016 |
| 1280 | rail 72 | 16 | 1176 | two columns | 360 | 800 |
| 1023 | drawer (0) | 16 | 991 | single column | — | 991 |
| 768 | drawer (0) | 16 | 736 | single column | — | 736 |
| 390 | phone (0) | 12 | 366 | single column | — | 366 |

At 1280 the owner gets the split by collapsing the menu to the rail. The full menu is the default (decision D4).

Height budget at 1440×900:
- Top bar 48 + no status bar → 852px of workspace.
- The right column's own scroll area is `100vh − 48 − 32` = 820px.

### 2.4 Scrolling rules

1. The **document** scrolls. Nothing in `main` becomes the page scroller.
   - Reason: `window.scrollY`, `tabScroll`, `RETURN[tab](scrollY)`, `scroll-padding-top` and every `scrollIntoView` call keep working unchanged.
2. **Sticky** elements, top to bottom:
   - `.top` (top 0),
   - `.statusbars` (top `--top-h`),
   - `.side` at ≥ 1024 (top `--sticky-top`, own scroll),
   - `.ws-right` in two-column mode (top `--sticky-top + gutter`, own scroll, `overscroll-behavior: contain`),
   - table headers `thead th` at `--sticky-top` (2.7).
3. **Not sticky:** `.ws-ctx` (it scrolls away; its controls are reached by scrolling up), `.ws-lower`, and the phone sub-tab strip (as today).
4. A `scrollIntoView` aimed at an element inside the sticky right column (for example, `#acctform-panel`, `#ptform`, `#szform`) scrolls that column. The browser does this natively. No code change is needed.
5. Horizontal overflow:
   - Only `.tbl-wrap` scrolls sideways (first column sticky, as today).
   - Never the page (batch 5 P3-13 rule kept).

### 2.5 Max widths, gutters, panel density

- **Workstation width.** `.ws` max 1760px, centred.
  - `.ws--narrow` (stock without a ticker) max 1280px.
  - The `--content-max` and `--content-max-wide` tokens stay defined for anything that still reads them, but `main` no longer uses them.
- **Gutters.** 16px between regions and lower panels; 12px between panels stacked inside one region (`--ws-gap`); 12px everywhere at ≤ 640.
- **Panels.**
  - `.panel` padding `12px 16px` in every region (today 16px).
  - `.panel h2` margin-bottom 8px.
  - Panels never nest inside panels. A right-panel block that today is a `.panel` inside another panel loses its border (`.ws-right .panel .panel { border: 0; padding: 0 }`, same as `.qsf-sec-body > .panel` today).
- **Context bar.** No card, no background, one bottom rule. The title is 18px (`--fs-xl`), and its meta line follows on the same row where width allows.

### 2.6 What every screen's right panel shows when nothing is selected

Each entry uses data the screen already loads (see section 3).

| Screen | Right panel with nothing selected |
|---|---|
| today | 오늘의 후보 (two candidate tables) |
| overview | 금리·환율·원자재 tiles (KR: 환율·대표 ETF) |
| map | 업종 순환 그래프 |
| macro | 경제 일정 |
| stock | Key figures, company description, 업종 내 위치 grades |
| chart | 지금 상태 + 최근 신호 |
| compare | 기간 성과 + 상관계수 |
| account | Totals + trade form |
| portfolio | Account summary + allocation |
| assist | 위험 관리 설정 |
| paper | Totals + entry form |
| qsf | Market state, stance and past record (the strip body) |
| committee | The view's summary |
| model | Capital and last-scan box |
| lab | Recording status |
| coin | 코인 시장 |
| watch | No right panel (single column, justified in 3.6) |

### 2.7 Table width modes

The ranking table switches mode on `.ws-main`'s own width (container `wsmain`), so the menu state and the right panel are already accounted for.

**Rank table (`.qsf-rank-tbl`, 12 columns, current column set in `qsfRankRow`).** Natural widths: 순위 56 · 종목 180 · 업종 96 · 점수 84 · 점수 변화 72 · 기술/재무/위험 관리/이벤트 4 × 64 · 판단 120 · 진입 140 · 가점/감점 180.

| Mode | `wsmain` width | Columns shown | Rules (all existing class hooks) | Minimum width |
|---|---|---|---|---|
| Full | ≥ 1184 | all 12 | nowrap | 1184px |
| Medium | 860–1183 | 10: area bars `.qd-col` hidden, change column `.qr-dcol` hidden, change under the score `.qr-md` shown | today's ≥ 1600 card-beside rule | 856px |
| Compact | 640–859 | as Medium; 진입 `.w2` and 가점/감점 `.qr-why` wrap (`min-width` 84px / 100px); 경계 근처 badge under the score | today's ≤ 1023 rules | **736px** (the two-column split requires main ≥ 744px, so the ranking is never squeezed below Compact beside a right panel) |
| Narrow | < 640 | 4: 업종 `.w`, 판단 `.w`, 진입 `.w2` hidden; 판단 + 진입 under the name `.qr-m2` | today's ≤ 640 rules | ~340px |

```css
@container wsmain (max-width: 1183px) { .qsf-rank-tbl .qd-col, .qsf-rank-tbl .qr-dcol { display: none; } .qsf-rank-tbl .qr-md { display: block; } }
@container wsmain (max-width: 859px)  { .qsf-rank-tbl .qr-why { white-space: normal; min-width: 100px; }
                                        .qsf-rank-tbl td.w2 { white-space: normal; word-break: keep-all; min-width: 84px; } }
@container wsmain (max-width: 639px)  { /* move today's @media (max-width: 640px) .qsf-rank-tbl rules here unchanged */ }
```

These replace the viewport rules:
- `@media (max-width: 1279px) .qd-col`,
- the `@media (max-width: 1023px)` rank block,
- the `@media (min-width: 1600px) .qsf-split …` block.

The phone media block may stay as well. The two agree at ≤ 640.

At 1920 with the full menu, main is 1144 (Medium). The area bars are hidden there, as they are today when the card is beside, because the open card shows them (QC-11 영역별 점수).

**Sticky header everywhere it can work.** A table whose wrapper does not need to scroll sideways keeps a sticky header at `--sticky-top`:
- `@container wsmain (min-width: 1184px) { .tbl-wrap:has(> .qsf-rank-tbl) { overflow: visible } }`.
- Same for Medium/Compact, because the table fits by construction. This extends today's `≥ 1024` rule (QR-36).

Wider tables (14-column order plan, 16-column committee performance, 12–14-column holdings) keep horizontal scroll with the sticky first column. Their header does not follow the page.

Natural widths and the region they sit in:
- watch 9 columns ≈ 860px (main, single column 1016–1760);
- account holdings 12 columns ≈ 1080px (main);
- portfolio holdings 14 columns ≈ 1180px (main);
- order plan 14 columns ≈ 1300px (full-width view);
- committee performance 16 columns ≈ 1400px (main);
- coin 10 columns ≈ 900px (main);
- screener 9 columns ≈ 980px (main).

These are given so the table spec can choose priority columns. No column is dropped by this layout spec.

**Right-panel content rules (container `wsright`, 360–480px).**

```css
@container wsright (max-width: 520px) {
  .qsf-cards { grid-template-columns: minmax(0, 1fr); }          /* two strategy cards stack (already true below 840px) */
  .qsf-balance, .asst-cands, .sp-cols { grid-template-columns: minmax(0, 1fr); }
  .ic-grid { grid-template-columns: minmax(0, 1fr); }
  .kv { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .asst-cand .w { display: none; } .asst-cand .qr-m2 { display: block; margin-top: 4px; font-size: var(--fs-sm); }
  .form { grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); }  .form .wide { grid-column: 1 / -1; }
  .qsf-dl { grid-template-columns: 96px minmax(0, 1fr); }
}
```

---

## 3. Screens

Notation:
- `[ID..ID]` lists inventory rows.
- "→ main" etc. names the region.
- Wireframes are desktop two-column (W ≥ 1120) unless marked.
- "768" means single column with the drawer menu.
- "390" means phone with the bottom bar.
- Today's phone rules for each feature (hidden columns, chart heights, 2-column tiles) stay unless stated.

### 3.1 오늘 `today`: the workstation landing (full workstation)

**Decision.** 오늘 stays the landing screen. It already is the fallback in `fromHash` and the COIN market's first screen.
- It combines market numbers, candidates, the day's actions and the question box, which makes it the full workstation.
- 시장 개요 stays as the second dashboard screen (3.2).

```
┌ ws-ctx ───────────────────────────────────────────────────────────────────────────────────────┐
│ 오늘 [미국]  headline (TD-13 h2)   ·  미국 시장 · 기준 거래일 2026-11-21 · 07:40 기준            │
│ [갱신 중… / 새 목록을 받지 못했습니다 (TD-25)]  [읽지 못한 부분 … (TD-14)]                         │
│ ┌S&P500┐┌나스닥┐┌다우┐┌러셀┐┌VIX┐┌10년물┐┌달러┐┌원/달러┐┌시장 상태 62/100┐   source · fetched (TD-15/16)│
├ ws-main ───────────────────────────────────────┬ ws-right (sticky, 360–480) ─────────────────┤
│ [물어보기 ………………………… ][묻기][물어볼 수 있는 것]       │ 오늘의 후보 [session] (TD-17)                 │
│ ┌ answer card (TD-04..12, TD-V1..V3) ─────────┐ │  스윙 · 지금 진입 가능 N · 매수 후보 M        │
│ │ 사도 됨 / 기다림 / 사지 않음 box …           │ │  ┌name score Δ  가점/감점┐  ×5 (TD-18)      │
│ └──────────────────────────────────────────────┘ │  장기 · 진입을 막는 조건 없음 …               │
│ 할 일과 알림                                      │  ┌…┐ ×5                                     │
│  먼저 볼 것 [3]   ▌item · chip · [탭에서 보기]      │  note                                       │
│  오늘 챙길 것 [2] ▌…  (TD-19..21)                 │                                             │
│  참고 [5]        ▌…                              │                                             │
├ ws-lower ─────────────────────────────────────────────────────────────────────────────────────┤
│ ▸ 작업 상태 (자동 실행·기록) [4]  (TD-22)      note (TD-23)                                       │
└───────────────────────────────────────────────────────────────────────────────────────────────┘
```

**Region assignment.**

| Region | Rows |
|---|---|
| ctx | TD-01 (title + market badge), TD-13 (headline + meta), TD-14, TD-25 refresh line, TD-15 + TD-16 market tiles as a full-width tile strip (`.asst-tiles`, `minmax(156px, 1fr)` → 7–9 per row at 1440), TD-26 |
| main | TD-02, TD-03 (question form), TD-04..TD-12 and TD-V1..TD-V3 (answer card in `#asst-out`), TD-19..TD-21 (grouped items), TD-24 (load/error states of the item host) |
| right | TD-17, TD-18 (candidates) |
| lower | TD-22 (ops fold), TD-23 (note) |
| shell | TD-27 (coin brief: no tiles and no candidates, so the right panel is empty and the screen is single column automatically) |

The tiles go in the context strip rather than the right panel. The coordinator's draft put them right. In a horizontal strip, 8–9 tiles read at a glance and keep their sparklines; in a 360px column they would need five rows. The right column then holds the one table-like block, the candidates.

**DOM change (assistant.js `renderToday` / `asstBrief`).** The skeleton is built once and the brief fills four hosts, so the answer card is never wiped by a brief refresh:

```html
<div class="ws" data-ws="today" id="asst-brief">
  <div class="ws-ctx" id="asst-ctx" data-brief></div>
  <div class="ws-body">
    <div class="ws-main"><div class="panel" id="asst-askp">…#asst-form, #asst-q, #asst-help, #asst-out (unchanged)…</div><div id="asst-items" data-brief></div></div>
    <div class="ws-right" role="complementary" aria-label="오늘의 후보" id="asst-cands" data-brief></div>
  </div>
  <div class="ws-lower" id="asst-ops" data-brief></div>
</div>
```

- `brief.dataset.at` stays on `#asst-brief`.
- The refresh line is inserted at the top of `#asst-ctx`.
- The dimming rule becomes `#asst-brief.refreshing [data-brief] > :not(.asst-refresh) { opacity: .55 }`, so the question box is never dimmed (same as today).
- A brief failure writes its message into `#asst-items`.

**768.** ctx (title, headline, tiles in 3 columns) → question + answer → items → candidates → ops.
**390.** Same order, with today's phone rules: tiles 2 columns without sparklines; candidate band and sector columns hidden, band under the name.

The question box now comes after the headline and tiles instead of before them. That is the only order change.

### 3.2 시장 개요 `overview`: second dashboard screen (market analysis)

```
┌ ws-ctx: 시장 개요 · 출처 Yahoo · 받아온 시각 · [상태] · basis (OV-07)  [정규장이 진행 중… (OV-06)] ┐
├ ws-main ─────────────────────────────────────────┬ ws-right ─────────────────────┤
│ 지수  ┌S&P 500┐┌나스닥┐┌다우┐┌러셀┐┌VIX┐          │ 금리·환율·원자재               │
│ 섹터 ETF ┌XLK┐┌XLF┐┌XLV┐┌XLE┐┌XLY┐┌XLP┐            │ ┌미 10년물 금리┐ (1 column of │
│          ┌XLI┐┌XLU┐┌XLB┐┌XLRE┐┌XLC┐               │ ┌달러인덱스  ┐  cards, 2 at  │
│                                                   │ ┌원/달러 ┐┌WTI┐┌금┐  ≥ 420px) │
└───────────────────────────────────────────────────┴──────────────────────────────┘
```

| Region | Rows |
|---|---|
| ctx | OV-06, OV-07 (source/time/basis line moved from the last panel to the context bar, next to the data), OV-08 (load/error) |
| main | `d.groups[0]` and `d.groups[2]` panels: OV-01..05, OV-09 |
| right | `d.groups[1]` panel (OV-01..05) |

- **Assignment rule in `renderOverview`.** If `d.groups.length === 3`, group index 1 goes right; otherwise every group goes in main.
  - Index 1 is the rates/FX group in both layouts: US 금리·환율·원자재, KR 환율·대표 ETF.
- **Grids.**
  - Main `.grid` uses `minmax(168px, 1fr)` (five index tiles fit one row at main 800).
  - Right grid uses `minmax(168px, 1fr)`, which gives 1 column at 360 and 2 at ≥ 420.
  - Card content and the neutral-tile rule are unchanged.

768: ctx → 지수 → 섹터 ETF → 금리·환율·원자재. 390: same, with today's 1–2 column grid.

### 3.3 시장 지도 `map` (chart-oriented)

```
┌ ws-main ─────────────────────────────────────────┬ ws-right ─────────────────────┐
│ 시장 히트맵 [1일|5일|1개월|QSF 점수][스윙|장기][기본 색|파랑·주황] │ 업종 순환 그래프               │
│ ┌──────────── treemap canvas 620px ───────────┐ │ ┌──── square = column ─────┐ │
│ │                                             │ │ │  선도 │ 약화              │ │
│ └─────────────────────────────────────────────┘ │ │  개선 │ 침체              │ │
│ legend · meta                                    │ └──────────────────────────┘ │
├ ws-lower ────────────────────────────────────────┴──────────────────────────────┤
│ 업종 상대 성과 (table, row → picks)        │ 업종 점수 상위 종목 (appears on choice)  │
│                                           │  스윙 상위 3 │ 장기 상위 3 · plan cards  │
└──────────────────────────────────────────────────────────────────────────────────┘
```

| Region | Rows |
|---|---|
| main | MP-01..MP-06 (heatmap panel, controls in its h2 row as today) |
| right | RO-01, RO-02 (RRG panel; the canvas already sizes to its parent's width, capped at 560) |
| lower | RO-03 (table), SP-01, SP-02 (picks + plan; hidden until a sector is chosen, so the table spans the lower width until then) |
| shell | MP-07 |

**DOM change.**
- `renderMap` writes:

  ```html
  <div class="ws" data-ws="map">
    <div class="ws-body"><div class="ws-main">heat panel</div><div class="ws-right" id="map-rrg"></div></div>
    <div class="ws-lower" id="map-more"></div>
  </div>
  ```

- `rotation.js` keeps writing its three panels into `#map-more`, then moves the first panel (the RRG) into `#map-rrg`: `$("#map-rrg").append(box.firstElementChild)`.
- IDs `rrg-cv`, `rrg-legend`, `rrg-meta`, `rrg-table`, `rrg-picks` are unchanged.
- `sectorpicks.js:16` `scrollIntoView({behavior:"smooth", block:"start"})` becomes `block: "nearest"`, so a two-column page does not jump when the picks appear beside the table. Single column still scrolls to them.

768/390: heatmap → RRG → table → picks (today's order). Heights are unchanged (520 on phone).

### 3.4 거시 `macro` (chart-oriented)

```
┌ ws-ctx: 미국 거시 지표 · [reason notice MA-02] ─────────────────────────────────────┐
├ ws-main ──────────────────────────────────────┬ ws-right (sticky, own scroll) ─────┤
│ ┌10년물┐ ┌2년물┐ ┌장단기┐   (mcard grid,         │ 다가오는 경제 일정 (60일)            │
│ ┌연방기금┐┌CPI┐┌실업률┐    minmax(240px,1fr))    │ 날짜 · 시각 · 나라 · 일정 table      │
│ ┌고용┐ ┌원/달러┐                                 │ notices · basis · sources         │
│ CPI note · source (MA-03)                        │                                   │
└────────────────────────────────────────────────┴───────────────────────────────────┘
```

| Region | Rows |
|---|---|
| ctx | MA-02 |
| main | MA-01, MA-03, MA-05 |
| right | MA-04 = `#econcal` with CAL-01..CAL-07 |

- `#econcal` keeps its id. `loadCalendar($("#econcal"))` is unchanged.
- In a 360–480px column the four calendar columns fit: 날짜 110 · 시각 48 · 나라 40 · 일정 wraps. The table keeps `.tbl-wrap` for the 360 case.

768/390: ctx → indicators → calendar. This is an in-screen order change: the calendar moves from above the indicators to below them. It fixes macro weakness 1.

### 3.5 종목 정보 `stock` (research layout)

With a ticker:

```
┌ ws-ctx (header band, #s-head) ─────────────────────────────────────────────────────────────────┐
│ Apple Inc. AAPL · NASDAQ      [＋ 관심종목] [비교 차트] [차트분석] [점수 카드]                     │
│ 234.12  +1.2%  [장중·미확정]  52주 범위 … · 200일선 대비 …   ·  기술 · Consumer Electronics · 웹사이트 │
├ ws-main ───────────────────────────────────────┬ ws-right (#s-facts) ──────────────────────────┤
│ 가격 차트 [3개월|1년|5년]  20일선 50일선 200일선      │ 핵심 지표  시가총액 · PER(후행) · PER(예상) │
│ ┌─────────── candles + volume, 420px ────────┐   │           PBR · 배당수익률 · 베타 · 평균 거래량 │
│ └────────────────────────────────────────────┘   │           상장 주식수   (kv, 2 columns)     │
│ meta (source · 마지막 일봉)                        │ ▸ 회사 설명 (Yahoo 영문 원문)               │
│                                                  │ 업종 내 위치 (A–F, 스윙/장기 × 5)          │
│                                                  │ source · fetched                          │
├ ws-lower ─────────────────────────────────────────────────────────────────────────────────────┤
│ [업종 비교] [연간 재무] [공시]  ← section nav (anchor buttons, sticky at --sticky-top)              │
│ 동종업계 비교 (peer table, sortable, 12 rows + "N개 모두 보기")                                    │
│ 연간 재무 요약 (years × rows)                                                                    │
│ 최근 SEC/DART 공시                                                                              │
└───────────────────────────────────────────────────────────────────────────────────────────────┘
```

| Region | Rows |
|---|---|
| ctx | ST-03 (name, code, exchange, sector · industry, 웹사이트), ST-04..ST-07 (four buttons), ST-08 (price line), ST-22 (header error) |
| main | ST-12..ST-18 (chart panel), ST-22 (chart error), ST-23, ST-24 |
| right | ST-09 (key figures), ST-10 (description fold), ST-11 (profile source), PE-01 (grade table "업종 내 위치") |
| lower | section nav; ST-19 / PE-02..PE-08 (`#s-peers`); ST-20 (`#s-fund`); ST-21 (`#s-fil`); ST-22 (section errors) |
| shell | ST-25, ST-26 |

**Right panel with nothing selected.** The stock screen always has its ticker: key figures, description and the A–F grades. That is the "score summary" the stock page lacked (stock weakness 2), from existing data only.

**DOM change.**
- `renderStock` writes `ws-ctx#s-head`, `ws-main` (chart panel), `ws-right#s-facts` (`.ws-first`), and `ws-lower` (section nav + `#s-peers`, `#s-fund`, `#s-fil`).
- `renderProfile(c)` writes the header part into `#s-head` and the key-figure block, description and source into `#s-facts`. The ids `#addw`, `#addc`, `#adda`, `#addq`, `#s-price` and `#sum` are unchanged.
- `peers.js paintPeers` writes the grade table into `#s-grades` (a child of `#s-facts`) when that element exists, and the rest into `#s-peers`. When `#s-grades` is missing, it writes both into `#s-peers` as today.
- The section nav is three `button.chip`s that call `scrollIntoView({block: "start"})` on `#s-peers`, `#s-fund` and `#s-fil` (scroll-padding already offsets the sticky bars). It is a navigation aid, not new data.
- 점수 카드 `#addq` may take `.btn-primary` to mark the main cross-link (stock weakness 1). Visual only.

**Without a ticker (ST-01, ST-02, WA-10, S-06, S-07).** `.ws.ws--single.ws--narrow` with one panel, as today.

**768.** Header band → key figures + description + grades (`.ws-first`: same place the facts have today, right under the name) → chart → section nav → peers → financials → filings.
**390.** Same. Chart 300px. The four buttons wrap under the title (today).

### 3.6 관심종목 `watch`: single-column table workspace (justified)

```
┌ ws-ctx: 미국 관심종목 N개 (WA-08)                     [추가할 종목 코드 ……][추가] (WA-02) ┐
├ ws-main (full width) ─────────────────────────────────────────────────────────────────┤
│ 종목 │ 종가 │ 전일 대비 │ 1개월 │ 추세(30일) │ 스윙 점수 │ 장기 점수 │ 상태 │ ✕            │
├ ws-lower: scan sentence · source · "관심종목은 이 Mac의 …" (WA-06) ─────────────────────────┤
```

| Region | Rows |
|---|---|
| ctx | WA-02, WA-08 |
| main | WA-01, WA-03, WA-04, WA-05, WA-07, WA-09 |
| lower | WA-06 |
| stock screen (unchanged) | WA-10 |

`.ws--single` is used because `/api/watchlist` returns only the row fields. A right panel could only repeat a row's own columns, which the brief forbids. The table (≈ 860px) gets the full width and a sticky header.

768: same; the table scrolls sideways under the sticky first column. 390: same.

### 3.7 차트분석 `chart` (chart-oriented)

```
┌ ws-ctx: 차트분석  삼성전자 · 005930   [종목 코드 …][보기]  chips: 코스피 코스닥 | recent… ┐
├ ws-main ─────────────────────────────────────────┬ ws-right ────────────────────────┤
│ [3개월|6개월|1년|3년|5년|10년] [캔들|OHLC|선] ☐볼린저 ☐신호 │ 지금 상태                         │
│ 이동평균 ☐5 ☐20 ☐60 … [기본(…)] 최대 N개              │  caveat notice                   │
│ ┌ price 400 ┐ ┌ 거래량 90 ┐ ┌ RSI 100 ┐ ┌ MACD 110 ┐  │  one line per indicator          │
│ legend · meta                                       │ 최근 신호 (이 기간 N건)            │
│                                                     │  date ▲/▼ close × 20, ▸ 나머지     │
│                                                     │  ▾ 신호의 관습적인 뜻               │
└─────────────────────────────────────────────────────┴──────────────────────────────────┘
```

| Region | Rows |
|---|---|
| ctx | CH-01, CH-02, CH-03 |
| main | CH-04..CH-12 |
| right | CH-13, CH-14 |
| shell | CH-15, CH-16 |

The chart's first panel is split: the title, `#cha-form` and the chip row go in ctx; `.cha-ctl` rows and `#cha-stack` stay in the main panel. All IDs are unchanged.

768/390: ctx → controls + stack → 지금 상태 → 최근 신호 (today's order). Phone heights are unchanged.

### 3.8 비교 `compare` (chart-oriented)

```
┌ ws-ctx: 수익률 비교 [3개월|1년|5년]  chips ■AAPL × ■SPY ×   [종목 코드 추가][추가]  index chips ┐
├ ws-main ──────────────────────────────────────┬ ws-right ──────────────────────────┤
│ ┌──── overlay return chart 380px ────┐         │ 기간 성과 (기간 수익률, 연환산,     │
│ └────────────────────────────────────┘         │  연 변동성, 최대 낙폭)              │
│ legend · meta                                  │ 일간 수익률 상관계수 (matrix)        │
├ ws-lower ──────────────────────────────────────┴────────────────────────────────────┤
│ 상관계수의 변화 (rolling chart 240px, legend, explanation)                            │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

| Region | Rows |
|---|---|
| ctx | CP-01, CP-02, CP-03, CP-04 |
| main | CP-05, CP-06 |
| right | CP-07, CP-08 (≤ 8 tickers → ≤ 9 columns; `.tbl-wrap` scrolls at 360) |
| lower | CP-09 |
| shell | CP-10 |

768/390: ctx → chart → 기간 성과 → 상관계수 → 변화 (today's order).

### 3.9 통합 계좌 `account` (portfolio: holdings / allocation)

```
┌ ws-ctx: 통합 계좌 · 미국 주식 · 한국 주식 · 코인   [원화|달러]   [integrity / missing price / FX notices] ┐
├ ws-main ──────────────────────────────────────────┬ ws-right (sticky) ────────────────────┤
│ 계좌별 (계좌·평가액·원화로·비중·현금·주식·코인·총 손익·자세히)│ ₩ 123,456,789  ≈ $…  (big total)       │
│ 보유 종목 (12 columns, all three accounts)            │ 총 손익 · 오늘 손익 · 현금 · 평가액 ·     │
│                                                     │ 넣은 돈 · 환율  (kv 2 columns)          │
│                                                     │ 거래 기록 추가  (form, 1–2 columns)      │
│                                                     │  종류 · 계좌 · 날짜 · 종목 … [기록 추가]  │
├ ws-lower ─────────────────────────────────────────────────────────────────────────────────┤
│ 거래 기록 (N건 · 추가만 가능…) table with 취소           notes · coin price error             │
└──────────────────────────────────────────────────────────────────────────────────────────┘
```

| Region | Rows |
|---|---|
| ctx | AC-02, AC-03, AC-04 |
| main | AC-07, AC-08 (per-account table + 자세히), AC-09 (holdings) |
| right | AC-05, AC-06 (totals block, `.ws-first`), AC-10..AC-14 (`#acctform-panel`) |
| lower | AC-16, AC-17 (journal), AC-18 (notes) |
| shell | AC-01 (entries); AC-15 (prefill scroll lands in the right column); AC-19 |

- The trade form is the account's ticket, so it sits beside the holdings instead of under two tables (account weakness 1).
- The rule C exception for this tab (`INTL_COLOR_TABS`) is unchanged.

**DOM change (`renderAccount`).** The first panel is split. `#acctunit` goes in ctx; the big total and kv go into a `.panel.ws-first` in the right; the per-account table goes in main. `#acctform-panel` and every form id are unchanged.

768/390: ctx → totals → per-account → holdings → form → journal → notes. This is today's order: totals, holdings, form, journal.

### 3.10 시장별 자세히 `portfolio` (holdings / allocation / risk)

```
┌ ws-ctx: [무결성 notice PF-01]  [시작하기 PF-02 when empty] ─────────────────────────────────────┐
├ ws-main ──────────────────────────────────────────┬ ws-right (sticky) ─────────────────────┤
│ 경고 N건 (PF-05)                                     │ 주식 두 계좌 합계 (PF-03)               │
│ 장기 보유 (table)  스윙 보유 (table)  구분 없음 (table) │ 미국(달러) 계좌 요약: big equity,        │
│ 보유 판정 (#sigpanel)                                 │  kv 9 (PF-04) · source · FX            │
│                                                     │ 섹터 비중 bars · 한도 (PF-09)            │
├ ws-lower (2-column grid) ────────────────────────────────────────────────────────────────┤
│ 위험 분석 #risk-panel (span-all: kv, per-holding table, correlation matrix)                 │
│ 계좌 수익률 vs SPY (#eqc 220px)           │ 매매 성과 (kv, by style, closed trades)           │
│ 거래 기록 추가 → [통합 계좌에서 기록하기]     │ note (PF-15)                                     │
│ 거래 기록 (span-all, with 취소)                                                              │
└──────────────────────────────────────────────────────────────────────────────────────────┘
```

| Region | Rows |
|---|---|
| ctx | PF-01, PF-02 |
| main | PF-05, PF-06, PF-07, PF-08 (row cells + `#sigpanel`) |
| right | PF-03, PF-04 (`.ws-first`), PF-09 (after main on narrow) |
| lower | PF-10 (span-all), PF-11, PF-12, PF-13, PF-14 (span-all), PF-15 |
| shell | PF-16 |

768/390 equals today's order: PF-03 → PF-04 → 경고 → holdings → 판정 → sectors → risk → equity → performance → form pointer → journal → note.

### 3.11 매매 보조 `assist` (tools)

```
├ ws-main ─────────────────────────────────────────┬ ws-right (sticky, own scroll) ────────┤
│ 포지션 크기 계산기 (form 5 fields + 계산)            │ 위험 관리 설정 (17 fields, 2 columns) │
│  result: N주 · kv · limits · [이 수량으로 매수 기록]  │  [저장]  explanation  message         │
│ P6-11B 계획 대조 (US only; 계산기 button fills the    │                                      │
│  calculator just above)                           │                                      │
├ ws-lower (2-column grid) ────────────────────────────────────────────────────────────────┤
│ 알림 센터 (#alertc: form · rules · 지금 확인 · log)  │ 다가오는 실적 발표 (#earncal, 14 days)     │
└──────────────────────────────────────────────────────────────────────────────────────────┘
```

| Region | Rows |
|---|---|
| main | AS-01..AS-04, AS-08 |
| right | AS-07 (`#stform` panel) |
| lower | AS-05 = AL-01..AL-06 (`#alertc`), AS-06 (`#earncal`) |
| shell | AS-09 |

**In-screen order change.** Settings sit beside the calculator they drive (assist weakness 1). The plan table, whose 계산기 button fills the calculator, moves up under it.
- 768/390: calculator → plan (US) → settings → alerts → earnings.
- Today's order was calculator → alerts → earnings → settings → plan.

### 3.12 모의 매매 `paper`

```
┌ ws-ctx: 모의 매매 기록 [가상의 계좌][주문을 보내지 않습니다] · note · fee basis · pointer (PT-01) ┐
├ ws-main ─────────────────────────────────────┬ ws-right (sticky) ─────────────────────────┤
│ 보유 중 (table + 매도 기록 buttons)              │ 평가액 · 현금 · 넣은 모의 자금 · 총 손익 …   │
│ 끝난 거래 (table + totals + caution)            │  (kv 8, 2 columns)                         │
│                                               │ 기록 form (종류 · 종목 · 수량 · 가격 …)      │
│                                               │  fee preview line · message               │
├ ws-lower: 기록 N건 (table with 취소) ───────────────────────────────────────────────────────┤
```

| Region | Rows |
|---|---|
| ctx | PT-01, PT-02 (when the file is broken, the screen is ctx only, as today) |
| main | PT-06, PT-07, PT-08 |
| right | PT-03 (`.ws-first`), PT-04, PT-05 (`.ws-first`) |
| lower | PT-09 |
| shell | PT-10 |

768/390: ctx → tiles → form → positions → closed → journal (today's order).

### 3.13 순위·카드 `qsf` (screener: the strongest table + analytics split)

**Shared frame.** The `renderQsf` template becomes:

```html
<div class="ws" data-ws="qsf" data-view="rank">
  <div class="ws-ctx">
    <details class="qsf-strip" id="qsfstrip">…unchanged summary + #qsfstatefull, caveat, #qsfrecord, #qsfstance…</details>  <!-- docked; see below -->
    <div class="qsf-nav">#qsfview · #qsfstratseg · 성향 #qsfstanceseg (unchanged, one row)</div>
    <div data-view="rank" class="qsf-evalrow"><form id="qsfform" class="qsf-form">…</form><div id="qsfmsg" …></div></div>
  </div>
  <div class="ws-body qsf-split">
    <div class="ws-main">
      <div data-view="rank"><div id="qsfrank"></div></div>
      <div data-view="screen"><div id="qsfscreen"></div></div>
      <div data-view="exec"><div id="qsfplan"></div></div>
      <div data-view="track">…the seven .fold hosts, unchanged ids…</div>
    </div>
    <div class="ws-right" role="complementary" aria-label="점수 카드와 시장 상태">
      <div id="qsfdetail" class="ws-first"></div>
    </div>
  </div>
  <div class="ws-lower">
    <div data-view="rank" class="span-all"><div class="fold" data-fold="cap"><div id="qsfcap"></div></div><div class="fold" data-fold="changes"><div id="qsfchanges"></div></div></div>
    <div data-view="exec" class="span-all"><div id="qsfpaper"></div></div>
  </div>
</div>
```

- `qsfSetView` already toggles every `#tab-qsf [data-view]`, so several hosts per view need no change. It must also set `ws.dataset.view = v`.
- `.ws[data-ws="qsf"][data-view="exec"], .ws[data-ws="qsf"][data-view="track"]` get the single-column treatment. Add `.ws--single` behaviour by selector, and `#qsfdetail { display: none }` in those two views, which matches today: the card lives inside the rank view.
- The `qsf-split` class stays on `.ws-body` for test pins. The old `.qsf-split` CSS block is deleted.

**Strip docking (`qsfDockStrip()`, about 10 lines in qsf.js).**
- When `wsCanSplit()` is true and the view is `rank` or `screen`, `#qsfstrip` is moved (the same node) into `.ws-right` after `#qsfdetail`. Otherwise it is moved back to the top of `.ws-ctx`.
- When docked:
  - With no card open, the strip is `open` (its body is the right panel's default content).
  - When a card opens (`qsfDrawDetail`), it is set closed, and its one-line summary stays visible under the card.
  - When the card folds (`qsfFoldCard`), it reopens.
- A user's own toggle is kept until the next card open/close.
- It is called after `renderQsf`, in `qsfSetView`, and from the content `ResizeObserver` (2.2).
- `qsfBeside` becomes `() => wsCanSplit() && (qsfState.view === "rank" || qsfState.view === "screen")`.

#### View: 오늘 순위 (rank)

```
┌ ws-ctx ─────────────────────────────────────────────────────────────────────────────────────────────┐
│ [오늘 순위|스크리너|주문 계획·가상 장부|판정 일정]  [스윙|장기]  미국 성향 [방어|보통|공격]                   │
│ [티커 (예: AAPL) ………][평가]  status line                                                             │
├ ws-main (Compact at 800 / Medium at 900–1144 / Full ≥ 1184) ─┬ ws-right (sticky, 360–480) ───────────┤
│ 스윙 순위 50개 [2026-11-21]                                    │ (card open)  name · [미국] tags         │
│ explainer lines · common push line                           │   [종목 화면] [닫기]                    │
│ 순위│종목 (chips, risk lines)│업종│점수 Δ│판단│진입│가점/감점     │   swing card / long card (stacked)    │
│ ─── sticky header ───                                        │   ▾ 근거 ▸ 계획 ▸ 요인별 계산          │
│  1 │ …                                                       │   ▸ 다섯 투자자 ▸ 가격 범위 ▸ 이력      │
│  2 │ …   (50 rows)                                           │ ─────────────────────────────────── │
│ footer lines                                                 │ ▸ 시장 상태 62/100 · 성향 · 점수 검증  │
│                                                              │ (no card) ▾ the same strip, open:     │
│                                                              │   market-state factors, caveat,       │
│                                                              │   과거 성적 fold, stance block          │
├ ws-lower ────────────────────────────────────────────────────────────────────────────────────────────┤
│ ▸ 이전 대상(거래대금 상위 N) (KR)        ▸ 직전 기록과 달라진 점                                          │
└──────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

| Region | Rows |
|---|---|
| ctx | QR-08, QR-09, QR-10 (view row); QR-11, QR-12 (rank form); QR-01..QR-07 (strip) when not docked |
| main | QR-20..QR-37 (`#qsfrank`) |
| right | QR-13, QR-15, QC-01..QC-26 (`#qsfdetail`); QR-01..QR-07 strip when docked |
| lower | QR-38 (`#qsfchanges` fold), QR-39 (`#qsfcap` fold, KR) |
| shell | QR-14, QR-16, QR-17, QR-18, QR-19 |

- **Right panel with nothing selected.** The strip body opens there:
  - market state with factors (QR-03),
  - the caveat (QR-04),
  - 과거 성적 with its verdict reasons (QR-05, QR-06),
  - the stance block (QR-07).
- This is existing data that complements the ranking: why the list should be read with care, and what the stance changes. No extra request is made: the strip already loads it.
- **Ranking table minimum widths.** See 2.7: 736px beside the right panel (Compact); 856px for Medium; 1184px for all 12 columns.
- **Row click (QR-21) — owner decision D1.** Two options:
  - **Proposed:** in two-column mode a row click opens that stock's card in the right panel instead of expanding the row. The row gets `aria-selected="true"` and a 3px accent inset.
    - It goes through the same path as `qsfOpenCard` without `scrollTo(0,0)`, uses the cached `qsfEval`, and pushes `#qsf/CODE`.
    - `qsfDrawDetail(d, r)` receives the row, so the scan-vs-now note (QC-26, today only in the expanded row) prints at the top of the card.
    - Everything else in the expanded row is already in the full card: the single-strategy card, the price-audit line, 당일 점검 (QC-22).
  - **If the owner declines:** rows keep expanding inline at every width, and the right panel shows a card only when opened by the form or a link (today's behaviour).
  - Either way, single-column mode keeps the inline expansion unchanged.

#### View: 스크리너 (screen)

```
├ ws-main ─────────────────────────────────────────┬ ws-right ───────────────────────┤
│ 스크리너 panel: form (검색, 업종, 판단, 진입, 신뢰도,    │ card of the stock opened with   │
│  점수/기술/재무/위험 관리 이상, checks, [초기화][CSV 저장])│ 점수 (D2), else the docked strip │
│ count line · sector spread · version notice       │                                 │
│ results table (sortable 점수/기술/재무/위험 관리/이벤트)  │                                 │
│ [N개 더 보기]                                       │                                 │
```

| Region | Rows |
|---|---|
| main | QS-01..QS-06, QS-08, QS-09 |
| right | QS-07 target (card) + strip |

**Score button QS-07 — owner decision D2.**
- **Proposed:** in two-column mode it opens the card in the right panel and **stays in the screener**, so the filter, results and scroll are kept (screener weakness 4).
- Single column keeps today's behaviour: switch to 오늘 순위, evaluate, scroll to `#qsfmsg`.
- The screener form stays inside its panel in main. It is built by `qsfScreenBuild` into `#qsfscreen`, and moving it to ctx would split one form across regions.

#### View: 주문 계획·가상 장부 (exec): full width

| Region | Rows |
|---|---|
| main | QE-01..QE-05, QE-10 (`#qsfplan`) |
| lower | QE-06..QE-09 (`#qsfpaper`) |

- Full width because the 14-column order table (≈ 1300px) needs it.
- No right panel. The strip returns to ctx. The card is hidden in this view, as today.
- QE-05 highlight and QC-07 jump are unchanged.

#### View: 판정 일정 (track): full width

| Region | Rows |
|---|---|
| main | QT-01..QT-10, FC-08..FC-12 (seven fold panels, unchanged ids and fold memory) |

Full width because the panels are 6–9-column tables. The strip is in ctx.

#### Score card (`#qsfdetail`, cross-view)

- Lives in the right panel in two-column rank/screen views.
- In single column it sits above the ranking (`.ws-first`, today's < 1600 place).
- Contents unchanged: QC-01..QC-26, FC-01..FC-07 (range fold), IC-11..IC-14 (committee fold).
- Width rules inside the 360–480 column are in 2.7:
  - strategy cards stack,
  - balance box one column,
  - investor grid one column,
  - factor table (QC-17) wraps its 근거 column (`white-space: normal`).

**768.** ctx (strip line, view row, form) → card (if open) → ranking (Compact mode at 736) → folds. Track/exec are the same as desktop, single column.
**390.** Same order; ranking in Narrow mode; view row wraps (today).

### 3.14 투자위원회 `committee`

**Shared frame.**
- `renderCommittee` writes `<div class="ws" data-ws="committee"><div class="ws-ctx">IC-01 header + disclaimer · IC-02 #icview</div><div class="ws-body" id="icbody"></div></div>`.
- Each view renderer writes `<div class="ws-main">…</div><div class="ws-right">…</div>` into `#icbody`.

```
dash:   ws-main: 위원회가 매수 조건으로 본 종목 (8-column table, ticker → card)   │ ws-right (.ws-first): 4 stats (2×2) + ▸ 분포와 국면 자세히
ports:  ws-main: #icport (portfolio panel: plain block, notices, 6 tiles, rules, holdings table) + note │
        ws-right (.ws-first): 여섯 포트폴리오 · session · [다시 받아보기] · six portfolios as a vertical list with counts · 겹치는 종목
compare: ws-main: form + matrix (5 engines + 위원회 + 4 numbers)               │ ws-right: tally per engine + notes
perf:   ws-main: 16-column record table + ratio line                           │ ws-right (.ws-first): kind/method/cost lines + 한 번의 읽기
```

| View | Region | Rows |
|---|---|---|
| (frame) | ctx | IC-01, IC-02 |
| dash | main | IC-04, IC-15 |
| dash | right | IC-03 |
| ports | main | IC-08, IC-15 |
| ports | right | IC-06 (regenerate), IC-07 (list + overlap) |
| ports landing | main (single column; right empty) | IC-05, IC-06 |
| compare | main | IC-09 table + form, IC-15 |
| compare | right | IC-09 tally panel + notes |
| perf | main | IC-10 table |
| perf | right | IC-10 head lines + reading block |
| qsf card | — | IC-11..IC-14 (3.13) |

- The `#icporttabs` seg is shown as a vertical list in the right panel: `.ws-right #icporttabs { display: flex; flex-direction: column; } .ws-right #icporttabs button { text-align: left; }`. Same buttons and handlers.
- **768/390.** ctx → right content marked `.ws-first` (stats, portfolio list, reading) → main → remaining right content (compare tally). This keeps each view's current top-to-bottom order, except perf, where the reading block now leads (committee perf weakness 3).

### 3.15 모델 `model`

```
┌ ws-ctx: {baseline name} [FROZEN] role (MO-01) ─────────────────────────────────────────────┐
├ ws-main ─────────────────────────────────────────┬ ws-right (.ws-first) ─────────────────┤
│ 모델 상위 종목 (10 columns; 금액/주수 follow capital)   │ 투자 자본금 [……][저장] note           │
│ 실행 ID · read-only sentence                        │ (KR) [스캔 실행] run note             │
│                                                   │ newer-empty-scan notice               │
│                                                   │ 최근 전체 스캔 · 기준 거래일 · 결과 ·    │
│                                                   │  시장 국면 · 기준 자본 (kv)             │
├ ws-lower ──────────────────────────────────────────────────────────────────────────────┤
│ 전향적 추적 (kv, outcome states)        │ 도전자 모델 비교 (US, span-all): table, [데이터 갱신 + │
│                                       │  오늘 신호 기록], message, automation line           │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

| Region | Rows |
|---|---|
| ctx | MO-01 |
| main | MO-06 |
| right | MO-02, MO-03, MO-04, MO-05 |
| lower | MO-07, MO-08, MO-09, MO-10 |
| shell | MO-11 (KR: no comparison panel) |

- The `lab.js` override still finds the placeholder by its h2 text "도전자 모델", now in `.ws-lower`. The finder searches `#tab-model .panel`, so no change is needed.
- Moving `#capInput` and `#capSave` to the right panel separates configuration from results (model weakness 1). `wireCapital` reads by id and is unchanged.

768/390: ctx → capital box and kv → top-5 table → tracking → challengers. This is today's order with the table after the kv, which is where it is today.

### 3.16 연구실 `lab`

`RENDER.lab` writes:

```html
<div class="ws ws--right-first" data-ws="lab">
  <div class="ws-body">
    <div class="ws-main" id="labbody"></div>
    <div class="ws-right"><div id="recpanel" class="ws-first"></div></div>
  </div>
</div>
```

| Region | Rows |
|---|---|
| main | LB-10, LB-11, LB-12, LB-13 (US simulation: NAV chart 320px, cost seg, metric tables, rules) |
| right | LB-01..LB-08 (`#recpanel`; its 5-column 판단까지 남은 기간 table keeps `.tbl-wrap`) |
| main (KR) | LB-09 gate |

- In KR, `renderLab` adds `.ws--single` to the block, because the main region would hold one sentence beside a tall column. The record then reads full width first, as today.
- 768/390: record → simulation (today's order).

### 3.17 코인 `coin` (COIN market only)

```
┌ ws-ctx: 코인 상대 순위 / 간이 순위 [status] [time 마감 · 4시간봉] · mode notice · ▸ caveat · stale warning · how ┐
├ ws-main ─────────────────────────────────────────┬ ws-right ─────────────────────────┤
│ 순위 │ 코인 │ 기대 상대 폭/간이 점수 │ 가격(USDT) │ 1일 │ │ 코인 시장 [참고]                   │
│  7일 │ 30일 │ 자금조달비 │ 변동성 │ 베타   (row → 비서)  │ 비트코인 · 7일 · 30일 · 200일 평균 대비 │
│ source · version                                 │ · 1년 고점 대비 · 내린 코인 · 평균 위 │
│                                                  │ · 평균 자금조달비 · note (kv 2 cols)  │
└──────────────────────────────────────────────────┴───────────────────────────────────┘
```

| Region | Rows |
|---|---|
| ctx | CO-c-02, CO-c-03, CO-c-04, CO-c-07 (explainer) |
| main | CO-c-06, CO-c-07 (footer) |
| right | CO-c-08 |
| shell | CO-c-01, CO-c-05 (UNAVAILABLE: ctx + empty message, single column) |

768/390: ctx → table → coin market (today's order).

---

## 4. Preservation table

Every inventory prefix and range, and where it lands. "Same screen" holds for all 421 rows: **no row moves to another screen.**

| Prefix (rows) | Screen | New region | Notes: moves inside the screen, folds, how it is reached |
|---|---|---|---|
| S-01..S-03 | shell | top bar | Unchanged |
| S-04, S-05 | shell | top bar search | Search max width 320/440px |
| S-06, S-07 | stock | main of `.ws--single` (no-ticker view) | Unchanged |
| S-08..S-11, S-13 | shell | top bar; **⋯ menu** below the widths in 1.7 | Reached via `⋯` (`#topmore`) on 641–1439; via 더보기 on phone (unchanged) |
| S-12 | shell | palette footer, ⋯ menu, 더보기 | Header button stays `hidden` (unchanged); ⋯ menu added as a third entry point |
| S-14, S-16, S-17 | shell | `.statusbars` sticky band under the top bar | Moved out of `<header>`; ids unchanged |
| S-15 | shell | popover under 폰 연결 (phone: bottom sheet) | Same element and content; no longer pushes the page |
| S-18 | shell | hidden `#groups` (keys 1-9, 더보기 source) + side-menu group headings | **Visible group row removed on desktop.** The tabs it led to are listed directly in the menu. The "group → last tab" memory still serves keys 1-9 and the phone bottom bar. |
| S-19 | shell | left menu (≥ 1024), drawer (641–1023), strip under header (≤ 640) | `paintGroups` rewritten (1.4) |
| S-20..S-22, S-24 | shell | unchanged | — |
| S-23 | shell | `main.wide` toggle kept; width now from `.ws` (max 1760) | Tests pin the toggle, not the width |
| S-25, S-26 | shell | bottom bar, 더보기 | Sheet gains the two status lines |
| S-27 | shell | footer in the content column | Unchanged text |
| S-28 | shell | toast centred over the content column | — |
| S-29..S-38, S-40..S-42 | shell / all | unchanged | `redrawAll` also runs on content resize |
| S-39 | shell | breakpoints 640/1023 unchanged; workstation columns by container width | 1279/1600 viewport rules replaced (2.7) |
| UI-01 | all | unchanged builders | `ui.panel` gains no new arguments |
| CM-01..CM-12 | shell | unchanged | — |
| CO-a-01..CO-a-08 | shell | `#collectbar` in `.statusbars` | "화면 새로 고침" also reloads the top-bar chips |
| PH-01..PH-09 | shell | `#phonebar` popover | — |
| TD-01, TD-13..TD-16, TD-25, TD-26 | today | ctx | Tiles become a full-width strip |
| TD-02..TD-12, TD-V1..TD-V3, TD-19..TD-21, TD-24 | today | main | — |
| TD-17, TD-18 | today | right | — |
| TD-22, TD-23 | today | lower | — |
| TD-27 | today | single column (right empty) | — |
| OV-01..OV-05, OV-09 | overview | main (groups 0, 2) / right (group 1) | — |
| OV-06..OV-08 | overview | ctx | OV-07 moved from the last panel to the context bar |
| MP-01..MP-07 | map | main | — |
| RO-01, RO-02 | map | right | — |
| RO-03 | map | lower | — |
| SP-01, SP-02 | map | lower (beside RO-03) | Scroll to picks: `block: "nearest"` |
| MA-01, MA-03, MA-05 | macro | main | — |
| MA-02 | macro | ctx | — |
| MA-04, CAL-01..CAL-07 | macro | right | **Calendar moves from above the indicators to beside them; below them on narrow** |
| ST-03..ST-08 | stock | ctx (header band) | — |
| ST-09..ST-11 | stock | right (`#s-facts`) | Moved out of the header panel |
| ST-12..ST-18, ST-23, ST-24 | stock | main | — |
| ST-19..ST-21 | stock | lower + section nav | — |
| ST-22, ST-25, ST-26 | stock | each section / shell | — |
| ST-01, ST-02 | stock | `.ws--single.ws--narrow` | — |
| PE-01 | stock | right (`#s-grades`) | Split out of the peers panel (peers.js) |
| PE-02..PE-08 | stock | lower (`#s-peers`) | — |
| WA-01..WA-09 | watch | ctx / main / lower (single column) | — |
| WA-10 | stock | no-ticker view | — |
| CH-01..CH-03 | chart | ctx | — |
| CH-04..CH-12 | chart | main | — |
| CH-13, CH-14 | chart | right | — |
| CH-15, CH-16 | chart | shell | — |
| CP-01..CP-04 | compare | ctx | — |
| CP-05, CP-06 | compare | main | — |
| CP-07, CP-08 | compare | right | — |
| CP-09 | compare | lower | — |
| CP-10 | compare | shell | — |
| AC-02..AC-04 | account | ctx | — |
| AC-05, AC-06 | account | right (`.ws-first`) | Split from the summary panel |
| AC-07..AC-09 | account | main | — |
| AC-10..AC-14 | account | right | **Form moves beside the holdings; after them on narrow** (narrow order unchanged) |
| AC-15 | account | right | Scroll lands in the right column |
| AC-16..AC-18 | account | lower | — |
| AC-01, AC-19 | account | shell | — |
| PF-01, PF-02 | portfolio | ctx | — |
| PF-03, PF-04, PF-09 | portfolio | right | — |
| PF-05..PF-08 | portfolio | main | — |
| PF-10..PF-15 | portfolio | lower | — |
| PF-16 | portfolio | shell | — |
| AS-01..AS-04, AS-08 | assist | main | **Plan table moves up under the calculator** |
| AS-07 | assist | right | **Settings move beside the calculator** |
| AS-05 (= AL-01..AL-06), AS-06 | assist | lower | AL rows belong to this tab (section 0 correction) |
| AS-09 | assist | shell | — |
| PT-01, PT-02 | paper | ctx | — |
| PT-03..PT-05 | paper | right | — |
| PT-06..PT-08 | paper | main | — |
| PT-09 | paper | lower | — |
| PT-10 | paper | shell | — |
| QR-01..QR-07 | qsf | ctx (single column, exec, track) or right (two-column rank/screen, open when no card) | **Strip docked in the right column at workstation widths** |
| QR-08..QR-12 | qsf | ctx | — |
| QR-13, QR-15 | qsf | right | — |
| QR-14, QR-16..QR-19 | qsf | shell | — |
| QR-20..QR-37 | qsf | main | **QR-21 row click → right-panel card in two-column mode (D1)**; inline expansion kept in single column |
| QR-38, QR-39 | qsf | lower (folds) | — |
| QC-01..QC-26 | qsf | right (two-column rank/screen) / above ranking (single column) | QC-26 also printed in the right-panel card when opened from a row (D1) |
| QS-01..QS-06, QS-08, QS-09 | qsf | main (screen view) | — |
| QS-07 | qsf | right-panel card (D2) | Single column unchanged |
| QE-01..QE-05, QE-10 | qsf | main (exec view, full width) | — |
| QE-06..QE-09 | qsf | lower (exec view) | — |
| QT-01..QT-10, FC-08..FC-12 | qsf | main (track view, full width) | — |
| FC-01..FC-07 | qsf | inside the card (right) | — |
| IC-01, IC-02 | committee | ctx | — |
| IC-03..IC-10, IC-15 | committee | per view (3.14) | — |
| IC-11..IC-14 | qsf | inside the card (right) | — |
| MO-01 | model | ctx | — |
| MO-02..MO-05 | model | right | **Capital box separated from the table** |
| MO-06 | model | main | — |
| MO-07..MO-10 | model | lower | — |
| MO-11 | model | shell | — |
| LB-01..LB-08 | lab | right (`#recpanel`) | — |
| LB-09..LB-13 | lab | main (KR: single column) | — |
| CO-c-01..CO-c-08 | coin | ctx / main / right per 3.17 | — |

**Folds.** No inventory row is newly folded. Folds that exist stay folds with their keys:
- `qse-qsf-folds`, `qse-fold-*`, `.asst-ops`, `.asst-more`, `co-sum`, caveat details, `fc-fold`, `ic-more`.

Two things become less folded:
- The qsf strip opens by default in the right panel when docked.
- The stock description stays a fold, but in the right panel.

**Behaviour changes that need the owner's yes** (everything else is placement): D1 (row click), D2 (screener score button). Section 6.

---

## 5. Implementation order

Each step is shippable on its own and keeps the app working. Pins that a step breaks are listed so they change in the same commit (inventory rule: about 25 tests pin static source text).

**Step 1: tokens and theme default** (`style.css`, `theme.js`, `app.js`)
- Add the layout tokens (1.2) and `--bg-2`, `--panel-2`, `--nav-active`. Dark is the default palette per the token spec.
- `theme.js`: `|| "dark"` and the `data-nav` line. `app.js` `let theme` fallback `"dark"`.
- Pins: any assertion on `|| "auto"` in `test_ui_batch_5.py`.

**Step 2: shell DOM and menu** (`index.html`, `style.css`, `app.js`)
1. index.html per 1.1: `#navtoggle`, chips, `.top-acts`, `#topmore`/`#topmenu`, `.statusbars`, `.shell > aside.side > (#groups, nav.tabs with .nav-grp/.nav-h)`, `.content > (main, footer)`, `#navscrim`.
2. app.js:
   - `paintGroups` rewrite (1.4).
   - `setTopH` (header + statusbars).
   - New `navInit()`: toggle, drawer, roving focus, `qse-nav`.
   - `toolsHtml()` shared by `moreOpen` and the new `topMenuOpen`.
   - New `loadTopChips()`: `qsfStateShort` + automation status, called on boot, `setMarket`, and `collect.js` finish.
   - Content `ResizeObserver` (2.2).
3. CSS: delete the sticky `.groups` rule and the `@media (min-width: 641px) .groups` block. Add the shell, menu, rail, drawer, phone-strip, status-band and popover rules (1.3–1.6). `main` max-width removed.
4. Pins:
   - `test_ui_batch_3.py:156-162` (sticky group bar, phone header rule list).
   - `test_ui_batch_5.py:67` (`<nav class="tabs" aria-label="탭" hidden>`).
   - `test_ui_groups.py:31,33` (`.tabs").hidden = mine.length < 2`, `.tabs[hidden]`).
   - Keep `test_ui_groups.py:13-34` true: `#groups` before `.tabs`, tab attribute order, the `.groups button` click binding, the keys 1-9 line.

**Step 3: the `.ws` component** (`style.css`, `app.js`)
- 2.2 CSS, `wsCanSplit()`, the rank-table container rules (2.7), `wsright` rules.
- Delete the `@media (max-width: 1279px) .qd-col` rule, the rank parts of the `1023` block, and the `@media (min-width: 1600px) .qsf-split` block.
- Pins: `test_ui_batch_5.py:31` (allowed media widths; `@container` is new syntax, so check the regex), `:43-47` (`.qsf-split … 560px`, `qsfBeside` matchMedia line, split markup).

**Step 4: screens.** Order is by value and risk. Each touches only its template function and container ids.

| # | Screen | Functions / containers touched |
|---|---|---|
| 4a | qsf | `renderQsf` template (3.13), `qsfSetView` (+`ws.dataset.view`), new `qsfDockStrip`, `qsfDrawDetail` / `qsfFoldCard` (strip open/close), `qsfBeside`; `.qsf-split` becomes `.ws-body.qsf-split` |
| 4b | today | `renderToday` skeleton, `asstBrief` (4 hosts, refresh line, error host), `.refreshing` rule; pin `test_today_shows_the_previous_list_while_it_refreshes` |
| 4c | stock | `renderStock` template, `renderProfile` (split into `#s-head` / `#s-facts`), `peers.js paintPeers` (`#s-grades`), section nav |
| 4d | account | `renderAccount` (split summary panel); `acctForm`/`acctRecord` unchanged |
| 4e | portfolio | `renderPortfolio` template (ctx/main/right/lower hosts); `holdingsHtml`, `loadSignals`, risk and equity loaders unchanged |
| 4f | assist | `renderAssist` template order; `renderAlerts($("#alertc"))`, `loadPlan`, `loadEarnings` unchanged |
| 4g | paper | `renderPaper` (title/tiles/form split) |
| 4h | committee | `renderCommittee` frame; `icDash`, `icPortsDraw`, `icCompare`, `icPerf` output main/right; `#icporttabs` vertical CSS |
| 4i | overview | `renderOverview` (group 1 → right) |
| 4j | macro | `renderMacro` template (`#econcal` into right) |
| 4k | map | `renderMap` template; `rotation.js` moves its first panel into `#map-rrg`; `sectorpicks.js:16` `block: "nearest"` |
| 4l | chart | `renderChart` template (ctx split) |
| 4m | compare | `renderCompare` template (ctx split, right, lower) |
| 4n | model | `renderModel` template (ctx/right/main/lower); `lab.js` override unchanged |
| 4o | lab | `RENDER.lab` skeleton, `renderLab` adds `.ws--single` on KR |
| 4p | coin | `renderCoin` template |
| 4q | watch | `renderWatch` template (`.ws--single`) |

**Step 5: approved behaviours.** D1 (row → right-panel card, `aria-selected`, QC-26 in the card) and D2 (screener keeps its view), only after the owner's yes.

**Step 6: verification.** The browser checks belong to the regression report.
- Every screen at 1920 / 1440 (full and rail) / 1280 / 1023 / 768 / 390, in dark and light.
- Each inventory row's check.
- The menu: keyboard, drawer, `qse-nav` reload.
- The sticky ranking header under the status band while a collect run is showing.

---

## 6. Owner decisions needed

| # | Question | Proposed default | If declined |
|---|---|---|---|
| D1 | In the two-column ranking, should a row click open the full card in the right panel (with the scan-vs-now note) instead of expanding the row? | Yes, at workstation widths only | Rows expand inline everywhere (today); the right panel shows a card only from the form or links |
| D2 | In the screener at workstation widths, should the 점수 button open the card on the right and stay in the screener? | Yes | Keeps switching to 오늘 순위 (today) |
| D3 | The top bar's market-state and data-time chips add one read each of existing endpoints (`/api/qsf/market-state`, `/api/automation/status`) on load and market change. Acceptable? (Owner decision 4 asks for both in the top bar.) | Yes | Chips omitted; market state stays in the qsf strip, data time in the footer/lab |
| D4 | Left menu default: full (232px) at every desktop width. At 1280–1439 the ranking/card split appears only with the rail (72px). | Full by default, rail on toggle (remembered as `qse-nav`) | Rail by default at 1024–1439 |
| D5 | Today: market tiles as a full-width strip in the context bar (coordinator draft had them in the right panel), candidates in the right panel | Strip | Tiles in the right column above the candidates |
| D6 | In-screen order changes on narrow screens: macro calendar below the indicators; assist plan table and settings moved up; committee perf reading first | Accept | Keep today's narrow order with `order` rules (possible for each) |

Not a decision, for the record:
- The visible desktop group row (S-18) disappears because the owner chose the left menu.
- Its group memory lives on in keys 1-9 and the phone bottom bar.
