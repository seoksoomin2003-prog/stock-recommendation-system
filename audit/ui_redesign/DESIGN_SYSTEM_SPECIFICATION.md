# Design system specification: Institutional Research Workstation

Written 2026-11-24 by Agent 1 (design system architect), read-only on code.
Baseline: `terminal/static/style.css` (609 lines) and `index.html` at commit `7c8e0af`, the inventory `EXISTING_UI_FEATURE_INVENTORY.md` (sections 0–1), and the shared brief.

Scope:
- This file defines tokens, type, spacing, component states, table, panel and chart conventions, and the migration order.
- Shell layout (left menu, top bar, two-column workspaces per screen) belongs to `WORKSTATION_LAYOUT_SPECIFICATION.md`.
  Chart drawing belongs to the visualization spec.
  Both must take their colours, sizes and states from this file.

Ground rules carried in unchanged:
- Owner decisions 1–6 of 2026-11-24.
- No score or logic change. No new metric. Missing is never 0. Stale is labelled. Labels are rule results.
- Every token change is listed with the test that pins it (section 14), so pins are updated on purpose, in the same commit.

Contents:
1. Paste-ready token block
2. Token ledger: kept, added, value changed
3. Colour semantics and rules
4. Contrast tables (WCAG 2.x, computed)
5. Chart and data-visualization palette
6. Typography
7. Space, radii, borders, elevation, surfaces, layers, motion, breakpoints
8. Iconography
9. Component states
10. Table conventions
11. Panel and control conventions
12. Chart conventions (shared with the visualization agent)
13. Light and dark strategy, theme.js, `data-color="kr"`
14. Migration plan and test-pin ledger
15. Places where this spec moves or hides something
16. Conflicts not resolved here

---

## 1. Paste-ready token block

Structure the tests rely on. Keep it exactly:
1. The first `:root {` block holds the **light** colours.
2. Then exactly one `:root[data-theme="dark"] {` block holds the **dark** colours.
3. Then the two rule C lines and the KR 50-day line, unchanged.
4. Then the `/* UI batch 3 P2-1 ... */` scale block.
5. Then `* { box-sizing`.

Notes on the tests:
- `tests/test_ui_batch_1.py::_tokens` reads 6-digit hex values from slices cut at these markers, and compares strings exactly.
- So:
  - write every hex in lower case;
  - keep `--ok` byte-identical to `--up-intl`;
  - never put a hex colour in the scale block;
  - never define `--up` or `--down` inside a theme block.
- Dark stays a `data-theme` block, not `prefers-color-scheme`, because `test_one_dark_palette_set_before_the_first_paint` forbids that media query in the CSS. theme.js decides the theme (section 13).

```css
:root {
  /* surfaces */
  --bg: #f3f5f8; --bg-2: #edf0f4; --panel: #ffffff; --head: #f7f8fa; --elevated: #ffffff;
  --hover: #eef1f5; --row-hover: #f3f6fa; --row-selected: #e9effb; --chip: #eef1f5; --seg-track: #eef1f5; --seg-on: #ffffff;
  /* lines */
  --line: #dde2ea; --line-soft: #e8ecf1; --line-strong: #7b8594; --grid: #edf0f3;
  /* text */
  --ink: #14171c; --ink-2: #3d4756; --muted: #5d6673; --faint: #8a93a0;
  /* accent */
  --accent: #2457d6; --accent-fill: #2457d6; --accent-fill-hover: #1e4bc0; --on-accent: #ffffff;
  /* price (rule C) and status */
  --up-intl: #067a4b; --down-intl: #c43038; --up-kr: #c22f35; --down-kr: #1f5fd1; --ok: #067a4b; --warn: #8f5600; --bad: #b3261e;
  /* judgement (owner decision 5) */
  --judge-buy: #6d28d9; --judge-hold: #64748b;
  /* chart series (compare lines, RRG quadrants) */
  --s1: #2a6fd6; --s2: #e06f22; --s3: #0f8a7e; --s4: #7f6400; --s5: #b04cb4; --s6: #5b8a1e; --s7: #6a57d2; --s8: #d23f3b;
  /* moving averages; --smaN are aliases (see the KR rule below) */
  --ma5: #d6457f; --ma10: #8c5a2b; --ma20: #b87500; --ma50: #2457d6; --ma60: #0f8c9e; --ma120: #5d6673; --ma200: #8a3ffc;
  --sma20: var(--ma20); --sma50: var(--ma50); --sma200: var(--ma200);
  /* heatmap ramps (read by map.js through cssVar) */
  --heat-mid: #cdd1d7; --heat-score-lo: #dee8fa; --heat-score-hi: #1d4fc4; --heat-cb-up: #1f5fd1; --heat-cb-down: #b35900;
  /* elevation (theme-specific) */
  --shadow-1: 0 1px 2px rgba(15,23,35,.06); --shadow-2: 0 6px 20px rgba(15,23,35,.12); --shadow-3: 0 16px 40px rgba(15,23,35,.18);
  --scrim: rgba(15,23,35,.35);
  color-scheme: light;
}
:root[data-theme="dark"] {
  --bg: #0b1018; --bg-2: #101722; --panel: #151e2b; --head: #182231; --elevated: #1b2635;
  --hover: #1e2a3a; --row-hover: #1a2432; --row-selected: #1c2c45; --chip: #1e2a3a; --seg-track: #101722; --seg-on: #212e44;
  --line: #273446; --line-soft: #1e2836; --line-strong: #6b7b92; --grid: #1e2836;
  --ink: #e5eaf1; --ink-2: #b4bfcd; --muted: #94a3b8; --faint: #6b7b92;
  --accent: #5b96f7; --accent-fill: #2563eb; --accent-fill-hover: #2f6ceb; --on-accent: #ffffff;
  --up-intl: #22c55e; --down-intl: #f46a6a; --up-kr: #f46a6a; --down-kr: #5b9cff; --ok: #22c55e; --warn: #f59e0b; --bad: #ff7b72;
  --judge-buy: #a78bfa; --judge-hold: #7d8da6;
  --s1: #5b9bf0; --s2: #f0884a; --s3: #26b5a6; --s4: #e8c547; --s5: #d77bd9; --s6: #9ccb5b; --s7: #b0a4f5; --s8: #f2706b;
  --ma5: #f07aa8; --ma10: #c08a5a; --ma20: #f0a531; --ma50: #6d9bff; --ma60: #3cc2d4; --ma120: #a3acb9; --ma200: #b98bff;
  --heat-mid: #2b3646; --heat-score-lo: #22304a; --heat-score-hi: #6d9bff; --heat-cb-up: #5b9cff; --heat-cb-down: #f0a531;
  --shadow-1: 0 1px 0 rgba(0,0,0,.35); --shadow-2: 0 8px 24px rgba(0,0,0,.5); --shadow-3: 0 16px 48px rgba(0,0,0,.6);
  --scrim: rgba(4,8,14,.6);
  color-scheme: dark;
}
/* rule C lines: unchanged text */
:root { --up: var(--up-intl); --down: var(--down-intl); }
:root[data-color="kr"] { --up: var(--up-kr); --down: var(--down-kr); }
:root[data-color="kr"] { --sma50: var(--ma60); }
/* UI batch 3 P2-1 (2026-11-23) ... keep this comment line: test_ui_batch_3 slices from it */
:root {
  --fs-xs: 11px; --fs-sm: 12px; --fs-md: 13px; --fs-base: 14px; --fs-lg: 16px; --fs-xl: 18px; --fs-display: 28px;
  --font-ui: -apple-system, BlinkMacSystemFont, "Segoe UI", "Apple SD Gothic Neo", "Malgun Gothic", "맑은 고딕", "Noto Sans KR", "Noto Sans CJK KR", Roboto, "Helvetica Neue", Arial, sans-serif;
  --font-mono: ui-monospace, "SF Mono", Menlo, Consolas, "D2Coding", monospace;
  --lh-tight: 1.2; --lh-ui: 1.4; --lh-body: 1.5; --lh-prose: 1.7;
  --sp-1: 4px; --sp-2: 8px; --sp-3: 12px; --sp-4: 16px; --sp-5: 24px; --sp-6: 32px;
  --r-sm: 4px; --r-md: 6px; --r-lg: 8px; --r-pill: 999px;
  --z-raise: 1; --z-header: 10; --z-nav: 12; --z-popover: 20; --z-drawer: 30; --z-dialog: 40; --z-toast: 50;
  --ctl-h: 32px; --ctl-h-sm: 28px; --ctl-h-touch: 40px;
  --row-h: 32px; --row-h-compact: 28px; --row-h-touch: 40px; --cell-x: 8px;
  --topbar-h: 48px; --nav-w: 216px; --nav-w-rail: 56px; --right-w: 560px;
  --dur-1: 120ms; --dur-2: 180ms; --ease: cubic-bezier(.2, 0, 0, 1);
  --content-max: 1280px; --content-max-wide: 1680px;
}
```

Notes on the block:
- `--shadow-*` moves from the scale block into the two theme blocks, because dark needs heavier shadows. The values are rgba, so the hex parser ignores them.
- The 7 `--fs-*` sizes are unchanged. `test_type_layers_and_corners_read_the_tokens` requires exactly seven `--fs-[a-z]+: Npx` in the scale block, in ascending order. No other token may be named `--fs-…`.
- `--font-ui` must not be named `--fs-font` for the same reason.

---

## 2. Token ledger

No existing token is renamed or removed. JS reads these names through `cssVar()`: `--ink`, `--muted`, `--panel`, `--grid`, `--line`, `--chip`, `--accent`, `--up`, `--down`, `--warn`, `--ok`, `--s1`–`--s8`, `--maN`, `--smaN`. Renaming any of them would mean editing ten JS files. The brief's names map onto existing tokens as follows:

| Brief name | Token | Status | Light | Dark (default) |
|---|---|---|---|---|
| App background | `--bg` | kept, value changed | `#f6f7f9` → `#f3f5f8` | `#0e1116` → `#0b1018` |
| Secondary surface (top bar, left menu, inset blocks, seg track) | `--bg-2` | **added** | `#edf0f4` | `#101722` |
| Panel | `--panel` | kept, value changed | `#ffffff` (same) | `#161b22` → `#151e2b` |
| Table header and panel title strip | `--head` | **added** | `#f7f8fa` | `#182231` |
| Elevated (popover, palette, tooltip, drawer, toast) | `--elevated` | **added** | `#ffffff` (+ shadow) | `#1b2635` |
| Hover (controls, list items) | `--hover` | kept, value changed | `#eef1f5` (same) | `#1f2630` → `#1e2a3a` |
| Row hover | `--row-hover` | **added** | `#f3f6fa` | `#1a2432` |
| Selected row and current nav item | `--row-selected` | **added** | `#e9effb` | `#1c2c45` |
| Badge and bar track | `--chip` | kept, value changed | `#eef1f5` (same) | `#1f2630` → `#1e2a3a` |
| Segmented track and on-state | `--seg-track`, `--seg-on` | **added** | `#eef1f5`, `#ffffff` | `#101722`, `#212e44` |
| Subtle border | `--line` | kept, value changed | `#e1e4e9` → `#dde2ea` | `#262d36` → `#273446` |
| Row divider | `--line-soft` | **added** | `#e8ecf1` | `#1e2836` |
| Strong border (inputs, ≥3:1) | `--line-strong` | kept, dark changed | `#7b8594` (same) | `#6b7686` → `#6b7b92` |
| Chart grid | `--grid` | kept, dark changed | `#edf0f3` (same) | `#1d232c` → `#1e2836` |
| Primary text | `--ink` | kept, dark changed | `#14171c` (same) | `#e6e9ee` → `#e5eaf1` |
| Secondary text | `--ink-2` | **added** | `#3d4756` | `#b4bfcd` |
| Muted text (meta, captions, column heads, axes) | `--muted` | kept, dark changed | `#5d6673` (same) | `#8b95a3` → `#94a3b8` |
| Disabled and decorative only | `--faint` | **added** | `#8a93a0` | `#6b7b92` |
| Accent (links, focus ring, current-item bar, sort mark) | `--accent` | kept, dark changed | `#2457d6` (same) | `#6d9bff` → `#5b96f7` |
| Accent fill (primary button, grade A) | `--accent-fill`, `--accent-fill-hover` | **added** | `#2457d6`, `#1e4bc0` | `#2563eb`, `#2f6ceb` |
| Text on accent fill | `--on-accent` | kept, dark changed | `#ffffff` (same) | `#0e1116` → `#ffffff` |
| Up / down, international | `--up-intl`, `--down-intl` | kept, dark changed | same | `#2fbf7f` → `#22c55e`; `#ff6369` → `#f46a6a` |
| Up / down, Korean | `--up-kr`, `--down-kr` | kept; dark up changed | same (pinned) | `#ff6369` → `#f46a6a`; `#5b9cff` same (pinned) |
| Status ok / warn / bad | `--ok`, `--warn`, `--bad` | kept, dark ok/warn changed | same | `--ok` = `--up-intl` = `#22c55e`; `--warn` `#f0a531` → `#f59e0b`; `--bad` `#ff7b72` same |
| Judgement | `--judge-buy`, `--judge-hold` | kept, dark hold changed | same | `#a78bfa` same; hold `#64748b` → `#7d8da6` |
| Series | `--s1`–`--s8` | kept, values re-picked | see section 5 | see section 5 |
| Moving averages | `--ma5`…`--ma200` | kept; light `--ma20` changed | `#d68a00` → `#b87500` | same |
| SMA aliases | `--sma20/50/200` | kept, now `var()` aliases | `var(--maN)` | `var(--maN)` |
| Heatmap ramps | `--heat-mid`, `--heat-score-lo/-hi`, `--heat-cb-up/-down` | **added** (values now hard-coded in `map.js`) | see block | see block |
| Elevation | `--shadow-1..3`, `--scrim` | shadows moved into theme blocks; `--scrim` added | see block | see block |
| Type | `--font-ui`, `--font-mono`, `--lh-*` | **added** | — | — |
| Layers | `--z-nav: 12`, `--z-drawer: 30` | **added** | — | — |
| Sizes | `--ctl-h*`, `--row-h*`, `--cell-x`, `--topbar-h`, `--nav-w`, `--nav-w-rail`, `--right-w`, `--dur-*`, `--ease` | **added** | — | — |

Notes on the ledger:
- **Why dark `--on-accent` becomes white:** the old pair was pale-blue fill with near-black text. White on `#2563eb` (5.17:1) reads as the institutional primary.
  - The brief's `#3b82f6` fails with white (3.68:1).
  - As text it also fails on raised surfaces (4.15:1 on `#1b2635`).
  - So the accent splits in two: `--accent` for text and lines, `--accent-fill` for fills.
- **Why dark `--down-intl` is `#f46a6a` and not the suggested `#ef4444`:** `#ef4444` is 4.46:1 on the panel and 3.77:1 on a selected row. Both fail 4.5:1.

---

## 3. Colour semantics and rules

Each colour family has one meaning. Never colour-only: every coloured state also carries a sign, glyph or word.

| Family | Tokens | Means | Where it may appear | Never |
|---|---|---|---|---|
| Accent (blue) | `--accent`, `--accent-fill` | "interactive / current / focus" | links, `.linkish` hover, focus ring, current nav item's left bar, selected-row left bar, sort mark, primary button fill, `.qr-rank` | on a number that is a price change, a score or a judgement |
| Price | `--up`, `--down` (from the rule C pair) | "the price moved up / down" | `.up/.down` spans made by `pct()`, candles, volume, the stop/target lines in the forecast strip, the heatmap "기본 색" ramp | status, judgement, buttons, a domain-score bar |
| Judgement | `--judge-buy` purple, `--judge-hold` grey, `--warn` amber for reduce/avoid/sell | "the program's rule result" | `.qsf-act` chip border and dot, `.asst-verdict` edge and heading, the committee's `IC_REC_COLOR` | as a background fill behind text; without the text label beside it |
| Status | `--ok`, `--warn`, `--bad` | "data or system state": saved, stale, failed | `.msg`, `.badge.STALE/.UNAVAILABLE/.ok`, `.alerts li`, `.asst-item.ACT/.DUE`, `.netbar`, `.toast` edge | price moves |
| Neutral data | `--muted` bars, `--accent` heat-score ramp | a score magnitude with no judgement | `.qsf-bar i`, `.qd-bar i`, `.bar i` | — |

Rules:
- **R1 (rule C):** `paintColorRule()` keeps owning `data-color="kr"`.
  - Korean screens: red up `--up-kr`, blue down `--down-kr`.
  - US screens and the unified account (`INTL_COLOR_TABS`): green up / red down.
  - `--ok` stays green on Korean screens. It is a status, not a price.
- **R2 (sign always):** a change value always carries `+` or `−`/`-`.
  - `pct()` already writes `+` for positive and the minus for negative, and zero is `.flat` (muted).
  - Headline price changes in the stock header and index tiles add ▲/▼ before the number.
  - Table cells use the sign only, because ▲▼ in every cell is noise.
- **R3 (accent vs Korean down):** on Korean screens `--down-kr` `#5b9cff` and `--accent` `#5b96f7` are the same hue (see section 16).
  - Accent is therefore never used on numbers or arrows. Price blue appears only on numerals, candles and arrows. Accent appears only on chrome (rings, bars, links, buttons).
  - A selected row on a Korean screen keeps blue numbers readable: 5.11:1 on `--row-selected`.
- **R4 (purple is judgement only in the UI chrome):** the series violet `--s7` and the MA violet `--ma200` live only inside canvases, where no judgement is drawn. A legend swatch beside them always names the series.
- **R5:** `--warn` amber is shared by "stale data" and "reduce/avoid" judgements. The meaning is always carried by the word beside it (지연/오래됨 vs 줄이기/피하기). This was decided on 2026-11-24 and is kept.

---

## 4. Contrast tables

Method:
- WCAG 2.x relative luminance, computed with a script (same formula as `tests/test_ui_batch_1.py::_contrast`).
- Thresholds: text ≥4.5:1, large text and graphics ≥3:1.
- `--faint` is only for disabled controls and decorative separators (`·`), which WCAG exempts. It is never used for information.
- `--judge-hold` is used as a graphic (chip border, dot, verdict edge). It appears as text only in `.asst-v-head b` on `--panel`, where it passes 4.5:1 in both themes (4.98 dark, 4.76 light).

**Dark (default)**

| token \ surface | bg `#0b1018` | bg-2 `#101722` | panel `#151e2b` | head `#182231` | elevated `#1b2635` | row-hover `#1a2432` | chip/hover `#1e2a3a` | row-selected `#1c2c45` | seg-on `#212e44` | need |
|---|---|---|---|---|---|---|---|---|---|---|
| ink `#e5eaf1` | 15.77 | 14.88 | 13.87 | 13.24 | 12.63 | 12.94 | 12.00 | 11.61 | 11.29 | ≥4.5 |
| ink-2 `#b4bfcd` | 10.24 | 9.66 | 9.00 | 8.59 | 8.20 | 8.40 | 7.79 | 7.54 | 7.33 | ≥4.5 |
| muted `#94a3b8` | 7.44 | 7.01 | 6.54 | 6.24 | 5.96 | 6.10 | 5.66 | 5.48 | 5.32 | ≥4.5 |
| accent `#5b96f7` | 6.49 | 6.12 | 5.71 | 5.45 | 5.20 | 5.33 | 4.94 | 4.78 | 4.65 | ≥4.5 |
| up-intl = ok `#22c55e` | 8.37 | 7.89 | 7.36 | 7.02 | 6.70 | 6.87 | 6.37 | 6.16 | 5.99 | ≥4.5 |
| down-intl = up-kr `#f46a6a` | 6.46 | 6.09 | 5.68 | 5.42 | 5.17 | 5.30 | 4.92 | 4.76 | 4.62 | ≥4.5 |
| down-kr `#5b9cff` | 6.94 | 6.55 | 6.10 | 5.83 | 5.56 | 5.69 | 5.28 | 5.11 | 4.97 | ≥4.5 |
| warn `#f59e0b` | 8.88 | 8.37 | 7.81 | 7.45 | 7.11 | 7.28 | 6.76 | 6.54 | 6.35 | ≥4.5 |
| bad `#ff7b72` | 7.56 | 7.13 | 6.65 | 6.35 | 6.06 | 6.20 | 5.75 | 5.57 | 5.41 | ≥4.5 |
| judge-buy `#a78bfa` | 7.01 | 6.61 | 6.16 | 5.88 | 5.61 | 5.75 | 5.33 | 5.16 | 5.01 | ≥4.5 |
| judge-hold (graphic) `#7d8da6` | 5.66 | 5.34 | 4.98 | 4.75 | 4.53 | 4.64 | 4.31 | 4.17 | 4.05 | ≥3 |
| line-strong (graphic) `#6b7b92` | 4.42 | 4.17 | 3.89 | 3.71 | 3.54 | 3.63 | 3.37 | 3.26 | 3.17 | ≥3 |
| faint (disabled only) `#6b7b92` | 4.42 | 4.17 | 3.89 | 3.71 | 3.54 | 3.63 | 3.37 | 3.26 | 3.17 | exempt |

**Light**

| token \ surface | bg `#f3f5f8` | bg-2 `#edf0f4` | panel `#ffffff` | head `#f7f8fa` | elevated `#ffffff` | row-hover `#f3f6fa` | chip/hover `#eef1f5` | row-selected `#e9effb` | seg-on `#ffffff` | need |
|---|---|---|---|---|---|---|---|---|---|---|
| ink `#14171c` | 16.45 | 15.71 | 17.96 | 16.90 | 17.96 | 16.57 | 15.86 | 15.57 | 17.96 | ≥4.5 |
| ink-2 `#3d4756` | 8.61 | 8.22 | 9.40 | 8.85 | 9.40 | 8.67 | 8.30 | 8.15 | 9.40 | ≥4.5 |
| muted `#5d6673` | 5.32 | 5.08 | 5.81 | 5.47 | 5.81 | 5.36 | 5.13 | 5.04 | 5.81 | ≥4.5 |
| accent `#2457d6` | 5.64 | 5.39 | 6.16 | 5.80 | 6.16 | 5.68 | 5.44 | 5.34 | 6.16 | ≥4.5 |
| up-intl = ok `#067a4b` | 4.94 | 4.72 | 5.39 | 5.08 | 5.39 | 4.98 | 4.76 | 4.68 | 5.39 | ≥4.5 |
| down-intl `#c43038` | 5.02 | 4.80 | 5.49 | 5.16 | 5.49 | 5.06 | 4.84 | 4.76 | 5.49 | ≥4.5 |
| up-kr `#c22f35` | 5.12 | 4.90 | 5.60 | 5.27 | 5.60 | 5.16 | 4.94 | 4.85 | 5.60 | ≥4.5 |
| down-kr `#1f5fd1` | 5.32 | 5.08 | 5.81 | 5.47 | 5.81 | 5.36 | 5.13 | 5.03 | 5.81 | ≥4.5 |
| warn `#8f5600` | 5.50 | 5.25 | 6.00 | 5.65 | 6.00 | 5.54 | 5.30 | 5.20 | 6.00 | ≥4.5 |
| bad `#b3261e` | 5.98 | 5.72 | 6.54 | 6.15 | 6.54 | 6.03 | 5.77 | 5.67 | 6.54 | ≥4.5 |
| judge-buy `#6d28d9` | 6.51 | 6.22 | 7.10 | 6.69 | 7.10 | 6.55 | 6.27 | 6.16 | 7.10 | ≥4.5 |
| judge-hold (graphic) `#64748b` | 4.36 | 4.16 | 4.76 | 4.48 | 4.76 | 4.39 | 4.20 | 4.13 | 4.76 | ≥3 |
| line-strong (graphic) `#7b8594` | 3.42 | 3.27 | 3.73 | 3.51 | 3.73 | 3.44 | 3.30 | 3.24 | 3.73 | ≥3 |
| faint (disabled only) `#8a93a0` | 2.84 | 2.72 | 3.11 | 2.92 | 3.11 | 2.87 | 2.74 | 2.69 | 3.11 | exempt |

Other pairs:

| Pair | Dark | Light | Need |
|---|---|---|---|
| `--on-accent` on `--accent-fill` | 5.17 | 6.16 | ≥4.5 |
| `--on-accent` on `--accent-fill-hover` | 4.70 | 7.44 | ≥4.5 |
| `--accent-fill` (button edge) on `--panel` / `--bg` | 3.24 / 3.69 | 6.16 / 5.64 | ≥3 |
| Focus ring `--accent` on any surface above | min 4.65 | min 5.34 | ≥3 |
| `--ink` on `--panel` (test requires ≥7) | 13.87 | 17.96 | ≥7 |

Every up/down colour passes 4.5:1 against every panel and row background in both themes, including `--row-selected` and `--seg-on`. The lowest are dark `--down-intl` 4.62 on `--seg-on` and light `--up-intl` 4.68 on `--row-selected`.

---

## 5. Chart and data-visualization palette

How it was validated:
- The bundled `validate_palette.js` was not present at the path in the brief.
- The same checks were computed with a script in the scratchpad: contrast against the chart surface, and the minimum pairwise CIEDE2000 under normal vision and simulated deuteranopia, protanopia and tritanopia (Machado 2009, severity 1).
- Rule of thumb used: a pair needs ΔE ≥ 5 to be told apart at line weight.

### 5.1 Categorical series `--s1`…`--s8` (compare lines, RRG quadrants)

`compare.js` keeps a slot per ticker, up to 8. The default view shows 3 (`cmpDefault`). Slots 1–4 are chosen to be colour-vision safe. Slots 5–8 are not, and need the legend and direct labels (rule V3 below).

| Slot | Dark | vs panel | Light | vs white | Hue |
|---|---|---|---|---|---|
| s1 | `#5b9bf0` | 5.90 | `#2a6fd6` | 4.84 | blue |
| s2 | `#f0884a` | 6.65 | `#e06f22` | 3.25 | orange |
| s3 | `#26b5a6` | 6.58 | `#0f8a7e` | 4.24 | teal |
| s4 | `#e8c547` | 9.99 | `#7f6400` | 5.64 | gold / olive |
| s5 | `#d77bd9` | 6.17 | `#b04cb4` | 4.63 | magenta |
| s6 | `#9ccb5b` | 8.87 | `#5b8a1e` | 4.12 | lime |
| s7 | `#b0a4f5` | 7.56 | `#6a57d2` | 5.38 | violet |
| s8 | `#f2706b` | 5.83 | `#d23f3b` | 4.65 | red |

Validation (minimum ΔE2000):

| Set | Normal | Deutan | Protan | Tritan |
|---|---|---|---|---|
| Dark s1–s4 | 26.8 | 9.0 | 14.6 | 8.0 |
| Light s1–s4 | 26.8 | 17.7 | 11.1 | 9.7 |
| Dark s1–s8 | 16.0 | 4.5 (s2/s6) | 3.2 (s4/s6) | 4.6 (s2/s8) |
| Light s1–s8 | 13.8 | 1.4 (s1/s7) | 0.9 (s2/s6) | 9.7 |
| Old dark s1–s8, for reference | 14.1 | 3.5 | 1.9 | 5.5 |

All slots pass ≥3:1 against the chart surface in both themes.

RRG mapping is unchanged (`rotation.js` `RRG_Q`): LEADING s3, WEAKENING s4, LAGGING s8, IMPROVING s1. These four are a mutually distinct set except s3/s8 for red-green viewers, which is why the quadrant names are always printed (they are today).

### 5.2 Moving averages `--ma5`…`--ma200`

- `MA_CHOICES = (5, 10, 20, 50, 60, 120, 200)` and `MA_MAX = 5`.
- Defaults: KR 5/20/60/120, US 20/50/200.
- Dark values are unchanged. They pass ≥5.6:1 on the new panel.
- Light `--ma20` (and so `--sma20`) changes from `#d68a00` (2.80:1 on white, fails 3:1) to `#b87500` (3.76:1).

Default sets under colour-vision simulation (minimum ΔE2000):
- KR default (pink, amber, teal, grey): ≥7.2 under every simulation.
- US default (amber, blue, violet): deutan 7.4, protan 2.9 for blue vs violet (50 vs 200). The line legend (`.legend`) names each line, so this is acceptable.
- On KR screens `--sma50` already maps to `--ma60` teal, so the falling-candle blue is not reused (existing rule, kept).

### 5.3 Heatmap ramps (`map.js`)

These values are hard-coded in `map.js` today. The new tokens hold the same values, re-tuned to the new surfaces. The visualization agent switches `heatColor()` to read them:

| Use | Token | Dark | Light | Today in `map.js` |
|---|---|---|---|---|
| "기본 색" diverging mid (|change| = 0) | `--heat-mid` | `#2b3646` | `#cdd1d7` | `[58,63,71]` / `[205,209,215]` |
| "기본 색" ends | `--up`, `--down` (rule C) | — | — | same |
| "파랑·주황" colour-safe ends | `--heat-cb-up`, `--heat-cb-down` | `#5b9cff` / `#f0a531` | `#1f5fd1` / `#b35900` | `HEAT_CB` (same values) |
| QSF score ramp (sequential, neutral) | `--heat-score-lo` → `--heat-score-hi` | `#22304a` → `#6d9bff` | `#dee8fa` → `#1d4fc4` | `[40,52,74]`→`#6d9bff` / `[222,232,250]`→`#1d4fc4` |
| Tile gap | `--panel` | — | — | same (2 px) |
| No data | `--chip` | — | — | same |

- Tile label colour stays as today: white when the tile luminance is < 0.55, else `#14171c`. These are on-tile constants, the same in both themes.
- Dark `--heat-mid` sits 1.5 steps above the panel, so a flat tile is visible as a tile.

### 5.4 Other chart colours

| Element | Token |
|---|---|
| Grid lines | `--grid` |
| Zero line, baseline | `--line-strong` at 1 px (today `--line`, which is nearly invisible on the new dark panel) |
| Crosshair (`.cha-xline`) | `--muted` at opacity .6 (unchanged) |
| Axis and tick labels | `--muted` |
| In-chart titles and values | `--ink` |
| The user's own line (내 계좌 equity) | `--accent` 2 px |
| Benchmark | `--muted` 1.3 px |
| Candles and volume | `--up` / `--down`; volume at 45% alpha |
| Forecast bands `.fc-b80/.fc-b50` | `--accent` tints (unchanged) |
| Volume spike dots | `--warn` (unchanged) |

---

## 6. Typography

### 6.1 Font stack (offline, no font files)

```
--font-ui: -apple-system, BlinkMacSystemFont, "Segoe UI", "Apple SD Gothic Neo", "Malgun Gothic", "맑은 고딕",
           "Noto Sans KR", "Noto Sans CJK KR", Roboto, "Helvetica Neue", Arial, sans-serif;
```

How it resolves per platform:
- **macOS / iOS:** SF Pro, with Hangul from Apple SD Gothic Neo through the system cascade.
- **Windows:** Segoe UI for Latin and digits (it has a `tnum` feature), with Hangul falling to Malgun Gothic.
- **Android / ChromeOS:** Roboto or Noto Sans, with Noto Sans CJK KR.
- **Linux:** Noto Sans CJK KR if installed.

Why this order:
- Segoe UI comes before Malgun Gothic so that Windows draws digits with Segoe UI's tabular figures.
- Pretendard is not listed. It is not bundled, and listing a font that only some devices have would make spacing differ between the Mac and the phone.
- `body` changes from the literal stack to `font: var(--fs-base)/var(--lh-body) var(--font-ui);`.
- Canvas code (`ctx.font = "11px -apple-system, sans-serif"` in 11 places) should use one helper: `const chartFont = (px, w = 400) => \`${w} ${px}px ${cssVar("--font-ui")}\``. That is a JS change, owned by the visualization agent.

`--font-mono` is only for `kbd`, `.tech-id` and the phone code. Numbers are never set in mono. Tabular figures do that job.

### 6.2 Scale (the 7 existing steps, unchanged values)

| Token | px | Weight | Line height | Use |
|---|---|---|---|---|
| `--fs-xs` | 11 | 600 (badges) / 400 | 1.2 | badges, axis and tick labels, `.tech-id`, nav group headings, `kbd`. **Minimum size anywhere, canvases included** (`app.js:782` and `map.js` draw 10 px today; raise them to 11) |
| `--fs-sm` | 12 | 400 / 600 | 1.4 | `.meta`, table header cells, `.kv` labels, form labels, legends, `.fold-hint`, toasts' secondary line, bottom-bar labels |
| `--fs-md` | 13 | 400 / 600 | 1.4 | **table body**, left-menu items, buttons, `.seg`, chips, inputs on desktop, notices, `.qsf-dl` |
| `--fs-base` | 14 | 400; 600 for titles | 1.5 | body text, **panel titles (`.panel h2`, 600)**, `.qsf-sec > summary`, top-bar brand |
| `--fs-lg` | 16 | 600 | 1.4 | `.kv b` values on summary strips, `.sp-score`, `.asst-sum`, **inputs on phones** (stops iOS zoom on focus) |
| `--fs-xl` | 18 | 600 / 700 | 1.25 | page title (stock name in the research header), `.ic-stat b`, `.asst-v-head b`, metric values in tiles (`.card .px`) |
| `--fs-display` | 28 (24 ≤640 px) | 700 | 1.15 | stock price headline (`.head .big`), `.qsf-score`, `.result .big`, `.phone-code` |

Weights:
- Only 400, 500, 600, 700. `.card .px` and `.sp-score` use 650 today; change them to 600, because system Korean fonts do not have 650.

Hangul rules:
- `word-break: keep-all` stays on wrapped Korean labels (the existing pattern).
- No `text-transform: uppercase` on Korean text. `.upper` is for tickers only.
- No letter-spacing on Hangul. Nav group headings may use `letter-spacing: .02em`, which only affects Latin.

### 6.3 Tabular numerals

Rules:
```css
table, .num, .kv b, .qsf-score, .head .big, .card .px, .ic-stat b, .ic-scores b, .sp-score, .tip, .fc-axis,
.phone-code, input[type="number"] { font-variant-numeric: tabular-nums lining-nums; }
```
- `.num` stays the class that JS adds (`pct()`, `pctPlain()`, 312 uses).
- Prose (`.plain-box`, `.asst-answer`, `.qsf-dl dd`) keeps proportional figures.
- Numbers in a column align on the right edge. Equal decimals per column come from the existing formatters (`fmt`, `pct`, `big`). This spec adds no new rounding.

---

## 7. Space, radii, borders, elevation, surfaces, layers, motion, breakpoints

### 7.1 Space (4 px grid; `--sp-1..6` unchanged)

| Use | Value |
|---|---|
| Gap between panels in a workspace column | `--sp-3` 12 px (≥1024), `--sp-3` (tablet), `--sp-2` 8 px (phone) |
| Panel padding | `--sp-4` 16 px desktop; `--sp-3` 12 px ≤640 px |
| Panel title to content | `--sp-3` |
| Section (h3 / `.qsf-sec`) top margin | `--sp-4` |
| Inline gaps in a control row | `--sp-2` |
| Table cell horizontal padding | `--cell-x` 8 px; first and last cell of a flush table 12 px (`--sp-3`) |
| Main area padding | `--sp-4` desktop / `--sp-3` ≤640 px (unchanged) |

### 7.2 Radii

Literal 4/6/8/10/12/14 px radii stay forbidden by `test_type_layers_and_corners_read_the_tokens`.

| Element | Radius |
|---|---|
| Panels, cards, `.qsf-card`, `.asst-answer`, `.plain-box` | `--r-md` 6 px (today `--r-lg`: a tighter corner reads as a workstation) |
| Inputs, buttons, `.seg`, badges, `.grade`, tooltip | `--r-sm` 4 px |
| Palette dialog, drawer edge, toast, more-sheet | `--r-lg` 8 px |
| Chips, judgement chip `.qsf-act` | `--r-pill` |
| Swatches | 2 px literal (allowed) |

### 7.3 Borders

- 1 px everywhere:
  - `--line` around panels and controls;
  - `--line-soft` between table rows;
  - `--line-strong` on form fields and the zero line.
- Left-edge accents keep their widths: 3 px `.notice`, `.alerts li`; 4 px `.asst-item`, `.toast`; 6 px `.asst-verdict`.
- The current nav item and a selected row use a 2 px inset bar: `box-shadow: inset 2px 0 0 var(--accent)`.

### 7.4 Surfaces and elevation

```
--bg (canvas behind everything)
 └ --bg-2   top bar, left menu, seg track, inset blocks inside a panel
 └ --panel  every .panel (one level; no panel in a panel)
     └ --head  table header row, optional panel title strip
 └ --elevated + --shadow-2  popovers (.sug, .tip, menus), left-menu flyout/drawer
 └ --elevated + --shadow-3  #cmd palette, .toast, .moresheet
```

Rules:
- **Dark:** separation comes from surface steps plus a 1 px `--line`. Panels carry no shadow (`--shadow-1` is a hairline used only on `.seg button.on` in light).
- **Light:** panels are white on `#f3f5f8` with `--line`; no shadow on panels.
- **No nested cards.** A block inside a panel that needs grouping uses `--bg-2` fill with no border and radius `--r-sm`. That applies to the following classes, which have a border today:
  - `.ic-card`, `.ic-committee`, `.ic-stat`, `.plain-box`, `.qsf-balance`, `.asst-answer`, `.qsf-card` when it sits inside a panel.
  
  A `.panel` inside a `.panel` loses border, padding and background. `.qsf-sec-body > .panel` already does this; generalise it as `.panel .panel { border: 0; padding: 0; background: transparent; }`.

### 7.5 Layers

| Token | Value | Use |
|---|---|---|
| `--z-raise` | 1 | sticky table header, sticky first column |
| `--z-header` | 10 | top bar, phone bottom bar |
| `--z-nav` | 12 | left menu (sticky column, rail) |
| `--z-popover` | 20 | `.sug`, `.tip`, nav flyout, `.moresheet` |
| `--z-drawer` | 30 | tablet nav drawer and its scrim |
| `--z-dialog` | 40 | `#cmd` |
| `--z-toast` | 50 | `.toast`, `#taptip` |

### 7.6 Motion

Motion is for state change only. Nothing moves on its own except a loading pulse.

| What | How |
|---|---|
| Colour and background on hover | `--dur-1` 120 ms, `--ease` |
| Fold open, drawer slide, rail expand | `--dur-2` 180 ms; drawer uses `transform` |
| Loading pulse | opacity 1 → .55 → 1 over 1.2 s, on the "불러오는 중…" text only |

- `@media (prefers-reduced-motion: reduce) { :root { --dur-1: 0ms; --dur-2: 0ms; } .is-loading { animation: none; } }`. This media query is allowed; only `prefers-color-scheme` is banned.
- No number tickers, no chart draw-in animation.

### 7.7 Breakpoints (allowed set only)

`test_four_widths_only` allows {380, 400, 640, 641, 1023, 1024, 1279, 1600}. The left menu therefore uses:

| Width | Left menu | Right analytics column |
|---|---|---|
| ≥1280 (default rules) | expanded, `--nav-w` 216 px, sticky | beside the table where the layout spec says so (`--right-w` 560 px at ≥1600; the layout spec may bring it to 1280–1599 at a narrower width) |
| 1024–1279 `@media (max-width: 1279px)` | rail `--nav-w-rail` 56 px, group icons only; the current group's tabs in a flyout (`--elevated`, `--z-popover`) | stacked below the table |
| 641–1023 `@media (max-width: 1023px)` | hidden; a menu button in the top bar opens a drawer (`--z-drawer`, `--scrim`) | stacked |
| ≤640 `@media (max-width: 640px)` | hidden; existing bottom bar + 더보기 sheet (unchanged) | stacked |

Adding a `min-width: 1280px` query would need a test change. Write the expanded state as the default and override it downwards.

---

## 8. Iconography

Decision: a hybrid.
1. **Chrome icons become one inline SVG sprite.** Put it at the top of `<body>` in `index.html`, as `<svg class="sprite" aria-hidden="true">` with `<symbol>` elements. Use it as `<svg class="ico" aria-hidden="true"><use href="#i-…"/></svg>`.
   - No icon font, no file, no network.
   - The sprite is hidden with `position:absolute; width:0; height:0; overflow:hidden`, not `display:none`.
2. **Content glyphs stay text:**
   - ▲▼ for price direction and sort;
   - `·` separators;
   - `→` in sentences;
   - `✕` in chip removal (`.chip .x`, with an `aria-label`);
   - ▸/▾ fold markers (`.fold h2::before`, `summary`).

   These are part of copied text, or small enough that a glyph is clearer. No test pins them.

```css
.ico { width: 16px; height: 16px; flex: none; fill: none; stroke: currentColor; stroke-width: 1.75;
       stroke-linecap: round; stroke-linejoin: round; vertical-align: -3px; }
.ico.lg { width: 20px; height: 20px; }   /* rail and bottom bar */
```

Icons always take the text colour of their control. A nav icon is never coloured by group.

Every icon-only button keeps a visible tooltip (`title`) and an `aria-label`. Today `#theme` has `aria-label="화면 테마 전환"` and `#cmdbtn` has its own label; keep both.

Symbols (24×24 viewBox; paths are a starting point and may be refined, keeping the stroke style):

| id | For | Path data |
|---|---|---|
| `i-today` | group 오늘 | `<rect x="3.5" y="5" width="17" height="15" rx="2"/><path d="M3.5 10h17M8 3v4M16 3v4"/>` |
| `i-market` | group 시장 | `<path d="M4 19.5h16"/><path d="M4 15l5-5 4 3 7-7"/>` |
| `i-stock` | group 종목 | `<path d="M6 3.5h8l4 4v13H6z"/><path d="M14 3.5v4h4M9 12h6M9 16h6"/>` |
| `i-chart` | group 차트 | `<path d="M7 4v4M7 15v5M17 6v4M17 15v4"/><rect x="5" y="8" width="4" height="7" rx="1"/><rect x="15" y="10" width="4" height="5" rx="1"/>` |
| `i-account` | group 내 계좌, top-bar 내 계좌 | `<rect x="3.5" y="6" width="17" height="13" rx="2"/><path d="M3.5 10h17"/><circle cx="16.5" cy="14.5" r="1"/>` |
| `i-score` | group 점수 | `<path d="M5 20v-8M12 20V5M19 20v-5"/>` |
| `i-verify` | group 검증·기록 | `<path d="M9 3.5h6M10 3.5v6l-5.2 8.7a1.5 1.5 0 0 0 1.3 2.3h11.8a1.5 1.5 0 0 0 1.3-2.3L14 9.5v-6"/><path d="M7.5 14.5h9"/>` |
| `i-coin` | group 코인 | `<circle cx="12" cy="12" r="8.5"/><circle cx="12" cy="12" r="4.5"/>` |
| `i-search` | search field | `<circle cx="11" cy="11" r="6.5"/><path d="M16 16l4.5 4.5"/>` |
| `i-collect` | 지금 수집 | `<path d="M20 12a8 8 0 1 1-2.34-5.66"/><path d="M20 4v4.5h-4.5"/>` |
| `i-phone` | 폰 연결 | `<rect x="7" y="3" width="10" height="18" rx="2"/><path d="M11 17.5h2"/>` |
| `i-theme` | ◐ toggle | `<circle cx="12" cy="12" r="8.5"/><path d="M12 3.5a8.5 8.5 0 0 1 0 17z" fill="currentColor"/>` |
| `i-menu` | tablet drawer button | `<path d="M4 7h16M4 12h16M4 17h16"/>` |
| `i-sidebar` | collapse / expand the left menu | `<rect x="3.5" y="4.5" width="17" height="15" rx="2"/><path d="M9.5 4.5v15"/>` |
| `i-close` | close (drawer, phone panel, toast 닫기 stays text) | `<path d="M6 6l12 12M18 6L6 18"/>` |
| `i-chevron` | flyout and expandable rows | `<path d="M9 6l6 6-6 6"/>` |
| `i-more` | 더보기, overflow menu | `<circle cx="5" cy="12" r="1.25" fill="currentColor"/><circle cx="12" cy="12" r="1.25" fill="currentColor"/><circle cx="19" cy="12" r="1.25" fill="currentColor"/>` |
| `i-info` | "what is this" next to rule-result labels | `<circle cx="12" cy="12" r="8.5"/><path d="M12 11v5M12 8h.01"/>` |

Notes:
- `⌘K` stays text in `#cmdbtn`: it is a key name, not an icon.
- The ◐ toggle may keep the ◐ character, or switch to `i-theme`. Either way the button keeps id `theme`, its `title` (which names 시스템/밝게/어둡게) and its `aria-label`.

---

## 9. Component states

One rule set, applied to every interactive class (`button`, `.seg button`, `.chip`, `.linkish`, `.qs-sort`, `tr.click`, `.qsf-rrow`, `.card[data-ticker]`, nav items, `#cmd-list li`, `.sug-item`, `summary`).

| State | Visual | Notes |
|---|---|---|
| Rest | as defined per component | — |
| Hover (pointer: fine only) | background `--hover` (controls) or `--row-hover` (rows); border `--line-strong` on bordered controls; text `--ink` | Replaces today's `button:hover { border-color: var(--accent) }`. Accent on hover made every button look selected. Wrap hover rules in `@media (hover: hover)` so touch does not stick |
| Focus-visible | `outline: 2px solid var(--accent); outline-offset: 2px` (rows: `-2px`) | Keep the pinned `:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }` and `tr[tabindex]:focus-visible { outline-offset: -2px; }`. The ring shows even on selected and filled items (≥4.65:1 everywhere) |
| Active / pressed (momentary) | background one step darker than hover: `color-mix(in srgb, var(--hover) 70%, var(--ink) 6%)`, no transform | No scale or translate |
| Selected / on (persistent) | rows: `--row-selected` + inset 2 px `--accent` bar on the first cell; seg: `--seg-on`; nav item: `--row-selected` + bar + 600 weight; chip: border `--accent` + `--row-selected` | Always mirrored in ARIA: `aria-current="page"` (nav), `aria-pressed` (seg, kept by the existing MutationObserver), `aria-expanded` (fold rows), `aria-selected` (only in listboxes: `#cmd-list`, `.sug`) |
| Disabled | `opacity: .55; cursor: not-allowed`; no hover change | Pinned (`button:disabled { opacity: .55`). Disabled controls keep a `title` that says why, where the JS already writes one (e.g. `.seg.idle`) |
| Idle (allowed but unused, `.seg.idle`) | opacity .5, still clickable | Pinned (`.seg.idle { opacity: 0.5; }`) |
| Loading (first load) | the existing `loading` string `<div class="panel empty">불러오는 중…</div>`, plus `aria-busy="true"` on the tab section and the `.is-loading` pulse | No skeleton bars or fake chart shapes: they look like data (rule: no fabricated charts) |
| Refreshing (data shown, new data coming) | existing `#asst-brief.refreshing` pattern, generalised as `.is-refreshing > :not(.asst-refresh)` at opacity .55, plus the existing "새로 고치는 중" line | Keeps the old numbers readable |
| Empty | `.empty`: centered, `--muted`, `--fs-md`, `padding: var(--sp-5) var(--sp-4)`, at least 96 px tall inside a table area; one sentence saying why, plus one action if one exists (`.collect-now` → 지금 수집) | An empty region shows this sentence. It never shows a blank panel and never shows 0 |
| Error | `.panel.err` from `errBox()`: text `--bad`, panel border `color-mix(in srgb, var(--bad) 45%, var(--line))`, Korean message from `errKo()`; with a 다시 시도 button where a retry exists | `.err` inline text stays `--bad` |
| Stale | `.badge.STALE` (warn text, warn 45% border) next to the data time; the time in `.meta` with "기준 YYYY-MM-DD HH:MM" from `stamp()` | Owner rule: stale data labelled. Never only a colour |
| Intraday / unconfirmed (`liveBadge`, "장중·미확정") | `.badge.live`: `--warn` text | Unchanged meaning |
| Frozen record | `.badge.FROZEN`: `--accent` text | Unchanged |
| Unavailable | `.badge.UNAVAILABLE`: `--bad` text; the value cell shows `DASH` | Missing is never 0 |
| MOCK / 가상 / 모의 / sample | new `.badge.mock`: `--muted` text, transparent background, `1px dashed var(--line-strong)` | For paper trades (모의 매매), committee paper portfolios (가상) and anything labelled as not real. The dashed edge is the "not real money" cue; the word carries the meaning |
| Rule-result caveat ("A BUY score does not authorize a trade") | `.meta` line under the judgement, `--muted` | Wording comes from the server; style only |

---

## 10. Table conventions

These apply to `table` everywhere. Named tables: `.qsf-rank-tbl`, `.qs-table`, `#peer-tbl`, `table.grades`, `table.cal`, `.fc-table`, `table.sp-ret`, `#qsfplan`, the account, portfolio, paper and watch tables.

### 10.1 Density

| Density | Row height | Body size | Cell padding | Applies to |
|---|---|---|---|---|
| Regular (default) | `--row-h` 32 px (`td { height: var(--row-h) }`, a minimum) | `--fs-md` 13 px, `--lh-ui` | `0 var(--cell-x)` vertical centring; 4 px top/bottom when the cell wraps | ranking (`.qsf-rank-tbl`), screener (`.qs-table`), holdings, watchlist, plan |
| Compact | `--row-h-compact` 28 px | `--fs-md`; secondary columns `--fs-sm` | `0 6px` | `table.cal`, `#peer-tbl`, `table.grades`, `.fc-table`, `table.sp-ret`, record tables inside `.qsf-record`, the lab and model tables. Class: `table.compact` (new), added by the screen templates |
| Touch (`pointer: coarse`) | `--row-h-touch` 40 px on clickable rows (`tr.click`, `.qsf-rrow`) | unchanged | unchanged | phones and tablets |

There is no user density toggle; that would be a new feature.

### 10.2 Alignment and text

- **Numeric cells align right.** That is the table default today: `th, td { text-align: right }` with `.l` for text. Keep it.
- Header cells align with their column. A numeric header is right-aligned, so its label sits over the digits.
- The first column is left-aligned and sticky (`position: sticky; left: 0`). It needs an opaque background that follows the row state. The state rules below set `td` backgrounds for the whole row, so the sticky cell matches.
- Units go in the header when they are the same for the whole column (e.g. "등락(%)"). Today's cells already carry `%`; keep the cell output (formatters are not changed).
- **Positive / negative:** colour plus sign (`pct()` → `.up/.down/.flat`). Zero is `.flat` `--muted`. No background tint on cells: tinted cells in a 50-row table look like a heatmap of judgements.
- **Missing:** `DASH` (`<span class="missing">—</span>`, `--muted`), right-aligned in numeric columns. Never `0`, never blank. A column that is missing for all rows on a screen stays visible with dashes. Hiding it is a layout decision, and must be flagged.
- **Truncation:**
  - Only names are truncated: `.qr-name`, `.nm`, `.sug-item span`, `.co-lead`. They get `max-width: 220px` (desktop), `overflow:hidden; text-overflow:ellipsis; white-space:nowrap`, and the full name in `title` (already written by `tickerLabel` contexts, or add it).
  - Rule-result text (`.qr-why`, `.qr-out`, `.qr-risk`, reasons, notes) is **never** truncated or line-clamped. It wraps with `word-break: keep-all`. Truncating a reason hides a feature.
- **Long tables:** no zebra striping. Rows are separated by 1 px `--line-soft`; the last row has no border.
- **Totals and primary rows** (`.rec-primary`, `tfoot`): weight 600, `border-top: 1px solid var(--line-strong)`.
- **Day or group separators** (`table.cal tr.day-start`): `border-top: 1px solid var(--line)` (today `--grid`), and the group's first cell in `--ink-2` 600.

### 10.3 Header

```css
th { height: var(--row-h-compact); font-size: var(--fs-sm); font-weight: 600; color: var(--muted);
     background: var(--head); border-bottom: 1px solid var(--line); white-space: nowrap; }
```

Sticky header:
- Every table taller than the viewport gets the `.qsf-rank-tbl` pattern: `position: sticky; top: var(--sticky-top); z-index: var(--z-raise); box-shadow: 0 1px 0 var(--line)`.
- At ≥1024 px its `.tbl-wrap` stops being a scroll box (pinned rule; keep it). Generalise with a class `table.sticky-head`, plus `.tbl-wrap:has(> .sticky-head) { overflow: visible; }` inside `@media (min-width: 1024px)`.
- Below 1024 px a wide table scrolls sideways inside `.tbl-wrap`. The header then sticks only within that box, which is accepted today.
- `--sticky-top` must equal the top bar's height once the group bar is no longer a horizontal sticky row (see section 15, item F4).

### 10.4 Sort indicator (`.qs-table` today, `#peer-tbl` to migrate)

One pattern for all sortable tables:
```html
<th aria-sort="descending|ascending|none"><button type="button" class="qs-sort" data-sort="k">라벨<span class="sort-mark" aria-hidden="true"> ▼</span></button></th>
```
```css
.qs-sort { font: inherit; font-weight: 600; color: inherit; min-height: 24px; }        /* pinned rule text kept */
th[aria-sort="ascending"], th[aria-sort="descending"] { color: var(--ink); }
.sort-mark { color: var(--accent); font-size: var(--fs-xs); }
th[aria-sort="none"] .qs-sort:hover::after { content: " ↕"; color: var(--faint); }
```
- Only the current sort column shows ▲ or ▼, in `--accent`. That distinguishes it from price arrows, which are never accent-coloured (R3).
- `#peer-tbl` today uses `th.sort` with a click handler on the `th` and no `aria-sort`. Migrating it to the button pattern is a `peers.js` change that brings keyboard support.

### 10.5 Row states

```css
tr.click:hover > td, .qsf-rrow:hover > td { background: var(--row-hover); }                  /* @media (hover: hover) */
tr.me > td, #qsfplan tr.hl > td, .qsf-rrow[aria-expanded="true"] > td, tr[aria-selected="true"] > td
  { background: var(--row-selected); }
tr.me > td:first-child, #qsfplan tr.hl > td:first-child, .qsf-rrow[aria-expanded="true"] > td:first-child
  { box-shadow: inset 2px 0 0 var(--accent); }
.qsf-exp-row > td { background: var(--bg-2); }          /* the expanded detail under a ranking row; today --bg */
tr.voided td { color: var(--muted); text-decoration: line-through; }                         /* unchanged */
```

These replace today's `color-mix(in srgb, var(--accent) 12%/14%, transparent)` tints and the `--chip` hover. Translucent tints make the sticky first cell show the content scrolling under it.

### 10.6 Horizontal overflow

- `.tbl-wrap { overflow-x: auto; }` stays.
- Add scroll shadows so a cut-off table is visible:
  ```css
  .tbl-wrap { background:
      linear-gradient(to right, var(--panel) 30%, transparent) left / 24px 100% no-repeat local,
      linear-gradient(to left, var(--panel) 30%, transparent) right / 24px 100% no-repeat local,
      linear-gradient(to right, rgba(0,0,0,.25), transparent) left / 10px 100% no-repeat scroll,
      linear-gradient(to left, rgba(0,0,0,.25), transparent) right / 10px 100% no-repeat scroll; }
  ```
- Column dropping by width stays as built (`.qd-col` ≤1279, `.qr-dcol` ≤1023, `.w/.w2` ≤640, and the card-open state at ≥1600). The dropped values are on the score card or on the second line (`.qr-m2`), as today.

### 10.7 Flush tables in panels

A panel whose main content is a table uses `.panel.flush`:
- `padding: 0`;
- the `h2` gets `padding: var(--sp-3) var(--sp-4)` and `border-bottom: 1px solid var(--line)`;
- the table runs edge to edge, with first and last cell padding `--sp-3`.

This is what turns a "card with a table" into a workstation grid.

---

## 11. Panel and control conventions

### 11.1 Panel header (`.panel > h2`, built by `ui.head`)

```
[title 14/600 --ink] [sub .meta 12 --muted] [badges]  ············  [actions: seg / buttons, margin-left:auto]
```

```css
.panel > h2 { display: flex; align-items: center; gap: var(--sp-2); flex-wrap: wrap; min-height: var(--ctl-h);
              margin: 0 0 var(--sp-3); font-size: var(--fs-base); font-weight: 600; line-height: var(--lh-ui); }
.panel > h2 > .ph-actions { margin-left: auto; display: inline-flex; gap: var(--sp-2); flex-wrap: wrap; }
```

- `ui.head({actions})` should wrap `actions` in `<span class="ph-actions">`. That is a one-line `ui.js` change.
- Templates that put a `.seg` straight in the `h2` (e.g. `#heat-mode`) keep working; they simply do not right-align until wrapped.
- The data time and source sit in the panel header's `.meta` (e.g. "기준 2026-11-24 07:30 · Yahoo 지연"), not in a footer line, when the screen has one time for the panel.

**Section header inside a panel** (`.panel h3`, `.qc-title`, `.qsf-card h3`, `.asst-answer h4`):
- `--fs-md` 600, `--ink-2`;
- `margin: var(--sp-4) 0 var(--sp-2)`;
- no rule line, except `.qsf-sec`, which keeps its top border.

**Fold / expand** (`details > summary`, `.fold` h2, `.qsf-sec`, `.co-sum`, `.qsf-record`, `.ic-more`, `.asst-more`):
- Summary row: `min-height: var(--ctl-h)`, `display:flex; align-items:center; gap:var(--sp-2)`, `--fs-base` 600, cursor pointer.
- Marker: ▸ closed, ▾ open, in `--muted`. This is already the case for `.fold h2::before`; use the same marker for `details` via `summary::before` and hide `::-webkit-details-marker`.
- Hint (`.fold-hint`): `--fs-sm` 400 `--muted`, hidden when open (pinned rule).
- Remembered fold state (`qse-fold-*`, `qse-qsf-folds`) is unchanged.

**Inline metric** (`.kv` from `ui.kv`, `.ic-stat`, `.qsf-meta`):
- Label: `--fs-sm` `--muted`, above.
- Value: `--fs-base` 600 tabular `--ink` (`--fs-lg` in summary strips).
- A delta follows the value as `pct()` output on the same line (the existing `#tab-paper` rule, generalised to `.kv b span { display:inline }`).
- **Metric strip** (row of key numbers at the top of a screen): `.kv.strip`, a single row, columns separated by 1 px `--line-soft` vertical rules, no boxes. This replaces equal bordered cards where the layout spec calls for a strip.

### 11.2 Badges and chips

| Class | Look | Use |
|---|---|---|
| `.badge` (neutral) | `--fs-xs` 600, `padding: 1px 6px`, height 18 px, `--r-sm`, background `--chip`, text `--muted` | neutral notes (보유, 관심, 참고, 대기) |
| `.badge.info` | as neutral, 500 weight | pinned |
| `.badge.ok` | text `--ok` | **rule missing today** (used twice); add it |
| `.badge.REAL` | text `--muted` | pinned |
| `.badge.STALE`, `.badge.live`, `.badge.risk-note`, `.badge.near-edge` | text `--warn`; `near-edge` adds a 1 px `--warn` border | unchanged meaning |
| `.badge.UNAVAILABLE` | text `--bad` | unchanged |
| `.badge.FROZEN` | text `--accent` | unchanged |
| `.badge.mock` (new) | transparent, `1px dashed var(--line-strong)`, `--muted` | 가상 / 모의 / sample |
| `.chip` | pill, `--fs-md`, `padding: 2px 10px`, background `--chip`, border 1 px `--line` | filters, compare tickers, question chips |
| `.chip.on` | border `--accent`, background `--row-selected`, 600 | replaces `outline: 2px solid var(--accent)`, which looked like a focus ring |
| `.qsf-act` judgement chip | unchanged: pill, 1.5 px `--act` border, 9 px `--act` dot, `--ink` 700 text | owner decision 5 |
| `.grade` A–F | unchanged structure; `.g-A` background `--accent-fill` with `--on-accent` text | pinned `color: var(--on-accent)` |

### 11.3 Segmented control `.seg` (`ui.seg`, `#market`, view switchers, ranges)

```css
.seg { display: inline-flex; padding: 2px; gap: 2px; background: var(--seg-track); border: 1px solid var(--line);
       border-radius: var(--r-sm); max-width: 100%; overflow-x: auto; }
.seg button { border: 0; border-radius: 3px; background: transparent; color: var(--muted); height: var(--ctl-h-sm);
              padding: 0 10px; font-size: var(--fs-md); white-space: nowrap; word-break: keep-all; flex: 0 0 auto; }
.seg button:hover { color: var(--ink); }
.seg button.on { background: var(--seg-on); color: var(--ink); font-weight: 600; box-shadow: inset 0 0 0 1px var(--line-strong); }
```

- **Change to a pinned rule:** today `.seg button.on { background: var(--ink); color: var(--panel); … }`. That is a full inversion, which in the dark default becomes bright white blocks across every view row. The proposed on-state is a raised neutral surface with a 3:1 edge and 600 weight. It is still neutral (not accent) and still mirrored by `aria-pressed`. The pin in `test_text_on_the_accent_passes_and_a_selected_segment_is_a_neutral_inversion` must change. See section 16, item U3.
- `border-radius: 3px` is a literal that the test allows (only 4/6/8/10/12/14 are banned).
- Touch: `.seg button { min-height: 42px }` under `(pointer: coarse)` (existing rule).

### 11.4 Buttons

| Variant | Class today | Rest | Hover | Size |
|---|---|---|---|---|
| Default (secondary) | `button` | background `--elevated` (dark) / `--panel` (light), border 1 px `--line`, text `--ink` | background `--hover`, border `--line-strong` | height `--ctl-h` 32, padding `0 12px`, `--fs-md`, `--r-sm` |
| Primary | `.btn-primary`, `.search button`, `.g-A` | background and border `--accent-fill`, text `--on-accent` | `--accent-fill-hover` | same |
| Ghost (top bar, toolbars) | `.ghost` | transparent, border transparent, text `--ink-2` | background `--hover`, text `--ink` | height 32, padding `0 8px`; icon-only ghost is 32×32 |
| Link-like | `.linkish`, `.qs-open`, `.qsf-go .linkish` | no chrome; `.qsf-go` links in `--accent` | text `--accent` (pinned rule) | min-height 24 |
| Small (inline in bars and rows) | `.collectbar button`, `.netbar button`, `.verbar button`, `.x` | default look | default | height `--ctl-h-sm` 28, padding `0 8px`, `--fs-sm` |
| Remove | `.x`, `.chip .x` | text `--muted` | text `--bad` | — |

- At most one primary button per panel.
- Destructive actions (removing a journal entry and the like) stay default style with a confirm step, as today.

### 11.5 Form fields

These stay on the pinned shared rule (`input…, select, textarea { … border: 1px solid var(--line-strong) … }`). Values:

| Property | Desktop | Phone (≤640 px) / coarse |
|---|---|---|
| Height | `--ctl-h` 32 px | `--ctl-h-touch` 40 px |
| Font | `--fs-md` 13 px | `--fs-lg` 16 px (stops iOS Safari zoom on focus; today 14 px zooms) |
| Background | `--bg` (an inset well on the panel) | same |
| Border | 1 px `--line-strong` (3.89:1 dark, 3.73:1 light on the panel) | same |
| Radius | `--r-sm` | same |
| Placeholder | `--muted` | same |
| Focus | `outline: 2px solid var(--accent); outline-offset: 1px` (pinned) | same |
| Invalid | border `--bad`, plus `.msg.err` text below; `aria-invalid="true"` | same |
| Label | `.form label`: `--fs-sm` `--muted` above the field, 3 px gap (unchanged) | same |

- The duplicate field rules in `.search input`, `.addrow input`, `.form input`, `.asst-ask input` set their own border, padding and background. They should be reduced to layout-only properties (flex, width), so the shared rule governs the look.
- `.search input` keeps `text-transform: uppercase` only while the market is not KR. Hangul is unaffected anyway.

### 11.6 Overlays

| Overlay | Surface | Edge | Shadow | Radius |
|---|---|---|---|---|
| `.tip` (chart hover) | `--elevated` | 1 px `--line` | `--shadow-2` | `--r-sm` |
| `.sug` (search suggestions) | `--elevated` | 1 px `--line` | `--shadow-2` | `--r-md` |
| `#cmd .cmd-box` | `--elevated` | 1 px `--line` | `--shadow-3` | `--r-lg` |
| `#cmd` backdrop | `--scrim` (today a literal rgba) | — | — | — |
| `.toast` | `--elevated` | 1 px `--line-strong`, 4 px left `--bad` / `--accent` | `--shadow-3` | `--r-lg` |
| `.moresheet` | `--elevated` | top 1 px `--line-strong` | `--shadow-3` | top corners `--r-lg` |
| Nav flyout and drawer | `--elevated` | right 1 px `--line` | `--shadow-2` | 0 |

Selected item in `#cmd-list` and `.sug`: `--row-selected` (today `--hover`), with `aria-selected`.

---

## 12. Chart conventions (shared with the visualization agent)

- **V1 Surface:** canvases draw on transparent or `--panel`. Charts sit in a panel with a header (title, period `.seg`, data time). A chart is never a panel on its own without a title.
- **V2 Axes:**
  - Price and return charts put the y-axis labels on the right, in a `padR` gutter of 44–56 px. `portfolio.js` and `lab.js` already do this.
  - Labels are `--muted`, `chartFont(11)`, tabular.
  - The x-axis shows 4–6 date labels in `YYYY-MM` or `MM-DD`, never overlapping.
- **V3 Series:**
  - Line widths: primary 1.75–2 px; secondary 1.25–1.5 px; MA 1.2 px.
  - Series beyond slot 4 must be named: legend plus a direct label at the line end when space allows.
  - Slots 5–8 may add a dash pattern (`[6,3]`) as a second cue. That is optional and owned by the visualization agent.
- **V4 Grid:** horizontal gridlines only, `--grid`, 1 px; 4–5 lines. The zero line uses `--line-strong`.
- **V5 Order:** draw grid, then bands, then benchmark, then series, then candles, then markers, then crosshair. The user's own series (내 계좌) is drawn last of the lines, so it stays on top.
- **V6 Colour meaning:**
  - Candles, volume and the heatmap "기본 색" follow `--up/--down` (rule C).
  - Compare lines use `--sN` by slot; RRG uses its four slots.
  - Domain-score bars use `--muted`; the heat score ramp is blue, which is neutral.
  - No judgement colours inside canvases.
- **V7 Tooltip:**
  - `.tip` (section 11.6), `--fs-sm`, tabular.
  - Label column `--muted`, values `--ink`. Changes carry sign and `.up/.down` colour.
  - The date is the first line.
  - The crosshair is `.cha-xline` (`--muted` .6).
- **V8 Missing data:** gaps, not zeros. A chart with no data shows the panel's `.empty` sentence instead of an empty axis box (no empty panels).
- **V9 Labels on charts:** `role="img"` and an `aria-label` that names what is drawn (existing). A text summary nearby states the period and the data time.
- **V10 Redraw:** canvases read tokens through `cssVar()` on every draw. `redrawAll()` already runs on a theme change, so a token change needs no extra JS.
- **V11 Fonts in canvases:** `chartFont(px, weight)` (section 6.1), 11 px minimum.

---

## 13. Light and dark strategy

### 13.1 Mechanism

The mechanism is unchanged:
- `theme.js` in `<head>` sets `data-theme="dark"|"light"` on `<html>` before the first paint.
- `app.js` `applyTheme()` handles later switches.
- The toggle cycles `auto → light → dark` and is saved as `qse-theme`.
- CSS holds one light block (`:root`) and one dark block (`:root[data-theme="dark"]`), and never uses `prefers-color-scheme` (pinned).

### 13.2 Dark by default (owner decision 3)

Change the fallback in **both** places from `"auto"` to `"dark"`:
- `theme.js`: `var t = "dark"; try { t = localStorage.getItem("qse-theme") || "dark"; } …`
- `app.js:549–550`: `let theme = "dark"; try { theme = localStorage.getItem("qse-theme") || "dark"; } …`

Consequences:
- A stored choice still wins. A device that already stored `auto` keeps following its OS (section 16, item U2).
- The pinned `applyTheme` line and the `setAttribute("data-theme", dark ? "dark" : "light")` line in `theme.js` are unchanged.
- The cycle order is unchanged, and `title` keeps saying 시스템/밝게/어둡게.

### 13.3 How the colour rule and theme combine

- `data-theme` and `data-color` are independent attributes on `<html>`. Four combinations exist:
  - dark/intl, dark/kr, light/intl, light/kr.
- `--up/--down` resolve through `var()` to the right pair for each. All four are covered by the contrast tables in section 4.
- `paintColorRule()` is untouched.
- Charts redraw on a theme change (`redrawAll`) and on a tab change (`redrawShown`), so canvases always pick up the current pair.

### 13.4 What must look the same in both themes

- The same structure, sizes, borders and states. Only token values differ.
- No component may set a colour literal for one theme only. The exceptions are the heatmap tile-label constants and `#taptip`'s fallback values inside `var()`.

---

## 14. Migration plan and test-pin ledger

Order (each step is one commit with its test updates; the app works after each):

**T1: Tokens (this file's section 1).**
- Replace the two colour blocks.
- Move shadows into them.
- Add the new scale tokens.
- No selector changes, except:
  - `--sma*` become aliases;
  - `#cmd` backdrop uses `--scrim`;
  - `.tip` and `.sug` use `--elevated`.
- Visible result: the new dark palette on the old layout.

**T2: Base elements.**
- `body` font.
- `button` / `.ghost` / `.btn-primary` / `.search button` / `.g-A` to section 11.4 (accent-fill).
- Fields to 11.5.
- `button:hover` to the `--line-strong` edge.
- Tabular-numeral rule (6.3).
- Minimum 11 px.

**C1: Shared components.**
- `.panel` (radius, flush, `.panel .panel`).
- `.panel > h2` and `.ph-actions` (plus `ui.js` `head()`).
- `.badge` incl. `.ok` and `.mock`; `.chip.on`; `.seg` (11.3).
- Folds; `.notice`; `.empty`/`.err`/loading states.
- Overlays (11.6).

**C2: Tables.**
- Section 10: density classes, header, row states replacing the accent tints, sticky-head generalisation, scroll shadows.
- Sort-mark span in `qsf.js`; `peers.js` migration.

**S1: Shell.**
- Layout agent's spec, using `--topbar-h`, `--nav-w`, `--nav-w-rail`, `--z-nav`, `--z-drawer`, `--scrim`, the icons in section 8, and the breakpoints in 7.7.
- Includes the theme default change (13.2) and the `setTopH` fix (section 15, item F4).

**V1: Charts.**
- `chartFont`.
- `--heat-*` read in `map.js`.
- Zero line to `--line-strong`.
- 10 px canvas text to 11.
- Optional dash patterns for slots 5–8.

**SC: Screens.**
- Per the layout spec: workspace columns, metric strips, flush table panels.
- Nested bordered blocks replaced by `--bg-2` insets (7.4).

What stays as it is:
- Rule C lines.
- Judgement classes (`.act-*`, `.asst-verdict.v-*`, `.qsf-act`, `.qsf-bar i` muted).
- `.qsf-split` at ≥1600.
- Ranking column-drop rules.
- Phone bottom bar and more-sheet, including the literal `height: 56px` and `body { padding-bottom: 56px; }` pins.
- Utility classes (`.m0`, `.mt-*`, `.wrap`, …).
- `.sr-only`.
- Focus rules.
- `#taptip`.
- The `(pointer: coarse)` block.

Test pins this spec changes (update them deliberately, in the step named):

| Step | Test | Current assertion | Change |
|---|---|---|---|
| T1 | `test_ui_batch_3.py::test_fields…` (line 41) | `CSS.count("--line-strong: #6b7686") == 1` | → `CSS.count("--line-strong: #6b7b92") == 1` (contrast asserts still pass: 3.89 / 4.42 dark) |
| T1 | `test_ui_batch_6.py::test_judgements_have_their_own_colours…` (line 39) | `"--judge-hold: #64748b;"` in both blocks | light unchanged; dark → `#7d8da6` (`#64748b` is 2.98:1 on the new selected row, under 3:1) |
| T1/T2 | `test_ui_batch_1.py::test_text_on_the_accent_passes…` (line 115) | `on-accent` vs `--accent` ≥4.5 | → `on-accent` vs `--accent-fill` ≥4.5 (5.17 dark, 6.16 light). The three selectors keep `color: var(--on-accent)` |
| C1 | same test (line 119) | `.seg button.on { background: var(--ink); color: var(--panel);` | → `.seg button.on { background: var(--seg-on); color: var(--ink);`; replace the "≥7 inversion" reason with `contrast(--ink, --seg-on) ≥ 7` (11.29 dark, 17.96 light). **Needs owner sign-off**, see section 16, item U3 |
| C2 | none pinned for `tr.me` / `#qsfplan tr.hl` tints | — | free to change |

Pins that stay green without change: verified against the values above.

| Test | Why it still passes |
|---|---|
| `test_ui_batch_1` light `--up-kr == #c22f35`, `--down-kr == #1f5fd1`; dark `--down-kr == #5b9cff` | values kept, written in lower case |
| `test_ui_batch_1` `--ok == --up-intl` | byte-identical |
| `test_ui_batch_1` up/down/ok/warn ≥4.5 on light chip and panel | light values unchanged |
| `test_ui_batch_1` `--ink` vs `--panel` ≥7 | 13.87 dark, 17.96 light |
| `test_ui_batch_2` `--muted` and `--warn` ≥4.5 on panel, chip and bg | min 5.66 dark, 5.13 light |
| `test_ui_batch_3` `--line-strong` ≥3 on panel and bg | 3.89 / 4.42 dark; 3.73 / 3.42 light |
| `test_ui_batch_3` 7 font sizes ascending; tokenised font-size, z-index and radius | kept; every new rule uses tokens |
| `test_chart_analysis` `--maN:` count == 2 | one definition per theme; `--smaN` aliases do not contain `--maN:` |
| `test_ui_batch_5` widths ⊆ allowed set | 7.7 uses 1279/1023/640 only |
| `test_ui_batch_5` no `prefers-color-scheme`; one dark block | kept |

Pins the **layout** step will touch (owned by the layout spec, listed so nothing is missed):
- `.groups {` exists;
- `.groups { position: sticky; top: var(--top-h, 0px); z-index: var(--z-header); }` inside `@media (min-width: 641px)`;
- `.tabs[hidden], .tabs button[hidden] { display: none; }`;
- the `.tabs {` … `.tabs button {` slice containing `flex-wrap: wrap` and no `overflow-x` (`test_screen_refresh_notice.py`);
- the phone header rules in `test_ui_batch_3`.

Recommendation: keep the class names `.groups` and `.tabs` and the element ids on the new vertical menu, so `app.js` selectors and these pins keep working. Only their layout properties change.

---

## 15. Places where this spec moves or hides something

| # | Item | What changes | Where it is afterwards |
|---|---|---|---|
| F1 | Left-menu tab labels at 1024–1279 px | The rail shows group icons only; tab names are not visible until the rail is opened | In the rail's flyout (hover, focus or click on a group icon) and via the expand button (`i-sidebar`). Every tab also stays reachable through ⌘K and number keys, as today |
| F2 | Left menu at 641–1023 px | Hidden behind the `i-menu` button | Drawer with all groups and tabs |
| F3 | Theme on first visit | Default dark instead of system | ◐ still cycles 시스템/밝게/어둡게 |
| F4 | `--sticky-top` calculation | `setTopH()` (`app.js:295–299`) adds the `.groups` height when `.groups` is `position: sticky`. If the vertical menu keeps class `.groups` and is sticky, its full height would be added and every sticky table header would sit far down the page | Change `setTopH` to add the group bar's height only when it is a horizontal bar (e.g. `g.offsetWidth > g.offsetHeight`), or to use the top bar only. Owner: layout/shell step |
| F5 | `.seg` on-state | Inversion replaced by a raised neutral state | Same buttons, same `aria-pressed` |
| F6 | Sort arrows in `#peer-tbl` | Move from header text into a `.sort-mark` span inside a button | Same columns, same order; now keyboard-operable |
| F7 | Nested bordered blocks (`.ic-card`, `.plain-box`, `.qsf-balance`, `.asst-answer`, …) | Lose their border inside a panel; become `--bg-2` insets | Same content, same place |

Nothing in this spec removes a feature, a label, a badge or a value.

---

## 16. Conflicts not resolved here

| # | Conflict | Why it cannot be fully resolved | What this spec does |
|---|---|---|---|
| U1 | **Korean down blue vs UI accent blue.** Owner decision 2 (blue = down on Korean screens) and decision 5 (blue = UI accent) put the same hue on two meanings. `--down-kr` `#5b9cff` (pinned) and `--accent` `#5b96f7` are both blue | Moving the accent off blue would break decision 5; changing Korean down off blue would break decision 2 | Separated by usage (R3): accent only on chrome (rings, bars, links, fills, sort marks), price blue only on numerals, arrows and candles, always with a sign. Owner may want to review this on a Korean ranking screen |
| U2 | **"Dark is the default" vs a stored `qse-theme=auto`.** A browser that already saved `auto` will keep following its OS, which may be light | Overriding a stored choice would ignore the user's own toggle | Only the fallback changes. If the owner wants dark everywhere now: one click of ◐ to 어둡게 per device, or a one-time migration (rewrite `auto` to `dark` once, under a new key such as `qse-theme-v2`). Needs an owner choice |
| U3 | **Segmented on-state.** The 2026-11-23 batch pinned "a selected segment is a neutral inversion". In the dark default this becomes bright white blocks in every view row | It is a recorded design decision with a test | Proposed raised neutral state (11.3). If the owner wants to keep the inversion, keep the pinned rule. Contrast passes either way |
| U4 | **Brief's suggested colours.** `#ef4444` negative and `#3b82f6` accent fail 4.5:1 on raised dark surfaces; `#64748b` hold fails 3:1 on the new selected row | Contrast rule wins over the suggestion | Re-picked: `#f46a6a`, `#5b96f7` text / `#2563eb` fill, `#7d8da6` (dark only). The suggested surfaces, `#22c55e`, `#f59e0b`, `#e5eaf1`, `#94a3b8` and `#273446` are used as given |
| U5 | **Eight compare lines are not all colour-vision safe.** No 8-colour palette is | — | Slots 1–4 are safe (deutan ΔE ≥ 9 dark, ≥ 17.7 light). Slots 5–8 rely on the legend, direct labels, and optionally dashes (V3) |
| U6 | **Pretendard.** Not bundled; the brief forbids external loading | — | System stack (6.1). Hangul glyphs differ by platform (Apple SD Gothic Neo on Apple devices, Malgun Gothic on Windows, Noto on Android). Digits are the same family wherever Segoe UI or SF exists |
