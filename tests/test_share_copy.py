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
                      "data/qsf/stance.json": "{}", ".venv/lib/x.py": "", "runs/a.txt": "",
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
            "research_data/krx_forward/2026-11-26.json.gz", "data/qsf/stance.json"} <= names
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
