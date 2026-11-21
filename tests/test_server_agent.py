"""The launchd agent that keeps the terminal server running (no real launchctl calls)."""
import plistlib
import subprocess
from types import SimpleNamespace

from terminal import server_agent

TOKEN = "123456:ABCdefGHIjklMNOpqrSTUvwxYZ_secret"


def test_plist_restarts_with_throttle_and_holds_no_secret(tmp_path, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", TOKEN)
    base = tmp_path / "with space"
    raw = server_agent.plist_bytes(base)
    pl = plistlib.loads(raw)
    assert pl["Label"] == "com.quantengine.terminal"
    assert pl["RunAtLoad"] is True and pl["KeepAlive"] is True and pl["ThrottleInterval"] >= 10
    cmd = pl["ProgramArguments"][2]
    assert pl["ProgramArguments"][:2] == ["/bin/zsh", "-lc"]
    assert "app.py terminal --port 8765" in cmd and "'" in cmd and "--open" not in cmd
    assert "StandardOutPath" not in pl and "launchd.log" in cmd and "mv -f" in cmd     # the shell rotates the start-up log
    assert TOKEN.encode() not in raw and "EnvironmentVariables" not in pl


def test_rotation_shell_snippet_runs(tmp_path):
    """The rotate-then-append part of the command, run for real with a stand-in for the server."""
    log = server_agent.log_path(tmp_path)
    log.parent.mkdir(parents=True)
    log.write_bytes(b"x" * (server_agent.LOG_MAX_BYTES + 1))
    cmd = plistlib.loads(server_agent.plist_bytes(tmp_path))["ProgramArguments"][2]
    cmd = cmd.split("exec ")[0] + f"echo started >> '{log}'"
    subprocess.run(["/bin/zsh", "-c", cmd], check=True)
    assert log.read_text() == "started\n" and log.with_name("launchd.log.1").stat().st_size > server_agent.LOG_MAX_BYTES


def test_install_and_uninstall_use_launchctl_only_on_own_plist(tmp_path, monkeypatch):
    calls = []
    plist = tmp_path / "LaunchAgents" / "com.quantengine.terminal.plist"
    monkeypatch.setattr(server_agent, "plist_path", lambda: plist)
    monkeypatch.setattr(server_agent, "_launchctl", lambda *a: calls.append(a) or SimpleNamespace(returncode=0, stderr="", stdout=""))
    res = server_agent.install(tmp_path)
    assert res["installed"] and plist.exists() and server_agent.log_path(tmp_path).parent.is_dir()
    assert [c[0] for c in calls] == ["bootout", "bootstrap"] and all(c[-1] == str(plist) for c in calls)
    server_agent.uninstall()
    assert not plist.exists() and calls[-1][0] == "bootout"


def test_status_reads_state_and_pid(tmp_path, monkeypatch):
    plist = tmp_path / "x.plist"
    plist.write_bytes(b"")
    out = "com.quantengine.terminal = {\n\tstate = running\n\tpid = 4242\n\truns = 3\n\tlast exit code = 0\n}"
    monkeypatch.setattr(server_agent, "plist_path", lambda: plist)
    monkeypatch.setattr(server_agent, "_launchctl", lambda *a: SimpleNamespace(returncode=0, stderr="", stdout=out))
    st = server_agent.status(tmp_path)
    assert st["installed"] and st["state"] == "running" and st["pid"] == 4242 and st["runs"] == 3 and st["last_exit_code"] == 0
    monkeypatch.setattr(server_agent, "_launchctl", lambda *a: SimpleNamespace(returncode=113, stderr="", stdout=""))
    assert server_agent.status(tmp_path)["installed"] is False


def test_a_device_without_launchctl_reads_as_not_installed(monkeypatch):
    """Off a Mac there is no launchctl: the status question raised FileNotFoundError and the status screen answered with an error."""
    from terminal import automation

    def missing(*a, **k):
        raise FileNotFoundError("launchctl")
    monkeypatch.setattr(automation.subprocess, "run", missing)
    res = automation._launchctl("print", "gui/501/x")
    assert res.returncode == 127 and res.stderr == "NO_LAUNCHCTL"
