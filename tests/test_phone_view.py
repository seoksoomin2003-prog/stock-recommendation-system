"""The phone's door (terminal/phone_view.py; user decisions 2026-11-22: Wi-Fi with a pairing code, reading and entries,
the account visible, switched by a button and off by default)."""
import http.client
import json
from datetime import datetime, timedelta, timezone

import pytest

from terminal import phone_view as pv
from terminal import server
from terminal.services import Terminal
from tests.test_terminal_1 import AFTER, fake_src
from tests.test_terminal_1 import _loopback_only  # noqa: F401  (autouse: these tests may reach 127.0.0.1 only)


class Clock:
    def __init__(self):
        self.t = datetime(2026, 11, 23, 9, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.t


# ---------------------------------------------------------------------- who is answered at all
def test_only_private_addresses_and_number_hosts_are_answered():
    assert pv.client_ok("192.168.0.7") and pv.client_ok("10.0.0.3") and pv.client_ok("127.0.0.1") and not pv.client_ok("8.8.8.8") and not pv.client_ok("::1") and not pv.client_ok("x")
    assert pv.host_ok("192.168.0.5:8766", 8766) and pv.host_ok("172.20.1.9:8766", 8766)
    assert not pv.host_ok("192.168.0.5:8765", 8766) and not pv.host_ok("192.168.0.5", 8766) and not pv.host_ok(None, 8766)
    assert not pv.host_ok("my-mac.local:8766", 8766) and not pv.host_ok("evil.example:8766", 8766) and not pv.host_ok("8.8.8.8:8766", 8766)      # a name is never answered (DNS rebinding)
    assert pv.device_name("Mozilla/5.0 (iPhone; CPU iPhone OS 19_0 like Mac OS X)") == "아이폰" and pv.device_name(None) == "기타 기기"


# ---------------------------------------------------------------------- the code and the devices
def test_it_is_off_until_switched_on_and_a_code_pairs_one_device(tmp_path):
    clock = Clock()
    p = pv.PhoneView(tmp_path, port=0, now=clock)
    assert p.status()["on"] is False and p.status()["code"] is None and p.pair("000000", "iPhone") == {"error": "PHONE_CODE_EXPIRED"} and p.device("anything") is None
    with pytest.raises(ValueError, match="PHONE_VIEW_OFF"):
        p.new_code()
    st = p.switch(True)
    code = st["code"]
    assert st["on"] is True and len(code) == 6 and code.isdigit() and st["tries_left"] == pv.CODE_TRIES == 5 and st["devices"] == []
    wrong = "000000" if code != "000000" else "111111"
    assert p.pair(wrong, "iPhone") == {"error": "PHONE_CODE_WRONG"} and p.status()["tries_left"] == 4
    got = p.pair(f" {code} ", "Mozilla/5.0 (iPhone; CPU iPhone OS 19_0)")
    token = got["token"]
    assert len(token) >= 40 and got["max_age"] == 180 * 86400
    st = p.status()
    assert st["code"] is None and [d["name"] for d in st["devices"]] == ["아이폰"] and p.pair(code, "iPhone") == {"error": "PHONE_CODE_EXPIRED"}      # one code, one device
    assert p.device(token) == st["devices"][0]["id"] and p.device(token + "x") is None and p.device(None) is None
    stored = (tmp_path / pv.STATE).read_text(encoding="utf-8")
    assert token not in stored and code not in stored                                               # only the cookie's hash is kept; the used code is gone


def test_five_wrong_tries_or_ten_minutes_close_the_code(tmp_path):
    clock = Clock()
    p = pv.PhoneView(tmp_path, port=0, now=clock)
    code = p.switch(True)["code"]
    wrong = "000000" if code != "000000" else "111111"
    assert [p.pair(wrong, None)["error"] for _ in range(5)] == ["PHONE_CODE_WRONG"] * 4 + ["PHONE_CODE_LOCKED"]
    assert p.pair(code, None) == {"error": "PHONE_CODE_LOCKED"} and p.status()["code"] is None and p.status()["code_state"] == "LOCKED"      # the right code no longer opens
    code = p.new_code()["code"]
    clock.t += timedelta(minutes=pv.CODE_MINUTES, seconds=1)
    assert p.pair(code, None) == {"error": "PHONE_CODE_EXPIRED"} and p.status()["code_state"] == "EXPIRED"
    assert "token" in p.pair(p.new_code()["code"], None)


def test_devices_are_limited_can_be_cut_and_run_out(tmp_path):
    clock = Clock()
    p = pv.PhoneView(tmp_path, port=0, now=clock)
    p.switch(True)
    tokens = [p.pair(p.new_code()["code"], "Android")["token"] for _ in range(pv.MAX_DEVICES)]
    assert p.pair(p.new_code()["code"], "Android") == {"error": "PHONE_TOO_MANY"} and len(p.status()["devices"]) == 5
    first = p.device(tokens[0])
    assert p.unpair(first)["devices"] and p.device(tokens[0]) is None and p.device(tokens[1]) is not None
    clock.t += timedelta(days=pv.DEVICE_DAYS + 1)
    assert p.device(tokens[1]) is None and p.status()["devices"] == []                               # paired 180 days ago: pair again
    clock.t -= timedelta(days=pv.DEVICE_DAYS + 1)
    assert p.device(tokens[2]) is not None
    assert p.switch(False)["on"] is False and p.device(tokens[2]) is None and p.switch(True)["devices"] == []      # off forgets every device


# ---------------------------------------------------------------------- the two listeners
@pytest.fixture()
def live(tmp_path, monkeypatch):
    monkeypatch.setenv("SEC_USER_AGENT", "Research Tool qse-tests@mailbox-test.net")
    t = Terminal(tmp_path, src=fake_src(), now=lambda: AFTER)
    httpd = server.serve(port=0, terminal=t, background=True, phone_port=0)
    yield httpd
    httpd.phone.stop()
    httpd.shutdown()
    httpd.server_close()


def ask(port, method, path, body=None, host=None, cookie=None, origin=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    headers = {"Host": host or f"127.0.0.1:{port}", **({"Cookie": cookie} if cookie else {}), **({"Origin": origin} if origin else {})}
    data = None
    if body is not None:
        data, headers["Content-Type"] = json.dumps(body).encode(), "application/json"
    c.request(method, path, body=data, headers=headers)
    r = c.getresponse()
    raw = r.read()
    c.close()
    try:
        parsed = json.loads(raw)
    except ValueError:
        parsed = raw.decode("utf-8", "replace")
    return r.status, parsed, r.getheader("Set-Cookie")


def test_nothing_listens_for_phones_until_the_button_is_pressed(live):
    local = live.server_port
    code, st, _ = ask(local, "GET", "/api/phone/status")
    assert code == 200 and st["on"] is False and st["listening"] is False and st["addresses"] == [] and live.phone._httpd is None
    assert ask(local, "POST", "/api/phone/code", {})[:2] == (400, {"error": "PHONE_VIEW_OFF"})
    code, st, _ = ask(local, "POST", "/api/phone/switch", {"on": True})
    assert code == 200 and st["on"] is True and st["listening"] is True and len(st["code"]) == 6 and live.phone._httpd.server_address[0] == "0.0.0.0"
    assert live.server_address[0] == "127.0.0.1"                                                     # the terminal's own listener never moves


def test_an_unpaired_device_sees_the_pairing_page_and_nothing_else(live):
    code = ask(live.server_port, "POST", "/api/phone/switch", {"on": True})[1]["code"]
    port = live.phone.port
    status, page, _ = ask(port, "GET", "/")
    assert status == 200 and "연결 코드" in page and "app.js" not in page
    assert ask(port, "GET", "/app.js")[1] == page and ask(port, "GET", "/index.html")[1] == page    # not one file of the terminal
    for method, path in (("GET", "/api/health"), ("GET", "/api/portfolio"), ("GET", "/api/phone/status"), ("POST", "/api/watchlist/add"), ("POST", "/api/phone/switch")):
        assert ask(port, method, path, {} if method == "POST" else None)[:2] == (401, {"error": "PHONE_NOT_PAIRED"}), path
    assert ask(port, "GET", "/", host=f"evil.example:{port}")[:2] == (403, {"error": "FORBIDDEN_HOST"})
    assert ask(port, "POST", "/api/phone/pair", {"code": code}, origin="http://evil.example")[:2] == (403, {"error": "FORBIDDEN_ORIGIN"})
    wrong = "000000" if code != "000000" else "111111"
    assert ask(port, "POST", "/api/phone/pair", {"code": wrong})[:2] == (403, {"error": "PHONE_CODE_WRONG"})
    assert ask(port, "GET", "/api/health", cookie=f"{pv.COOKIE}=made-up")[:2] == (401, {"error": "PHONE_NOT_PAIRED"})


def test_a_paired_phone_reads_and_makes_entries_and_the_rest_stays_on_the_computer(live):
    local = live.server_port
    code = ask(local, "POST", "/api/phone/switch", {"on": True})[1]["code"]
    port = live.phone.port
    status, body, cookie = ask(port, "POST", "/api/phone/pair", {"code": code}, origin=f"http://127.0.0.1:{port}")
    assert status == 200 and body == {"status": "OK"} and cookie.startswith(f"{pv.COOKIE}=") and "HttpOnly" in cookie and "SameSite=Strict" in cookie and "Max-Age=15552000" in cookie
    mine = cookie.split(";")[0]
    assert ask(port, "GET", "/api/health", cookie=mine)[0] == 200
    status, page, _ = ask(port, "GET", "/", cookie=mine)
    assert status == 200 and "app.js" in page and "연결 코드" not in page                              # the terminal itself now
    origin = f"http://127.0.0.1:{port}"
    assert ask(port, "POST", "/api/watchlist/add", {"ticker": "MSFT", "market": "US"}, cookie=mine, origin=origin)[0] == 200
    assert ask(port, "POST", "/api/watchlist/add", {"ticker": "MSFT", "market": "US"}, cookie=mine, origin="http://evil.example")[:2] == (403, {"error": "FORBIDDEN_ORIGIN"})
    for path in ("/api/settings", "/api/capital", "/api/qsf/fund-period", "/api/qsf/rank-rules", "/api/qsf/turnover-rules", "/api/automation/run", "/api/lab/run", "/api/model/scan",
                 "/api/phone/switch", "/api/phone/code", "/api/phone/unpair"):
        assert ask(port, "POST", path, {"on": True}, cookie=mine, origin=origin)[:2] == (403, {"error": "PHONE_MAC_ONLY"}), path
    assert ask(port, "GET", "/api/phone/status", cookie=mine)[:2] == (200, {"on": True, "available": False, "phone": True})      # no code, no other device
    assert [d["name"] for d in ask(local, "GET", "/api/phone/status")[1]["devices"]] == ["기타 기기"]
    # switching off closes the door and forgets the phone
    assert ask(local, "POST", "/api/phone/switch", {"on": False})[1]["listening"] is False
    with pytest.raises(OSError):
        ask(port, "GET", "/api/health", cookie=mine)
    assert ask(local, "POST", "/api/phone/switch", {"on": True})[1]["devices"] == []
    assert ask(live.phone.port, "GET", "/api/health", cookie=mine)[:2] == (401, {"error": "PHONE_NOT_PAIRED"})


def test_the_door_reopens_after_a_restart_only_when_it_was_left_on(tmp_path, monkeypatch):
    monkeypatch.setenv("SEC_USER_AGENT", "Research Tool qse-tests@mailbox-test.net")
    t = Terminal(tmp_path, src=fake_src(), now=lambda: AFTER)
    a = server.serve(port=0, terminal=t, background=True, phone_port=0, phone_listener=True)
    try:
        assert a.phone._httpd is None                                                                 # never switched on: nothing opens at start
        a.phone.switch(True)
    finally:
        a.phone.stop(); a.shutdown(); a.server_close()
    b = server.serve(port=0, terminal=t, background=True, phone_port=0, phone_listener=True)
    try:
        assert b.phone._httpd is not None and b.phone.status()["on"] is True
    finally:
        b.phone.stop(); b.shutdown(); b.server_close()
    c = server.serve(port=0, terminal=t, background=True, phone_port=0)                               # a scratch server does not open it by itself
    try:
        assert c.phone._httpd is None
    finally:
        c.shutdown(); c.server_close()


def test_every_changing_request_is_either_a_phone_entry_or_named_as_computer_only():
    posts = {path for (method, path) in server.routes(object()) if method == "POST"}
    assert pv.PHONE_WRITES <= posts
    assert posts - pv.PHONE_WRITES == {"/api/settings", "/api/capital", "/api/qsf/rank-rules", "/api/qsf/turnover-rules", "/api/automation/run", "/api/lab/run",
                                       "/api/model/scan", "/api/phone/switch", "/api/phone/code", "/api/phone/unpair",
                                       "/api/qsf/stance", "/api/qsf/fund-period"}      # a new changing request must be put on one side (the stance sizes orders: a setting)
