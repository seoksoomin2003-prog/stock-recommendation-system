"""UI/UX audit 2026-11-23, third batch (reports/ui_ux_assessment_2026_11_23/UI_UX_REMEDIATION_ROADMAP.md P1-11, P1-12, P2-1..P2-4)
with the user's decisions of the same day: a phone bottom bar of today, stock, score, account and more; score-card sections all
folded except the basis; shared parts plus five small screens.  Display only: nothing here scores, ranks or records."""
import re
from pathlib import Path

from tests.test_ui_batch_1 import _contrast, _tokens, body, node
from tests.test_ui_batch_2 import media

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "terminal" / "static"
CSS = (STATIC / "style.css").read_text(encoding="utf-8")
QSF = (STATIC / "qsf.js").read_text(encoding="utf-8")
APP = (STATIC / "app.js").read_text(encoding="utf-8")
HTML = (STATIC / "index.html").read_text(encoding="utf-8")
UI = (STATIC / "ui.js").read_text(encoding="utf-8")


# ---------------------------------------------------------------- P2-1 one scale
def test_type_layers_and_corners_read_the_tokens():
    root = CSS[CSS.index("/* UI batch 3 P2-1"):CSS.index("* { box-sizing")]
    sizes = re.findall(r"--fs-[a-z]+: (\d+)px", root)
    assert len(sizes) == 7 and [int(x) for x in sizes] == sorted(int(x) for x in sizes)
    for k in ("--sp-1: 4px", "--sp-6: 32px", "--r-pill: 999px", "--z-header: 10", "--z-toast: 50", "--content-max: 1280px"):
        assert k in root, k
    assert not re.search(r"font-size:\s*\d", CSS) and not re.search(r"z-index:\s*\d", CSS)          # every size and layer is a token
    assert not re.search(r"border-radius:\s*(4|6|8|10|12|14)px", CSS)
    assert ":root { --fs-display: 24px; }" in media(CSS, "max-width: 640px")                         # the phone lowers the display size


# ---------------------------------------------------------------- P2-2 one field style whose edge can be seen
def test_every_field_shares_one_rule_and_its_edge_passes_three_to_one():
    rule = CSS[CSS.index("/* UI batch 3 P2-2"):CSS.index("/* TERMINAL-2")]
    assert 'input[type="search"]' in rule and "select, textarea {" in rule and "border: 1px solid var(--line-strong)" in rule
    assert ":focus-visible { outline: 2px solid var(--accent)" in rule
    light = _tokens(CSS[:CSS.index(':root[data-theme="dark"]')])
    dark = _tokens(CSS[CSS.index(':root[data-theme="dark"]'):CSS.index("* { box-sizing")])
    for t in (light, dark):
        for surface in ("--panel", "--bg"):
            assert _contrast(t["--line-strong"], t[surface]) >= 3, surface
    assert CSS.count("--line-strong: #6b7b92") == 1                                                 # one dark block since batch 5 (value of 2026-11-24)


# ---------------------------------------------------------------- P2-3 utility classes for the common inline styles
def test_common_inline_styles_became_classes():
    count = sum(p.read_text(encoding="utf-8").count('style="') for p in STATIC.glob("*.js"))
    assert count <= 70, count                                                                       # was about 261; the rest are dynamic
    for js in STATIC.glob("*.js"):
        src = js.read_text(encoding="utf-8")
        assert 'style="margin:0"' not in src and 'style="white-space:normal"' not in src, js.name
    for k in (".m0 { margin: 0 !important; }", ".mt-2 { margin-top: var(--sp-2) !important; }", ".wrap { white-space: normal !important; }"):
        assert k in CSS


# ---------------------------------------------------------------- P2-4 shared parts escape plain text
def test_the_shared_parts_escape_text_and_keep_html():
    got = node(UI + """
console.log(JSON.stringify([
  ui.empty('<b>x</b>'), ui.badge('a&b', 'info', 'say "hi"'), String(html`<i>${'<s>'}</i>${raw('<u>ok</u>')}${['<a>', raw('<b>')]}`),
  ui.table({ cols: [{ label: '날짜', cls: 'l' }], rows: [], empty: '없음' }),
  ui.table({ cols: [{ label: 'A<' }], rows: ['<tr><td>1</td></tr>'], cls: 'cal' }),
  ui.head({ title: '제목<', sub: '부제', actions: '<button>b</button>' }),
  ui.seg({ items: [['US', '미국'], ['KR', '한국']], value: 'KR', label: '시장' }),
  ui.kv([['이름', '<b>값</b>']])]));""")
    assert got[0] == '<div class="empty">&lt;b&gt;x&lt;/b&gt;</div>'
    assert got[1] == '<span class="badge info" title="say &quot;hi&quot;">a&amp;b</span>'
    assert got[2] == "<i>&lt;s&gt;</i><u>ok</u>&lt;a&gt;<b>"
    assert got[3] == '<div class="empty">없음</div>'
    assert got[4] == '<div class="tbl-wrap"><table class="cal"><thead><tr><th>A&lt;</th></tr></thead><tbody><tr><td>1</td></tr></tbody></table></div>'
    assert got[5] == '<h2>제목&lt; <span class="meta m0">부제</span> <span class="ph-actions"><button>b</button></span></h2>'      # actions at the right end (stage 2)
    assert 'aria-pressed="false">미국' in got[6] and 'class="on" aria-pressed="true">한국' in got[6] and 'aria-label="시장"' in got[6]
    assert got[7] == '<div class="kv"><div><span>이름</span><b><b>값</b></b></div></div>'
    assert HTML.index('<script src="ui.js">') < HTML.index('<script src="app.js">')
    for name in ("calendar.js", "peers.js", "alerts.js", "coin.js", "sectorpicks.js"):
        assert "ui." in (STATIC / name).read_text(encoding="utf-8"), name


# ---------------------------------------------------------------- P1-12 the card: a summary strip, the basis open, the rest folded
FOLD_PRELUDE = """const store = {};
globalThis.localStorage = { getItem: (k) => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); } };
"""


def test_sections_fold_by_default_and_remember_what_the_user_opened():
    js = FOLD_PRELUDE + 'const QSF_FOLD_KEY = "qse-fold-";\n' + body(QSF, "function qsfFoldOpen(") + body(QSF, "function qsfFold(") + """
const a = [qsfFold('basis', 'T', 'B', true), qsfFold('plan', 'T', 'B')];
store['qse-fold-plan'] = '1'; store['qse-fold-basis'] = '0';
const b = [qsfFold('basis', 'T', 'B', true), qsfFold('plan', 'T', 'B', false, 'x1')];
console.log(JSON.stringify([...a, ...b]));"""
    got = node(js)
    assert got[0] == '<details class="qsf-sec" data-fold="basis" open><summary>T</summary><div class="qsf-sec-body">B</div></details>'
    assert " open" not in got[1] and " open" not in got[2] and 'id="x1" open>' in got[3]
    assert 'document.addEventListener("toggle"' in QSF and "localStorage.setItem(QSF_FOLD_KEY + el.dataset.fold" in QSF


def test_the_card_keeps_its_content_under_the_new_sections():
    card = body(QSF, "function qsfCard(")
    assert card.index('class="qsf-meta qsf-sum"') < card.index('qsfFold("basis"') < card.index('qsfFold(c.position ? "plan-held" : "plan"') < card.index('qsfFold("factors"')
    basis = card[card.index('qsfFold("basis"'):card.index('qsfFold(c.position')]
    assert "${qsfBalance(c.balance)}" in basis and "<h3>영역별 점수</h3>" in basis and "<h3>진입</h3>" in basis and "`, true)}" in basis
    summary = card[card.index('class="qsf-meta qsf-sum"'):card.index("</div>", card.index('class="qsf-meta qsf-sum"'))]
    assert "qsfEntry(e.status, c.strategy)" in summary and 'c.strategy === "SWING"' in summary and "h.stop" in summary and "h.target" in summary
    gates = card.index("위험 게이트")
    assert gates < card.index('qsfFold("basis"')                                                  # a blocking gate never hides in a fold
    assert "!!c.position)}" in card and "planOpen" not in QSF                                       # a held stock's plan opens
    for kept in ("plainBlock(c.plain)", "qsfStaleNote(c)", "qsfFundPeriodNote(c)", "c.what_would_change", "c.not_advice", "names[f.factor] || f.factor"):
        assert kept in card, kept


def test_the_detail_folds_committee_range_and_history_and_loads_them_when_opened():
    detail = body(QSF, "function qsfDrawDetail(")
    # ranges and risk come before the score cards and open by themselves (user decision 2026-11-25): the record supports them, not the direction
    order = [detail.index(k) for k in ('qsfFold("range-first"', '<div class="qsf-cards">', 'qsfFold("committee"', 'qsfFold("tech"')]
    assert order == sorted(order) and 'true, "qsffcfold")' in detail and detail.index("qsfRiskGradeLine(d.risk_grade)") < order[1]
    assert detail.index("QSF_RISK_NOTE") < order[0] and detail.index("d.deals") < order[0] and detail.index("qsfAuditLine(d.price_audit)") < order[0]
    assert 'qsfOnOpen($("#qsffcfold"), () => fcStock($("#qsffc"), d.ticker, d.market, d.cards));' in detail
    assert 'qsfOnOpen($("#qsftechfold"), () => qsfHistory($("#qsfhistory"), d.ticker, d.market));' in detail
    tech = detail[detail.index('qsfFold("tech"'):]
    for k in ("QSF_RANK_NOTE[d.rank_basis]", "P6-11B 참고", 'id="qsftodayfold"', 'id="qsfhistory"'):
        assert k in tech, k
    got = node("""const calls = []; const el = { open: false, ls: [], addEventListener(t, f) { this.ls.push(f); }, removeEventListener(t, f) { this.ls = this.ls.filter((x) => x !== f); } };
""" + body(QSF, "function qsfOnOpen(") + """
qsfOnOpen(el, () => calls.push('load')); el.ls.forEach((f) => f()); el.open = true; el.ls.slice().forEach((f) => f()); el.ls.slice().forEach((f) => f());
const open = { open: true }; qsfOnOpen(open, () => calls.push('now'));
console.log(JSON.stringify(calls));""")
    assert got == ["load", "now"]                                                                   # once on the first open; at once when already open


# ---------------------------------------------------------------- P1-11 phone header and bottom bar
def test_the_bottom_bar_holds_the_five_decided_entries():
    bar = HTML[HTML.index('<nav class="bottombar"'):HTML.index("</nav>", HTML.index('<nav class="bottombar"'))]
    labels = re.findall(r">([^<>]+)</button>", bar)
    assert labels == ["오늘", "종목", "점수", "코인", "내 계좌", "더보기"] and 'data-group="coin" hidden' in bar
    assert 'aria-controls="moresheet"' in bar and '<div class="moresheet" id="moresheet" role="dialog" aria-label="더보기" hidden></div>' in HTML
    assert "paintBar(g);" in body(APP, "function paintGroups(")
    assert 'const BAR_GROUPS = ["today", "stock", "score", "coin", "account"];' in APP
    assert all(f'["{k}",' in APP for k in ("collect", "phonebtn", "cmdbtn", "theme"))                # the header buttons the phone hides


def test_the_bar_follows_the_market_and_marks_where_the_user_is():
    js = """const groupShownFor = (coin) => (g) => (coin ? g === "today" || g === "coin" : g !== "coin");
let groupShown;
const mk = (k) => ({ dataset: { group: k }, hidden: false, cls: new Set(), attrs: {}, classList: { toggle(c, on) { on ? this.o.add(c) : this.o.delete(c); } }, toggleAttribute(a, on) { this.attrs[a] = on; } });
const btns = ["today", "stock", "score", "coin", "account"].map(mk); btns.forEach((b) => (b.classList.o = b.cls));
const more = mk("more"); more.classList.o = more.cls;
const $ = (s) => ({ querySelectorAll: () => btns, querySelector: () => more });
""" + 'const BAR_GROUPS = ["today", "stock", "score", "coin", "account"];\n' + body(APP, "function paintBar(") + """
const shot = () => [btns.filter((b) => !b.hidden).map((b) => b.dataset.group + (b.cls.has("on") ? "*" : "")).join(","), more.cls.has("on")];
groupShown = groupShownFor(false); paintBar("score"); const us = shot(); paintBar("market"); const usMore = shot();
groupShown = groupShownFor(true); paintBar("account"); const coin = shot();
console.log(JSON.stringify([us, usMore, coin]));"""
    us, us_more, coin = node(js)
    assert us == ["today,stock,score*,account", False] and us_more == ["today,stock,score,account", True]
    assert coin == ["today,coin,account*", False]


def test_the_phone_header_is_one_line_and_the_computer_keeps_a_sticky_group_bar():
    phone = media(CSS, "max-width: 640px")
    assert ".top .ver, #acctbtn, #collect, #phonebtn, #cmdbtn, #theme { display: none; }" in phone and ".groups { display: none; }" in phone
    assert "min-height: 48px" in phone and ".search { order: 0; flex: 1 1 0;" in phone
    assert "position: fixed; left: 0; right: 0; bottom: 0; z-index: var(--z-header); height: 56px;" in phone and "body { padding-bottom: 56px; }" in phone
    # workstation shell 2026-11-24: the group bar is replaced by the left menu (a column, so it is not added to the sticky height)
    assert ".groups { display: none; }" in CSS and ".side { position: sticky; top: var(--sticky-top, 0px);" in CSS and "ro.observe($(\"#statusbars\"))" in APP
    assert ".bottombar, .moresheet { display: none; }" in CSS and "setTopH();" in APP and "new ResizeObserver(setTopH)" in APP


# ---------------------------------------------------------------- batch 2 leftover: the reason column on a phone
def test_the_reason_column_keeps_korean_words_whole_and_fits_a_small_phone():
    base = CSS[CSS.index(".qsf-rank-tbl .qr-why {"):CSS.index("}", CSS.index(".qsf-rank-tbl .qr-why {"))]
    assert "word-break: keep-all" in base and "overflow-wrap: anywhere" in base                    # a word longer than the cell still breaks
    assert ".qsf-rank-tbl .qr-why { min-width: 68px;" in media(CSS, "max-width: 400px")
