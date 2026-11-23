"""UI/UX audit 2026-11-23, second batch (reports/ui_ux_assessment_2026_11_23/UI_UX_REMEDIATION_ROADMAP.md P1-7..P1-10) with the
user's decisions of the same day: one status strip that opens, a card that closes and folds when the tab is entered from the menu,
tablets drop the four area columns, and the four rare risks become a short line under the name.  Display only: nothing here
scores, ranks or records."""
from pathlib import Path

from tests.test_ui_batch_1 import _contrast, _tokens, body, node

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "terminal" / "static"
QSF = (STATIC / "qsf.js").read_text(encoding="utf-8")
CSS = (STATIC / "style.css").read_text(encoding="utf-8")
ASST = (STATIC / "assistant.js").read_text(encoding="utf-8")
PRELUDE = """const isNum = (v) => typeof v === 'number' && isFinite(v);
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
"""


def media(css, query):
    """Every @media block with this query, joined."""
    head, out, i = f"@media ({query}) {{", [], 0
    while (i := css.find(head, i)) >= 0:
        depth, j = 0, css.index("{", i)
        for k in range(j, len(css)):
            depth += {"{": 1, "}": -1}.get(css[k], 0)
            if depth == 0:
                out.append(css[j:k + 1])
                break
        i = j
    assert out, query
    return "\n".join(out)


# ---------------------------------------------------------------- P1-8 one status strip
def test_the_score_tab_opens_with_one_strip_that_keeps_every_warning():
    head = body(QSF, "async function renderQsf(")
    strip = head[head.index('<details class="qsf-strip" id="qsfstrip">'):head.index('<div class="qsf-nav">')]
    line = strip.split("</summary>")[0]
    assert 'id="qsfstripstate"' in line and 'id="qsfstripstance"' in line and "점수 검증: 높은 점수의 수익 근거 아직 없음 · 참고용" in line
    opened = strip.split("</summary>")[1]
    for part in ('<div id="qsfstatefull">', '<div class="notice qsf-caveat">', '<div id="qsfrecord">', '<div id="qsfstance">'):
        assert part in opened, part                                    # the full text, the past record and the stance switch open from it
    assert "qsfStrip();" in head and "<h2>종목 점수 (QSF)</h2>" not in QSF
    rank_view = head[head.index('<div data-view="rank">'):head.index('<div id="qsfrank">')]
    assert '<form id="qsfform"' in rank_view                           # the ticker box sits in the ranking view now


def test_the_short_market_state_keeps_the_size_warning():
    js = PRELUDE + body(QSF, "function qsfStateShort(") + """
const bad = { status: "REAL", score_100: 15, state: "ADVERSE", label: "나쁨", size_factor: 0.5 };
const fine = { status: "REAL", score_100: 72, state: "FAVOURABLE", label: "좋음", size_factor: 1 };
const kr = { status: "REAL", score_100: 25, state: "ADVERSE", label: "나쁨", size_factor: 1 };
const unknown = { status: "REAL", score_100: null, state: "UNKNOWN", label: "읽을 수 없음", size_factor: 0.5 };
console.log(JSON.stringify([bad, fine, kr, unknown, null].map(qsfStateShort)));"""
    bad, fine, kr, unknown, none = node(js)
    assert "<b class=\"num\">15</b>/100" in bad and "나쁨" in bad and "새 주문 크기 50%" in bad and "risk-note" in bad
    assert "72" in fine and "새 주문 크기" not in fine and "risk-note" not in fine
    assert "25" in kr and "새 주문 크기" not in kr                     # Korea has no size brake (user decision 2026-11-16)
    assert "자료 없음" in unknown and "나쁜 날로 취급" in unknown and "새 주문 크기 50%" in unknown
    assert none == "시장 상태 읽지 못함"


def test_the_market_state_block_is_shown_once_and_plans_say_which_one_they_read():
    assert QSF.count("qsfMarketState(") == 2                           # the definition and the strip's full text
    assert "qsfMarketState(" not in body(QSF, "async function qsfRank(") and "/api/qsf/market-state" not in body(QSF, "async function qsfRank(")
    assert "qsfMarketState(" not in body(QSF, "function qsfDrawDetail(")
    plan = body(QSF, "function qsfPlanHtml(")
    assert plan.count("qsfPlanState(d.market_state)") == 2 and "${qsfPlanState(plan.market_state)}" in QSF
    js = PRELUDE + body(QSF, "function qsfStateShort(") + QSF[QSF.index("const qsfPlanState"):QSF.index("function qsfPlanHtml(")] + """
console.log(JSON.stringify([qsfPlanState({ score_100: 15, state: "ADVERSE", label: "나쁨", size_factor: 0.5, session: "2026-11-20" }), qsfPlanState(null)]));"""
    one, none = node(js)
    assert one.startswith('<div class="meta">이 계획이 읽은 시장 상태') and "새 주문 크기 50%" in one and "2026-11-20 기록" in one and none == ""


def test_the_strip_names_the_chosen_stance():
    draw = body(QSF, "async function qsfStanceDraw(")
    assert '$("#qsfstripstance")' in draw and "성향 <b>" in draw


# ---------------------------------------------------------------- P1-9 the open card closes, and folds when entered from the menu
def test_a_card_closes_to_one_line_and_reopens():
    detail = body(QSF, "function qsfDrawDetail(")
    assert 'class="ghost qsf-close"' in detail and '$("#qsfdetail .qsf-close").onclick = () => qsfFoldCard();' in detail and "qsfState.cardOpen = true;" in detail
    fold = body(QSF, "function qsfFoldCard(")
    assert "카드 다시 열기" in fold and 'history.replaceState(null, "", "#qsf")' in fold and "state.card = null;" in fold
    assert "qsfDrawDetail(d);" in fold and 'history.replaceState(null, "", "#" + tabHash("qsf"))' in fold     # reopening restores the address


def test_the_menu_folds_the_card_but_a_card_link_and_back_forward_do_not():
    opener = body(QSF, "function qsfOpenCard(")
    assert "qsfState.opening = true;" in opener and 'try { show("qsf", push); } finally { qsfState.opening = false; }' in opener
    back = body(QSF, "function qsfReturn(")
    assert back.index("qsfFoldCard()") < back.index("window.scrollTo(") and "!qsfState.opening &&" in back
    render = body(QSF, "async function renderQsf(")
    assert render.startswith("async function renderQsf(keep = false) {") and "else qsfFoldCard();" in render
    assert "keep && wasOpen" in render and QSF.count("renderQsf(true)") == 2          # a new scan and a stance change keep an open card


# ---------------------------------------------------------------- P1-10 judgement and entry at every width
def test_the_ranking_fits_by_width_without_losing_judgement_or_entry():
    assert ".qsf-rank-tbl .qd-col { display: none; }" in media(CSS, "max-width: 1279px")
    tablet = media(CSS, "max-width: 1023px")
    assert ".qsf-rank-tbl .qr-dcol { display: none; }" in tablet and ".qsf-rank-tbl .qr-md { display: block; }" in tablet
    phone = media(CSS, "max-width: 640px")
    assert ".qsf-rank-tbl .w, .qsf-rank-tbl .w2, .asst-cand .w { display: none; }" in phone
    assert ".qsf-rank-tbl .qr-m2, .asst-cand .qr-m2 { display: block;" in phone and "word-break: keep-all" in phone
    assert ".qsf-rank-tbl .w, .qsf-rank-tbl .w2" not in media(CSS, "max-width: 1023px")
    row = body(QSF, "function qsfRankRow(")
    assert '<div class="qr-m2">${qsfLabel(r)} ${entry}</div>' in row and '<td class="l w2">${entry}</td>' in row
    assert row.count("qd-col") == 1 and row.count("qr-dcol") == 1 and 'class="w qd-col"' in body(QSF, "async function qsfRank(")
    assert '<div class="qr-m2">${esc(r.band_label || "")}</div>' in body(ASST, "function asstCands(")


# ---------------------------------------------------------------- P1-7 rare risks read as a line, common notes as quiet chips
def test_the_four_rare_risks_are_a_line_and_the_common_notes_are_quiet():
    cut = QSF.index("function qsfRiskLines(")
    js = PRELUDE + 'const QSF_DEAL_NOTE = "deal", QSF_FILING_NOTE = "filing", QSF_RISK_NOTE = "risk";\n' + QSF[cut:QSF.index("function qsfReason(")] + """
const rows = [{ deal: { label: "합병", form: "DEFM14A", date: "2026-11-01" } }, { filing_events: { financing: true } }, { high_risk: { session: "x" } },
  { price_audit: { level: "warn", text: "값이 다름" } }, { filing_events: { buyback: true } }, { price_audit: { level: "ok" } }, {}];
console.log(JSON.stringify([rows.map(qsfRiskLines), qsfBuybackChip({ buyback: true }), qsfBuybackChip({ financing: true })]));"""
    lines, chip, none = node(js)
    assert "합병 절차 공시 · 인수 가격에 묶일 수 있음" in lines[0] and 'title="deal 합병(DEFM14A, 2026-11-01)"' in lines[0]
    assert "자금조달 결정 공시" in lines[1] and "변동성 상위 20%" in lines[2] and "시세 이력 확인 필요" in lines[3] and 'title="값이 다름"' in lines[3]
    assert all(x.startswith('<div class="qr-risk"') for x in lines[:4]) and lines[4:] == ["", "", ""]
    assert 'class="badge info"' in chip and "자사주 취득" in chip and none == ""
    row = body(QSF, "function qsfRankRow(")
    for old in ("qsfRiskTag()", "qsfFilingTags(", "qsfDealTag(", "qsfAuditTag(", '<span class="badge" title="자료가'):
        assert old not in row, old
    assert "${qsfRiskLines(r)}" in row and "${qsfBuybackChip(r.filing_events)}" in row and '<span class="badge info" title="자료가' in row
    assert '<div class="qr-out">실행 대상 아님 · ${why}</div>' in row
    assert 'class="badge info" title="지금 고른 성향의 기준을' in QSF and 'class="badge ok" title="지금 고른 성향' not in QSF


def test_the_new_marks_are_readable_in_both_themes():
    light = _tokens(CSS[:CSS.index(':root[data-theme="dark"]')])
    dark = _tokens(CSS[CSS.index(':root[data-theme="dark"]'):CSS.index("* { box-sizing")])
    for t in (light, dark):
        for ground in ("--panel", "--chip", "--bg"):
            assert _contrast(t["--muted"], t[ground]) >= 4.5 and _contrast(t["--warn"], t[ground]) >= 4.5, ground
    assert ".badge.info { color: var(--muted);" in CSS and ".qr-risk { color: var(--warn);" in CSS
