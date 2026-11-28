"""SH-1 (2026-11-27, user decision): a copy to hand over keeps the data keys, drops the Telegram lines and the personal entries."""
import zipfile
from pathlib import Path

from terminal import server, share

ROOT = Path(__file__).resolve().parents[1]


def _base(tmp_path):
    base = tmp_path / "proj"
    for rel, text in {"app.py": "print(1)\n", "ops/run.command": "#!/bin/zsh\n", "data/terminal/journal.jsonl": "{\"mine\": 1}\n",
                      "data/terminal/watchlist.json": "[]", "data/terminal/phone_view.json": "{}", "data/terminal/cache/x.json": "{}",
                      "data/qsf/ledger/index.jsonl": "{}\n", "data/qsf/ledger/2026-11-26.jsonl.gz": "z", "research_data/krx_forward/2026-11-26.json.gz": "z",
                      "data/qsf/stance.json": "{}", "data/qsf/rank_rules_switch.json": "{}", "data/qsf/verdict_seals.json": "{}", ".venv/lib/x.py": "", "runs/a.txt": "",
                      "reports/audit_x/evidence/agent_07/watchlist.json": "[]", "reports/RUNBOOK.md": "x",
                      ".env": "# keys\n# TELEGRAM_BOT_TOKEN=old-secret\nDART_API_KEY=dart-value\nexport TELEGRAM_BOT_TOKEN=tg-secret\nTELEGRAM_CHAT_ID = 12345\nSEC_USER_AGENT=\"someone\"\n"}.items():
        p = base / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return base


def test_the_copy_keeps_the_data_keys_and_the_records_and_leaves_out_telegram_and_personal_entries(tmp_path):
    base, out = _base(tmp_path), tmp_path / "out"
    out.mkdir()
    res = share.make(base, out)
    target = next(out.glob("QuantEngine-*.zip"))
    with zipfile.ZipFile(target) as z:
        names = {n[len(share.TOP) + 1:] for n in z.namelist()}
        env = z.read(f"{share.TOP}/.env").decode("utf-8")
        mode = z.getinfo(f"{share.TOP}/ops/run.command").external_attr >> 16
    assert "DART_API_KEY=dart-value" in env and "SEC_USER_AGENT" in env and "TELEGRAM" not in env and "tg-secret" not in env and "12345" not in env
    assert {"app.py", "ops/run.command", ".env", share.README, "data/qsf/ledger/index.jsonl", "data/qsf/ledger/2026-11-26.jsonl.gz",
            "research_data/krx_forward/2026-11-26.json.gz", "data/qsf/verdict_seals.json"} <= names
    assert not names & {"data/qsf/stance.json", "data/qsf/rank_rules_switch.json"}          # the owner's stance and apply buttons stay behind (2026-11-27)
    assert not names & {"data/terminal/journal.jsonl", "data/terminal/watchlist.json", "data/terminal/phone_view.json", "data/terminal/cache/x.json", ".venv/lib/x.py", "runs/a.txt"}
    assert "reports/RUNBOOK.md" in names and not any("/evidence/" in n for n in names) and "old-secret" not in env
    assert mode & 0o111                                                         # a .command file stays one that can be double-clicked
    assert res["keys_held_back"] == ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"] and res["keys_kept"] == ["DART_API_KEY", "SEC_USER_AGENT"]
    said = str(res)
    assert "dart-value" not in said and "tg-secret" not in said and str(Path.home()) not in res["path"]      # names only, never a value
    assert not list(out.glob("*.part"))


def test_a_copy_without_a_key_file_says_so_and_the_request_is_for_the_computer_only(tmp_path):
    base = _base(tmp_path)
    (base / ".env").unlink()
    res = share.make(base, tmp_path)
    assert res["key_file"] is False and "키 없이" in res["text"]
    assert ("POST", "/api/share/make") in server.routes(object())
    js = (ROOT / "terminal" / "static" / "lab.js").read_text(encoding="utf-8")
    assert 'data-rec-backup="share"' in js and "window.confirm" in js and "/api/share/make" in js
    assert (ROOT / "ops" / "처음 설치.command").read_text(encoding="utf-8").startswith("#!/bin/zsh")


def test_a_computer_with_no_way_to_send_counts_a_notice_as_told_and_the_first_page_says_what_to_do_about_warnings():
    from terminal import automation, notify
    assert notify.send_macos("t", "b", platform="win32") == {"status": "NOT_AVAILABLE"}
    assert automation._told({"status": "NOT_AVAILABLE"}) and automation._told({"status": "SENT"})
    assert not automation._told({"status": "FAILED"}) and not automation._told({"status": "NOT_CONFIGURED"}) and not automation._told(None)
    assert 'tg["status"] == "SENT"' not in (ROOT / "terminal" / "automation.py").read_text(encoding="utf-8")
    for word in ("그래도 열기", "추가 정보", "낮에", "Windows는 알림이 전혀 없으므로", "다른 버전으로는 설치되지 않습니다", "하루 호출 한도"):
        assert word in share.README_TEXT
    cmd = (ROOT / "ops" / "처음 설치.command").read_text(encoding="utf-8")
    assert "sys.version_info[:2] == (3, 14)" in cmd and "--managed-python --python 3.14" in cmd and "ops/set_contact.py" in cmd
    assert "com.quantengine.terminal.plist" in cmd                               # a second copy on a computer that already runs one is refused
    assert "screen_only" in (ROOT / "terminal" / "static" / "lab.js").read_text(encoding="utf-8")


def test_the_copy_lands_in_a_folder_of_its_own_under_home_never_on_a_desktop_a_cloud_may_upload(tmp_path, monkeypatch):
    monkeypatch.setattr(share.Path, "home", classmethod(lambda cls: tmp_path))
    (tmp_path / "Desktop").mkdir()
    assert share.default_folder() == tmp_path / share.FOLDER and "Desktop" not in share.default_folder().parts
    res = share.make(_base(tmp_path))
    assert list((tmp_path / share.FOLDER).glob("QuantEngine-*.zip")) and not list((tmp_path / "Desktop").iterdir()) and res["status"] == "REAL"


def test_starting_a_listener_never_asks_the_system_for_the_computers_name(monkeypatch):
    import socket
    monkeypatch.setattr(socket, "getfqdn", lambda *a: (_ for _ in ()).throw(AssertionError("name lookup")))
    for host in ("127.0.0.1", "0.0.0.0"):
        httpd = server._Server((host, 0), server.BaseHTTPRequestHandler)
        assert httpd.server_port == httpd.server_address[1] and httpd.server_name == host
        httpd.server_close()


def test_the_copy_has_one_file_to_press_per_system_beside_the_folder_and_asks_for_no_python(tmp_path):
    """2026-11-28 (user request): unpack, press one file.  The start file copies the program into the home folder and the real
    installer fetches its own Python, so the first page no longer asks the receiver to install anything."""
    res = share.make(_base(tmp_path), tmp_path / "out")
    assert res["status"] == "REAL"
    with zipfile.ZipFile(next((tmp_path / "out").glob("*.zip"))) as z:
        names = set(z.namelist())
        assert {share.README, share.MAC_START, share.WIN_START, f"{share.TOP}/{share.README}"} <= names
        assert (z.getinfo(share.MAC_START).external_attr >> 16) & 0o111
        bat = z.read(share.WIN_START)
        assert bat.startswith(b"@echo off\r\nchcp 65001") and b"\n" not in bat.replace(b"\r\n", b"")
        assert z.read(share.MAC_START).decode("utf-8").startswith("#!/bin/zsh")
    assert "$HOME/QuantEngine" in share.MAC_START_TEXT and "%USERPROFILE%\\QuantEngine" in share.WIN_START_TEXT
    assert "덮어쓰지 않고" in share.MAC_START_TEXT and "덮어쓰지 않고" in share.WIN_START_TEXT          # a folder with records is never copied over
    assert "미리 설치할 필요가 없습니다" in share.README_TEXT and "python.org" not in share.README_TEXT
    assert ".tools" in share.SKIP_DIRS                                            # the fetched Python never rides in a copy made from a copy
    bat1 = (ROOT / "ops" / "windows" / "1 처음 설치.bat").read_text(encoding="utf-8")
    assert "uv.exe venv --managed-python --python 3.14" in bat1 and "ops\\set_contact.py" in bat1 and "terminal-agent install" in bat1
    assert 'start "" http://127.0.0.1:8765' in bat1 and "(" not in "".join(x for x in bat1.splitlines() if x.startswith("echo"))


def test_the_installer_asks_each_computer_for_its_own_contact_and_keeps_it_in_the_key_file_only(tmp_path, monkeypatch, capsys):
    import importlib.util
    spec = importlib.util.spec_from_file_location("set_contact", ROOT / "ops" / "set_contact.py")
    sc = importlib.util.module_from_spec(spec); spec.loader.exec_module(sc)
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)
    monkeypatch.delenv("QE_SKIP_SCHEDULE", raising=False)
    env = tmp_path / ".env"
    env.write_text("OPENDART_API_KEY=k\nSEC_USER_AGENT=\nECOS_API_KEY=e\n", encoding="utf-8")
    assert sc.main(env, ask=lambda _: "", tty=True) == "SKIPPED" and sc.stored(env.read_text(encoding="utf-8")) == ""
    assert sc.main(env, ask=lambda _: "x", tty=False) == "NOT_ASKED"                 # no one at the keyboard: nothing is asked or written
    answers = iter(["not an address", "someone@a-real-domain.kr"])
    assert sc.main(env, ask=lambda _: next(answers), tty=True) == "SAVED"
    text = env.read_text(encoding="utf-8")
    assert text == "OPENDART_API_KEY=k\nSEC_USER_AGENT=QuantEngine someone@a-real-domain.kr\nECOS_API_KEY=e\n"
    assert "someone@" not in capsys.readouterr().out                             # the address is never printed back
    assert sc.main(env, ask=lambda _: 1 / 0, tty=True) == "ALREADY"                  # set once, never asked again
    assert sc.with_value("A=1\n", "v") == "A=1\nSEC_USER_AGENT=v\n"
    _, kept, _ = share.key_file("SEC_USER_AGENT=\nTELEGRAM_BOT_TOKEN=t\n")
    assert kept == ["SEC_USER_AGENT"]
