"""UI/UX audit 2026-11-23, fifth batch: structure (reports/ui_ux_assessment_2026_11_23/UI_UX_REMEDIATION_ROADMAP.md P2-11, P2-12,
P2-13, P2-21, P2-22, P3-4, P3-6, P3-8, P3-12, P3-13) with the user's decisions of the same day: table screens up to 1680 px with the
score card beside the ranking from 1600 px, single-key shortcuts kept with a switch, Today shows the previous list while it refreshes,
whole rows stay clickable and also open with Tab and Enter.  Display only: no score, band edge or record changes."""
import re
from pathlib import Path

from tests.test_ui_batch_1 import body, node
from tests.test_ui_batch_2 import media

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "terminal" / "static"
APP = (STATIC / "app.js").read_text(encoding="utf-8")
QSF = (STATIC / "qsf.js").read_text(encoding="utf-8")
CMD = (STATIC / "command.js").read_text(encoding="utf-8")
ASST = (STATIC / "assistant.js").read_text(encoding="utf-8")
CSS = (STATIC / "style.css").read_text(encoding="utf-8")
HTML = (STATIC / "index.html").read_text(encoding="utf-8")
THEME = (STATIC / "theme.js").read_text(encoding="utf-8")
JS = {p.name: p.read_text(encoding="utf-8") for p in STATIC.glob("*.js")}


def line(src, start):
    i = src.index(start)
    return src[i:src.index("\n", i) + 1]


# ---------------------------------------------------------------- P2-11 four widths, one place in JS, wide table screens
def test_four_widths_only():
    widths = set(re.findall(r"@media \((?:max|min)-width: (\d+)px\)", CSS))
    assert widths <= {"380", "400", "640", "641", "1023", "1024", "1279", "1600"}, widths           # 380/400: phone fine-tuning, 1279: area columns
    assert not {"560", "600", "700", "720", "760"} & widths
    for name, src in JS.items():
        assert "innerWidth < 600" not in src, name
    assert 'const isPhone = () => window.matchMedia("(max-width: 640px)").matches;' in APP
    assert ":root { --fs-display: 24px; }" in media(CSS, "max-width: 640px") and ".asst-cands" in media(CSS, "max-width: 1023px")


def test_table_screens_widen_and_the_card_sits_beside_the_ranking():
    assert "--content-max-wide: 1680px;" in CSS and "main.wide > .tab:not(:has(> .ws)) { max-width: var(--content-max-wide); }" in CSS      # workstation stage 3: a screen in a .ws grid uses --ws-max
    assert 'const WIDE_TABS = new Set(["qsf", "committee", "portfolio", "watch", "lab", "model", "coin"]);' in APP
    assert '$("main").classList.toggle("wide", WIDE_TABS.has(tab));' in body(APP, "function show(tab")
    # workstation stage 4 (2026-11-24): the card sits in the score tab's right column whenever the workspace grid has two columns
    # (content column 1120 px or wider) instead of beside the ranking from a 1600 px window; the old .qsf-split block is gone
    assert ".qsf-split:has(" not in CSS and "qsf-split" not in media(CSS, "min-width: 1600px")
    tpl = body(QSF, "async function renderQsf(")
    assert '<div class="ws-body qsf-split"><div class="ws-main">' in tpl and '<div data-view="rank"><div id="qsfrank"></div></div>' in tpl
    assert '<div class="ws-right" role="complementary" aria-label="점수 카드와 시장 상태"><div id="qsfdetail" class="ws-first"></div></div>' in tpl
    assert 'const qsfBeside = () => wsCanSplit() && (qsfState.view === "rank" || qsfState.view === "screen");' in QSF
    assert 'if (!qsfBeside()) $("#qsfmsg").scrollIntoView' in QSF                                      # the ranking keeps its place
    assert ".ws-right > * { order: 1; min-width: 0; }" in CSS and "position: sticky; top: calc(var(--sticky-top, 0px) + var(--gutter));" in CSS   # right column sticks


# ---------------------------------------------------------------- P2-12 rows and fold titles open from the keyboard
def test_clickable_rows_take_focus_and_open_with_enter_or_space():
    keyable = line(APP, "const KEYABLE")
    for sel in ("tr.click", "tr[data-coin]", "tr[data-fund]", "div.card[data-ticker]", "b[data-ticker]", ".fold > div > .panel > h2"):
        assert sel in keyable, sel
    mark = body(APP, "function markKeyable(")
    assert "el.tabIndex = 0;" in mark and 'if (el.tagName !== "TR") el.setAttribute("role", "button");' in mark
    assert 'h.setAttribute("aria-expanded", h.closest(".fold").classList.contains("open"))' in mark
    assert "new MutationObserver(" in APP and 'attributeFilter: ["class"]' in APP
    keys = APP[APP.index('if ((e.key !== "Enter" && e.key !== " ")'):]
    assert "e.target.click();" in keys[:300]
    assert 'document.addEventListener("click", (e) => { const el = e.target.closest("[data-ticker]");' in APP      # the whole row still opens


# ---------------------------------------------------------------- P2-13 selected state, focus, palette
def test_selected_state_and_focus_are_announced():
    assert 'role="tablist"' not in HTML and '<nav class="tabs" aria-label="탭">' in HTML                # the left menu since 2026-11-24
    assert 'b.toggleAttribute("aria-current", b.dataset.group === g)' in body(APP, "function paintGroups(")
    assert 'x.toggleAttribute("aria-current", x === b)' in body(APP, "function paintTitle(")
    assert 'b.setAttribute("aria-pressed", b.classList.contains("on"))' in body(APP, "function markKeyable(")
    assert ":focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }" in CSS
    assert "#cmd-q:focus-visible { box-shadow: inset 0 -2px 0 var(--accent); }" in CSS
    assert "html { scroll-padding-top:" in CSS and ".qs-sort { font-weight: 600; white-space: nowrap; min-height: 24px; }" in CSS
    assert 'id="qsfmsg" class="meta" role="status" aria-live="polite"' in QSF


def test_the_command_palette_is_a_modal_that_gives_focus_back():
    assert 'role="dialog" aria-modal="true"' in CMD and 'role="combobox"' in CMD and 'aria-controls="cmd-list"' in CMD
    assert '$("#cmd-q").setAttribute("aria-activedescendant", on.id)' in body(CMD, "function cmdPaint(")
    assert "cmdBack = document.activeElement" in body(CMD, "function cmdOpen(")
    close = body(CMD, "function cmdClose(")
    assert "if (back && cmdBack && cmdBack.isConnected) cmdBack.focus();" in close
    assert "cmdClose(false); it.run();" in CMD                                                        # moving somewhere does not jump back
    assert '(document.activeElement === $("#cmd-q") ? $("#cmd-keys") : $("#cmd-q")).focus();' in CMD       # Tab stays inside


# ---------------------------------------------------------------- P2-21 one dark palette, no dead rules
def test_one_dark_palette_set_before_the_first_paint():
    assert "prefers-color-scheme" not in CSS and CSS.count(':root[data-theme="dark"] {') == 1
    assert HTML.index('<script src="theme.js"></script>') < HTML.index("<body>")
    assert 'localStorage.getItem("qse-theme")' in THEME and 'setAttribute("data-theme", dark ? "dark" : "light")' in THEME
    apply = body(APP, "function applyTheme(")
    assert 'document.documentElement.dataset.theme = t === "dark" || (t === "auto" && systemDark()) ? "dark" : "light";' in apply
    assert 'addEventListener("change", () => (theme === "auto" ? applyTheme("auto") : redrawAll()))' in APP


def test_rules_for_removed_screens_are_gone():
    for dead in (".qsf-row {", ".qsf-rows {", ".qsf-item {", ".qsf-top {", ".qsf-plan {", ".fc-levels {", ".qr-gate:empty"):
        assert dead not in CSS, dead
    assert CSS.count("#cmd-q {") == 1 and CSS.count(".qs-sort {") == 1
    assert "@media (max-width: 600px) { .top { position: static; } }" not in CSS                     # it was overridden by the phone header


# ---------------------------------------------------------------- P2-22 redraws do not pile up; Today comes back at once
def test_redraws_are_keyed_and_hidden_tabs_wait():
    for name, src in JS.items():
        assert "redrawers.add(" not in src and "redrawers.delete(" not in src, name
    assert "const redrawers = new Map(), redrawLater = new Set();" in APP
    i = APP.index("const redrawers = new Map()")
    got = node(APP[i:APP.index("window.matchMedia(", i)].replace(
        "const redrawers", "const state = { tab: \"watch\" };\nconst redrawers") + """
const calls = [];
for (let i = 0; i < 5; i++) redrawOn("watch", "sparks", () => calls.push("watch"));      // five visits to the watch tab
redrawOn("map", "heat", () => calls.push("map"));
redrawAll();
const afterAll = calls.slice();
redrawShown("map");
redrawShown("map");
console.log(JSON.stringify([redrawers.size, afterAll, calls]));""")
    assert got == [2, ["watch"], ["watch", "map"]]                                                    # one function per part; a hidden tab draws once on return


def test_today_shows_the_previous_list_while_it_refreshes():
    assert 'ALWAYS_FRESH.add("today")' not in ASST and "RETURN.today = asstReturn;" in ASST
    ret = body(ASST, "function asstReturn(")
    assert "asstBrief(true);" in ret and "asstPending" in ret
    brief = body(ASST, "async function asstBrief(")
    assert 'brief.classList.add("refreshing")' in brief and "갱신 중… 아래는 ${esc(stamp(had) || had)}에 만든 목록입니다." in brief
    assert "새 목록을 받지 못했습니다" in brief and 'brief.dataset.at = d.generated_at || "";' in brief
    assert "token !== asstBriefToken || market !== state.market" in brief
    assert "#asst-brief.refreshing [data-brief] > :not(.asst-refresh) { opacity: 0.55; }" in CSS      # workstation stage 3: only the four brief hosts dim


# ---------------------------------------------------------------- P3-4 h1, palette name, single-key switch
def test_each_screen_has_an_h1_and_single_keys_can_be_switched_off():
    assert '<h1 id="pagetitle" class="sr-only">퀀트 터미널</h1>' in HTML and ".sr-only {" in CSS
    assert "paintTitle(tab);" in body(APP, "function show(tab")
    assert 'aria-label="명령창 열기 (⌘K)"' in HTML and '<button id="keysbtn" class="ghost" type="button" hidden>' in HTML
    assert 'keysOn = localStorage.getItem("qse-keys") !== "off";' in CMD
    assert "if (!keysOn || !cmdEl.hidden || typing(e)" in CMD                                          # Cmd/Ctrl+K is checked before this line
    k = CMD.index('if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k")')
    assert k < CMD.index("if (!keysOn || !cmdEl.hidden")
    assert '["keysbtn", "한 글자 단축키"]' in APP and '(!b.hidden || id === "keysbtn")' in APP


# ---------------------------------------------------------------- P3-6 one prefix for the browser's settings
def test_old_setting_names_move_to_the_qse_prefix_once():
    block = APP[APP.index("const STORE_RENAMES"):APP.index("} catch (e) { /* storage unavailable: defaults */ }") + 60]
    got = node("""const data = { recentTickers: '["AAPL"]', qsfView: "exec", heatView: "{}", "qse-chart": "kept", chartAnalysis: "old" };
const localStorage = { getItem: (k) => (k in data ? data[k] : null), setItem: (k, v) => { data[k] = String(v); }, removeItem: (k) => { delete data[k]; } };
""" + block + "\nconsole.log(JSON.stringify(data));")
    assert got == {"qse-recent": '["AAPL"]', "qse-qsf-view": "exec", "qse-heat-view": "{}", "qse-chart": "kept"}      # a newer value is kept
    for name, src in JS.items():
        for old in ("recentTickers", "qsfView", "qsfFolds", "heatView", "chartAnalysis", "compareTickers"):
            uses = re.findall(r'localStorage\.\w+Item\("' + old + '"', src) + re.findall(r'_KEY = "' + old + '"', src)
            assert not uses, (name, old)


# ---------------------------------------------------------------- P3-8 outside links open only http(s)
def test_outside_links_are_http_only():
    got = node(line(APP, "const safeUrl") + """console.log(JSON.stringify([safeUrl("https://www.sec.gov/x"), safeUrl(" http://a.b "), safeUrl("javascript:alert(1)"),
  safeUrl("data:text/html,x"), safeUrl(null)]));""")
    assert got == ["https://www.sec.gov/x", "http://a.b", "", "", ""]
    for name, src in JS.items():
        for m in re.finditer(r'href="\$\{([^}]*)\}"', src):
            assert m.group(1).startswith("esc(safeUrl("), (name, m.group(0))
    assert "<b>${esc(a.label)}</b>" in JS["account.js"] and '<li class="${esc(a.level)}">' in JS["alerts.js"]


# ---------------------------------------------------------------- P3-12 band colours come from the server's band list
def test_band_colours_read_the_servers_bands():
    bar = body(QSF, "function qsfBar(")
    assert not re.search(r"\b(70|55|40)\b", bar) and "act-" not in bar      # UI batch 6 P2-8: a domain bar is not a judgement, so no tone
    cls = body(QSF, "function qsfClass(")
    assert not re.search(r"\b40\b", cls) and 'band !== "SELL_AVOID"' in cls
    assert 'api("/api/qsf/bands")' in QSF
    from terminal.qsf import config, rank_notes
    got = rank_notes.bands()["bands"]
    assert [(b["start"], b["key"]) for b in got] == [(float(s), k) for s, k, _ in sorted(config.BANDS, key=lambda b: -b[0])]
    assert '("GET", "/api/qsf/bands"): lambda q, b: qsf_rank_notes.bands(),' in (ROOT / "terminal" / "server.py").read_text(encoding="utf-8")
    got = node("""const isNum = (v) => typeof v === "number" && isFinite(v);
const QSF_ACTION_CLASS = { AVOID: "act-sell", BUY: "act-buy" };
""" + "let qsfBands = " + __import__("json").dumps(got) + ";\n" + body(QSF, "function qsfBandKey(")
        + body(QSF, "function qsfClass(") + """console.log(JSON.stringify([qsfBandKey(80), qsfBandKey(54.9), qsfBandKey(39.9), qsfClass("AVOID", 45), qsfClass("AVOID", 30),
  qsfClass("BUY", 75)]));""")
    assert got == ["STRONG_BUY_CANDIDATE", "WEAK_REDUCE", "SELL_AVOID", "act-reduce", "act-sell", "act-buy"]


# ---------------------------------------------------------------- P3-13 the page no longer hides what overflows
def test_the_page_does_not_hide_sideways_overflow():
    assert not re.search(r"body \{[^}]*overflow-x: hidden", CSS)
