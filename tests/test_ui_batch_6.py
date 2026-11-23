"""UI/UX audit 2026-11-23, sixth batch: workflow (reports/ui_ux_assessment_2026_11_23/UI_UX_REMEDIATION_ROADMAP.md P1-13, P2-8, P2-15,
P2-16, P2-18, P2-20, P2-25, P3-7, P3-9) with the user's decisions of 2026-11-24: judgements purple and grey, states neutral, prices keep
their colours; names that do not repeat ('가상' for what the program records itself); a factor shared by most rows moves above the
table; a colour-safe heatmap choice.  Also the user's request of the same day: the stance buttons stay in plain sight.
Display only: no score, band edge, stance value or record changes."""
import json
import re
from pathlib import Path

from tests.test_ui_batch_1 import body, node

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "terminal" / "static"
JS = {p.name: p.read_text(encoding="utf-8") for p in STATIC.glob("*.js")}
APP, QSF, ASST, CO, PF, AC, MAP, CMP, FC, CMD = (JS[n] for n in ("app.js", "qsf.js", "assistant.js", "committee.js", "portfolio.js", "account.js",
                                                                "map.js", "compare.js", "forecast.js", "command.js"))
CSS = (STATIC / "style.css").read_text(encoding="utf-8")
HTML = (STATIC / "index.html").read_text(encoding="utf-8")


# ---------------------------------------------------------------- user request: the stance is chosen without opening anything
def test_the_stance_buttons_sit_in_the_view_row_not_inside_the_folded_strip():
    tpl = body(QSF, "async function renderQsf(")
    nav = tpl[tpl.index('<div class="qsf-nav">'):tpl.index("</div>", tpl.index('<div class="qsf-nav">'))]
    strip = tpl[tpl.index('<details class="qsf-strip"'):tpl.index("</details>")]
    assert 'id="qsfstanceseg"' in nav and 'aria-label="성향"' in nav and "qsfstanceseg" not in strip
    draw = body(QSF, "async function qsfStanceDraw(")
    assert '$("#qsfstanceseg")' in draw and "data-level" in draw and "title=" in draw
    # the folded box keeps the explanation only: no second set of buttons
    box = draw[draw.index("box.innerHTML"):]
    assert "data-level" not in box[:box.index("`;")]
    assert '(seg || box).querySelectorAll("button[data-level]")' in draw


# ---------------------------------------------------------------- P2-8 one meaning per colour
def test_judgements_have_their_own_colours_and_states_are_neutral():
    # dark hold grey of 2026-11-24 (DESIGN_SYSTEM_SPECIFICATION.md section 2: #64748b fell under 3:1 on the selected row)
    for theme, buy, hold in ((":root {", "#6d28d9", "#64748b"), (':root[data-theme="dark"]', "#a78bfa", "#7d8da6")):
        block = CSS[CSS.index(theme):CSS.index("}", CSS.index(theme))]
        assert f"--judge-buy: {buy};" in block and f"--judge-hold: {hold};" in block
    assert ".act-buy { --act: var(--judge-buy); }" in CSS and ".act-sell { --act: var(--warn); }" in CSS
    assert "#16A34A" not in CSS and "#DC2626" not in CSS
    assert ".qsf-bar i { display: block; height: 100%; background: var(--muted); }" in CSS
    assert ".badge.REAL { color: var(--muted); }" in CSS and ".alerts li.info { border-left-color: var(--muted); }" in CSS
    rec = [l for l in CO.splitlines() if l.startswith("const IC_REC_COLOR")][0]
    assert "--up" not in rec and "--bad" not in rec and '"var(--judge-buy)"' in rec


def test_neutral_tiles_show_a_sign_and_no_colour():
    got = node("""const isNum = (v) => typeof v === "number" && isFinite(v); const DASH = "-";
""" + [l for l in APP.splitlines() if l.startswith("const NEUTRAL_TILE")][0] + "\n" + [l for l in APP.splitlines() if l.startswith("function pctPlain")][0] + """
console.log(JSON.stringify([NEUTRAL_TILE.test("^VIX"), NEUTRAL_TILE.test("^TNX"), NEUTRAL_TILE.test("DX-Y.NYB"), NEUTRAL_TILE.test("KRW=X"),
  NEUTRAL_TILE.test("^GSPC"), NEUTRAL_TILE.test("^KS11"), pctPlain(1.234), pctPlain(-0.5), pctPlain(null)]));""")
    assert got[:6] == [True, True, True, True, False, False]
    assert got[6] == '<span class="flat num">+1.23%</span>' and got[7] == '<span class="flat num">-0.50%</span>' and got[8] == "-"
    assert 'cv.hasAttribute("data-plain") ? "--ink"' in APP


# ---------------------------------------------------------------- P2-15 names that do not repeat
def test_tab_and_view_names():
    assert '<button data-tab="account" data-group="account">통합 계좌</button>' in HTML
    assert '<button data-tab="qsf" data-group="score">순위·카드</button>' in HTML and '<button data-tab="stock" data-group="stock">종목 정보</button>' in HTML
    assert 'exec: "주문 계획·가상 장부", track: "판정 일정"' in QSF and 'perf: "가상 성과"' in CO
    for name, src in list(JS.items()) + [(p.name, p.read_text(encoding="utf-8")) for p in (ROOT / "terminal").rglob("*.py")]:
        for old in ("모의 장부", "모의 포트폴리오", "모의 체결", "모의 성과", "점수 탭", "추적·검증"):
            assert old not in src, (name, old)
    # the hand-kept paper trades keep their name
    assert "모의 매매 기록" in JS["paper.js"]


def test_the_code_opens_the_stock_screen_and_the_score_opens_the_card():
    row = body(QSF, "function qsfRankRow(")
    assert 'class="linkish" data-ticker="${esc(r.ticker)}"' in row
    assert 'tr.onclick = (e) => { if (!e.target.closest("a, button")) toggle(tr); };' in QSF       # the name click does not also fold the row
    for start in ("function qsfChangeRow(", "async function qsfScreenRun("):
        src = body(QSF, start)
        assert 'class="linkish" data-ticker=' in src and 'class="qs-open num" data-t=' in src
    assert "`${code} 점수 카드`" in CMD and "qsfOpenCard(code)" in CMD


# ---------------------------------------------------------------- P2-25 a factor most rows share moves above the table
def test_a_common_factor_moves_above_the_table_and_rows_show_the_next_one():
    src = body(QSF, "function qsfReason(") + body(QSF, "function qsfCommonPush(")
    rows = [{"plus": {"label": "추세", "points": 5}, "plus_more": [{"label": "수익성", "points": 2}], "minus": {"label": "가치", "points": -3}, "minus_more": []}
            for _ in range(5)] + [{"plus": {"label": "수익성", "points": 4}, "plus_more": [], "minus": {"label": "부채", "points": -1}, "minus_more": []}]
    got = node("""const esc = (s) => String(s); const DASH = "-";
""" + src + f"""const rows = {json.dumps(rows)}; const c = qsfCommonPush(rows);
console.log(JSON.stringify([c, qsfReason(rows[0], c), qsfReason(rows[5], c), qsfCommonPush(rows.slice(0, 4))]));""")
    c, first, last, few = got
    assert c["plus"] == "추세" and c["plusN"] == 5 and c["minus"] == "가치" and c["rows"] == 6   # 가치 is 5 of 6 too: 83% -> also common
    assert "수익성" in first and "추세" not in first
    assert "수익성" in last and "부채" in last and few["plus"] is None                                             # fewer than five rows: nothing moves


def test_the_short_line_carries_the_next_factors():
    from terminal.qsf import rank_notes as RN
    b = {"plus": [{"label": a, "points": p} for a, p in (("a", 3.04), ("b", 2), ("c", 1), ("d", 0.5))], "minus": [{"label": "z", "points": -1}]}
    s = RN.short(b)
    assert s["plus"] == {"label": "a", "points": 3.0} and [x["label"] for x in s["plus_more"]] == ["b", "c"] and s["minus_more"] == []


# ---------------------------------------------------------------- P2-16 one trade form
def test_one_trade_form_in_the_unified_account():
    assert "function formHtml(" not in PF and "function bindForm(" not in PF and "let prefill" not in PF
    assert '$("#jgo").onclick = () => acctRecord(mk);' in PF and "acctRecord(marketOf(d.ticker), {" in PF
    rec = body(AC, "function acctRecord(")
    assert 'show("account")' in rec and "scroll: true" in rec
    form = body(AC, "function acctFormHtml(")
    assert "fill = f.fill || {}" in form and 'fill.style === k ? " selected"' in form


# ---------------------------------------------------------------- P1-13 from the card to the plan row and the size calculator
def test_the_card_leads_to_the_plan_row_and_the_size_calculator():
    go = body(QSF, "function qsfCardGo(")
    assert 'e.status === "ENTRY_NOW"' in go and "qsf-toplan" in go and "qsf-tosize" in go and 'c.strategy === "SWING" && isNum(h.stop)' in go
    assert '<tr data-plan="${esc(o.ticker)}">' in QSF and "qsfPlanFocus();" in body(QSF, "async function qsfPlan(")
    focus = body(QSF, "function qsfPlanFocus(")
    assert 'classList.add("hl")' in focus and "notify(" in focus
    assert "if (state.sizeFill) {" in PF and "f.requestSubmit()" in PF
    assert "acctRecord('" in QSF            # the no-account plan offers the account form


# ---------------------------------------------------------------- P2-18 deep links, remembered style, the view in the address
def test_deep_links_and_the_view_in_the_address():
    assert 'ORDERS_MORE: "exec"' in ASST and 'NEW_VERDICT: "track"' in ASST and 'IC_INTERRUPT: "ports"' in ASST
    assert "asstGo(go.dataset.tab, go.dataset.ticker, go.dataset.view)" in ASST
    assert 'localStorage.setItem("qse-qsf-strategy", s)' in QSF and 'localStorage.getItem("qse-qsf-strategy")' in QSF
    th = body(APP, "function tabHash(")
    got = node("""const state = { tab: "qsf", card: null, market: "US", ticker: null }; const marketOf = () => "US"; const qsfState = { view: "exec" };
""" + th + """const out = [tabHash("qsf")]; qsfState.view = "rank"; out.push(tabHash("qsf")); state.card = "AAPL"; out.push(tabHash("qsf"));
console.log(JSON.stringify(out));""")
    assert got == ["qsf:exec", "qsf", "qsf/AAPL"]
    assert '[tab, view] = head.split(":")' in body(APP, "function fromHash(")
    assert "history.pushState" in body(QSF, "function qsfSetView(") and 'qsfSetView(b.dataset.v, true)' in QSF
    assert 'qsfState.view = "rank";' in body(QSF, "function qsfOpenCard(")


# ---------------------------------------------------------------- P2-20 Today items as one line; committee status as numbers
def test_today_items_fold_after_the_first_sentence():
    got = node(body(ASST, "function asstFirst(") + """console.log(JSON.stringify([asstFirst("첫 문장입니다. 둘째 문장."), asstFirst("마침표 없음"), asstFirst("1.5% 올랐습니다. 다음"),
  asstFirst("Apple Inc. 72점. 다음")]));""")
    assert got == ["첫 문장입니다.", "마침표 없음", "1.5% 올랐습니다.", "Apple Inc. 72점."]
    item = body(ASST, "function asstItem(")
    assert '<details class="asst-more"><summary>${esc(first)}</summary>' in item and 'class="asst-act"' in item
    assert ".asst-item { border-left-width: 4px; }" in CSS
    dash = CO[CO.index("위원회 현황 <span"):]
    assert dash.index('class="ic-stats"') < dash.index('<details class="ic-more">') < dash.index("자주 나온 위험")


# ---------------------------------------------------------------- P3-7 heatmap colour choice; the unused toggle is dimmed
def test_heatmap_colour_choice_and_idle_toggle():
    assert 'palette: v.palette === "cb" ? "cb" : "std"' in MAP and 'id="heat-pal"' in MAP and 'pick("#heat-pal", "palette")' in MAP
    assert "palette: heat.palette" in MAP and "heatSide(v >= 0, dark)" in MAP
    idle = body(MAP, "function heatIdle(")
    assert 'st.classList.toggle("idle", !score)' in idle and ".seg.idle { opacity: 0.5; }" in CSS
    # the colour-safe pair is blue and orange, and both read against the panel
    from tests.test_ui_batch_1 import _contrast
    assert _contrast("#1f5fd1", "#ffffff") >= 3 and _contrast("#b35900", "#ffffff") >= 3


# ---------------------------------------------------------------- P3-9 compare labels stay inside; FC-1 axis has middle ticks
def test_compare_labels_stay_inside_and_the_range_axis_has_five_ticks():
    assert "const floor = h - 28;" in CMP and "Math.min(ends[i].yy" in CMP
    axis = FC[FC.index('<div class="fc-axis">'):FC.index("</d", FC.index('<div class="fc-axis">'))]
    assert axis.count("<span>") == 5 and "기준 종가 0%" in axis
