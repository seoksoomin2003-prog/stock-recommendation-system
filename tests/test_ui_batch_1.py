"""UI/UX audit 2026-11-23, first batch (reports/ui_ux_assessment_2026_11_23/UI_UX_REMEDIATION_ROADMAP.md P0-1..3, P1-1..6) with the
user's decisions of the same day: colour rule C (Korean screens red up / blue down), every proposed wording change, whole scores with
a mark near a band edge, and a market-state clause on the Today first line.  Display only: nothing here scores or records."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from terminal import assistant as A
from terminal.qsf import config as cfg
from terminal.qsf import rank_notes as RN
from terminal.services import Terminal

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "terminal" / "static"
APP = (STATIC / "app.js").read_text(encoding="utf-8")
QSF = (STATIC / "qsf.js").read_text(encoding="utf-8")
CSS = (STATIC / "style.css").read_text(encoding="utf-8")


def body(src, start, end="\n}\n"):
    i = src.index(start)
    return src[i:src.index(end, i) + len(end)]


def node(js):
    if not shutil.which("node"):
        pytest.skip("node is not installed")
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


# ---------------------------------------------------------------- P0-1 an open outside the bar's range draws no body
def test_an_open_outside_the_bar_is_not_trusted():
    js = "const isNum = (v) => typeof v === 'number' && isFinite(v);\n" + body(APP, "function goodOpen(") + """
console.log(JSON.stringify([goodOpen({open: 0, low: 171500, high: 178500}), goodOpen({open: 175000, low: 171500, high: 178500}),
  goodOpen({open: 180000, low: 171500, high: 178500}), goodOpen({open: null, low: 1, high: 2}), goodOpen({open: 5})]));"""
    assert node(js) == [False, True, False, False, True]


def test_both_price_charts_skip_the_body_and_say_so():
    draw = body(APP, "function drawPrice(") if "function drawPrice(" in APP else APP
    assert "if (okOpen) ctx.fillRect(" in draw and "없음(원자료 이상)" in APP and "tickLabel(v, nt.digits), pw + 6" in APP
    chart = (STATIC / "chart.js").read_text(encoding="utf-8")
    assert "const okOpen = goodOpen(b)" in chart and "if (!okOpen) {" in chart


# ---------------------------------------------------------------- P0-2 the dividend yield the committee rejects
def test_a_dividend_yield_above_the_committee_limit_is_marked_not_dropped():
    from terminal.committee.figures import MAX_DIVIDEND_YIELD
    raw = {"dividendYield": 10.05, "trailingPE": 12.0}
    got = Terminal._dividend_check(raw)
    assert got == {**raw, "dividendYieldSuspect": True, "dividendYieldLimit": MAX_DIVIDEND_YIELD} and "dividendYieldSuspect" not in raw
    for fine in ({"dividendYield": 0.32}, {"dividendYield": MAX_DIVIDEND_YIELD}, {}, {"dividendYield": None}):
        assert Terminal._dividend_check(fine) is fine
    assert Terminal._dividend_check({"dividendYield": -1.0})["dividendYieldSuspect"] is True
    line = next(x for x in APP.splitlines() if '["배당수익률"' in x)
    assert "p.dividendYieldSuspect" in line and "원자료 이상" in line and "p.dividendYieldLimit" in line and "8%" not in line


# ---------------------------------------------------------------- P0-3 an index tile says which change is which
def test_an_index_tile_labels_both_changes():
    card = body(APP, "function card(i) {")
    assert '1일</span> ${chg(i.change_pct)}' in card and '1개월</span> ${chg(i.change_1m_pct, 1)}' in card
    assert ".card .chg .nw { display: block; white-space: nowrap; }" in CSS


# ---------------------------------------------------------------- colour rule C and the accent contrast
def _tokens(block):
    return dict(re.findall(r"(--[\w-]+):\s*(#[0-9a-fA-F]{6})", block))


def _contrast(a, b):
    def lum(h):
        c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        c = [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
        return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
    x, y = sorted((lum(a), lum(b)), reverse=True)
    return (x + 0.05) / (y + 0.05)


def test_price_colours_follow_the_market_and_status_green_does_not():
    light = _tokens(CSS[:CSS.index(':root[data-theme="dark"]')])
    dark = _tokens(CSS[CSS.index(':root[data-theme="dark"]'):CSS.index("* { box-sizing")])
    for t in (light, dark):
        assert {"--up-intl", "--down-intl", "--up-kr", "--down-kr", "--ok", "--on-accent"} <= set(t) and "--up" not in t
        assert t["--ok"] == t["--up-intl"]
        for k in ("--up-kr", "--down-kr"):
            assert _contrast(t[k], t["--panel"]) >= 4.5, k
    assert light["--up-kr"] == "#c22f35" and light["--down-kr"] == "#1f5fd1" and dark["--down-kr"] == "#5b9cff"
    assert ':root { --up: var(--up-intl); --down: var(--down-intl); }' in CSS and ':root[data-color="kr"] { --up: var(--up-kr); --down: var(--down-kr); }' in CSS
    assert ".badge.REAL { color: var(--muted); }" in CSS and ".msg.ok { color: var(--ok); }" in CSS


def test_the_rule_is_set_before_a_tab_draws_and_the_account_keeps_the_international_pair():
    rule = body(APP, "function paintColorRule() {")
    js = """const state = { market: "KR", tab: "today" }; const ds = {}; const document = { documentElement: { dataset: ds } };
const INTL_COLOR_TABS = new Set(["account"]);
""" + rule + """
const seen = []; paintColorRule(); seen.push(ds.color || null); state.tab = "account"; paintColorRule(); seen.push(ds.color || null);
state.tab = "today"; state.market = "US"; paintColorRule(); seen.push(ds.color || null); console.log(JSON.stringify(seen));"""
    assert node(js) == ["kr", None, None]
    assert 'const INTL_COLOR_TABS = new Set(["account"]);' in APP
    show = body(APP, "function show(tab, push = true) {")
    assert show.index("paintColorRule();") < show.index("RENDER[tab]()") and "paintColorRule();" in body(APP, "function paintMarket() {")


def test_text_on_the_accent_passes_and_a_selected_segment_is_a_neutral_inversion():
    light = _tokens(CSS[:CSS.index(':root[data-theme="dark"]')])
    dark = _tokens(CSS[CSS.index(':root[data-theme="dark"]'):CSS.index("* { box-sizing")])
    assert _contrast(dark["--on-accent"], dark["--accent"]) >= 4.5 and _contrast(light["--on-accent"], light["--accent"]) >= 4.5
    for sel in (".search button {", ".btn-primary {", ".g-A {"):
        rule = CSS[CSS.index(sel):CSS.index("}", CSS.index(sel))]
        assert "color: var(--on-accent)" in rule and "#fff" not in rule
    assert ".seg button.on { background: var(--ink); color: var(--panel);" in CSS
    assert _contrast(dark["--ink"], dark["--panel"]) >= 7 and _contrast(light["--ink"], light["--panel"]) >= 7


# ---------------------------------------------------------------- P1-1 no certification words on unvalidated outputs
def test_unvalidated_outputs_carry_no_approval_words():
    committee = (STATIC / "committee.js").read_text(encoding="utf-8")
    forecast = (STATIC / "forecast.js").read_text(encoding="utf-8")
    assert "신뢰 ${icNum" not in committee and "<th>신뢰</th>" not in committee and "기대수익률:" not in committee
    assert "규칙 엔진</span>" in committee and "실존 투자자의 의견이 아닙니다 ·" in committee and "color:var(--up)" not in committee
    assert "과거 점검 통과</span>" not in forecast and forecast.count("방향 근거 없음</span>") == 2
    assert "정상 추천" not in APP and "<h3>추천 상위 종목</h3>" not in APP and "모델 알파(순위용)" in APP
    from terminal.committee import council
    assert council.SCORE_KO["confidence"] == "자료·일치"


# ---------------------------------------------------------------- P1-2 the QSF risk domain is named for its direction
def test_the_risk_domain_says_higher_is_better():
    assert 'RISK: "위험 관리"' in QSF and '["risk", "위험 관리"]' in QSF and "높을수록 위험이 낮고" in QSF
    assert '${k === "RISK" ? " · 높을수록 좋음" : ""}' in QSF and "/ 100, 높을수록 위험)" in QSF


# ---------------------------------------------------------------- P1-3 the Today first line on an adverse day
@pytest.mark.parametrize("state, want", [
    ({"state": "ADVERSE", "score_100": 15.2, "size_factor": 0.5}, " 시장 상태 나쁨(15/100) — 새 주문 크기 절반 규칙 적용 중."),
    ({"state": "ADVERSE", "score_100": 25.0, "size_factor": 1.0}, " 시장 상태 나쁨(25/100)."),
    ({"state": "UNKNOWN", "score_100": None, "size_factor": 0.5}, " 시장 상태를 읽을 수 없음 — 새 주문 크기 절반으로 계산 중."),
    ({"state": "UNKNOWN", "score_100": None, "size_factor": 1.0}, ""),
    ({"state": "NORMAL", "score_100": 61.0, "size_factor": 1.0}, ""),
    (None, ""),
])
def test_the_first_line_names_an_adverse_day(state, want):
    assert A.market_clause(state) == want


def test_the_limits_sentence_sits_under_the_candidates_title():
    asst = (STATIC / "assistant.js").read_text(encoding="utf-8")
    cands = body(asst, "function asstCands(c, note) {")
    assert cands.index('<div class="notice">${esc(note)}</div>') < cands.index('<div class="asst-cands">')


# ---------------------------------------------------------------- P1-4 long-term entry is named as the score tab names it
def test_today_names_long_term_entry_as_the_score_tab_does():
    asst = (STATIC / "assistant.js").read_text(encoding="utf-8")
    assert 'k === "LONG_TERM" ? "진입을 막는 조건 없음" : "지금 진입 가능"' in body(asst, "function asstCands(c, note) {")
    assert "장기는 '진입을 막는 조건 없음'" in A.candidates([], {})["note"]


# ---------------------------------------------------------------- P1-6 whole scores and the edge mark
def test_band_edges_come_from_the_engine_settings():
    assert RN.band_edges() == sorted({b[0] for b in cfg.BANDS if b[0] > 0}, reverse=True) == [80.0, 70.0, 55.0, 40.0]   # not the exit line 67
    assert A.candidates([], {})["band_edges"] == RN.band_edges()


def test_whole_scores_and_the_edge_mark():
    js = "const isNum = (v) => typeof v === 'number' && isFinite(v);\n" + body(QSF, "function qsfInt(v) {", "\n") + body(QSF, "function qsfNear(") + """
const E = [80, 70, 55, 40];
console.log(JSON.stringify([qsfInt(69.8), qsfInt(70.2), qsfNear(69.8, E) !== "", qsfNear(70.9, E) !== "", qsfNear(75, E), qsfNear(62, E), qsfNear(69.8, null)]));"""
    assert node(js) == ["70", "70", True, True, "", "", ""]
    row = body(QSF, "function qsfRankRow(")
    assert "<b>${qsfInt(r.score)}</b>${qsfNear(r.score, edges)}" in row and "notes && notes.band_edges, common)" in QSF
    assert 'v >= 1 ? "up" : v <= -1 ? "down" : "flat"' in body(QSF, "function qsfDelta(") and "점수 변화(전일)</th>" in QSF
    assert "[80" not in QSF and "70, 67" not in QSF          # the edges are not kept in the page


# ---------------------------------------------------------------- light theme check (2026-11-23): small coloured text passes on the chip too
def test_light_theme_green_and_amber_pass_on_the_chip_and_kr_moves_the_50_day_line_off_blue():
    light = _tokens(CSS[:CSS.index(':root[data-theme="dark"]')])
    for k in ("--up-intl", "--ok", "--down-intl", "--up-kr", "--down-kr", "--warn"):
        assert _contrast(light[k], light["--chip"]) >= 4.5 and _contrast(light[k], light["--panel"]) >= 4.5, k
    assert ':root[data-color="kr"] { --sma50: var(--ma60); }' in CSS
