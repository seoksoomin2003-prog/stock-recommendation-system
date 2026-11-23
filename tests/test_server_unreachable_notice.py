"""A request that fails is not shown as 'no record': the page says the server did not answer."""
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "terminal" / "static"


def test_a_failed_request_raises_its_own_error_and_shows_the_notice():
    app = (STATIC / "app.js").read_text(encoding="utf-8")
    assert 'catch (e) { netDown(true); throw new Error("SERVER_UNREACHABLE"); }' in app and 'SERVER_UNREACHABLE: "터미널 서버에 연결되지 않습니다."' in app
    assert "실제로 기록이 없다는 뜻이 아닐 수 있습니다" in app and "setInterval(ping, 5000)" in app and "clearInterval(netTimer)" in app
    assert '<div id="netbar" class="netbar" role="alert" hidden></div>' in (STATIC / "index.html").read_text(encoding="utf-8")
    assert ".netbar[hidden] { display: none; }" in (STATIC / "style.css").read_text(encoding="utf-8")


def test_the_rank_view_tells_a_failed_request_from_a_missing_scan():
    js = (STATIC / "qsf.js").read_text(encoding="utf-8")
    failed, missing = js.index("순위를 불러오지 못했습니다"), js.index("아직 스캔 기록이 없습니다. 매일 자동 실행 뒤에 표시됩니다.")
    assert failed < missing and "스캔 기록이 없다는 뜻이 아닙니다" in js
