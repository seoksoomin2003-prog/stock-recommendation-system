"""UI/UX audit 2026-11-23, fourth batch (reports/ui_ux_assessment_2026_11_23/UI_UX_REMEDIATION_ROADMAP.md P2-5, P2-6, P2-7, P2-10,
P2-14, P2-17, P2-19, P2-24, P3-1, P3-2, P3-3, P3-5, P3-10, P3-11) with the user's decisions of the same day: Korean units kept in one
format, one time format (2026-11-23 12:23), Korean names first on every Korean screen, internal names small and grey.  Display only."""
import re
from pathlib import Path

from tests.test_ui_batch_1 import body, node
from tests.test_ui_batch_2 import media

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "terminal" / "static"
APP = (STATIC / "app.js").read_text(encoding="utf-8")
QSF = (STATIC / "qsf.js").read_text(encoding="utf-8")
CSS = (STATIC / "style.css").read_text(encoding="utf-8")
HTML = (STATIC / "index.html").read_text(encoding="utf-8")
JS = {p.name: p.read_text(encoding="utf-8") for p in STATIC.glob("*.js")}
PRELUDE = """const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const isNum = (v) => typeof v === "number" && isFinite(v);
const DASH = '<span class="missing">—</span>';
const KR_RE = /^[0-9][0-9A-Z]{5}$/;
const marketOf = (t) => (KR_RE.test(String(t).toUpperCase()) ? "KR" : "US");
"""


def helpers(*names):
    return PRELUDE + "".join(body(APP, n) if n.startswith("function") else APP[APP.index(n):APP.index("\n", APP.index(n)) + 1] for n in names)


# ---------------------------------------------------------------- P2-5 big amounts: Korean units, one format
def test_big_amounts_keep_korean_units_with_separators():
    got = node(helpers("function big(", "function bigInText(") + """
console.log(JSON.stringify([big(1.1246e15, "KRW"), big(3.52e12, "USD"), big(8.35e11, "KRW"), big(1.724e10, "USD"), big(12345, ""), big(null),
  bigInText("20일 평균 거래대금 17,237,663,755달러"), bigInText("기준 1,234원, 평균 52,000,000,000원")]));""")
    assert got[:4] == ["₩1,124.6조", "$3.52조", "₩8,350억", "$172.4억"] and got[4] == "1.2만" and got[5] == '<span class="missing">—</span>'
    assert got[6] == "20일 평균 거래대금 $172.4억" and got[7] == "기준 1,234원, 평균 ₩520.0억"                          # under 1억 stays as written
    assert "${bigInText(esc(x.text))}" in QSF and "${bigInText(esc(f.explanation || f.reason || \"\"))}" in QSF


def test_every_missing_value_is_the_same_dash():
    for name, src in JS.items():
        assert 'class="missing">없음</span>' not in src, name
    committee = JS["committee.js"]
    assert '? DASH : Number(v).toLocaleString("ko-KR"' in committee and '? DASH : (v * 100).toFixed(d) + "%"' in committee and '"–"' not in committee
    assert "%</span>` : DASH);" in JS["sectorpicks.js"]


# ---------------------------------------------------------------- P3-11 one time format
def test_times_read_the_same_everywhere():
    got = node(helpers("function stamp(", "function when(") + """
console.log(JSON.stringify([stamp(new Date(2026, 10, 23, 9, 5)), when(new Date(2026, 0, 2, 14, 30).toISOString()), stamp("nonsense"), when(null)]));""")
    assert got == ["2026-11-23 09:05", "2026-01-02 14:30", "", "—"]
    assert "const alTime = (iso) => stamp(iso) || esc(iso);" in JS["alerts.js"] and "const coinWhen = (ms) => stamp(new Date(ms));" in JS["coin.js"]
    assert "const phoneWhen = (iso) => stamp(iso);" in JS["phone.js"] and 'dateStyle: "short"' not in APP


# ---------------------------------------------------------------- P2-10 Korean names first
def test_korean_stocks_lead_with_the_name():
    got = node(helpers("const nameFirst", "function tickerLabel(", "const tickerText") + """
console.log(JSON.stringify([tickerLabel("005930", "삼성전자"), tickerLabel("AAPL", "Apple"), tickerLabel("005930", ""), tickerText("005930", "삼성전자"),
  tickerText("AAPL", "Apple"), tickerLabel("000660", "SK하이닉스", ' class="pointer"')]));""")
    assert got[0] == '<b>삼성전자</b> <span class="meta m0">005930</span>' and got[1] == '<b>AAPL</b> <span class="meta m0">Apple</span>'
    assert got[2] == "<b>005930</b>" and got[3] == "삼성전자 005930" and got[4] == "AAPL Apple" and got[5].startswith('<b class="pointer">SK하이닉스</b>')
    assert QSF.count("${tickerLabel(r.ticker, r.name)}") == 2 and "${tickerLabel(m.ticker, m.name)}" in QSF and "tickerText(d.ticker" in QSF
    for name in ("account.js", "committee.js", "portfolio.js", "calendar.js"):
        assert "tickerLabel(" in JS[name], name
    assert "nameFirst(r.ticker, r.name) ? r.name : r.ticker" in JS["assistant.js"]


# ---------------------------------------------------------------- P2-6 axis ticks, P2-24 sparklines, P2-14 chart names
def test_axis_ticks_are_round_numbers_with_separators():
    got = node(PRELUDE + body(APP, "function niceTicks(") + APP[APP.index("const tickLabel"):APP.index("\n", APP.index("const tickLabel")) + 1] + """
const f = (a, b) => { const q = niceTicks(a, b); return q.ticks.map((v) => tickLabel(v, q.digits)).join(" "); };
console.log(JSON.stringify([f(54000, 386000), f(171.3, 236.8), f(0.812, 1.034), f(99.5, 101.2), f(5, 5)]));""")
    assert got[0] == "100,000 150,000 200,000 250,000 300,000 350,000" and got[1] == "180 190 200 210 220 230"
    assert got[2] == "0.85 0.90 0.95 1.00" and got[3].startswith("99.50 99.75 100.00") and got[4] == ""
    # workstation stage 6: the price ticks are right-aligned at the canvas edge (the digits line up); chaGrid does the same inside
    assert "tickLabel(v, nt.digits), w - 4, yy)" in APP and 'ctx.textAlign = "right"' in body(JS["chart.js"], "function chaGrid(") and "chaGrid(P.ctx, pw, lo, hi, py, grid, muted, (v) => tickLabel(v, nt.digits), 4, nt.ticks);" in JS["chart.js"]


def test_charts_have_names_and_sparklines_a_start_line():
    setup = body(APP, "function setupCanvas(")
    assert 'cv.setAttribute("role", "img")' in setup and 'cv.getAttribute("aria-hidden") !== "true"' in setup
    sp = body(APP, "function spark(")
    # stage 2 (visualization spec section 8 items 18-19): the start line is a faint solid line (a dashed one reads as a threshold),
    # and a missing day is a gap in the line, not a day taken out of the time axis
    assert sp.index('cv.setAttribute("aria-hidden", "true")') < sp.index("setupCanvas(") and "setLineDash" not in sp
    assert "line(ctx, all, (i) => (i / (all.length - 1)) * w" in sp and "all = vals || []" in sp
    assert 'cv.setAttribute("aria-label", `${tickerText(state.ticker' in body(APP, "function drawPrice(")
    assert "${sparkRange(i.spark)}" in body(APP, "function card(") and "그래프 폭" in body(APP, "function sparkRange(")


# ---------------------------------------------------------------- P2-7, P2-17, P2-19
def test_empty_ratio_columns_fold_into_one_line():
    peers = JS["peers.js"]
    assert "const cols = PEER_COLS.filter(([k]) => d.peers.some((r) => isNum(peerVal(r, k))))" in peers
    assert peers.count("${cols.map(") == 2 and "값이 하나도 없는 열" in peers and 'peerState.sort = "market_cap"' in peers


def test_no_screen_asks_for_a_terminal_command():
    for name, src in JS.items():
        assert "python app.py" not in src, name
    assert 'class="ghost collect-now">지금 수집</button>' in QSF and 'closest(".collect-now")' in APP


def test_internal_names_are_small_and_grey():
    card = body(QSF, "function qsfCard(")
    assert '<span class="tech-id" title="채점 규칙 이름입니다.' in card and '<span class="tech-id" title="점수 공식의 버전입니다.' in card
    assert '<span class="tech-id">실행 ID ${esc(b.run_id)}</span>' in APP and ".tech-id { font-size: var(--fs-xs); color: var(--muted);" in CSS


# ---------------------------------------------------------------- P3-1, P3-2, P3-3, P3-5, P3-10
def test_date_fields_say_which_calendar_they_use():
    assert '${f.market === "US" ? "(미국 기준)" : ""}<input name="date"' in JS["account.js"]
    assert '<label>날짜${isKR() ? "" : "(미국 기준)"}<input name="date"' in JS["paper.js"]


def test_messages_stay_inside_the_page_and_confirms_stay_for_records():
    for name, src in JS.items():
        assert not re.search(r"(?<![\w.])alert\(", src), name
    # workstation stage 2 (2026-11-24, owner decision U-6): the five confirmations (voiding records three times, phone off, basis
    # switch) stay, but in the page's own dialog; the browser's confirm window is gone
    assert not any(re.search(r"(?<![\w.])confirm\(", src) for src in JS.values())
    for name in ("account.js", "paper.js", "portfolio.js", "phone.js", "qsf.js"):
        assert JS[name].count("await uiConfirm(") == 1, name
    dlg = body(JS["ui.js"], "function uiConfirm(")
    assert 'role="alertdialog" aria-modal="true"' in dlg and 'e.key === "Escape"' in dlg and 'e.key === "Tab"' in dlg and "back.focus()" in dlg
    assert "document.body.appendChild(wrap)" in dlg and "ui.escape(message)" in dlg
    assert '<div id="toast" class="toast" role="status" aria-live="polite" hidden></div>' in HTML
    note = body(APP, "function notify(")
    assert 'el.setAttribute("role", tone === "err" ? "alert" : "status")' in note and "esc(text)" in note
    assert ".toast { bottom: 64px; }" in media(CSS, "max-width: 640px")


def test_segments_sticky_heads_and_the_company_description():
    assert ".seg button { white-space: nowrap; word-break: keep-all;" in CSS and ".seg { max-width: 100%; overflow-x: auto; }" in CSS
    wide = media(CSS, "min-width: 1024px")
    assert ".tbl-wrap:has(> .qsf-rank-tbl) { overflow: visible; }" in wide and "position: sticky; top: var(--sticky-top, 0px)" in wide
    assert '"--sticky-top", top + gh + "px"' in APP
    assert '<details class="co-sum" id="sum"><summary>회사 설명' in APP and 'lang="en"' in APP and 's.classList.toggle("open")' not in APP
