"""The screen's layout (2026-11-21): six groups of tabs, the score tab's caveat as one line that opens, long sections that open from their titles.
Read from the page's own files; nothing is rendered."""
import re
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "terminal" / "static"
read = lambda name: (STATIC / name).read_text(encoding="utf-8")      # noqa: E731
GROUPS = ["today", "market", "stock", "account", "score", "verify"]


def test_every_tab_belongs_to_one_of_six_groups_and_keeps_its_section():
    html = read("index.html")
    nav = html[html.index('<nav class="groups"'):html.index('<nav class="tabs"')]
    assert re.findall(r'data-group="(\w+)"', nav) == GROUPS and re.findall(r">([^<]+)</button>", nav) == ["오늘", "시장", "종목", "내 계좌", "점수", "검증·기록"]
    tabs = re.findall(r'<button data-tab="(\w+)" data-group="(\w+)"', html)
    assert len(tabs) == 13 and {g for _, g in tabs} == set(GROUPS) and len({t for t, _ in tabs}) == 13
    assert [g for _, g in tabs] == sorted((g for _, g in tabs), key=GROUPS.index)          # the tabs of a group sit together, in the groups' order
    assert dict(tabs)["qsf"] == "score" and dict(tabs)["today"] == "today" and [t for t, g in tabs if g == "market"] == ["overview", "map", "macro"]
    assert [t for t, g in tabs if g == "account"] == ["portfolio", "assist", "paper"] and [t for t, g in tabs if g == "verify"] == ["model", "lab"]
    for tab, _ in tabs:
        assert f'id="tab-{tab}"' in html, tab


def test_the_shown_tab_lights_its_group_and_a_group_returns_to_its_last_tab():
    js, css, cmd = read("app.js"), read("style.css"), read("command.js")
    assert "paintGroups(tab);" in js[js.index("function show(tab"):js.index("function paintMarket")]
    assert "groupTab[g] = tab;" in js and "show(groupTab[g] || first.dataset.tab)" in js and 'document.querySelector(".tabs").hidden = mine.length < 2;' in js
    assert '.groups button").forEach((b) => (b.onclick = () => showGroup(b.dataset.group)))' in js
    assert ".tabs[hidden], .tabs button[hidden] { display: none; }" in css and ".groups {" in css
    assert 'document.querySelectorAll(".groups button")[+e.key - 1]' in cmd and "묶음 바로가기" in cmd and "탭 바로가기" not in cmd


def test_the_caveat_is_one_line_that_opens_and_nothing_of_it_was_removed():
    from terminal.qsf import config
    js = read("qsf.js")
    block = js[js.index('<details class="notice qsf-caveat">'):js.index('<div id="qsfrecord"></div>')]
    assert "<summary><b>점수가 높다고 수익이 더 좋았다는 근거는 아직 확인되지 않았습니다. 참고용으로만 쓰세요.</b>" in block and block.rstrip().endswith("</details>")
    assert config.VALIDATION_NOTICE.split("근거를 찾지 못했습니다. ", 1)[1] in block and "주문을 실행하지 않고, 투자 자문이 아닙니다." in block      # the whole text is still there
    assert '<details class="qsf-record"><summary>과거 성적: 이 점수를 얼마나 믿을 수 있나' in js and '<details class="qsf-record" open>' not in js


def test_long_sections_open_from_their_titles_and_only_the_verdict_schedule_starts_open():
    js, css = read("qsf.js"), read("style.css")
    track = js[js.index('<div data-view="track">'):js.index("qsfFolds(el);")]
    assert re.findall(r'data-fold="(\w+)"', track) == ["readings", "top3", "fcast", "method", "regime", "look", "valid"]
    for box in ("qsfreadings", "qsftop3", "qsffcast", "qsfmethod", "qsfregime", "qsflook", "qsfvalid"):
        assert f'<div id="{box}"></div></div>' in track, box
    assert 'const QSF_FOLD_OPEN = ["readings"];' in js and 'data-fold="changes"><div id="qsfchanges"></div>' in js and 'data-fold="cap"><div id="qsfcap"></div>' in js
    assert "if (f.classList.contains(\"open\")) redrawAll();" in js and 'e.target.closest("button, a, input, select")' in js
    assert ".fold:not(.open) > div > .panel > :not(h2) { display: none; }" in css
