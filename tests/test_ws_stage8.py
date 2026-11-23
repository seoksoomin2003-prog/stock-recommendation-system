"""Workstation redesign stage 8 (2026-11-24): the refinement round after the visual critique and the functional check.
The data-time chip reaches 연구실's 자동 실행 block, #qsf:<view> from another tab shows that view, the menu starts as a rail below
1440 px when nothing is saved (owner decision), the ranking keeps its area bars from a 1120 px column (chief decision on QR-31), the
score card in the right column (sticky head, closed sections, short table forms, scroll reset), one always-visible line above the
ranking with the rest in 읽는 법 (owner decision), the screener's one area column, the two-column grid with the lower line in the main
column, and the Today candidates in a narrow column.  Display and wiring only: no score, rank or business-logic change."""
import json
import re
from pathlib import Path

from tests.test_ui_batch_1 import body, node
from tests.test_ui_batch_2 import media

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "terminal" / "static"
JS = {p.name: p.read_text(encoding="utf-8") for p in STATIC.glob("*.js")}
CSS = (STATIC / "style.css").read_text(encoding="utf-8")
APP, QSF, LAB, ASST, FC, THEME = JS["app.js"], JS["qsf.js"], JS["lab.js"], JS["assistant.js"], JS["forecast.js"], JS["theme.js"]


def line(src, start):
    i = src.index(start)
    return src[i:src.index("\n", i) + 1]


# ---------------------------------------------------------------- A. the data-time chip opens 연구실 at its 자동 실행 block
def test_the_data_time_chip_waits_for_the_record_and_scrolls_to_the_automation_block():
    record = body(LAB, "async function renderRecord(")
    assert '<h3 id="rec-auto">자동 실행</h3>' in record
    assert "let labRecordReady = Promise.resolve();" in LAB and "labRecordReady = renderRecord();" in body(LAB, "RENDER.lab = async function", "\n};\n")
    chip = APP[APP.index('$("#datatime").onclick'):]
    chip = chip[:chip.index("\n};\n")]
    assert 'await show("lab");' in chip and "await labRecordReady.catch(() => {});" in chip and '$("#rec-auto")' in chip
    assert "#autoline" not in chip                                     # the model tab's line is not on 연구실
    assert "누르면 연구실 탭의 자동 실행 줄을 봅니다" in APP                     # the tooltip now tells the truth


# ---------------------------------------------------------------- C3. #qsf:<view> from another tab shows that view
ROUTE = r"""
let booted = true;
const state = { tab: "lab", loaded: { qsf: true }, ticker: null, card: null };
const qsfState = { view: "track" };
const QSF_VIEWS = { rank: 1, screen: 1, exec: 1, track: 1 };
const RENDER = { qsf: 1, lab: 1, map: 1, today: 1 };
const calls = [];
const show = (t, push) => { calls.push(["show", t, push]); state.tab = t; };
const qsfSetView = (v) => { calls.push(["view", v]); qsfState.view = v; };
const drawn = { yes: true };
const $ = (s) => (s === "#qsfview" && drawn.yes ? {} : null);
const setMarket = () => {}, marketOf = () => "US";
const location = { hash: "" };
""" + line(APP, "const HASH_TICKER") + body(APP, "function fromHash(") + r"""
const out = [];
location.hash = "#qsf:exec"; fromHash(); out.push([qsfState.view, calls.splice(0)]);                 // drawn before, from 연구실
state.tab = "map"; location.hash = "#qsf:screen"; fromHash(); out.push([qsfState.view, calls.splice(0)]);
location.hash = "#qsf:screen"; fromHash(); out.push([qsfState.view, calls.splice(0)]);              // same tab, same view: nothing
location.hash = "#qsf:rank"; fromHash(); out.push([qsfState.view, calls.splice(0)]);                // same tab: the view only
state.tab = "lab"; state.loaded.qsf = false; drawn.yes = false; location.hash = "#qsf:track"; fromHash();
out.push([qsfState.view, calls.splice(0)]);                                                         // not drawn yet: renderQsf reads the view
console.log(JSON.stringify(out));
"""


def test_a_view_address_from_another_tab_shows_that_view():
    got = node(ROUTE)
    assert got[0] == ["exec", [["show", "qsf", False], ["view", "exec"]]]
    assert got[1] == ["screen", [["show", "qsf", False], ["view", "screen"]]]
    assert got[2] == ["screen", []]
    assert got[3] == ["rank", [["view", "rank"]]]
    assert got[4] == ["track", [["show", "qsf", False]]]


def test_the_view_and_an_open_card_stay_in_the_address_and_the_right_column_starts_at_the_top():
    sv = body(QSF, "function qsfSetView(")
    assert "if (right && was !== v) right.scrollTop = 0;" in sv
    assert '(qsfState.cardOpen || v !== "rank") && location.hash !== "#" + tabHash("qsf")) history.replaceState(null, "", "#" + tabHash("qsf"));' in sv
    assert "if (right) right.scrollTop = 0;" in body(QSF, "async function qsfPick(")
    detail = body(QSF, "function qsfDrawDetail(")
    assert "if (qsfBeside()) { qsfSideFolds($(\"#qsfdetail\")); if (right) right.scrollTop = 0; }" in detail
    assert detail.index("qsfSideFolds(") < detail.index('qsfOnOpen($("#qsffcfold")')       # sections are closed before their loaders wait


# ---------------------------------------------------------------- C7. the rail below 1440 px when nothing is saved (owner decision)
NAV = r"""
function navFor(width, saved) {
  const attrs = {};
  globalThis.localStorage = { getItem: (k) => (k === "qse-nav" ? saved : k === "qse-theme-v2" ? "1" : null), setItem() {} };
  globalThis.window = { matchMedia: (q) => { const m = /max-width: (\d+)px/.exec(q); return { matches: m ? width <= Number(m[1]) : false }; } };
  globalThis.document = { documentElement: { setAttribute: (k, v) => { attrs[k] = v; } } };
  eval(THEME_SRC);
  return attrs["data-nav"];
}
console.log(JSON.stringify([navFor(1920, null), navFor(1440, null), navFor(1439, null), navFor(1280, null), navFor(1100, null),
  navFor(1280, "full"), navFor(1920, "rail"), navFor(1300, "junk")]));
"""


def test_the_menu_starts_as_a_rail_below_1440_unless_a_width_was_saved():
    got = node("const THEME_SRC = " + json.dumps(THEME) + ";\n" + NAV)
    assert got == ["full", "full", "rail", "rail", "rail", "full", "rail", "rail"]
    assert 'const NAV_RAIL_BELOW = "(max-width: 1439px)";' in APP
    apply = body(APP, "function navApply(")
    assert "navPref() || (window.matchMedia(NAV_RAIL_BELOW).matches" in apply                    # a saved choice wins
    assert "window.matchMedia(NAV_RAIL_BELOW).addEventListener(\"change\", navApply);" in APP
    assert "(max-width: 1279px)\").addEventListener(\"change\", navApply)" not in APP


# ---------------------------------------------------------------- C1. the score card in the right column
def test_the_card_in_the_right_column_has_a_sticky_head_closed_sections_and_short_tables():
    assert 'const QSF_SIDE_FOLDS = new Set(["basis", "plan", "plan-held", "factors", "committee", "range", "tech"]);' in QSF
    side = body(QSF, "function qsfSideFolds(")
    assert 'el.dataset.fold = "side-" + k;' in side and 'el.open = qsfFoldOpen("side-" + k, false);' in side
    head = media(CSS, "wsright (min-width: 1px)", "@container {} {{")
    assert "#qsfdetail > .panel > h2 { position: sticky; top: 0;" in head and "background: var(--panel);" in head
    short = media(CSS, "wsright (max-width: 520px)", "@container {} {{")
    assert "table.tbl-stack > tbody > tr { display: block;" in short and "td[data-l]::before { content: attr(data-l);" in short
    card = body(QSF, "function qsfCard(")
    assert '<table class="tbl-stack"><thead><tr><th class="l">요인</th>' in card
    for lab in ('data-l="배점"', 'data-l="기여"', 'data-l="근거"'):
        assert lab in card, lab
    assert FC.count('class="fc-table tbl-stack"') == 3
    for lab in ('data-l="50% 범위"', 'data-l="80% 범위"', 'data-l="시세 대비"', 'data-l="${hs[i]}거래일 안에"', 'data-l="같은 묶음의 과거 실제"'):
        assert lab in FC, lab
    got = node(r"""
const store = { "qse-fold-side-basis": "1" };
const localStorage = { getItem: (k) => (k in store ? store[k] : null) };
const QSF_FOLD_KEY = "qse-fold-";
""" + body(QSF, "function qsfFoldOpen(") + line(QSF, "const QSF_SIDE_FOLDS") + body(QSF, "function qsfSideFolds(") + r"""
const els = ["basis", "plan-held", "range", "fcast"].map((k) => ({ dataset: { fold: k }, open: true }));
qsfSideFolds({ querySelectorAll: () => els });
console.log(JSON.stringify(els.map((e) => [e.dataset.fold, e.open])));""")
    assert got == [["side-basis", True], ["side-plan-held", False], ["side-range", False], ["fcast", True]]


# ---------------------------------------------------------------- C8. one line above the ranking, the rest in 읽는 법 (owner decision)
def test_one_caveat_line_stays_above_the_ranking_and_the_rest_is_folded():
    rank = body(QSF, "async function qsfRank(")
    top = rank[rank.index("box.innerHTML = `<div class=\"panel\"><h2>${QSF_STRAT"):rank.index('<div class="tbl-wrap"><table class="qsf-rank-tbl">')]
    assert '<div class="meta qr-caveat">점수순으로 보여 줄 뿐 수익이 더 좋다는 근거는 아닙니다.</div>' in top
    assert top.count('<div class="meta') == 1                                                   # the only visible explanation line
    assert '<details class="qr-how" data-fold="rankhow"${qsfFoldOpen("rankhow", false) ? " open" : ""}><summary>읽는 법' in top
    start = rank.index("const how = `")
    how = rank[start:rank.index("box.innerHTML = `", start)]
    for kept in ("'상위 3'은", "d.stance.label", "QSF_RISK_NOTE", "QSF_FILING_NOTE", "QSF_DEAL_NOTE", "${commonLine}"):
        assert kept in how, kept
    dock = body(QSF, "function qsfDockStrip(")
    assert "right.appendChild(strip); strip.open = false;" in dock
    assert 'strip.parentNode.classList.contains("ws-right")) strip.open = false;' in body(QSF, "function qsfCardShown(")


# ---------------------------------------------------------------- C5. the screener's area scores in one column below 900 px
def test_the_screener_folds_its_four_area_columns_into_one_below_900px():
    narrow = media(CSS, "wsmain (max-width: 899px)", "@container {} {{")
    assert ".qs-table .qs-dcol { display: none; }" in narrow and ".qs-table .qs-dmini { display: table-cell;" in narrow
    assert ".qs-table .qs-dmini { display: none; }" in CSS
    run = body(QSF, "async function qsfScreenRun(")
    assert "${qsfDomMini(r.domains)}" in run and '<td class="num qs-dcol">' in run and '<th class="qs-dmini"' in run
    got = node("const isNum = (v) => typeof v === 'number' && isFinite(v);\n" + line(QSF, "const QSF_SCREEN_DOMAIN")
               + 'const QSF_DOMAIN_NAME = { TECHNICAL: "기술", FUNDAMENTAL: "재무", RISK: "위험 관리", EVENTS: "이벤트" };\n'
               + body(QSF, "function qsfDomMini(") + """
console.log(JSON.stringify(qsfDomMini({ TECHNICAL: 54, FUNDAMENTAL: 61.4, RISK: null })));""")
    assert 'title="기술 54 · 재무 61 · 위험 관리 없음 · 이벤트 없음"' in got
    assert got.count('<i class="none"></i>') == 2 and 'style="height:54%"' in got     # a missing area is an outline, not a zero bar


# ---------------------------------------------------------------- C4. two columns: the lower line sits in the main column
def test_two_columns_put_the_lower_line_under_main_and_the_right_column_beside_both():
    split = media(CSS, "content (min-width: 1120px)", "@container {} {{")
    assert "grid-template-columns: minmax(0, 1fr) var(--ws-right); grid-template-rows: auto auto 1fr;" in split
    assert "> .ws-body { display: contents; }" in split
    assert "grid-column: 2; grid-row: 2 / span 2;" in split and "> .ws-lower { grid-column: 1; grid-row: 3; }" in split
    assert "position: sticky; top: calc(var(--sticky-top, 0px) + var(--gutter));" in split
    assert "Math.min(640, Math.max(420, window.innerHeight - 380))" in body(APP, "function drawPrice(")


# ---------------------------------------------------------------- C6. Today candidates in a narrow column
def test_today_candidates_show_the_chip_alone_and_wrap_their_reasons_when_narrow():
    cands = body(ASST, "function asstCands(c, note) {")
    assert 'title="${esc(tickerText(r.ticker, r.name || ""))}"' in cands and '<span class="meta m0 an-sub">' in cands
    narrow = media(CSS, "acand (max-width: 440px)", "@container {} {{")
    assert ".asst-cand .an-sub { display: none; }" in narrow and ".asst-cand td.aw { white-space: normal;" in narrow
    assert ".asst-cand { container: acand / inline-size; }" in CSS


# ---------------------------------------------------------------- D. polish
def test_whole_korean_words_and_a_menu_that_keeps_the_current_tab_in_view():
    assert ".nw { white-space: nowrap; }" in CSS and "body { word-break: keep-all; overflow-wrap: break-word; }" in CSS
    rail = media(CSS, "min-width: 1024px")
    assert 'html[data-nav="rail"] .nav-h { position: absolute; width: 1px;' in rail              # still read by screen readers
    assert 'if (onBtn && navWide() && onBtn.offsetParent) onBtn.scrollIntoView({ block: "nearest" });' in body(APP, "function show(tab")
    assert re.search(r"if \(r\.unit === \"ratio\"\).*<span class=\"num\">", body(APP, "function renderFund("))    # a margin is a level, not a move
    assert '<h2>연구실 <span class="meta m0">' in LAB and '<h2>모델 <span class="tech-id"' in APP
