"""Finding a stock, carrying the open stock across tabs, and keeping the score tab as it was left (2026-11-22).
Read from the page's own files; nothing is rendered, so these protect the wiring, not the look."""
import re
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "terminal" / "static"
read = lambda name: (STATIC / name).read_text(encoding="utf-8")      # noqa: E731


def body(js: str, start: str, end: str) -> str:
    return js[js.index(start):js.index(end, js.index(start) + len(start))]


def test_a_typed_word_is_looked_up_among_the_scanned_stocks_before_it_is_opened_as_a_ticker():
    """Typing `apple`, `삼성전자` or the mistyped `APPL` leads to the stock or to "혹시 이 종목인가요?", not to an empty
    screen for ticker APPLE; a code outside the scan (an ETF, an index) can still be opened as typed."""
    js, cmd = read("app.js"), read("command.js")
    find = body(js, "async function findSymbol(", "\nfunction symbolChoices(")
    assert "/api/symbols?q=${encodeURIComponent(q)}&market=${mk}" in js and "await symbolSuggest(q)" in find
    assert find.index("d.exact") < find.index("openTyped(q)") < find.index("symbolChoices(q, items)")      # exact first, nothing found opens as before
    choices = body(js, "function symbolChoices(", "\n// 검색창 자동 완성")
    assert "혹시 이 종목인가요?" in choices and "그대로 열기" in choices and 'data-ticker="${esc(i.ticker)}"' in choices and "'${esc(q)}'" in choices
    assert "esc(i.ticker)" in js and "esc(i.name)" in js and "esc(MARKET_KO[i.market] || i.market)" in js      # every inserted text is escaped
    submit = body(js, '$("#search").onsubmit', "};")
    assert "findSymbol(t)" in submit and "openTicker(t)" not in submit and "if (isCoin()) { askAssistant(t);" in submit
    assert "run: () => findSymbol(code)" in cmd and "run: () => findSymbol(q)" in cmd                      # the palette asks the same way


def test_the_search_box_suggests_while_typing_and_the_palette_adds_the_same_stocks():
    """Up to eight suggestions under the search box after a short pause; arrows move, Enter opens the highlighted one,
    Esc and a click outside close.  The palette lists the same stocks unless the word is a command."""
    js, cmd, css = read("app.js"), read("command.js"), read("style.css")
    assert "setTimeout(() => sugLoad(q), 150)" in js and ".slice(0, 8)" in body(js, "async function sugLoad(", "\n$(")
    keys = body(js, '$("#q").addEventListener("keydown"', "});")
    for key in ('"ArrowDown"', '"ArrowUp"', '"Enter" && !e.isComposing && sug.sel >= 0', '"Escape"'):
        assert key in keys, key
    assert '!e.target.closest("#search")) sugClose();' in js
    assert ".sug[hidden] { display: none; }" in css and ".search { position: relative; }" in css
    assert "symbolSuggest(q)" in body(cmd, "function cmdSymbols(", "\n}") and "cmdIsCommand(q.toLowerCase())" in cmd
    assert "cmdPaint(); cmdSymbols(e.target.value);" in cmd and "esc(it.label)" in cmd and "esc(it.hint)" in cmd


def test_a_ticker_is_kept_as_recent_only_once_it_is_known_to_exist():
    """A mistyped ticker does not become a "최근 본 종목" shortcut or a default of the compare tab: it is stored when it
    is a scanned stock, or after its chart came back with prices."""
    js = read("app.js")
    opened = body(js, "function openTicker(", "\n}")
    assert "if (knownSymbols.has(state.ticker)) rememberTicker(state.ticker);" in opened
    assert re.findall(r"^\s*rememberTicker\(", opened, flags=re.M) == []                                    # never unconditionally
    assert 'if (c.status !== "UNAVAILABLE") rememberTicker(t);' in body(js, "async function loadChart(", "\n}")
    assert js.count("rememberTicker(") == 3                                                                # the definition and these two calls


def test_the_open_stock_is_carried_to_the_other_tabs_without_being_submitted():
    """With a stock open, the score tab's evaluate box and the alert and sizing forms start with its code; nothing is
    submitted and typed text is never replaced.  The stock screen and the score card link to each other."""
    js, qsf = read("app.js"), read("qsf.js")
    fill = body(js, "function prefillTicker(", "\n}")
    assert "marketOf(state.ticker) !== state.market" in fill and "if (input.value && input.value !== input.dataset.prefill) return;" in fill
    assert "submit" not in fill and "onsubmit" not in fill
    assert qsf.count('prefillTicker($("#qsfticker"));') == 2                                               # when built and when returned to
    assert "prefillTicker(f.ticker);" in read("alerts.js") and 'prefillTicker($("#szform").elements.t);' in read("portfolio.js")
    assert 'id="addq" type="button"' in js and ">점수 카드</button>" in js and "qsfOpenCard(c.ticker)" in js
    card = body(qsf, "function qsfOpenCard(", "\n}")
    assert card.index('qsfSetView("rank")') < card.index("qsfEvaluate(t, state.market, push)")
    assert 'data-ticker="${esc(d.ticker)}"' in body(qsf, "function qsfDrawDetail(", "\n}") and ">종목 화면</button>" in qsf


def test_an_evaluated_card_has_its_own_address():
    """`#qsf/TICKER` opens the score tab on that stock's card, so reload and back/forward return to it; `#tab` and
    `#stock/TICKER` work as before and an unknown name still falls back to the first screen."""
    js, qsf = read("app.js"), read("qsf.js")
    assert "return `qsf/${state.card}`;" in body(js, "function tabHash(", "\n}") and "if (push) location.hash = tabHash(tab);" in js
    assert 'location.hash = tabHash("qsf");' in body(qsf, "async function qsfEvaluate(", "\n}")
    hashed = body(js, "function fromHash(", "\n}")
    assert 'tab === "qsf" && HASH_TICKER.test(' in hashed and "return qsfOpenCard(card, false);" in hashed
    assert hashed.index("qsfOpenCard(card, false)") < hashed.index('show(RENDER[tab] ? tab : RENDER.today ? "today" : "overview", false);')
    assert 'if (tab === "stock" && tk) { state.ticker = decodeURIComponent(tk).toUpperCase();' in hashed


def test_the_score_tab_is_kept_and_its_scan_is_fetched_once():
    """Coming back to the score tab in the same market leaves expanded rows, the evaluated card and the scroll position;
    switching swing/long reuses the scan already fetched (kept five minutes, dropped when a collect run ends or the
    screen is refreshed)."""
    js, qsf, collect = read("app.js"), read("qsf.js"), read("collect.js")
    assert qsf.count("/api/qsf/latest") == 2 and "api(`/api/qsf/latest?market=${mk}`)" in body(qsf, "function qsfLatest(", "\n}")      # the comment and the one fetch
    assert "const QSF_LATEST_TTL_MS = 5 * 60 * 1000;" in qsf and "qsfLatest(mk).catch(" in body(qsf, "async function qsfRank(", "\n}")
    assert "state.loaded.qsf = true;" in body(qsf, "async function renderQsf(", "\n}") and "RETURN.qsf = qsfReturn;" in qsf
    assert "window.scrollTo(0, folded ? 0 : scrollY);" in body(qsf, "function qsfReturn(", "\n}")          # batch 2: a folded card starts at the top
    shown = body(js, "function show(tab", "\n}")
    assert "if (!state.loaded[tab] || ALWAYS_FRESH.has(tab)) RENDER[tab]();" in shown and "else if (RETURN[tab]) RETURN[tab](tabScroll[tab] || 0);" in shown
    assert '"qsf"' not in js[js.index("const ALWAYS_FRESH"):js.index("const RENDER")]
    assert "state.loaded = {};" in body(js, "function setMarket(", "\n}")                                   # a market change still rebuilds every tab
    assert "qsfDropLatest();" in body(collect, "function collectStale(", "\n}") and collect.count("collectStale();") == 2      # run finished, refresh pressed
