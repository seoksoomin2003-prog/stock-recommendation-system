"""A page left open learns that the screen files changed, and the tab row wraps instead of pushing tabs out of sight."""
from pathlib import Path

from terminal import services
from terminal.services import Terminal
from tests.test_terminal_1 import AFTER, fake_src

ROOT = Path(__file__).resolve().parents[1]


def test_the_health_answer_carries_a_mark_that_moves_when_a_screen_file_changes(tmp_path, monkeypatch):
    t = Terminal(tmp_path, src=fake_src(), now=lambda: AFTER)
    first = t.health()["screen"]
    assert first == services.screen_stamp() and len(first) == 12
    static = tmp_path / "static"
    static.mkdir()
    (static / "app.js").write_text("one", encoding="utf-8")
    (static / "notes.txt").write_text("not a screen file", encoding="utf-8")
    monkeypatch.setattr(services, "__file__", str(tmp_path / "services.py"))
    a = services.screen_stamp()
    (static / "notes.txt").write_text("changed, but not a screen file", encoding="utf-8")
    assert services.screen_stamp() == a
    (static / "app.js").write_text("two!", encoding="utf-8")
    assert services.screen_stamp() != a
    b = services.screen_stamp()
    (static / "paper.js").write_text("new", encoding="utf-8")
    assert services.screen_stamp() != b


def test_the_page_checks_the_mark_and_offers_a_reload_and_the_tab_row_wraps():
    js = (ROOT / "terminal" / "static" / "app.js").read_text(encoding="utf-8")
    assert "h.screen !== screenStamp" in js and "screenChanged()" in js and "location.reload()" in js and "프로그램 화면이 업데이트되었습니다" in js
    assert js.index("let screenStamp = null, healthAt = 0;") < js.index("function show(tab")           # declared before anything can call show()
    assert 'id="verbar"' in (ROOT / "terminal" / "static" / "index.html").read_text(encoding="utf-8")
    css = (ROOT / "terminal" / "static" / "style.css").read_text(encoding="utf-8")
    tabs = css[css.index(".tabs {"):css.index(".tabs button {")]
    assert "flex-wrap: wrap" in tabs and "overflow-x" not in tabs
