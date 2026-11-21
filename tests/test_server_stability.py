"""Server robustness: malformed requests get an answer, unexpected errors are logged without secrets, saves never lose updates."""
import json
import logging
import socket
import threading
import urllib.request

import pytest

from terminal import server
from terminal.services import Terminal
from tests.test_terminal_1 import AFTER, fake_src
from tests.test_terminal_1 import _loopback_only  # noqa: F401  (autouse: these tests may reach 127.0.0.1 only)


@pytest.fixture()
def live(tmp_path):
    t = Terminal(tmp_path, src=fake_src(), now=lambda: AFTER)
    httpd = server.serve(port=0, terminal=t, background=True)
    yield httpd, t
    httpd.shutdown()
    httpd.server_close()


def raw(port, data: bytes) -> bytes:
    with socket.create_connection(("127.0.0.1", port), timeout=10) as s:
        s.sendall(data)
        return s.recv(4096)


def test_malformed_length_and_body_are_answered(live):
    httpd, _ = live
    p = httpd.server_port
    assert b" 400 " in raw(p, b"POST /api/watchlist/add HTTP/1.1\r\nHost: localhost:%d\r\nContent-Length: abc\r\n\r\n" % p).split(b"\r\n")[0] + b" "
    assert b"413" in raw(p, b"POST /api/watchlist/add HTTP/1.1\r\nHost: localhost:%d\r\nContent-Length: 999999\r\n\r\n" % p).split(b"\r\n")[0]
    deep = b"[" * 4000 + b"]" * 4000
    assert b"400" in raw(p, b"POST /api/watchlist/add HTTP/1.1\r\nHost: localhost:%d\r\nContent-Length: %d\r\n\r\n" % (p, len(deep)) + deep).split(b"\r\n")[0]


def test_unexpected_error_is_logged_with_traceback_but_no_secret(live, tmp_path, monkeypatch):
    httpd, t = live
    monkeypatch.setenv("ECOS_API_KEY", "sekretvalue123")
    path = server.setup_error_log(tmp_path)
    try:
        def boom(market="US"):
            raise RuntimeError("GET https://x/api/sekretvalue123/ for someone@example-mail.net")
        t.overview = boom
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(f"http://127.0.0.1:{httpd.server_port}/api/overview", timeout=10)
        assert e.value.code == 500 and b"sekret" not in e.value.read()
        for h in server.log.handlers:
            h.flush()
        text = path.read_text(encoding="utf-8")
        assert "Traceback" in text and "/api/overview" in text and "RuntimeError" in text
        assert "sekretvalue123" not in text and "example-mail" not in text and "[REDACTED]" in text
        with urllib.request.urlopen(f"http://127.0.0.1:{httpd.server_port}/api/health", timeout=10) as r:
            h = json.loads(r.read())["server_errors"]
        assert h["count"] == 1 and h["last"]["path"] == "/api/overview" and h["last"]["type"] == "RuntimeError"
    finally:
        for h in list(server.log.handlers):
            if getattr(h, "baseFilename", "") == str(path):
                server.log.removeHandler(h)
                h.close()


def test_concurrent_saves_lose_nothing(live):
    httpd, t = live
    base = f"http://127.0.0.1:{httpd.server_port}"
    t._save_watchlist([])
    names = [f"T{i:02d}" for i in range(20)]

    def add(n):
        req = urllib.request.Request(base + "/api/watchlist/add", data=json.dumps({"ticker": n}).encode(), method="POST",
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=20).read()
    threads = [threading.Thread(target=add, args=(n,)) for n in names]
    [th.start() for th in threads]
    [th.join() for th in threads]
    assert sorted(t.watchlist()) == names


def test_idle_connection_is_closed(live, monkeypatch):
    httpd, _ = live
    monkeypatch.setattr(httpd.RequestHandlerClass, "timeout", 0.5)
    with socket.create_connection(("127.0.0.1", httpd.server_port), timeout=5) as s:
        assert s.recv(10) == b""          # the server hung up instead of waiting forever
