# Financial visualization specification (workstation redesign)

Agent 3 (financial data visualization). Written 2026-11-24, read-only against baseline `7c8e0af`.
Inputs: `scratchpad/brief_design.md` (binding owner decisions), the dataviz method (choosing a form, colour formula, marks and anatomy, interaction, anti-patterns), every visual in `terminal/static/*.js`, `style.css`, and `audit/ui_redesign/EXISTING_UI_FEATURE_INVENTORY.md`.

Scope rules I kept:
- No score, rank, label or calculation changes. No new data sources and no new server fields. Every number drawn below already reaches the browser today. The three "new" visuals in section 6 draw payload fields that the screen already receives but does not draw yet. Each is marked **NEW (existing data)**.
- Missing data is never drawn as 0. Stale data is labelled. Judgement labels stay rule results.
- Colour rule C (owner decision 2): Korean screens red up / blue down; US screens and the unified account green up / red down; `data-color="kr"` switches it. Price colours only mean "price moved". Judgement colours: buy purple, hold grey, reduce/avoid/sell amber. Blue is the UI accent. A domain-score bar is neutral.
- Every feature row in the inventory keeps a location. Where this spec moves or hides something, it says where it goes (section 9 lists them all).

Contents
1. Shared chart foundation (tokens, theme, type, axes, marks, hover, missing, stale, empty, responsive, accessibility)
2. Palette decisions and validator results
3. Per-visual specifications (every existing visual, V-01 … V-38)
4. Investment score presentation
5. Factor contribution in the card
6. New visuals from existing payload fields (3) and ranking micro-visuals
7. Portfolio allocation, sector exposure, risk visualization, market regime indicator
8. Colour-role corrections (current code that breaks a binding rule)
9. Moves, hides and owner decisions
10. Not built: no data
11. Implementation order and test pins

---

## 1. Shared chart foundation

### 1.1 Where charts draw

All canvases go through `setupCanvas(cv, h)` (`app.js`), which handles DPR, `role="img"` and an `aria-label` fallback. Hover uses the one floating `#tip` (`.tip`). Redraws are registered with `redrawOn(tab, part, fn)`, and `redrawAll()` runs on theme change, OS scheme change and resize (120 ms debounce). The redesign keeps this machinery and adds three small shared helpers in `app.js`:

| Helper | Purpose | Replaces |
|---|---|---|
| `vizTokens()` | Reads every chart token once per draw: `const T = vizTokens()` returns `{surface, grid, axis, tick, ink, ink2, muted, cross, up, down, bench, bar, track, missing, s:[8], ma:{5..200}, warn, bad, ok, judgeBuy, judgeHold}`. It calls `getComputedStyle(document.documentElement)` once instead of ~15 `cssVar()` calls per draw. | Scattered `cssVar("--grid")` etc. in each draw function. `cssVar` stays for one-offs. |
| `vizFont(px = 11, weight = 400)` | Returns `"${weight} ${px}px -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', 'Noto Sans KR', sans-serif"`. Canvas text must use the page's Korean fallback. Today canvases say `-apple-system, sans-serif`, so Korean labels on Windows fall back to a different face. | `ctx.font = "11px -apple-system, sans-serif"` (12 places) |
| `vizHover(cv, {count, xOf, plotW, onIndex, onLeave})` | One pointer and keyboard crosshair driver (section 1.6). | Separate `onmousemove` blocks in `drawPrice`, `cmpDraw`, `cmpRoll`, `chaHover`; adds hover to `drawEquity`, `drawLab`, `mini`. |

`vizTokens()` must be called **inside** each draw function, never cached at load time. That way the theme toggle (`applyTheme` → `redrawAll`) and the market switch (`data-color` change → screen re-render) always paint the current values.

### 1.2 Chart tokens (dark is the default, light is kept)

Tokens live on `:root` (light) and `:root[data-theme="dark"]`. The structure is the same in both themes; only the values change. All chart code reads the names, never hex values. Exceptions are listed in section 2.6: the heatmap's fixed colour-blind pair, which is an owner decision, and the in-tile label ink.

| Token | Job | Dark | Light | Notes |
|---|---|---|---|---|
| `--viz-surface` | chart background (= `--panel`) | `#151E2B` | `#FFFFFF` | canvases are transparent. The heatmap and RRG fill it explicitly, so it must equal the panel they sit on |
| `--grid` | hairline gridlines, 1 px solid | `#1E2A3A` (1.16:1) | `#EDF0F3` | recessive by design, never dashed |
| `--axis` | zero line, baseline, plot frame | `#3A4A60` (1.86:1) | `#7B8594` | = `--line-strong` |
| `--tick` | tick and date labels | `#94A3B8` (6.54:1) | `#5D6673` (5.81:1) | = `--muted` |
| `--ink` | primary series (emphasis), close line, text in charts | `#E5EAF1` (13.9:1) | `#14171C` | |
| `--ink-2` | secondary text in tooltips | `#C3CCD8` | `#3B4350` | |
| `--cross` | crosshair hairline | `#94A3B8` @ 0.6 | `#5D6673` @ 0.6 | DOM line `.viz-xline` (exists as `.cha-xline`) |
| `--bench` | benchmark line | `#94A3B8` | `#5D6673` | = `--muted`; 1.5 px solid |
| `--viz-bar` | neutral magnitude fill (domain bars, meters, risk share) | `#8A98AD` | `#64748B` | not a judgement and not a price |
| `--viz-track` | meter track | `#1B2635` | `#EEF1F5` | = elevated / chip |
| `--viz-missing` | "no value" tile/cell fill | `#151E2B` + 1 px inset `#3A4A60` | `#FFFFFF` + 1 px inset `#C3C9D2` | never a ramp colour |
| `--up-intl` / `--down-intl` | price up / down, US and unified account | `#0FA05C` / `#E76250` | `#02721C` / `#C13A46` | validated (section 2.2) |
| `--up-kr` / `--down-kr` | price up / down, Korean screens | `#E76250` / `#4C8DFF` | `#C13A46` / `#1F5FD1` | validated |
| `--up` / `--down` | resolved by `data-color` | — | — | unchanged mechanism (`style.css` lines 15–19) |
| `--s1`…`--s8` | categorical identity (compare lines, lab models, RRG, account split) | `#3987e5 #d95926 #199e70 #c98500 #d55181 #0ca30c #9085e9 #e66767` | `#2a78d6 #eb6834 #1baf7a #eda100 #e87ba4 #008300 #6250d6 #e34948` | dark `--s6` changes from `#008300` (3.39:1 on the new panel) to `#0ca30c` (5.00:1) |
| `--ma5`…`--ma200` | moving-average identity | section 2.3 | section 2.3 | `--sma20/50/200` become aliases of `--ma20/50/200` |
| `--band-80` / `--band-50` | forecast range bands | `color-mix(in srgb, #8A98AD 30%, transparent)` / `color-mix(in srgb, #8A98AD 65%, transparent)` | `color-mix(in srgb, #64748B 22%, transparent)` / `color-mix(in srgb, #64748B 55%, transparent)` | were accent blue (section 8) |
| `--heat-mid` | diverging midpoint (0 %) | `#3A3F47` | `#CDD1D7` | neutral grey, no hue (current values kept) |
| `--heat-seq-lo` / `--heat-seq-hi` | score map, sequential, one neutral hue | `#243042` → `#CBD5E1` | `#E2E8F0` → `#334155` | were blue (section 8) |
| `--judge-buy` / `--judge-hold` / `--warn` | judgement (pills, never chart marks) | `#A78BFA` / `#8B97A8` / `#F59E0B` | `#6D28D9` / `#64748B` / `#8F5600` | binding decision 5. `--warn` dark changes from `#f0a531` to the brief's `#F59E0B` (7.81:1) |
| `--ok` / `--bad` | status only (data state, pass/fail) | `#22C55E` / `#F87171` | `#067A4B` / `#B3261E` | always with a text label |

Contrast of the dark text-bearing tokens was measured with the skill's `contrast()` on panel `#151E2B`, base `#0B1018` and elevated `#1B2635`. Every text token is ≥ 4.5:1 on all three except `--accent #3B82F6`, which is 4.15:1 on elevated. On dark surfaces, accent-coloured **text** therefore uses `--accent-text #60A5FA` (6.01:1 on elevated). The brief's `#EF4444` is 4.46:1 on the panel, below 4.5 for small text, so the down/up-kr red is `#E76250` (5.00:1 panel, ≥ 4.5 elevated).

### 1.3 Type in charts

| Element | Spec |
|---|---|
| Tick / date labels | `vizFont(11)` = `--fs-xs`, colour `--tick`. Price ticks are **right-aligned** to the canvas right edge minus 4 px (`textAlign = "right"`, x = `w - 4`), so digits line up at the right like a table column. Today they are left-aligned at `pw + 6`. |
| Axis title (RRG only) | `vizFont(11)`, `--tick` |
| Direct end labels (compare, MA tags) | `vizFont(11, 600)`, `--ink`, beside an 8 × 8 px swatch of the series colour. Text never takes the series colour. |
| In-tile labels (heatmap) | `vizFont(12, 600)` for the name on large tiles, `vizFont(10)` on small ones. Ink is chosen by tile luminance: `#FFFFFF` if luminance < 0.55, else `#14171C`. This is the existing `lumOf` rule and the same in both themes. |
| Tooltip | `--fs-sm` (12 px). The value comes first in `--ink` 600 weight; the label follows in `--ink-2`. `font-variant-numeric: tabular-nums` (`.tip .num`). |
| Hero numbers (score, market state, equity) | proportional figures (no `tabular-nums`) at display size. Tables keep `tabular-nums`. The `.qsf-score` rule must drop `.num` from the hero (currently `class="qsf-score num"`). |

### 1.4 Axes and ticks

- **One value axis per plot. No dual axes anywhere.** No current chart has one; keep it that way.
- **Value ticks use `niceTicks(lo, hi, n)`** (1·2·2.5·5 × 10ⁿ steps, `tickLabel` with `ko-KR` grouping). It is already used by `drawPrice` and the `chaDraw` price pane. It must also replace the "4 equal divisions" in:
  - `cmpDraw`: labels like 13 % or 27 % today. Use `niceTicks(lo*100, hi*100, 5)` and label `${v}%`.
  - `drawEquity`: same in percent, with one decimal only when the step is < 1.
  - `drawLab` (log scale): compute `niceTicks` on the return-percent range `(min nav − 1)…(max nav − 1)`, then place each tick at `y(1 + v/100)` on the log scale. The labels stay `+20 %` and the axis is still logarithmic.
  - `chaGrid` for the volume pane: `niceTicks(0, vmax, 2)`, formatted with `big(v, "")`.
  Fixed reference ticks stay fixed where the value is the meaning: RSI `[low, 50, high]` from `settings.rsi`, MACD `[0]`, rolling correlation `[-1, -0.5, 0, 0.5, 1]`.
- **Zero line**: wherever the range spans 0 (compare, equity, MACD, rolling correlation, macro minis), draw 1 px `--axis` across the plot. It is one step stronger than `--grid` and never dashed.
- **Date axis**: one helper `vizDates(ctx, dates, x, y, w)`. It replaces three copies (`drawPrice`, `cmpDraw`/`cmpRoll`, `chaDates`) and keeps the current rule: step = `round(n / (w < 600 ? 4 : 7))`; format `YY.MM` (`2026-11-24` → `26.11`); `YYYY-MM` when n > 600; no label in the last third of a step. Equity and lab currently print only the first and last full dates. They move to `vizDates` too, so every time axis reads the same way.
- **Gutter**: right gutter = 58 px for prices and 48 px for percents (as now). Plot right edge = `w − gutter`. Hit testing must use the same `pw` (section 1.6).

### 1.5 Mark specs (same in every chart)

| Mark | Spec | Applies to |
|---|---|---|
| Primary series line | 2 px, `lineJoin = lineCap = "round"` | close line, compare lines, equity "내 계좌", lab models, rolling correlation, RSI/MACD line |
| Context line | 1.5 px | moving averages, MACD signal, volume average, benchmark |
| Benchmark | 1.5 px `--bench`, solid; legend label "기준: SPY/코스피 …" | equity, lab SPY, new paper-book curve |
| Bollinger band | 9 % `--tick` wash plus 1 px dashed (4,3) edges. This is the **one dashed line** in the system: it reads as an envelope, and it is never a gridline. | `chaDraw` |
| Candle body | width = `min(bw × 0.7, 12)`, min 1 px; wick 1 px. Up/down colour by `close ≥ open`. A bad open (`goodOpen()` false) draws the wick only, in `--tick`. | `drawPrice`, `chaDraw` |
| Unconfirmed last candle | when the last bar's `intraday` is true (the flag `liveBadge(L.intraday)` already reads), draw the body **hollow**: 1.5 px stroke, no fill. Add a tag "장중·미확정" above it in `--warn` text, `vizFont(10)`. | `drawPrice`, `chaDraw` |
| Volume bar | width `bw × 0.8` capped at 12 px, square at the baseline, up/down colour at 0.45 alpha | both price charts |
| Bars (meters, domain, risk share) | 6 px high in table rows, 8 px in cards; fully rounded ends (`border-radius: 999px`) because they are meters, not baseline bars; fill `--viz-bar` on `--viz-track` | section 6.2 |
| Markers | ≥ 8 px (r ≥ 4), filled, 2 px ring in `--viz-surface` | RRG heads (r = 5 now, keep), signal triangles 9 px, MA end dots |
| Area wash | series colour at 10 % | only the 50 % / 80 % forecast bands and the Bollinger wash. No decorative area under lines. |
| Surface gap | 2 px `--viz-surface` between touching fills | heatmap tiles (exists: `r.x + 1 … r.w − 2`), sector frames (2 px stroke in `--viz-surface`, exists) |

### 1.6 Hover, crosshair and keyboard (hand-drawn canvas)

**Hit testing**, by chart family:

| Family | Approach | Charts |
|---|---|---|
| Index series (one value per x) | Snap to the nearest index. For candles: `i = clamp(floor((px − plotLeft) / bw), 0, n−1)` (existing). For lines spread over `pw`: `i = clamp(round(px / pw × (n−1)), 0, n−1)` (existing in compare). Ignore the pointer when `px > pw` (in the gutter). The crosshair snaps to `x(i)`, not to the pointer. | `drawPrice`, `chaDraw` (4 panes share one index), `cmpDraw`, `cmpRoll`, `drawEquity`, `drawLab`, `mini`, new paper curve, new score history |
| Rectangles | Linear scan of the stored rect list (`heat.rects`). Fine up to ~600 tiles. The hit area is the full tile **including** its 2 px gap: test against `[x, x+w) × [y, y+h)` of the unshrunk rect, which is what is stored today. | `heatDraw` |
| Points (scatter) | Nearest head within **12 px** (`Math.hypot < 12`, today `< 10`). That gives a 24 px target for an r = 5 dot plus its ring. | `rrgDraw` |
| HTML micro-visuals | Native `title`, plus `phone.js` taptip on coarse pointers. No canvas. | qd-bar, qsf-bar, meters, fc-strip |

**Pointer model.** All canvas charts use Pointer Events, not mouse events, so a finger works: `pointermove` and `pointerdown` show the readout, and `pointerleave` / `pointercancel` hide it. `chaHover` already does this; `drawPrice`, `cmpDraw`, `cmpRoll` and `heatDraw` still use `onmousemove` and must move. Each chart container gets `touch-action: pan-y` (already on `.cha-stack`) so vertical page scroll still works on phones while a horizontal drag scrubs the crosshair.

**Crosshair.** A DOM overlay line `.viz-xline` is absolutely positioned inside the chart's `position: relative` wrapper (`.chart`, `.cha-stack`). Width 1 px, background `--cross`, `pointer-events: none`. It is a generalisation of `.cha-xline`. Moving the crosshair never repaints the canvas. On `chaDraw` it spans all four panes (as now). The price chart also shows a **y-value tag** in the right gutter: a 16 px high box at the hovered bar's close, filled `--ink`, text `--viz-surface`, showing `tickLabel(close, digits)`.

**Tooltip (`#tip`).**
- One readout lists **every series at that x**, sorted by value descending for compare (as now). In the order drawn for the others.
- Value first, then name. Rows are keyed with a short **line key** (12 × 2 px of the series colour), not a filled box. The current `.swatch` squares inside tooltips become `.key-line`; legends keep swatches for bars and line keys for lines.
- Placement: right of the pointer by 14 px, flipped left when it would overflow (exists). Also clamp `top` so the tip stays inside `[8, innerHeight − tip.offsetHeight − 8]` (missing today).
- Content keeps `esc()` on every data string; ticker names come from payloads.
- Missing values in the tip print `없음`, never `0` or blank (the current `fmt` already returns `-`; use `DASH`).
- On touch, the tip is anchored 16 px above the finger contact point, not below it under the finger.

**Keyboard.** Every chart canvas that has a hover readout gets `tabindex="0"` and these keys:
- ←/→ move the index by 1; Shift+←/→ by 10; Home/End jump to the first/last.
- Esc hides the readout.

The readout shows at `x(i)`. The same text is written to one visually hidden polite live region `#viz-live` (`role="status"`), so screen-reader users hear the values. Focus style: 2 px `--accent` outline offset 2 px (`.chart canvas:focus-visible`). Treemap: ←/→ step through `heat.rects` in drawing order, and Enter opens the ticker (same as click). RRG: ←/→ step through `rrg.heads`, and Enter loads sector picks (same as click).

### 1.7 Missing data (gaps, never 0)

| Rule | Where it already holds | Where it must change |
|---|---|---|
| A line breaks at a non-number (`line()` lifts the pen) | `line()` in `app.js` | `spark()` and `mini()` **filter out** non-numbers before drawing, which pulls later points left and silently shortens time. Keep the index positions, draw with `line()` so gaps show, and compute lo/hi from numbers only. |
| A missing bar draws nothing | volume, MACD histogram | — |
| A missing tile is `--viz-missing` with no value text | heatmap uses `--chip` | use `--viz-missing` (panel fill + 1 px inset `--axis`), so "no value" never looks like a low score or a flat 0 % move. Tooltip line "점수 없음" / "등락 없음". |
| A missing meter shows text, not an empty bar | `qsfBar` → "데이터 없음"; `qd-bar` → `—` | `loadRisk` risk-share bar: `width: 0%` when `risk_share` is missing. Must render `—` with no `.bar`. A 0 % bar claims a 0 % risk contribution. |
| Clamping hides negatives | — | risk-share bars clamp negative `risk_share` (a hedge) to 0 width while the text shows the negative value. Spec: draw a negative share as a bar growing **left** from a centre tick (diverging meter, `--viz-bar`), sign in the text. |
| A series with < 2 points draws nothing and says why | `spark` returns silently | `spark`: keep silent (the card shows the date and badge). `mini`: show `.meta` "관측치 부족" under the card. |

### 1.8 Stale, intraday, frozen and experimental labels

- The project has **no MOCK status**: `STATUS_KO` = REAL / STALE / UNAVAILABLE / FROZEN / EXPERIMENTAL. No chart may invent one.
- Every chart panel's header row shows `badge(status)` **in the header, beside the title**, whenever status ≠ REAL. Today the badge sits in the meta line under the chart (`#c-meta`, `#cmp-meta`, `#heat-meta`, `#rrg-meta`), which is easy to miss. The meta line keeps its full text (source, fetched time, basis). Only the badge is duplicated up.
- Intraday: the "장중·미확정" `liveBadge` stays in the header and meta, and the last candle is hollow (1.5).
- Forecast (FC-1/FC-2) verdict badges (`fcTestBadge`, `fcTouchBadge`) keep their exact text. They are verdicts with reasons (memory rule: verdict labels need reasons) and sit beside the strip.
- Paper / hypothetical data (lab, paper book, committee portfolios) keeps its `참고용` / `가상` badges in the panel header. In charts, the plot background is unchanged (no watermark).

### 1.9 Empty states

A chart with no drawable data never draws axes. It hides the canvas (`cv.hidden = true`) and shows one `.empty` line **in the plot's place, at the plot's height** (min-height = the chart height). That way the layout does not jump when data arrives. Each chart's existing reason text is kept verbatim (`cmpRoll` "두 개 이상이고 기간이 상관을 잴 만큼 길 때 보입니다.", `loadEquity` "거래 기록이 생기면 계좌 가치 곡선을 그립니다.", etc.). On refetch (market or range change), hold the previous render at `opacity: .45` with `aria-busy="true"` on the wrapper until the new data paints. No skeleton flash (`asstBrief` already uses this pattern with `.refreshing`).

### 1.10 Responsive heights and widths

The canvas width is always the wrapper's width (`setupCanvas` uses `clientWidth`). Heights per breakpoint:

| Chart | ≥ 1600 (workstation, right column) | 1024–1599 | 641–1023 | ≤ 640 |
|---|---|---|---|---|
| Stock price (`drawPrice`) | 420 | 420 | 360 | 300 |
| 차트분석 price / vol / RSI / MACD | 400 / 90 / 100 / 110 | same | 360 / 80 / 90 / 100 | 300 / 70 / 80 / 90 |
| Compare / rolling corr | 380 / 240 | 380 / 240 | 320 / 220 | 280 / 200 |
| Heatmap | 620 | 620 | 560 | 520 |
| RRG | `min(560, width)` square | same | same | `width` (square) |
| Equity / paper curve (new) | 240 | 240 | 220 | 200 |
| Lab | 320 | 320 | 280 | 240 |
| Macro mini | 90 | 90 | 90 | 90 |
| Score history (new) | 120 | 120 | 110 | 100 |
| Spark (card / table) | 28 / 24 | same | same | same |

When a chart sits in the workstation's **right analytics column** (~480–560 px at 1600 px), `w < 600`, so the date rule drops to 4 labels by itself. Compare end labels need `padR = 92`. Below 520 px of plot width, compare drops its direct end labels and relies on the legend (the rule is already `labels = series ≤ 4`; add `&& w >= 520`). Use `isPhone()` (≤ 640) and a new `isNarrow()` (≤ 1023) to pick heights. Do not use the window width for charts inside the right column: use the wrapper width (`cv.parentElement.clientWidth`) for the label decisions.

### 1.11 Accessibility

- `role="img"` plus a **data summary** `aria-label`, not just the panel title. Each draw sets it. `drawPrice` does this today ("TICKER 가격 차트: A부터 B까지, 종가 x에서 y"). Add equivalents:
  - compare: "수익률 비교: 기간 A~B, 종목별 기간 수익률 …"
  - equity: "내 계좌 TWR x%, 기준 지수 y%, 기간 A~B"
  - heatmap: "시장 히트맵: N개 종목, 색은 1일 등락, 크기는 시가총액"
  - RRG: "업종 순환: 선도 n, 개선 n, 약화 n, 침체 n"
  - lab: "모델 n개와 SPY 누적 수익률"
  - chart analysis: as `drawPrice`, plus "RSI 마지막 값 x"
- **Sparklines stay `aria-hidden`**. The card text carries the values.
- **Table alternative.** Every chart must have its numbers reachable without hover. Existing twins are kept:
  - compare → `#cmp-stats`
  - correlation → `#cmp-corr`
  - RRG → `#rrg-table`
  - lab → `#labtbl`
  - chart signals → `#cha-sigs`
  - forecast → `fc-table`
  - risk → its table

  Missing twins get a `<details class="viz-table"><summary>표로 보기</summary>` under the chart, built from the **same payload**:
  - `drawPrice`: the last 30 bars (date, 시, 고, 저, 종, 거래량, 20/50/200일).
  - `chaDraw`: the last 30 bars with RSI and MACD.
  - `drawEquity`: one row per month-end point of `d.points` (date, 내 계좌 %, 기준 %).
  - `heatDraw`: tiles sorted by the active colour value (name, ticker, sector, value, market cap).
  - `mini`: the card already shows value, previous and 1-year-ago; enough.
  - New paper curve: the last 20 sessions.
- `@media (forced-colors: active)`: canvases get `border: 1px solid CanvasText`. Legends and badges keep text labels. No information is carried by colour alone in any chart: up/down carries a sign and an arrow (`pct()` prints the sign), judgement pills carry text, RRG heads sit in a named quadrant, and MA lines carry end tags (2.3).
- `prefers-reduced-motion`: there is no chart animation. Keep it that way. The crosshair does not ease.

### 1.12 Dark/light rendering

- The canvas reads tokens at draw time (`vizTokens()` inside every draw function). `applyTheme()` already calls `redrawAll()`, and the OS listener calls `applyTheme("auto")`. Hidden tabs are queued in `redrawLater` and painted by `redrawShown` on entry. Nothing else is needed.
- **Market switch** changes `data-color`, and `setMarket` clears every tab and resets redrawers, so the next draw reads the new up/down. A chart that is visible during a market switch is re-rendered by its tab's render function; no extra hook.
- Values that were hard-coded in JS move to tokens:
  - `map.js` score-ramp RGB arrays and `mid` arrays → `--heat-seq-lo/hi`, `--heat-mid`.
  - `HEAT_CB` stays a JS constant: it is the owner-chosen colour-blind pair, fixed in both themes by design. Its dark/light pick moves from `lumOf(--panel)` to `document.documentElement.dataset.theme`.
  - The in-tile label ink `#ffffff` / `#14171c` stays fixed: a label inside a fill is chosen by the fill's luminance, not by theme.
- Test both themes for every chart at 1600, 1280, 768 and 390 px (section 11).

---

## 2. Palette decisions and validator results

All runs used the skill's `scripts/validate_palette.js` (OKLab ΔE ×100, Machado 2009 CVD simulation). Surfaces: dark panel `#151E2B`, light panel `#FFFFFF`. Output pasted verbatim (blank lines removed).

### 2.1 Categorical series `--s1…--s8` (compare, lab, RRG, account split)

```
=== A. series s1-s8 reference dark steps on new panel #151E2B
Palette (dark, surface #151E2B, categorical): 8 slots
  [PASS] Lightness band         all 8 inside L 0.48–0.67
  [PASS] Chroma floor           all 8 >= 0.1
  [PASS] CVD separation         worst adjacent #c98500↔#199e70 ΔE 8.4 (protan) · tritan 8.7
  [PASS] Normal-vision floor    worst adjacent #d55181↔#c98500 ΔE 19.3 (normal)
  [PASS] Contrast vs surface    all 8 >= 3:1
  → ALL CHECKS PASS
=== B. series light on #FFFFFF
Palette (light, surface #ffffff, categorical): 8 slots
  [PASS] Lightness band         all 8 inside L 0.43–0.77
  [PASS] Chroma floor           all 8 >= 0.1
  [PASS] CVD separation         worst adjacent #eda100↔#1baf7a ΔE 9.1 (protan) · tritan 5.8
  [PASS] Normal-vision floor    worst adjacent #e87ba4↔#eda100 ΔE 19.6 (normal)
  [WARN] Contrast vs surface    below 3:1 — relief required (visible labels or table view): [["#1baf7a",2.82],["#eda100",2.17],["#e87ba4",2.69]]
  → ALL CHECKS PASS
```

The light WARN obligates relief. Every categorical chart has direct labels or a table twin: compare (end labels ≤ 4 + stats table), lab (table with ● key), RRG (names beside dots + table), account split (figures in the table).

**Market-aware slot order for compare** (colour still follows the entity for as long as it stays on the chart):
- US and the unified account: `s1 s2 s3 s4 s5 s7 s6 s8`. Green and red go last, so a compare line does not look like "up/down" until more than six series are on the chart.
- Korean screens: `s2 s3 s4 s5 s6 s7 s8 s1`. Blue (= down on Korean screens) goes last, and red (= up) sits in 7th place. Today the default first series `^KS11` gets blue, the Korean "down" colour.
- `cmp.slots` is reset when `state.market` changes, so the order follows the screen.

```
=== CMP-US dark order s1,s2,s3,s4,s5,s7,s6,s8
  [PASS] Lightness band / [PASS] Chroma floor
  [WARN] CVD separation         worst adjacent #e66767↔#0ca30c ΔE 7.1 (deutan) · tritan 8.7
  [PASS] Normal-vision floor    worst adjacent #d55181↔#c98500 ΔE 19.3 (normal)
  [PASS] Contrast vs surface    all 8 >= 3:1
=== CMP-US light order
  [WARN] CVD separation         worst adjacent #e34948↔#008300 ΔE 7.2 (protan) · tritan 5.8
  [PASS] Normal-vision floor    worst adjacent #e87ba4↔#eda100 ΔE 19.6 (normal)
  [WARN] Contrast vs surface    below 3:1 — relief required: [["#1baf7a",2.82],["#eda100",2.17],["#e87ba4",2.69]]
=== CMP-KR dark order s2,s3,s4,s5,s6,s7,s8,s1
  [PASS] CVD separation         worst adjacent #c98500↔#199e70 ΔE 8.4 (protan) · tritan 8.7
  [PASS] Normal-vision floor    worst adjacent #d55181↔#c98500 ΔE 19.3 (normal)
  [PASS] Contrast vs surface    all 8 >= 3:1   → ALL CHECKS PASS
=== CMP-KR light order s2,s3,s4,s5,s6,s7,s8,s1
  [PASS] CVD separation         worst adjacent #eda100↔#1baf7a ΔE 9.1 (protan) · tritan 5.8
  [PASS] Normal-vision floor    worst adjacent #e87ba4↔#eda100 ΔE 19.6 (normal)
  [WARN] Contrast vs surface    below 3:1 — relief required: [["#1baf7a",2.82],["#eda100",2.17],["#e87ba4",2.69]]
```

(An earlier KR candidate, `s2…s7,s1,s8`, **failed**: blue next to violet, ΔE 1.9 CVD / 9.8 normal. It was rejected.) The US WARN (7th↔8th, CVD 6–8) is legal only with secondary encoding. Compare is capped at 8 series and lists every series in the legend with its return. Past four series, the direct end labels drop and the legend + tooltip + stats table carry identity.

### 2.2 Price up/down (rule C), re-picked for the new dark panel

The brief's `#22C55E` (L 0.72, outside the dark band; deutan ΔE 5.5 vs red, a FAIL) and `#EF4444` (4.46:1, under 4.5 for text) were replaced. I searched OKLCH for the green/red pair that maximises deutan separation while keeping ≥ 4.5:1 on the elevated surface `#1B2635`.

```
=== C1 brief pair (rejected) up/down intl dark  #22C55E,#F05252
  [FAIL] Lightness band         outside band: [["#22C55E",0.723]]
  [FAIL] CVD separation         worst adjacent #F05252↔#22C55E ΔE 5.5 (deutan)
=== P1 intl dark final  #0FA05C,#E76250
  [PASS] Lightness band         all 2 inside L 0.48–0.67
  [PASS] Chroma floor           all 2 >= 0.1
  [WARN] CVD separation         worst adjacent #E76250↔#0FA05C ΔE 6.6 (deutan) · tritan 32.8
  [PASS] Normal-vision floor    worst adjacent #E76250↔#0FA05C ΔE 28.6 (normal)
  [PASS] Contrast vs surface    all 2 >= 3:1
=== P2 kr dark final  #E76250,#4C8DFF
  [PASS] CVD separation         worst adjacent #4C8DFF↔#E76250 ΔE 25.2 (protan) · tritan 33.0
  [PASS] Normal-vision floor    worst adjacent #4C8DFF↔#E76250 ΔE 31.7 (normal)   → ALL CHECKS PASS
=== P3 intl light final  #02721C,#C13A46
  [PASS] CVD separation         worst adjacent #C13A46↔#02721C ΔE 8.1 (deutan) · tritan 30.8
  [PASS] Normal-vision floor    worst adjacent #C13A46↔#02721C ΔE 29.3 (normal)   → ALL CHECKS PASS
=== P4 kr light final  #C13A46,#1F5FD1
  [PASS] CVD separation         worst adjacent #1F5FD1↔#C13A46 ΔE 22.4 (protan) · tritan 30.8
  [PASS] Normal-vision floor    worst adjacent #1F5FD1↔#C13A46 ΔE 31.1 (normal)   → ALL CHECKS PASS
```

Text contrast (WCAG 2) of the finals:

| Colour | Dark panel | Dark elevated | Light panel | Light chip |
|---|---|---|---|---|
| `#0FA05C` up-intl (dark) | 4.95 | ≥ 4.5 | — | — |
| `#E76250` down-intl / up-kr (dark) | 5.00 | ≥ 4.5 | — | — |
| `#4C8DFF` down-kr (dark) | 5.24 | 4.77 | — | — |
| `#02721C` up-intl (light) | — | — | 6.13 | ≥ 4.5 |
| `#C13A46` down-intl / up-kr (light) | — | — | 5.30 | ≥ 4.5 |
| `#1F5FD1` down-kr (light) | — | — | 5.81 | 5.13 |

The dark green/red pair sits in the CVD 6–8 band. No green/red pair on this surface clears 8 while keeping text contrast; the search topped out at 6.6. That is legal **only** with secondary encoding, which rule C already requires: every price change prints its sign (`+`/`−`) and the table arrow, and candles carry the OHLC tooltip. The heatmap keeps its owner-chosen colour-blind option `파랑·주황` for US screens (section 8, item 9).

### 2.3 Moving averages (`--ma5 … --ma200`), drawn over candles

Constraint found by search: MA lines sit on top of up/down candles, so the honest test is MAs **plus** both candle colours. With 3–4 default MAs plus 2 candle colours, all-pairs can never pass (the method's series cap is 3). The design therefore combines three things:
- (a) the **default sets** in each market avoid the candle hues;
- (b) MAs are validated **adjacent in period order**, because neighbouring periods draw neighbouring lines;
- (c) **every MA line gets a direct end tag** (secondary encoding, mandatory).

Mapping (per market, matching rule C):

| Period | US (green up / red down) dark · light | KR (red up / blue down) dark · light | Default in |
|---|---|---|---|
| 5 | pink `#F7A8CF` · `#e87ba4` | same | KR chart analysis |
| 10 | green `#0ca30c` · `#008300` | same | — |
| 20 | amber `#E8C547` · `#eda100` | same | all four default sets |
| 50 | blue `#3987e5` · `#2a78d6` | aqua `#199e70` · `#1baf7a` (shared with 60; current KR rule "50-day line leaves blue" kept) | US both; KR stock chart |
| 60 | aqua `#199e70` · `#1baf7a` | same | KR chart analysis |
| 120 | violet `#9085e9` · `#6250d6` | neutral `#94A3B8` · `#64748B` (solid 1.5 px; the Bollinger edges are dashed, so they stay distinct) | KR chart analysis |
| 200 | slate `#CBD5E1` · `#334155` (neutral) | same | US both; KR stock chart |

Candle separation of the defaults (pairwise vs up and down, dark; CVD / normal ΔE), measured:
- US 20 amber-step `#E8C547`: 16.8/25.9 vs up, 17.4/23.9 vs down.
- US 50 blue: 22.1/23.9, 22.2/30.7.
- 200 slate: 23.7/29.2, 22.6/27.8.
- KR 5 pink `#F7A8CF`: 18.4/19.6 vs red up.
- KR 60 aqua: 8.0/27.6 vs up, 21.9/23.9 vs down.
- KR 120 grey: 13.6/20.1, 14.0/15.6.

All defaults clear the normal-vision floor of 15 against both candle colours.

Adjacent validation of the chromatic MAs in period order:
```
=== MA-US dark full order 5 pink,10 green,20 amber(yellow step),50 blue,60 aqua,120 violet
  [FAIL] Lightness band         outside band: [["#F7A8CF",0.819],["#E8C547",0.832]]
  [PASS] Chroma floor           all 6 >= 0.1
  [PASS] CVD separation         worst adjacent #E8C547↔#0ca30c ΔE 15.2 (protan) · tritan 4.0
  [PASS] Normal-vision floor    worst adjacent #199e70↔#3987e5 ΔE 20.9 (normal)
  [PASS] Contrast vs surface    all 6 >= 3:1
=== MA-US light full order
  [PASS] Lightness band / Chroma floor
  [PASS] CVD separation         worst adjacent #eda100↔#008300 ΔE 16.2 (protan) · tritan 9.6
  [PASS] Normal-vision floor    worst adjacent #1baf7a↔#2a78d6 ΔE 24.0 (normal)
  [WARN] Contrast vs surface    below 3:1 — relief required: [["#e87ba4",2.69],["#eda100",2.17],["#1baf7a",2.82]]
=== MA-KR dark chromatic order 5 pink,10 green,20 amber,50/60 aqua
  [FAIL] Lightness band         outside band: [["#F7A8CF",0.819],["#E8C547",0.832]]
  [PASS] CVD separation         worst adjacent #E8C547↔#0ca30c ΔE 15.2 (protan) · tritan 28.1
  [PASS] Normal-vision floor    worst adjacent #199e70↔#E8C547 ΔE 26.3 (normal)
=== MA-KR light chromatic order
  [PASS] CVD separation         worst adjacent #1baf7a↔#eda100 ΔE 9.1 (protan) · tritan 27.0
  [PASS] Normal-vision floor    worst adjacent #1baf7a↔#eda100 ΔE 22.9 (normal)
  [WARN] Contrast vs surface    below 3:1 — relief required: [["#e87ba4",2.69],["#eda100",2.17],["#1baf7a",2.82]]
```

**Declared deviation, for the owner to accept or veto:** the two dark steps `#F7A8CF` and `#E8C547` sit above the categorical lightness band (L 0.82/0.83 > 0.67). That check exists to keep categorical series equally weighted. Here those two lines must be lighter to separate from the red candle: the in-band amber `#c98500` measures only 11.8 normal-vision ΔE against `#E76250` (FAIL), and the in-band options the search found were muddy (`#a1790c`, CVD 5.6). The lines stay at 1.5 px, so the extra lightness does not make them dominate. If the owner rejects this, the fallback is `#c98500` with the candle conflict covered only by the end tags.

Other trade-offs:
- KR 50 and 60 share aqua. Both are only on screen when the user ticks both in 차트분석 (max 5 of 7). Their end tags "50" / "60" then carry identity, and the `#cha-ma` swatches show the same colour with the number.
- Non-default periods (US 10 green, US 60 aqua) can sit near the up colour. The end tags carry them too.

**MA end tag (mandatory)**: at the last non-missing value of each MA, draw a 6 px dot (ring 2 px `--viz-surface`) at `x(last)`. In the right gutter, at that y, draw a tag: the 8 px colour swatch plus the period number (`20`) in `--ink` `vizFont(10, 600)`. Collision: sort the tags by y and push them apart by 12 px within the plot. On compare, this is the existing end-label routine (`cmpDraw` lines 103–109); reuse it as `vizEndTags(ctx, items, x0, top, bottom)`. On the stock chart the h2 legend (`20일선/50일선/200일선`) stays.

### 2.4 RRG quadrant colours (scatter → all-pairs, capped at three hues)

The current dots use `--s3, --s4, --s8, --s1`: four hues in an all-pairs form (over the cap). On Korean screens, 침체 (lagging) is red (= up) and 개선 (improving) is blue (= down), the reverse of the reading. New mapping: 선도 `--s3` aqua, 개선 `--s7` violet, 약화 `--s2` orange, 침체 neutral `--judge-hold`-grey `#8B97A8` / `#64748B`. Grey reads as "nothing doing", and it is not a categorical slot.

```
=== RRG dark s3,s7,s2 all pairs
  [PASS] Lightness band / Chroma floor
  [PASS] CVD separation         worst all-pairs #d95926↔#199e70 ΔE 9.4 (deutan) · tritan 9.4
  [PASS] Normal-vision floor    worst all-pairs #9085e9↔#199e70 ΔE 24.6 (normal)
  [PASS] Contrast vs surface    all 3 >= 3:1   → ALL CHECKS PASS
=== RRG light s3,s7,s2 all pairs
  [PASS] CVD separation         worst all-pairs #eb6834↔#1baf7a ΔE 9.2 (deutan) · tritan 18.0
  [PASS] Normal-vision floor    worst all-pairs #eb6834↔#1baf7a ΔE 27.6 (normal)
  [WARN] Contrast vs surface    below 3:1 — relief required: [["#1baf7a",2.82]]
```

The quadrant is also encoded by position and by the corner name, and every dot is named. The table `#rrg-table` is the relief.

### 2.5 Lab models (`LAB_COLORS`)

Today the lab uses `--sma20, --ok, --sma200, --sma50` for its four models. `--ok` is a **status** colour used as series 2, which breaks the reserved-status rule. New: `MOM_12_1 --s1`, `LOWVOL_252 --s2`, `TREND_SWING --s3`, `BASE_EW --s4`, `SPY --bench`. The lab is US-only (green up / red down), and none of these is green or red.

```
=== LAB dark s1-s4
  [PASS] CVD separation         worst adjacent #c98500↔#199e70 ΔE 8.4 (protan) · tritan 24.4
  [PASS] Normal-vision floor    worst adjacent #c98500↔#199e70 ΔE 19.8 (normal)
  [PASS] Contrast vs surface    all 4 >= 3:1   → ALL CHECKS PASS
=== LAB light s1-s4
  [PASS] CVD separation         worst adjacent #eda100↔#1baf7a ΔE 9.1 (protan) · tritan 27.0
  [PASS] Normal-vision floor    worst adjacent #eda100↔#1baf7a ΔE 22.9 (normal)
  [WARN] Contrast vs surface    below 3:1 — relief required: [["#1baf7a",2.82],["#eda100",2.17]]
```

The relief is the `#labtbl` table with its ● keys (exists), plus direct end labels (4 series ≤ 4).

### 2.5b Heatmap colour-blind pair (owner decision 2026-11-24, kept)

```
=== C5 heat colour-blind pair dark  #5b9cff,#f0a531
  [FAIL] Lightness band         outside band: [["#5b9cff",0.695],["#f0a531",0.777]]
  [PASS] CVD separation         worst adjacent #f0a531↔#5b9cff ΔE 28.7 (protan)
  [PASS] Normal-vision floor    ΔE 32.1   [PASS] Contrast vs surface
```

The band FAIL is irrelevant for a two-pole diverging ramp: these are the **saturated end** of a ramp that mixes from the grey midpoint, not categorical series. Kept as decided. See section 8, item 9 for the Korean-screen note.

### 2.6 Sequential and diverging ramps (not categorical, so not run through the categorical validator; the method says that check fails a ramp by design)

| Ramp | Use | Dark | Light | Rule |
|---|---|---|---|---|
| Diverging price (heatmap 1d/5d/1m) | change % | `--heat-mid #3A3F47` → `--up` / `--down` at ±span (3 %/8 %/15 %) | `#CDD1D7` → `--up` / `--down` | existing `mixRgb`; neutral grey midpoint; saturates past ±span; legend states the span (exists) |
| Sequential score (heatmap score mode) | QSF score 40→80 | `#243042` → `#CBD5E1` | `#E2E8F0` → `#334155` | one neutral hue, monotone lightness; was blue (section 8) |
| Correlation cells (new shading, 6.4) | \|r\| 0→1 | `--viz-track` → `color-mix(--viz-bar 70%)` | same tokens | neutral; the sign is always printed |

---

## 3. Per-visual specifications

Format per visual:
- **Shows**: the analytical relationship.
- **Form**: the chart type and whether it is kept or changed, with the reason.
- **Axes**: axes, units, labels and ticks.
- **Colour**: colour by job.
- **Marks**: mark specs.
- **Hover**: tooltip, crosshair and hit-testing.
- **Bench**: benchmark treatment.
- **Missing**: missing-data treatment.
- **Stale**: stale and other status labels.
- **Empty**: empty state.
- **Resp**: responsive behaviour.
- **A11y**: accessibility.
- **Theme**: dark/light rendering.

Common rules from section 1 are not repeated.

### V-01 Sparkline — `app.js:spark` (overview cards `card()`, watchlist `renderWatch` 추세(30일) column, Today tiles `asstTiles`)
- **Shows:** the shape of the last ~30 closes for one instrument, against its own first day.
- **Form:** kept (a stat tile with a sparkline is the right form for a single current value plus trend).
- **Axes:** none. A dotted first-day baseline exists today (`setLineDash([2,3])`). Change it to a **1 px solid `--axis` hairline** at 50 % alpha: a dashed rule reads as a threshold. "그래프 폭 x%" (`sparkRange`) stays as the scale caption, because each card auto-scales.
- **Colour:** last ≥ first → `--up`, else `--down`, per rule C (price moved). `data-plain` (VIX, rates, FX, `NEUTRAL_TILE`) → `--ink`. Keep both.
- **Marks:** 1.5 px line (was 1.4); end dot r = 2 (4 px — the one place below the 8 px marker rule, because the tile is 28 px tall; document it as the sparkline exception).
- **Hover:** none (`aria-hidden`); the card's text carries the values.
- **Bench:** none.
- **Missing:** gaps via `line()` (1.7). Today nulls are filtered and the line is compressed.
- **Stale:** the card meta keeps `badge(status)` + `liveBadge`.
- **Empty:** fewer than 2 points → nothing drawn; the card keeps its date.
- **Resp:** 70 × 28 in cards, 80 × 24 in the watch table (the inline style moves to `.spark-sm` in CSS).
- **A11y:** hidden; values in text.
- **Theme:** tokens per draw; `redrawOn("overview"|"today"|"watch","sparks")` exists.

### V-02 Stock price chart — `app.js:drawPrice` (종목 정보, `#pc`)
- **Shows:** daily OHLC over 3mo/1y/5y with 20/50/200-day SMAs (server-computed) and volume, so the user sees trend and where price sits against its averages.
- **Form:** kept (candles, falling back to a close line when `bw < 1.8`). Volume stays a separate pane inside the same canvas (bottom 18 %), sharing the x axis. That is not a dual axis.
- **Axes:** right price axis, `niceTicks`, right-aligned labels (1.3). Volume pane has no axis labels today; add one label, the `big(vmax)` at the top-right of the volume pane in `--tick`. Dates via `vizDates`.
- **Colour:** candles and volume `--up`/`--down`; bad open → wick only in `--tick`; SMA `--ma20/50/200` per 2.3; close line `--ink`.
- **Marks:** per 1.5; hollow intraday last candle; MA end tags (2.3); y-value crosshair tag.
- **Hover:** index snap; `.viz-xline`; tooltip as today (date, 시 고 저 종, 거래량, 20/50/200일), with "없음(원자료 이상)" kept for a bad open; Pointer Events; keyboard.
- **Bench:** none. The relative-to-index view lives in 비교; add a one-line link "지수와 비교" → `compareWith([ticker])`, which exists (CM-05 behaviour).
- **Missing:** SMA gaps at the start (fewer than N days) stay gaps; a missing volume draws nothing.
- **Stale:** the header shows `badge(c.status)` when ≠ REAL, plus `liveBadge`; `#c-meta` text kept.
- **Empty:** UNAVAILABLE → canvas hidden, `#c-meta` empty text kept at plot height.
- **Resp:** 420 / 360 / 300 (1.10). The range seg and SMA legend stay in the panel header and wrap under the title at ≤ 640.
- **A11y:** existing summary label; add "표로 보기" (last 30 bars); `tabindex=0` with keys.
- **Theme:** `redrawOn` exists.

### V-03 Macro mini chart — `app.js:mini` (거시 cards `.mcard`)
- **Shows:** the level of one macro series over ~260 observations.
- **Form:** kept (small line).
- **Axes:** today only the first and last month. Add a 2-tick y axis: the min and max values via `fmtMacro`, at the left inside the plot top and bottom, `--tick`, 10 px. Keep the first/last dates.
- **Colour:** line `--ink`, not `--accent`. A macro level is not a price move and not the UI accent, and on Korean screens blue means down. Zero line `--axis` when the range spans 0 (exists).
- **Marks:** 1.5 px; end dot r = 3.
- **Hover:** **add** `vizHover`: the tooltip shows the date and the formatted value (`fmtMacro`), index snap.
- **Bench:** none.
- **Missing:** gaps kept by index (stop filtering, 1.7). Observations are irregular by nature, so the x positions are observation order; say so in the existing footnote "차트는 최근 약 260개 관측치".
- **Stale:** the card shows `badge(m.status)` (exists).
- **Empty:** fewer than 2 points → "관측치 부족" `.meta`.
- **Resp:** 90 px; the grid is `minmax(280px, 1fr)`.
- **A11y:** label "<label> 최근 값 x (날짜)"; values are in the card text.
- **Theme:** `redrawOn("macro","minis")` exists.

### V-04 … V-08 차트분석 — `chart.js:chaDraw` (price, volume, RSI, MACD panes) and `chaHover`
- **Shows:** classic technical state: candles/OHLC/line with chosen MAs, Bollinger band, volume with its average, RSI with bands, and MACD line/signal/histogram. Classic signals are marked as **untested** (CHART-1 rule; never feeds a score).
- **Form:** kept: four stacked panes sharing one x index (small multiples on one time axis, the honest way to show 4 measures with different units, never a dual axis).
- **Axes:**
  - price: `niceTicks`;
  - volume: `niceTicks(0, vmax, 2)` with `big()`;
  - RSI: fixed `[low, 50, high]` with the 9 % `--tick` band between low/high (exists);
  - MACD: zero line in `--axis`, plus 2 nice ticks;
  - dates on the price and MACD panes (exists).
  The pane captions `.cha-pane` (`RSI(14, 와일더 방식) · 기준선 30/70`, `MACD(12, 26, 9) · 선, 시그널, 막대`) stay as text above each pane.
- **Colour:**
  - candles and volume `--up`/`--down` (price moved);
  - MAs per 2.3;
  - Bollinger `--tick` wash + dashed edges;
  - close line (line mode) `--ink`;
  - volume average `--ink` 1.5 px;
  - RSI line `--ink` (was `--accent`);
  - MACD line `--ink`, signal `--ma20` amber (exists via `chaMaColor(20)`);
  - **MACD histogram `--viz-bar` at 45 %**, both signs (was up/down). A momentum sign is not a price move; the position above or below the zero line carries the sign.
  - **Signal markers `--ink`** triangles with a 2 px surface ring, shape ▲/▼ carrying the side (were up/down coloured). **Volume-spike dot `--ink`** with ring (was `--warn`, a judgement colour). The legend text "▲ 오름 쪽 · ▼ 내림 쪽 신호 · ● 거래량 급증 (모두 검증 안 됨)" stays; its `<b class="up/down/c-warn">` glyph colours become plain ink. See section 8, items 3–4.
- **Marks:** per 1.5; triangles 9 px, offset 9 px from the bar's high/low (exists); MA end tags; hollow intraday last candle.
- **Hover:** existing shared crosshair over all panes (`chaHover`, Pointer Events, `.cha-xline`). The tooltip keeps every value including RSI, MACD and the signal names. Add keyboard (1.6) on `#cha-stack` (tabindex on the stack, not on each canvas).
- **Bench:** none.
- **Missing:** RSI/MACD warm-up gaps stay gaps; a bad open draws the wick only (exists).
- **Stale:** the header badge + `#cha-meta` (status, live, range, short-history note) kept.
- **Empty:** UNAVAILABLE → hide `#cha-stack`, empty text in `#cha-meta` (exists); `#cha-lines` / `#cha-sigs` cleared (exists).
- **Resp:** 1.10 heights. The controls `.cha-ctl` and the MA checkboxes wrap; in the workstation they sit in the right column (Agent 1/2 layout), and the chart keeps the main width.
- **A11y:** each pane canvas keeps its aria-label ("가격 차트", "거래량", "RSI", "MACD") with a data summary; table twin "표로 보기" (last 30 bars); `#cha-sigs` is the signal table.
- **Theme:** `redrawOn("chart","main")` exists.

### V-09 Return comparison — `compare.js:cmpDraw`
- **Shows:** cumulative total return (dividends included) from a common start (0 %) for up to 8 tickers/indices, so the user compares paths.
- **Form:** kept (multi-line indexed to a common base, the method's answer to different price scales).
- **Axes:** % axis via `niceTicks` (was 4 equal steps), zero line `--axis` (was `--tick`), dates via `vizDates`.
- **Colour:** categorical with the market-aware slot order (2.1); colour follows the entity (`cmpSlot`, exists).
- **Marks:** 2 px lines; direct end labels when ≤ 4 series and plot width ≥ 520 (swatch + name in `--ink`, exists); legend always (exists, with total return).
- **Hover:** index snap, all series sorted by value (exists); line keys; Pointer Events; keyboard; `.viz-xline`.
- **Bench:** an index in the list (`^GSPC`, `^KS11`, `SPY`) is just one of the series. No special treatment, because the user picks the comparison. Default first series is the market index (`cmpDefault`).
- **Missing:** `d.missing` tickers listed in meta (exists); gaps via `line()`.
- **Stale:** header badge; meta (source, range, basis, mixed-market note) kept.
- **Empty:** status ≠ REAL → empty text (exists) at plot height.
- **Resp:** 1.10.
- **A11y:** data label; `#cmp-stats` table is the twin (exists).
- **Theme:** `redrawOn("compare","main")` exists.

### V-10 Rolling correlation — `compare.js:cmpRoll`
- **Shows:** how the N-day correlation of each series with the first item moved over time (`d.rolling`, server-computed).
- **Form:** kept (lines on a fixed −1…1 axis).
- **Axes:** fixed ticks −1, −0.5, 0, 0.5, 1; 0 in `--axis`, others `--grid` (exists).
- **Colour:** the same entity colours as V-09.
- **Marks:** 2 px.
- **Hover:** exists; move to `vizHover`.
- **Missing / empty:** "두 개 이상이고 …" empty text (exists).
- **Resp:** 240 / 220 / 200.
- **A11y:** legend shows the last value per series (exists); add "표로 보기" with monthly rows.
- **Theme:** exists.

### V-11 Correlation matrix (compare) — `compare.js:cmpTables` `#cmp-corr`, and holdings correlation — `portfolio.js:loadRisk`
- **Shows:** pairwise same-day return correlations.
- **Form:** kept as a **table**; add neutral cell shading (6.4). Not a coloured heat chart: the numbers stay the primary channel.
- The diagonal stays `—` (exists).

### V-12 Market heatmap — `map.js:heatDraw` (squarified treemap)
- **Shows:** sector → stock treemap. Size = market cap. Colour = 1d/5d/1m change (diverging) **or** QSF score (sequential).
- **Form:** kept. A treemap is the established form for "market at a glance" with nested part-to-whole by cap. Labels only where they fit (exists: `r.w > 34 && r.h > 18`).
- **Axes:** none. The legend line states size and colour encoding and the saturation span (exists). Change it to a 160 × 8 px **gradient key** drawn in HTML (`.heat-key` with `linear-gradient(to right, var(--down), var(--heat-mid), var(--up))`), with ticks `−span`, `0`, `+span`. The current coloured-text legend uses series colour as text, which the method forbids; the text goes back to `--tick`.
- **Colour:**
  - change modes → diverging, grey midpoint, rule C sides; `cb` palette → fixed blue/orange (2.5b, 8);
  - score mode → neutral sequential `--heat-seq-lo/hi` (section 8);
  - missing → `--viz-missing` (1.7).
- **Marks:** 2 px surface gap between tiles (exists); sector frame stroke 2 px `--viz-surface` (exists); sector name in `--tick` 11 px when the frame is > 50 × 40 (exists).
- **Hover:** rect scan (1.6); tooltip (name, ticker, sector, cap, 1d/5d/1m, score + band) kept; the hovered tile gets a 2 px `--ink` inset stroke (lift); click and Enter open the ticker (exists); keyboard ← → steps tiles.
- **Bench:** none.
- **Missing:** tiles without `market_cap` are excluded from area (they cannot be sized). They are listed in meta "시가총액 없음: …" (exists).
- **Stale:** header badge; meta (session, model version, basis) kept.
- **Empty:** "스캔 결과가 없습니다" (exists).
- **Resp:** 620 / 560 / 520. At ≤ 640 the tile labels drop below `r.w > 34`, as now.
- **A11y:** data label; add the "표로 보기" sorted table.
- **Theme:** tokens; the dark/light pick for `HEAT_CB` from `data-theme`.

### V-13 Sector rotation graph (RRG approximation) — `rotation.js:rrgDraw`
- **Shows:** each sector ETF's relative-strength ratio (x) vs its momentum (y) against the index, with an 8-week tail. Quadrant = phase.
- **Form:** kept (scatter with tails; the established RRG form).
- **Axes:** symmetric around 100 on both axes (`span`); centre cross in `--axis` (was `--tick`); frame `--grid`; axis titles "상대강도 비율 →", "모멘텀 →" in `--tick` (exist). Add the tick values `100 − span/2`, `100`, `100 + span/2` on both axes in 10 px `--tick`.
- **Colour:** quadrant per 2.4; the quadrant wash stays at 7 % (exists); tails `--tick` at 60 % (exists).
- **Marks:** head r = 5, 2 px surface ring (exists); tail dots r = 2 (context, allowed below 8 px since not interactive); labels in `--ink` with leader lines on collision (exists).
- **Hover:** nearest head < 12 px (1.6); tooltip kept; click and Enter → `loadSectorPicks` (exists).
- **Bench:** the index is the 100/100 origin. Say "기준 지수 …" in meta (exists).
- **Missing:** `d.missing` funds listed (exists).
- **Stale:** header badge.
- **Empty:** exists.
- **Resp:** square, `min(560, width)`.
- **A11y:** data label; `#rrg-table` twin (exists, with quadrant swatch + name).
- **Theme:** `redrawOn("map","rrg")` exists.

### V-14 Forecast range strip — `forecast.js:fcStrip` (HTML/CSS, in the card fold "가격 범위")
- **Shows:** for 5 and 20 sessions ahead, the stored 50 % and 80 % close ranges around today's close (symmetric in log space), with the swing card's stop and target levels placed by distance. This is magnitude, not direction (the verdict badge says so).
- **Form:** kept (range bars on one shared log-distance axis per row). It is honest: a range is the payload.
- **Axes:** `fc-axis`, 5 labels from `−span` to `+span` and "기준 종가 0%" (exists).
- **Colour:** bands `--band-80` / `--band-50`, **neutral** (were accent blue; section 8). Centre line `--ink` (exists). Stop/target marks `--ink` 2 px, told apart by the tags "손절"/"목표" (exist, `fc-tag`) and by position. They were `--down`/`--up`, but a planned level is not a price move (section 8). The legend keys follow.
- **Marks:** track 16 px, `--r-sm` corners (exists); marks overhang 3 px (exists).
- **Hover:** none (HTML). Every number is in the table beside it (exists).
- **Missing:** a horizon without a range draws no row; the text "가격 이력이 120거래일에 못 미쳐 … 0이 아닙니다." (exists).
- **Stale / verdict:** `fcTestBadge` beside it (exists).
- **Empty:** NO_RECORD / NOT_IN_RECORD / BROKEN texts (exist).
- **Resp:** `fc-row` grid 78px/1fr → 62px at ≤ 640 (exists); `max-width: 760px` removed inside the workstation lower panel (full panel width).
- **A11y:** `role="img"` with a full label (exists); table twin (exists).
- **Theme:** CSS tokens only.

### V-15 Forecast tables — `forecast.js:fcLevelLines`, `fcTouchLines`, `fcTrackHtml`
- **Shows:** where the stop/target fall within the ranges; the stored touch probabilities; the past check and the forward record.
- **Form:** tables, kept. No chart is added: the touch table is a small 2 × 6 grid of probabilities that the user reads as numbers, and a chart would add nothing.
- **Missing:** "아직 없음" (`.missing`, exists).
- Verdict badges are kept verbatim.

### V-16 Account equity vs benchmark — `portfolio.js:drawEquity` (시장별 자세히)
- **Shows:** the account's time-weighted return vs the benchmark index over the same days.
- **Form:** kept (two lines indexed to 0 %). **Emphasis form**: the account is the story, the benchmark is context.
- **Axes:** % via `niceTicks`; zero line `--axis`; dates via `vizDates` (was first/last only).
- **Colour:** account `--ink` 2 px (was `--accent`; blue reads as "down" on Korean screens and is the UI accent); benchmark `--bench` 1.5 px.
- **Marks:** end labels: "내 계좌 x%" and "<bench> y%" at the line ends (2 series ≤ 4). They replace the in-plot "● 내 계좌 / ● bench" text drawn at (4,18), which collides with the line in the top-left corner.
- **Hover:** **add** `vizHover`: date, 내 계좌 %, 기준 %, difference (account − bench, signed, plain ink).
- **Bench:** `d.benchmark` (SPY or 코스피) named in the label and tooltip.
- **Missing:** points filtered by `isNum` for the range; draw with gaps.
- **Stale:** `#eq-meta` (source, fetched, method) kept; the header badge if status ≠ REAL.
- **Empty:** "거래 기록이 생기면 …" (exists).
- **Resp:** 240 / 220 / 200.
- **A11y:** data label + "표로 보기" (month-end rows).
- **Theme:** `redrawOn("portfolio","equity")` exists.

### V-17 Sector weights meter list — `portfolio.js:renderPortfolio` "섹터 비중"
- **Shows:** each sector's share of the account against the sector limit `max_sector_pct`.
- **Form:** kept as a **meter list** (name, bar, figure per row; bars aligned).
- **Change:** draw the limit as a 2 px `--ink` tick on every track at `max_sector_pct`, so "how close to the limit" is visible before going over.
- **Colour:** fill `--viz-bar`; over the limit `--warn` **plus** the text "한도 초과" after the figure (today only the colour changes: `.bar.over`).
- **Marks:** 8 px track, round ends; sort rows by weight descending (today in payload order).
- **Missing:** a sector with a non-number weight shows `—` and no bar.
- **Resp:** at ≤ 640 the bar drops under the name (meter-list rule).
- **A11y:** the figure is printed; the bar is `aria-hidden`.

### V-18 Risk panel — `portfolio.js:loadRisk`
- **Shows:** beta, volatility, VaR/ES, worst day/20d, max drawdown, effective N, per-holding risk contribution, and the correlation matrix.
- **Form:** the KPI row (`.kv`) is kept as stat tiles. Risk contribution is kept as a meter list, with the fixes in 1.7: missing → `—`, negative → leftward from a centre tick. The correlation matrix stays a table with neutral shading (6.4).
- **Colour:** neutral bars; no up/down on risk figures (they are not price moves); VaR/ES numbers in `--ink`.
- **Missing:** `short_history` names listed (exists).
- **Stale:** the header shows `from ~ to · days` (exists) + meta.

### V-19 Lab backtest NAV — `lab.js:drawLab`
- **Shows:** cumulative NAV of 4 fixed rule models vs SPY on a log scale, for the chosen cost (bps).
- **Form:** kept (log scale is correct for multi-year compounding).
- **Axes:** nice % ticks on the log scale (1.4); dates via `vizDates`.
- **Colour:** per 2.5; SPY `--bench` 1.5 px.
- **Marks:** 2 px models; direct end labels (4 + SPY).
- **Hover:** **add** `vizHover`: date, each model's cumulative %, SPY.
- **Bench:** SPY "매수 후 보유", named.
- **Stale:** the `참고용` badge and the limitations notice stay first (exist).
- **Empty:** exists.
- **Resp:** 320 / 280 / 240.
- **A11y:** `#labtbl` + `#labyr` tables are the twin (exist).
- **Theme:** `redrawOn("lab","main")` exists.

### V-20 Domain score bars in the card — `qsf.js:qsfBar` (in `qsfCard`, "영역별 점수")
- See section 4/5. Neutral `--viz-bar` (exists: `.qsf-bar i {background: var(--muted)}`), 8 px, round ends, 110 px wide, number after.
- The reference domain shows "참고 · 점수 미반영". RISK carries "· 높을수록 좋음" (exists).
- Missing → "데이터 없음" (exists).

### V-21 Domain mini-bars in the ranking row — `qsf.js:qsfRankRow` `.qd-bar`
- See section 6.2.

### V-22 Score change cell — `qsf.js:qsfDelta`
- See section 6.2 (colour correction).

### V-23 Evidence balance — `qsf.js:qsfBalance`
- See section 5 (becomes a diverging point bar list).

### V-24 가점/감점 cell — `qsf.js:qsfReason`
- Kept as text with ▲/▼ glyphs and signed points in `--ink` (it already avoids price colour: P2-8).

### V-25 Score number + band + near-edge
- Section 4.

### V-26 Judgement pill — `qsf.js:qsfLabel` `.qsf-act`
- Kept: 1.5 px ring + 9 px dot in `--act` (judge-buy / judge-hold / warn / mix for reduce), text in `--ink`. The colour is never the only channel (the label text is always present).

### V-27 Market state — `qsf.js:qsfMarketState`, `qsfStateShort`; `assistant.js:asstTiles` state tile; `committee.js` stat
- Section 7.4.

### V-28 Gates, risk lines, avoid marks — `qsfCard` gates notice, `qsfRiskLines`, `qsfClass` AVOID
- Section 7.3.

### V-29 Peer grades A–F — `peers.js:paintPeers` `.grade.g-*`
- **Shows:** the stock's within-sector percentile per score part, binned A–F.
- **Form:** kept (ordinal letter cells; the title tooltip shows the rank and value).
- **Colour:** an **ordinal neutral ramp** (was accent blue, which on Korean screens is the down colour):
  - A = `--ink` fill with `--viz-surface` text;
  - B = `color-mix(--ink 45%, transparent)` with `--ink` text;
  - C = `--viz-track` fill;
  - D/F = outline `--axis`, `--tick` text.
  The letters carry the order, and colour only reinforces it.
- **Missing:** `—` with a reason tooltip (exists).

### V-30 Committee stat tiles and opinions — `committee.js` `.ic-stat`, `.ic-scores`, `icBadge`
- **Form:** stat tiles (kept).
- Hero values use proportional figures (drop `.num` on `.ic-stat b`; keep `tabular-nums` in tables).
- Opinion badges keep their text; buy-type opinions use `--judge-buy`, hold `--judge-hold`, sell/avoid `--warn` (same judgement mapping, binding decision 5).

### V-31 Today candidates — `assistant.js:asstCands` (score + change + 가점/감점)
- The score change `<small class="up/down/flat">` and the why lines `<div class="up/down">` use **price colours for score points**. Change them to `--ink` (≥ 1 point) / `--tick` (< 1 point), with the sign and ▲▼ kept (section 8). The score is an integer with `qsfNear` (exists).

### V-32 Paper-book tiles — `qsf.js:qsfPaperHtml` `pc()`
- Return %, benchmark % and drawdown % are money results of price moves. They keep `--up`/`--down` **with the sign** (exists).
- Max drawdown is always ≤ 0: show it in `--ink` with "−", not red. A drawdown is a risk figure, not a day's move.

### V-33 Regime-weights conditions — `qsf.js:qsfRegimeHtml`
- "충족/미달" use `.up`/`.down`. Change to status `--ok`/`--bad` **with the existing words** (a test result is a status, not a price).

### V-34 Unified account parts table — `account.js:renderAccount`
- A table with a 비중 column. See 7.1 for the optional segmented bar (existing figures).

### V-35 Sector picks grades — `sectorpicks.js` `.grade` + `.sp-score`
- Same ordinal neutral ramp as V-29.

### V-36 Overview / Today stat tiles — `app.js:card`
- Value (`--fs-xl`, proportional), 1일 and 1개월 change (signed, rule C colour or plain for `NEUTRAL_TILE`), sparkline (V-01), date, "그래프 폭".
- Kept. The 1일 / 1개월 period labels stay (`.meta m0`).

### V-37 Score history (table) — `qsf.js:qsfHistory`
- A table today. A small chart is added from the same rows: section 6.3, **NEW (existing data)**.

### V-38 Hand-kept 모의 매매 — `paper.js`
- KPI `.kv` + tables only. No series in the payload (`paper_trade.py` returns no curve), so **no chart**: section 10.

---

## 4. Investment score presentation

Applies to the card header (`qsfCard` `<header>`), the ranking row (`qsfRankRow` 점수 column), Today candidates (`asstCands`) and the order plan (`qsfPlanHtml`). Calculations are unchanged; this is display only.

| Element | Spec | Source |
|---|---|---|
| Score number | Card: `c.score.toFixed(1)` at `--fs-display` (28/24 px), weight 700, proportional figures, `<small>/100</small>` in `--tick`. Tables: whole number `qsfInt` (user decision 2026-11-23), `tabular-nums`, weight 600, right-aligned. A null score → `-` (card) / `—` (table), never 0. | `c.score`, `r.score` |
| Band | A text chip right of the number: `구간: {band_label}` (card, exists); in tables the judgement pill carries `title="구간: …"` (exists). No band colour other than the judgement pill. | `c.band_label`, `r.band` |
| Band position strip (card only, **NEW display of existing data**) | A 100-unit horizontal strip, 6 px high, under the score: segments at the server's band edges (`/api/qsf/bands` → `qsfBands[].start`). Segment fills: `--viz-track`, separated by 2 px gaps; **no judgement colours on the strip** (the pill already carries the judgement). A 2 × 12 px `--ink` marker at the score. Edge values under the strip in 10 px `--tick`. This shows how far the score is from the next band, which the "경계 근처" badge says only when within 1 point. Drawn only after `qsfBands` arrives (that file's rule: no band colours before the bands are received). | `qsfBands`, `c.score` |
| Near-edge mark | The existing `qsfNear(score, edges)` badge "경계 근처" (`--warn` ring) with its title (exact score and edge) is kept in cards, ranking and Today. Ranking ≤ 1023 px: it drops under the score (exists). | `notes.band_edges`, `c.band_edges` |
| Confidence | **Separate**, never multiplied into or blended with the score. Card: `신뢰도(자료의 양) 높음/보통/낮음/부족` in `.qsf-meta` with the title "맞을 확률이 아닙니다" (exists), plus `데이터 반영률 x%` and `요인 안 수치 반영률`. Ranking: chip "자료 보통/낮음" only when ≠ HIGH (exists). No opacity or size scaling of the score by confidence, ever. | `c.confidence`, `c.coverage`, `c.input_coverage` |
| Missing-factor tag | `qsfMissTag` "자료 없는 요인 n" chip kept; its title explains the band hold-back. | `r.missing_factors`, `r.band_held_back` |
| Judgement | `qsfLabel` pill (judgement colours). AVOID above the lowest band shows reduce-amber (`qsfClass`, exists). | `c.action`, `c.action_label` |
| Diagnostic only | When gates fire: the "진단용 점수" text next to the band (exists). The score keeps full ink; actionability is said in words ("실행 대상 아님 · …"), not by greying the number. | `c.diagnostic_only`, `r.actionability` |
| Scan vs live | `qsfScanNote` line when the card score differs from the scan score (exists); model-version notice (exists). | |
| Disclaimer | `c.not_advice` at the card foot (exists); the ranking meta "점수순으로 보여 줄 뿐 …" (exists). The brief's "A BUY score does not authorize a trade" is already carried by these texts. Do not shorten them. | |

---

## 5. Factor contribution visualisation in the card (existing data only)

Data available on every card:
- `c.balance = {plus:[{label, points, text}], minus:[…], points_sum, missing:[…], labels}`. Points are added to or subtracted from the 50 midpoint; their sum = score − 50 (`terminal/qsf/rank_notes.py`).
- `c.factors = [{factor, weight, contribution, scored, status, explanation}]`.
- `c.domains = {KEY: {label, score_100, max_points, reference}}`.

### 5.1 Evidence balance → diverging point bars (replaces the two bulleted lists' coloured numbers; the text stays)

- **Form:** a diverging bar list centred on a zero line that means "50점 midpoint". One row per factor in `plus` then `minus`, sorted by |points| descending. Left: the label (`--ink`). Centre: a bar growing right for +, left for −. Right: the signed value `+3.2점` / `−1.4점` (`--ink`, `tabular-nums`). The explanation `x.text` sits under the label in `.meta` (exists).
- **Scale:** common to the card: half-width = `max(|points|)` over both lists, rounded up to a nice step via `niceTicks(0, max, 2)`. Two tick labels (0 and the max) in 10 px `--tick` on the axis row.
- **Colour:** **no hue for polarity.** The bar fill is `--viz-bar`; the side and the sign carry polarity. Rule: price colours mean price moved; purple/amber mean a judgement. A factor push is neither. Today `qsfBalance` colours the points with `.up`/`.down`, which on Korean screens makes a plus red and a minus blue; section 8 lists this.
- **Marks:** 8 px bars, round end at the data end, square at the zero line; zero line 1 px `--axis`.
- **Footer:** the existing `qb-note` sentence "중간(50점)에서 … = xx.x점" plus the missing list (exists). It also serves as the check that the bars add up.
- **Missing:** factors in `b.missing` are listed in text, with no bar (never a 0-length bar).
- **Responsive:** ≥ 641 px: label column 40 %, bar 40 %, value 20 %. ≤ 640: label on its own line, bar + value under it.
- **A11y:** the list stays a `<ul>`. Each `li` has the text value; the bars are `aria-hidden`.
- **Where:** inside the existing "근거" fold, same position.

### 5.2 Factor table → inline contribution meter

In the "요인별 계산" table (`qsfCard` → `factors`), the 기여 column becomes `[meter] 3.2`:
- The meter is 48 × 6 px. Its fill = `contribution / weight` (the share of that factor's available points actually earned), `--viz-bar` on `--viz-track`.
- Fill is 0 when contribution = 0; no meter when `contribution === null` (prints `-`, exists) or `scored === false` (prints `참고`).
- The number stays the primary value. The weight column (배점) is unchanged.
- **Not shown:** any per-factor "importance" beyond `weight`. No such data exists.

### 5.3 Domain bars

These stay neutral 0–100 meters (V-20). The domain's `max_points` stays in the label (`30점`). There is no domain-level "points contributed" field, so no stacked score bar is built (section 10).

---

## 6. New visuals from existing payload fields, and ranking micro-visuals

### 6.1 NEW (existing data): QSF paper-book equity curve (가상 체결 장부)
- **Data:** `/api/qsf/paper-book` already returns `curve: [{session, equity, benchmark_close}]` (last 260 sessions, `terminal/qsf/paper_book.py:333`). The screen draws none of it today.
- **Form:** two lines indexed to the first session (= 0 %). The book's equity is `--ink` 2 px. The benchmark (`d.benchmark`, SPY or 코스피, close indexed to its first non-null value) is `--bench` 1.5 px. This is the same emphasis form as V-16.
- **Calculation note:** indexing (`v / v0 − 1`) is a display transform of stored values, the same as compare/equity. It is not a new metric. The tiles keep the server's `return_pct` and `benchmark_return_pct`.
- **Axes, hover, missing:** as V-16. A null `benchmark_close` → a gap.
- **Labels:** the `판정 전 참고` and `가상의 금액` badges stay in the header.
- **Where:** directly under the paper-book tiles, before "보유 n종목".
- **Empty:** fewer than 2 points → nothing, with the line "곡선은 기록이 2거래일 이상 쌓이면 그립니다."

### 6.2 Ranking-table micro-visuals (`qsfRankRow`)

| Cell | Spec |
|---|---|
| 순위 | Number, right-aligned, tabular. "상위 3" chip under it (exists, `badge ok`). Change the chip from status green (`.badge.ok`) to a neutral outline chip: "top 3" is a rank fact, not a status. |
| 점수 | Integer, weight 600, `qsfNear` badge (section 4). |
| 점수 변화(전일) `qsfDelta` | **Colour correction:** `≥ +1` / `≤ −1` → `--ink` weight 600 with a sign (`+1.4` / `−2.0`); `|Δ| < 1` → `--tick` (exists as `flat`). **No up/down colours**: a score change is not a price move (today `.up`/`.down`). "새로" stays for a missing previous value. On narrow screens, the duplicate in `.qr-md` under the score is kept (exists). |
| 기술 / 재무 / 위험 관리 / 이벤트 `qd-bar` | 32 × 6 px track `--viz-track`, fill `--viz-bar` (was 26 px), round ends; the number after it, right-aligned in a fixed 2-digit slot (`min-width: 2ch`) so the numbers align down the column. The bar keeps `Math.max(2, v)`, so a true 0 still shows a stub; missing → `—` with no bar (exists). Header tooltips kept (RISK: "높을수록 위험이 낮고 …"). Hidden < 1280 px (exists): the domains remain in the card. |
| 판단 | Judgement pill (V-26). |
| 진입 | Text, plus a "실행 대상 아님 · {gates}" line (exists). |
| 가점 / 감점 | `qsfReason`, ▲▼ + label + signed points in `--ink` (exists), common-push note line above the table (exists). |
| Risk lines under the name | `qsfRiskLines` as small text lines (section 7.3). |

Column order and widths belong to the table spec (Agent 2). The micro-visual sizes above are fixed so the table spec can reserve them: domain cell 32 + 4 + 2ch ≈ 56 px; change cell 5ch.

### 6.3 NEW (existing data): recorded score history line (card fold "이력과 기술 정보")
- **Data:** `/api/qsf/history` rows per strategy: `{session, score, action, confidence, price, model_version, model_changed}`. Today it is a table only.
- **Form:** one line per strategy (스윙, 장기), each in its own small plot (small multiples, 120 px). The y axis is fixed 0–100 with **band edges as 1 px `--grid` lines** labelled with the edge value (from `qsfBands`). Points are r = 3 markers in `--ink` on a 1.5 px `--ink` line.
- **Model changes:** **at every row with `model_changed`, the line is broken** and a 1 px `--axis` vertical rule is drawn with the tag "공식 변경". The two sides are different formulas; joining them would show a formula change as a score move. This follows the existing table's footnote "* 앞 기록과 모델 버전이 다릅니다".
- **Hover:** session, score, judgement text, confidence text, recorded price, model version.
- **No colour by judgement on the points:** the table below lists the judgements, and the point colour stays ink.
- **Empty:** fewer than 2 sessions → no plot; the table only.
- **Twin:** the existing table (kept, under the plot).

### 6.4 Correlation table shading (compare `#cmp-corr`, risk panel holdings matrix)
- Cell background = neutral ramp on |r|: `color-mix(in srgb, var(--viz-bar) calc(|r| × 60%), transparent)`. Text stays `--ink` and signed (`−0.32`). The diagonal is `—` with no fill.
- Missing → `—` with no fill.
- No hue for sign: a sign-diverging blue/red would collide with rule C on both markets, and the number already carries it.
- The legend line under the table: "칸이 짙을수록 상관의 크기(절대값)가 큽니다. 부호는 숫자로 봅니다."

---

## 7. Portfolio allocation, sector exposure, risk, market regime

### 7.1 Allocation (data check)

| Data | Exists? | Where | Visual |
|---|---|---|---|
| Account parts US / KR / coin, as a share of the won total | **Yes.** `account.js` computes `a.equity_krw / t.krw` for the 비중 column. | 통합 계좌 | **Thin segmented bar** (8 px, round ends, no text, 2 px surface gaps) above the parts table, one segment per account in `--s1`, `--s2`, `--s3` (US, KR, coin; fixed order = entity). The table rows get a matching swatch, which replaces a legend (the method's "thin bar beside its figures"). Drawn **only when every part's `equity_krw` is a number and `t.krw > 0`**. Otherwise no bar, and the existing notice ("환율을 받지 못해 …") explains why. Unified account = international colour rule; no categorical slot here is up/down-like. |
| Holdings' share of the whole (`weight_total_pct`) | Yes | 통합 계좌 holdings | Kept as a number column; add a 40 × 6 px neutral meter beside the figure (sorted by value, exists). |
| Per-market holdings weight (`h.weight_pct`) | Yes | 시장별 자세히 | Number column, plus the same meter. |
| Style split long/swing vs target (`st.LONG.share_pct`, `target_long_pct`) | Yes | holdings table heads | Add a 120 × 6 px meter: fill = long share, with a 2 px `--ink` tick at the target. Text stays ("주식 중 72% (목표 70%)"). |
| Committee portfolio weights and sector weights (`p.holdings[].weight`, `p.sectors`) | Yes | 투자위원회 › 여섯 포트폴리오 | The sector line (text today) → a ranked bar list (one neutral hue, largest first, the figure at the bar tip). Weight column gets a meter. Cash share = a separate stat tile (exists). |

### 7.2 Sector exposure
- **Per market:** yes (`d.sectors`, V-17, with the limit tick).
- **Unified across markets:** **no**. The unified-account payload has no sector field, so not built (section 10).
- **Versus a benchmark's sector weights:** no benchmark weights exist, so not built (section 10).

### 7.3 Risk visualisation (gates, risk lines, avoid marks, plan risk)

| Item | Data | Spec |
|---|---|---|
| Risk gates (card) | `c.gates[]` text | `.notice` block: title "위험 게이트 n건", the gate texts, "점수는 진단용 … 실행 대상이 아닙니다" (exists). Add a leading 12 px **diamond icon** (CSS: a 9 × 9 square rotated 45°, 1.5 px `--warn` border, no fill). That gives a non-colour cue; no emoji. |
| Gates in ranking | `r.gates` → "실행 대상 아님 · 실적 발표 임박, …" (`QSF_GATE`) | `.qr-out` line in `--warn` text with the same diamond icon. |
| Rare-risk lines | merger proxy, financing decision, top-20 % volatility, price audit (`qsfRiskLines`) | Kept as short text lines under the name (`.qr-risk`): plain `--ink-2` text with a 6 px `--warn` dot in front, title = the full note (exists). They are reference marks that never change the score, so they must not look like a judgement pill. |
| Common reference chips | buyback, confidence, missing factors, stance | Colourless `.badge.info` (exists). |
| Avoid marks | AVOID → `act-sell` (amber) in the lowest band; above it → `act-reduce` (`qsfClass`) | Judgement pill; text always present. KR avoid-marks reading (reference) keeps its badge `risk-note` text. |
| Stop distance / plan risk | `h.stop`, `stop_distance_pct`, `s.risk_to_stops(_pct)`, `s.unprotected` | Numbers (kept). Swing card: the forecast strip shows the stop and target positions (V-14). "손절가 미설정" → `.missing` text (exists). |
| Portfolio alerts | `d.alerts[]` with `level` | `ul.alerts` with `li.bad` / `li.warn`: status colour plus a leading icon (diamond for warn, a filled 8 px square for bad), text first. |
| High-risk tag (card header) | `d.high_risk` → `qsfRiskTag()` | Kept; badge `risk-note`. |
| Risk grade (KR, reference) | `qsfRiskGradeLine(d.risk_grade)` | Text line (kept); no chart. |

### 7.4 Market regime indicator (market state)

Data: `/api/qsf/market-state` → `{score_100, label, state (FAVOURABLE / … / UNKNOWN), mid, size_factor, factors:[{factor, normalized}], note, session}`. It enters no score (QSF-1.4.0). A US adverse day halves new order size.

| Place | Spec |
|---|---|
| **Top bar** (owner decision 4: market state lives in the top bar) | A compact chip `시장 상태 62/100 · {label}` (`qsfStateShort` text), plus a 48 × 4 px meter: track `--viz-track`, fill `--viz-bar`, and a 2 × 8 px `--ink` tick at `mid`. Adverse (`state ≠ FAVOURABLE`): the chip gets `risk-note` (amber text), and when `size_factor < 1` the second chip `새 주문 크기 50%` (exists in text). Unknown or unreadable: "시장 상태 읽지 못함" / "자료 없음 · 나쁜 날로 취급" (exists), no meter. Clicking the chip opens the full block (below). In COIN market the chip is hidden (no stock market state). |
| **Full block** (`qsfMarketState`, inside the qsf strip's expanded area, kept) | Hero `62/100`, label badge, "점수 미반영 · {mid} 미만이면 나쁨", session. Factors as a **meter list**: one row per factor (`VIX`, `VIX 기간 구조`, `하이일드 스프레드`, …), each a 0–100 neutral meter with its number; `normalized === null` → "없음", no bar. Today the factors are one text line. The note line is kept. |
| **Today tile** (`asstTiles` `.asst-state`) | Same content as the chip, at tile size (value, label badge, size line, session). Kept. |
| **Committee stat** `시장 상태 x/100` | Kept as a stat tile. |
| **Order plan** (`qsfPlanState`) | Kept text; the halving rule text stays next to the plan. |

Colour: the score meter is neutral; adverse = amber **text** (`risk-note`) + words. Green is never used for "favourable": on US screens green means price up, and the state is not a price.

**Not built:** a market-state history line. Only today's value is served, so there is nothing to draw (section 10).

---

## 8. Colour-role corrections (current code that breaks a binding rule)

Each is a display-only change. None alters a value, a label's wording or a rule.

| # | Where | Now | Rule broken | Spec |
|---|---|---|---|---|
| 1 | `qsf.js:qsfBalance` point numbers | `.up` / `.down` | price colour on score points (Korean screens show a plus in red) | `--ink` with sign; diverging neutral bars (5.1) |
| 2 | `qsf.js:qsfDelta`; `assistant.js:asstCands` `moved()` and `why()` | `.up` / `.down` | price colour on score change / points | `--ink` ≥ 1, `--tick` < 1, sign and ▲▼ kept |
| 3 | `chart.js` signal triangles (price, RSI, MACD panes) and the `#cha-sigs` ▲▼ glyphs | `--up` / `--down` | price colour on an untested classic signal | `--ink` triangles; shape = side; legend glyphs plain |
| 4 | `chart.js` volume-spike dot | `--warn` | judgement colour on a data mark | `--ink` dot with ring |
| 5 | `chart.js` MACD histogram | `--up` / `--down` by sign | price colour on momentum sign | `--viz-bar` at 45 %, sign by position |
| 6 | `forecast.js` `.fc-stop` / `.fc-target` | `--down` / `--up` | price colour on planned levels | `--ink`, named by tags and position |
| 7 | `forecast.js` `.fc-b80` / `.fc-b50` | accent blue | blue = down on Korean screens; a range is not the UI accent | neutral `--band-80/50` |
| 8 | `map.js` score mode ramp | blue ramp | blue = down on Korean screens | neutral sequential `--heat-seq-lo/hi` |
| 9 | `map.js` `HEAT_CB` on Korean screens | up = blue, down = orange | on Korean screens blue means **down** in the standard palette, so switching to 파랑·주황 flips blue's meaning | **Owner decision** (2026-11-24 chose the pair). Recommendation: on Korean screens the `파랑·주황` button stays, but its tooltip says "한국 색(빨강 오름·파랑 내림)은 이미 색각 친화입니다. 이 단추는 미국 화면용 색입니다". The legend's gradient key always shows which end is which. No behaviour change without the owner's yes. |
| 10 | `rotation.js` quadrant colours | `--s3/--s4/--s8/--s1` | red = up and blue = down on Korean screens, reversed vs the phase meaning; 4 hues over the scatter cap | 2.4 mapping |
| 11 | `lab.js` `LAB_COLORS` | `--ok` as a series | status colour reused as a series | 2.5 mapping |
| 12 | `qsf.js:qsfRegimeHtml` 충족/미달 | `.up` / `.down` | price colour on a test result | `--ok` / `--bad` + the words |
| 13 | `portfolio.js:drawEquity`, `app.js:mini`, `chart.js` RSI/MACD line | `--accent` | accent used as a data series (blue = down on Korean screens) | `--ink` |
| 14 | `peers.js` / `sectorpicks.js` `.g-A/.g-B` | accent fills | same | neutral ordinal ramp (V-29) |
| 15 | `qsfRankRow` "상위 3" | `.badge.ok` (status green) | status colour on a rank fact | neutral outline chip |
| 16 | `map.js` legend text | coloured text spans | text in a series colour | text `--tick` plus gradient key |
| 17 | `portfolio.js:loadRisk` risk share | missing → 0 % bar; negative clamped to 0 | missing shown as 0 | `—`; diverging meter |
| 18 | `app.js:spark`, `mini` | non-numbers filtered (time compressed) | gaps hidden | index-preserving gaps |
| 19 | `app.js:spark` baseline | dashed | dashed rule reads as a threshold | solid hairline |

Items 1–2 and 12 extend the existing P2-8 rule ("가점·감점은 가격 방향이 아니라 … 가격 색을 쓰지 않습니다") to the places it missed. Several tests pin source text (inventory §0: about 25 files). The implementer must update the pins listed in section 11 in the same commit.

---

## 9. Moves, hides and owner decisions

| Item | Change | New location | Inventory row |
|---|---|---|---|
| Market state short line | Duplicated into the top bar as a chip + meter (stays in the qsf strip too) | top bar (Agent 1 shell) | QR strip rows |
| Status badge of each chart | Duplicated into the panel header (meta line keeps the full text) | panel header | ST-16, map/compare meta rows |
| In-plot "● 내 계좌 / ● bench" text (equity) | Replaced by line end labels | same chart | portfolio equity row |
| Heatmap coloured-text legend | Replaced by gradient key + plain text (same words) | under the heatmap | map legend row |
| Score history | Table kept; small plot added above it | card fold "이력과 기술 정보" | QC history row |
| Paper-book curve | Added (existing field) | under the paper-book tiles | QE paper-book row |
| Domain bars in ranking | Unchanged visibility (hidden < 1280 px, as now) | card keeps the domains | QR-31 |
| **Owner decisions requested** | (a) accept the two lighter dark MA steps outside the band (2.3) or take the in-band fallback; (b) 파랑·주황 note on Korean screens (8.9); (c) MA colour remap — the visible change: US 50 stays blue and 20 stays amber, but 200 becomes slate (was violet) and KR 5/120 change; (d) neutral score heatmap (8.8). | — | — |

No feature is removed. Every changed visual keeps its tab, its panel and its interaction (click, Enter, tooltip content).

---

## 10. Not built: no data

| Wished visual | Why not | What exists instead |
|---|---|---|
| Committee "가상 성과" daily curves | `committee/record.py` computes daily returns only for the one-time reading (`keep_daily=True` in `committee/reading.py`). `/api/committee/performance` does not send them. Building it needs a server field (out of scope). | 16-column metrics table |
| Hand-kept 모의 매매 equity curve | `paper_trade.py` returns no time series | KPI tiles, tables |
| Unified (3-account) sector exposure | the account payload has no sector per holding | per-market sector meter (V-17) |
| Sector exposure vs benchmark weights | no benchmark sector weights anywhere | own weights vs limit |
| Account drawdown (underwater) chart | would be a new client-side calculation; only the max drawdown figure is served (risk panel) | max drawdown KPI; equity curve |
| VaR / return distribution histogram | daily portfolio returns are not served | VaR/ES KPIs |
| Market-state history line | only the current value is served | chip, meter, factors |
| Factor exposure / style exposure (value, momentum, size betas) | no exposure model exists | beta to the index (risk panel) |
| Domain "points contributed" stacked score bar | no per-domain points field (only `score_100` and `max_points`) | per-factor balance bars (5.1), domain meters |
| Intraday chart | no intraday bars; only the `intraday` flag (inventory note) | hollow last candle + "장중·미확정" |
| Signal outcome statistics on the chart | deliberately not computed (CHART-1: "신호 뒤 가격이 어떻게 됐는지는 계산하지 않았습니다") | signal table with the caveat |
| Correlation **charts** beyond what exists | none needed: the compare tab already has a correlation matrix (table) and a rolling-correlation **line chart** (V-10), and the risk panel a holdings matrix | add neutral shading only (6.4) |

---

## 11. Implementation order and test pins

1. **Tokens** (`style.css`): add the section 1.2 tokens in both theme blocks; the new up/down values; `--ma*` per market (`:root` US values, `:root[data-color="kr"]` overrides `--ma50`, `--ma120`); alias `--sma20/50/200` → `--ma20/50/200`; remove the old `:root[data-color="kr"] { --sma50: var(--ma60) }` (now covered by `--ma50`). Dark `--s6` → `#0ca30c`.
2. **Shared helpers** (`app.js`): `vizTokens`, `vizFont`, `vizDates`, `vizEndTags`, `vizHover` (+ `.viz-xline`, `#viz-live`), the tooltip clamp, and the `spark`/`mini` gap fix.
3. **Colour-role corrections** (section 8, items 1–19), one commit per file.
4. **Per-chart upgrades**: niceTicks on compare/equity/lab; hover on equity/lab/mini; keyboard everywhere; table twins; MA end tags; intraday hollow candle; header badges.
5. **New visuals**: band position strip, balance bars, factor meters, score history plot, paper-book curve, account split bar, sector limit ticks, market-state chip meter and factor meters, correlation shading.
6. **Check** each chart at 1600 / 1280 / 768 / 390 px × dark/light × US/KR. Use a scratch tab, not the user's 127.0.0.1:8765 tab (memory: browser pane rule). Verify:
   - no label collisions;
   - nothing drawn as 0 where data is missing;
   - theme toggle repaints all visible canvases and hidden tabs on entry;
   - market switch flips the up/down and MA colours.

Test pins likely affected (they pin source text; update in the same commit, per the test guard rule):
- `tests/test_ui_batch_4.py` (`drawPrice`, `setupCanvas`, `niceTicks`, `spark`);
- the chart-analysis tests (`tests/test_chart_analysis*.py`);
- `tests/test_ui_batch_1.py` / `_2.py` (`qsfDelta`, `qsfNear`, card header);
- the tests for P2-8 / `qsfReason`;
- forecast UI tests (`fc-stop`, `fc-b80` class names: **keep the class names**, change only the CSS values, so pins on markup survive);
- map/heatmap tests (`HEAT_CB`, legend text).

Run `grep -rn "up\\\"\|--accent\|fc-b80\|HEAT_CB\|LAB_COLORS\|qsfDelta\|qsfBalance" tests/` before starting, to list the exact pins.
