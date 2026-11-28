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
                      "reports/audit_x/evidence/agent_07/watchlist.json": "[]", "reports/RUNBOOK.md": "x", "reports/audit_x/AGENT_08.md": "the owner holds 005930",
                      "reports/QSF_X_PROTOCOL.md": "rules", "reports/AUDIT_2026.md": "about the owner", "reports/qsf/QSF_ONE.json": "{}", "reports/qsf/deep/x.json": "{}",
                      "tracking/ledger/observations.jsonl": "{\"capital\": 1}\n", "docs/setup.md": "x", "notes.md": f"see {Path.home()}/somewhere",
                      ".env": "# keys\n# TELEGRAM_BOT_TOKEN=old-secret\nDART_API_KEY=dart-value\nexport TELEGRAM_BOT_TOKEN=tg-secret\nTELEGRAM_CHAT_ID = 12345\nSEC_USER_AGENT=\"App owner@owner-domain.kr\"\nQPP_CAPITAL=777000\nQPP_CAPITAL_KRW=888000\nQPP_BACKUP_DIR=/somewhere\n"}.items():
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
    assert "DART_API_KEY=dart-value" in env and "TELEGRAM" not in env and "tg-secret" not in env and "12345" not in env
    # 2026-11-29 (user decision after the hand-over audit): the capital, the SEC contact and the owner's folder lines stay home
    assert "SEC_USER_AGENT" not in env and "owner@" not in env and "QPP_CAPITAL" not in env and "777000" not in env and "888000" not in env and "QPP_BACKUP_DIR" not in env
    # ... and so do the audit texts about the owner's terminal, the baseline scan record and a text that spells out the home folder
    assert {"reports/QSF_X_PROTOCOL.md", "reports/qsf/QSF_ONE.json"} <= names
    assert not names & {"reports/audit_x/AGENT_08.md", "reports/AUDIT_2026.md", "reports/qsf/deep/x.json", "tracking/ledger/observations.jsonl", "docs/setup.md", "notes.md"}
    assert res["files_naming_this_computer"] == ["notes.md"]
    assert {"app.py", "ops/run.command", ".env", share.README, "data/qsf/ledger/index.jsonl", "data/qsf/ledger/2026-11-26.jsonl.gz",
            "research_data/krx_forward/2026-11-26.json.gz", "data/qsf/verdict_seals.json"} <= names
    assert not names & {"data/qsf/stance.json", "data/qsf/rank_rules_switch.json"}          # the owner's stance and apply buttons stay behind (2026-11-27)
    assert not names & {"data/terminal/journal.jsonl", "data/terminal/watchlist.json", "data/terminal/phone_view.json", "data/terminal/cache/x.json", ".venv/lib/x.py", "runs/a.txt"}
    assert "reports/RUNBOOK.md" in names and not any("/evidence/" in n for n in names) and "old-secret" not in env
    assert mode & 0o111                                                         # a .command file stays one that can be double-clicked
    assert res["keys_held_back"] == ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "SEC_USER_AGENT", "QPP_CAPITAL", "QPP_CAPITAL_KRW", "QPP_BACKUP_DIR"] and res["keys_kept"] == ["DART_API_KEY"]
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
    assert "TZ=Asia/Seoul date +%H" in cmd and "매일 수집은 이미 등록돼 있어" in cmd       # no night registration; a running collection is not restarted
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
    assert "update_from.py" in share.MAC_START_TEXT and "update_from.py" in share.WIN_START_TEXT and '"%DST%.part"' in share.WIN_START_TEXT
    assert "미리 설치할 필요가 없습니다" in share.README_TEXT and "python.org" not in share.README_TEXT
    assert ".tools" in share.SKIP_DIRS                                            # the fetched Python never rides in a copy made from a copy
    bat1 = (ROOT / "ops" / "windows" / "1 처음 설치.bat").read_text(encoding="utf-8")
    assert "uv.exe venv --managed-python --python 3.14" in bat1 and "ops\\set_contact.py" in bat1 and "terminal-agent install" in bat1 and "goto noreg" in bat1
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
    text, kept, held = share.key_file("SEC_USER_AGENT=QuantEngine receiver@a-real-domain.kr\nTELEGRAM_BOT_TOKEN=t\nECOS_API_KEY=e\n")
    assert kept == ["ECOS_API_KEY"] and "receiver@" not in text                   # a receiver who makes a copy does not pass their address on


def test_a_newer_copy_changes_the_program_files_only_and_asks_first(tmp_path, capsys):
    import importlib.util
    spec = importlib.util.spec_from_file_location("update_from", ROOT / "ops" / "update_from.py")
    up = importlib.util.module_from_spec(spec); spec.loader.exec_module(up)
    src, dst = tmp_path / "new", tmp_path / "old"
    for base, mark in ((src, "new"), (dst, "old")):
        for rel in ("app.py", "terminal/x.py", "data/loader.py", ".env", "data/qsf/ledger/index.jsonl", "research_data/a/b.json", "tracking/t.jsonl", "reports/qsf/QSF_A.json", "reports/RUNBOOK.md"):
            (base / rel).parent.mkdir(parents=True, exist_ok=True)
            (base / rel).write_text(mark, encoding="utf-8")
    (src / "terminal" / "added.py").write_text("new", encoding="utf-8")
    read = lambda rel: (dst / rel).read_text(encoding="utf-8")
    assert up.main(src, dst, ask=lambda _: "y", tty=False) == "NOT_ASKED" and read("app.py") == "old"
    assert up.main(src, dst, ask=lambda _: "", tty=True) == "KEPT" and read("app.py") == "old"
    assert up.main(src, dst, ask=lambda _: "y", tty=True, is_running=lambda _: {"pid": 1}) == "BUSY" and read("app.py") == "old"      # never under a running collection
    assert up.main(src, dst, ask=lambda _: "y", tty=True, is_running=lambda _: None) == "UPDATED"
    assert [read(r) for r in ("app.py", "terminal/x.py", "terminal/added.py", "reports/RUNBOOK.md", "data/loader.py")] == ["new"] * 5      # data/ is also a package of the program
    assert [read(r) for r in (".env", "data/qsf/ledger/index.jsonl", "research_data/a/b.json", "tracking/t.jsonl", "reports/qsf/QSF_A.json")] == ["old"] * 5
    assert up.main(src, src, ask=lambda _: "y", tty=True) == "NOT_A_PAIR"


def test_without_the_sec_contact_the_us_scores_are_skipped_with_the_reason_and_run_once_it_is_set(monkeypatch):
    from terminal import automation, record_status
    assert "연락처 입력" in automation.NO_SEC
    src = (ROOT / "terminal" / "automation.py").read_text(encoding="utf-8")
    assert src.count('if not sec_ready():') == 2 and 'for n in ("QSF", "US_CHALLENGER") if (steps.get(n) or {}).get("detail") == NO_SEC' in src
    said = record_status.alerts({}, {"capital_configured": True, "status": "REAL"}, {"installed": True, "sec_configured": False}, "OK")
    assert any("SEC 연락처" in a["text"] and a["level"] == "bad" for a in said)
    assert not any("SEC 연락처" in a["text"] for a in record_status.alerts({}, {"capital_configured": True, "status": "REAL"}, {"installed": True, "sec_configured": True}, "OK"))
    for name in ("연락처 입력.command", "자동 실행 해제.command"):
        assert (ROOT / "ops" / name).read_text(encoding="utf-8").startswith("#!/bin/zsh")
    assert ".venv" not in (ROOT / "ops" / "자동 실행 해제.command").read_text(encoding="utf-8")      # works after the folder was moved: no Python of the folder is needed
    # the key file is read as it is written by the installer, by hand, or with an export prefix; an empty line does not hide a set one
    assert automation.sec_in_key_file('SEC_USER_AGENT=\nexport SEC_USER_AGENT="QuantEngine someone@a-real-domain.kr"\n')
    assert not automation.sec_in_key_file("SEC_USER_AGENT=\n") and not automation.sec_in_key_file("SEC_USER_AGENT_OTHER=QuantEngine someone@a-real-domain.kr\n")
    assert not automation.sec_in_key_file("# SEC_USER_AGENT=QuantEngine someone@a-real-domain.kr\n")
    from utils import runtime_config
    assert runtime_config.sec_user_agent_status("QuantEngine kimyouri@a-real-domain.kr")["status"] == "CONFIGURED"      # "your" inside a name is not the template
    assert runtime_config.sec_user_agent_status("App/1.0 <your e-mail>")["status"] == "INVALID" and runtime_config.sec_user_agent_status("App your real e-mail x@a-real-domain.kr")["status"] == "INVALID"


def test_the_daily_job_skips_both_us_score_steps_without_the_contact_and_runs_them_once_it_is_there(tmp_path, monkeypatch):
    from terminal import automation
    asked = []
    d = automation.Daily(tmp_path, runner=lambda n, a: asked.append(n) or 0)
    monkeypatch.setattr(automation, "sec_ready", lambda: False)
    for name in ("QSF", "US_CHALLENGER"):
        got = d._step(name, "2026-11-27")
        assert got["status"] == automation.SKIPPED and got["detail"] == automation.NO_SEC
    assert asked == []                                                          # no 20-minute scan that could record nothing
    monkeypatch.setattr(automation, "sec_ready", lambda: True)
    assert d._step("QSF", "2026-11-27")["status"] == automation.OK and asked == ["QSF"]


def test_a_record_behind_makes_the_buy_check_wait_and_a_holiday_week_does_not(monkeypatch):
    from datetime import datetime, timezone
    from terminal import assistant, record_status

    class Q:
        def __init__(self, now): self._now = now
        def now(self): return self._now

    class T:
        def __init__(self, now): self.qsf = Q(now)

    mon = T(datetime(2026, 11, 30, 12, 0, tzinfo=timezone.utc))               # Monday midday UTC: Friday 11-27 is the last finished US session
    assert assistant._behind(mon, "US", "2026-11-27") == 0 and assistant._behind(mon, "US", "2026-11-25") == 1      # 11-26 was Thanksgiving
    assert assistant._behind(mon, "US", "2026-11-20") >= assistant.STALE_SESSIONS
    monkeypatch.setattr(record_status, "_kr_calendar", lambda q: ["2026-09-23", "2026-09-24", "2026-09-30"])      # a holiday week: one session in six days
    assert assistant._behind(mon, "KR", "2026-09-24") == 1                      # six calendar days, one session: not stale
    monkeypatch.setattr(record_status, "_kr_calendar", lambda q: None)
    assert assistant._behind(mon, "KR", "2026-09-24") is None and assistant._behind(mon, "COIN", "2026-09-24") is None      # unknown is never read as stale
    snap = {"score": 80.0, "entry_status": "ENTRY_NOW", "actionability": "ACTIONABLE", "price": 100.0, "data_date": "2026-11-20", "confidence": "HIGH"}
    args = dict(gates=[], marks=[], earnings={}, soon=False, level="NORMAL", wide=[], state={}, held=False)
    late = assistant.buy_verdict(snap, "SWING", "US", **args, behind=5)
    assert late["key"] == "WAIT" and "5거래일 뒤처져" in str(late) and "2026-11-20" in str(late)
    assert "뒤처져" not in str(assistant.buy_verdict(snap, "SWING", "US", **args, behind=1)) and "뒤처져" not in str(assistant.buy_verdict(snap, "SWING", "US", **args))


def test_a_holding_without_a_price_is_not_called_an_unrecorded_account():
    from terminal import assistant
    plan = {"status": "NO_ACCOUNT", "candidates": 4, "candidates_by": {}, "price_missing": ["GONE"], "reason": "보유 종목 GONE의 시세를 받지 못해 계좌 평가액을 계산하지 못했습니다."}
    one = assistant.plan_items(plan, "US")[0]
    assert one["level"] == "DUE" and "GONE" in one["text"] and "기록돼 있지 않아" not in one["text"] and "시세 누락" in one["short"]
    none = assistant.plan_items({"status": "NO_ACCOUNT", "candidates": 4, "candidates_by": {}}, "US")[0]
    assert none["level"] == "INFO" and "기록돼 있지 않아" in none["text"]
    js = (ROOT / "terminal" / "static" / "qsf.js").read_text(encoding="utf-8")
    assert "(d.price_missing || []).length" in js
