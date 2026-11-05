"""Daily automation (TERMINAL-4): challenger record, P6-11B scan and tracking, backup, alerts.

Each step runs in its own process (memory is returned between steps on an 8GB machine) and at most once per
completed US session, so the schedule can fire several times a day: later firings only retry what failed.
A day that is never run cannot be recorded afterwards (no backfill), so missed sessions are reported.
"""
import fcntl
import hashlib
import json
import os
import plistlib
import shlex
import shutil
import subprocess
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from terminal import notify
from utils import nyse_calendar

LABEL = "com.quantengine.daily"
SCHEDULE = ((7, 10), (8, 10), (12, 10), (20, 10))     # KST: the US close is 06:00-07:00, later slots are retries
STEP_TIMEOUT = 45 * 60
KEEP_BACKUPS = 60
KEEP_SESSIONS = 40
OK, FAILED, SKIPPED = "OK", "FAILED", "SKIPPED"
STEP_NAMES = {"LAB": "도전자 기록", "SCAN": "P6-11B 스캔", "TRACK": "P6-20 추적 갱신", "QSF": "QSF 점수 기록(미국)", "QSF_KR": "QSF 점수 기록(한국)", "BACKUP": "백업"}
BACKUP_GLOBS = ("data/terminal/journal.jsonl", "data/terminal/settings.json", "data/terminal/watchlist.json",
                "data/lab/ledger.jsonl", "tracking/*.jsonl", "tracking/excluded_runs.json", "tracking/ledger/*.jsonl",
                "tracking/kr/*.jsonl", "data/qsf/ledger/index.jsonl")


def backup_root() -> Path:
    return Path(os.getenv("QPP_BACKUP_DIR") or Path.home() / "QuantEngineBackups")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def backup(base: Path, day: str, root: Optional[Path] = None) -> Dict[str, Any]:
    """Copy personal records to a dated folder OUTSIDE the project, verify each copy, keep the newest folders."""
    root = Path(root or backup_root())
    tmp = root / f".{day}.partial"
    shutil.rmtree(tmp, ignore_errors=True)
    n = 0
    for pattern in BACKUP_GLOBS:
        for src in sorted(base.glob(pattern)):
            dst = tmp / src.relative_to(base)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            if _sha(src) != _sha(dst):
                raise OSError("backup verification failed")
            n += 1
    # QSF shards are immutable and large, so they are mirrored once instead of copied into every dated folder.
    mirror = root / "qsf_ledger"
    for src in sorted((base / "data" / "qsf" / "ledger").glob("*.jsonl.gz")):
        dst = mirror / src.name
        if not dst.exists():
            mirror.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            if _sha(src) != _sha(dst):
                raise OSError("backup verification failed")
            n += 1
    tmp.mkdir(parents=True, exist_ok=True)
    final = root / day
    shutil.rmtree(final, ignore_errors=True)
    tmp.rename(final)
    folders = sorted(p for p in root.iterdir() if p.is_dir() and _is_date_name(p.name))
    for old in folders[:-KEEP_BACKUPS]:
        shutil.rmtree(old, ignore_errors=True)
    return {"files": n, "path": str(final)}


def _is_date_name(name: str) -> bool:
    """Only folders named like a date are ever pruned; anything else in the backup folder is left alone."""
    try:
        return datetime.strptime(name, "%Y-%m-%d").strftime("%Y-%m-%d") == name
    except ValueError:
        return False


class Daily:
    def __init__(self, base: Path, now: Callable[[], datetime] = None, runner: Callable = None,
                 telegram: Callable = None, macos: Callable = None, terminal: Any = None, backup_dir: Path = None):
        self.base = Path(base)
        self.dir = self.base / "data" / "automation"
        self.state_file = self.dir / "state.json"
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.runner = runner or self._run_process
        self.telegram = telegram or notify.send_telegram
        self.macos = macos or notify.send_macos
        self._terminal = terminal
        self.backup_dir = backup_dir

    # ------------------------------------------------------------------ state
    def state(self) -> Dict[str, Any]:
        try:
            return json.loads(self.state_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"sessions": {}, "alerts": [], "notified": {}}

    def _save(self, st: Dict[str, Any]) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        keep = sorted(st["sessions"])[-KEEP_SESSIONS:]
        st["sessions"] = {k: st["sessions"][k] for k in keep}
        tmp = self.state_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.state_file)

    @contextmanager
    def _exclusive(self):
        self.dir.mkdir(parents=True, exist_ok=True)
        with open(self.dir / "run.lock", "w") as fh:
            try:
                fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                yield False
                return
            yield True

    # ------------------------------------------------------------------ steps
    def _run_process(self, name: str, argv: List[str]) -> int:
        logs = self.dir / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        with open(logs / f"{self.now().date().isoformat()}.log", "a", encoding="utf-8") as fh:
            fh.write(f"\n=== {name} {self.now().isoformat()}\n")
            fh.flush()
            try:
                return subprocess.run([sys.executable, str(self.base / "app.py"), *argv], cwd=self.base, stdout=fh,
                                      stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, timeout=STEP_TIMEOUT).returncode
            except subprocess.TimeoutExpired:
                fh.write("timeout\n")
                return 124

    def _lab_recorded(self, session: str) -> bool:
        from terminal.lab.service import Lab
        recs, integ = Lab(self.base, now=self.now).read_ledger()
        return integ["status"] == "OK" and any(r["signal_session"] == session for r in recs)

    def _step(self, name: str, session: str) -> Dict[str, Any]:
        at = self.now().isoformat()
        try:
            if name == "LAB":
                rc = self.runner(name, ["lab", "update"])
                good = rc == 0 and self._lab_recorded(session)      # exit 0 alone does not prove today's record exists
                return {"status": OK if good else FAILED, "at": at, "detail": None if good else f"기록 안 됨 (코드 {rc})"}
            if name == "SCAN":
                if not os.getenv("QPP_CAPITAL", "").strip():
                    return {"status": SKIPPED, "at": at, "detail": "QPP_CAPITAL 미설정"}
                rc = self.runner(name, ["scan"])
                return {"status": OK if rc == 0 else FAILED, "at": at, "detail": self._scan_status() if rc == 0 else f"코드 {rc}"}
            if name == "TRACK":
                rc = self.runner(name, ["track"])
                return {"status": OK if rc == 0 else FAILED, "at": at, "detail": None if rc == 0 else f"코드 {rc}"}
            if name == "QSF":
                rc = self.runner(name, ["qsf", "scan"])
                return {"status": OK if rc == 0 else FAILED, "at": at, "detail": None if rc == 0 else "데이터 미준비" if rc == 3 else f"코드 {rc}"}
            if name == "QSF_KR":
                rc = self.runner(name, ["--market", "KR", "qsf", "scan"])
                return {"status": OK if rc == 0 else FAILED, "at": at, "detail": None if rc == 0 else "데이터 미준비" if rc == 3 else f"코드 {rc}"}
            res = backup(self.base, session, self.backup_dir)
            return {"status": OK, "at": at, "detail": f"{res['files']}개 파일"}
        except Exception as exc:                                    # one failed step never stops the others
            return {"status": FAILED, "at": at, "detail": type(exc).__name__}

    def _scan_status(self) -> Optional[str]:
        runs = sorted((self.base / "runs").glob("*_market_scan_*"), key=lambda p: p.name)
        if not runs:
            return None
        try:
            return json.loads((runs[-1] / "execution_status.json").read_text(encoding="utf-8")).get("display_status")
        except (OSError, ValueError):
            return None

    # ------------------------------------------------------------------ alerts and gaps
    def _alerts(self) -> Dict[str, Any]:
        try:
            if self._terminal is None:
                from terminal.services import Terminal
                self._terminal = Terminal(self.base, now=self.now)
            pf = self._terminal.portfolio()
        except Exception as exc:
            return {"status": "UNAVAILABLE", "error": type(exc).__name__, "items": [], "stale": []}
        if pf["integrity"]["status"] != "OK":
            return {"status": "INTEGRITY", "items": [], "stale": []}
        stale = [f"{h['ticker']} ({h['date'] or '시세 없음'})" for h in pf["holdings"] if h["status"] != "REAL"]
        return {"status": "OK", "items": pf["alerts"], "stale": stale}

    def missing_sessions(self, session: str) -> List[str]:
        from terminal.lab.service import Lab
        recs, _ = Lab(self.base, now=self.now).read_ledger()
        have = {r["signal_session"] for r in recs}
        if not have:
            return []
        return [d.isoformat() for d in nyse_calendar.sessions_between(min(have), session) if d.isoformat() not in have]

    @staticmethod
    def compose(session: str, steps: Dict[str, Dict[str, Any]], alerts: Dict[str, Any], prev: List[str],
                missing: List[str]) -> str:
        icon = {OK: "✅", FAILED: "❌", SKIPPED: "⏭"}
        lines = [f"📊 퀀트 터미널 일일 요약 (기준 거래일 {session})", "", "[작업]"]
        for name, label in STEP_NAMES.items():
            s = steps.get(name) or {}
            lines.append(f"{icon.get(s.get('status'), '·')} {label}" + (f": {s['detail']}" if s.get("detail") else ""))
        if any((steps.get(n) or {}).get("status") == FAILED for n in STEP_NAMES):
            lines.append("실패한 작업은 다음 예약 시각에 다시 시도합니다.")
        if (steps.get("SCAN") or {}).get("status") == SKIPPED:
            lines.append("P6-11B는 오늘 기록이 없습니다. .env에 QPP_CAPITAL을 설정하면 매일 스캔합니다.")
        lines += ["", "[포트폴리오 경고]"]
        if alerts["status"] == "INTEGRITY":
            lines.append("🚨 거래 기록 무결성 오류: 터미널에서 확인이 필요합니다.")
        elif alerts["status"] != "OK":
            lines.append("⚠️ 경고를 계산하지 못했습니다 (시세 또는 기록을 읽지 못함).")
        elif not alerts["items"]:
            lines.append("없음")
        else:
            mark = {"bad": "🚨", "warn": "⚠️", "info": "🎯"}
            new = [a for a in alerts["items"] if _key(a) not in prev]
            old = [a for a in alerts["items"] if _key(a) in prev]
            lines += [f"{mark[a['level']]} {a['text']}" for a in new]
            if old:
                lines.append("계속되는 경고:")
                lines += [f"  · {a['text']}" for a in old]
        if alerts.get("stale"):
            lines.append("오래되었거나 없는 시세로 계산: " + ", ".join(alerts["stale"]))
        if missing:
            lines += ["", f"⚠️ 도전자 기록이 빠진 거래일 {len(missing)}일: {', '.join(missing[-5:])}",
                      "지난 날짜는 소급 기록하지 않습니다."]
        lines += ["", "일봉 종가 기준 자동 계산이며 주문은 실행하지 않습니다."]
        return "\n".join(lines)

    # ------------------------------------------------------------------ run
    def run(self, resend: bool = False) -> Dict[str, Any]:
        with self._exclusive() as got:
            if not got:
                return {"status": "ALREADY_RUNNING"}
            return self._run(resend)

    def _run(self, resend: bool) -> Dict[str, Any]:
        session = nyse_calendar.latest_completed_session(self.now()).isoformat()
        st = self.state()
        steps = st["sessions"].setdefault(session, {})
        pending = [n for n in STEP_NAMES if (steps.get(n) or {}).get("status") not in (OK, SKIPPED)]
        if "LAB" not in pending and not self._lab_recorded(session):
            pending.insert(0, "LAB")                # a voided or missing record is retried even if it once reported OK
        if (steps.get("SCAN") or {}).get("status") == SKIPPED and os.getenv("QPP_CAPITAL", "").strip():
            pending.append("SCAN")                  # a skipped scan runs as soon as capital is configured
        delivered = (st.get("notified") or {}).get("session") == session
        if not pending and delivered and not resend:
            return {"status": "UP_TO_DATE", "session": session}
        for name in pending:
            steps[name] = self._step(name, session)
            self._save(st)
        alerts = self._alerts()
        prev = st.get("alerts") or []
        missing = self.missing_sessions(session)
        text = self.compose(session, steps, alerts, prev, missing)
        sig = hashlib.sha256(text.encode("utf-8")).hexdigest()
        notified = st.get("notified") or {}
        out = {"status": "DONE", "session": session, "steps": steps, "telegram": None, "macos": None}
        if resend or notified.get("signature") != sig:
            out["telegram"] = self.telegram(text)
            failures = [STEP_NAMES[n] for n in STEP_NAMES if (steps.get(n) or {}).get("status") == FAILED]
            urgent = sum(1 for a in alerts["items"] if a["level"] == "bad")
            body = (f"실패: {', '.join(failures)}. " if failures else "") + f"경고 {len(alerts['items'])}건" + \
                   (f", 긴급 {urgent}건" if urgent else "")
            out["macos"] = self.macos(f"퀀트 터미널 {session}", body)
            ok = out["telegram"]["status"] == "SENT" if out["telegram"]["status"] != "NOT_CONFIGURED" \
                else out["macos"]["status"] == "SENT"
            if ok:
                st["notified"] = {"session": session, "signature": sig, "at": self.now().isoformat()}
                st["alerts"] = sorted(_key(a) for a in alerts["items"])    # "new" clears only once actually delivered
        st["last_run"] = {"at": self.now().isoformat(), "session": session, "telegram": out["telegram"],
                          "macos": out["macos"], "missing_sessions": missing}
        self._save(st)
        return out


def _key(a: Dict[str, Any]) -> str:
    return f"{a['code']}:{a.get('ticker') or a['text']}"


# ---------------------------------------------------------------------- launchd
def plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def plist_bytes(base: Path) -> bytes:
    """A login shell supplies the user's environment: nothing secret is copied into the plist."""
    py = shlex.quote(sys.executable)
    cmd = f"cd {shlex.quote(str(base))} && exec {py} app.py automation run"
    logs = base / "data" / "automation"
    return plistlib.dumps({
        "Label": LABEL, "ProgramArguments": ["/bin/zsh", "-lc", cmd], "RunAtLoad": True,
        "StartCalendarInterval": [{"Hour": h, "Minute": m} for h, m in SCHEDULE],
        "StandardOutPath": str(logs / "launchd.log"), "StandardErrorPath": str(logs / "launchd.log"),
        "ProcessType": "Background"})


def _launchctl(*args: str):
    return subprocess.run(["launchctl", *args], capture_output=True, text=True)


def install(base: Path) -> Dict[str, Any]:
    (base / "data" / "automation").mkdir(parents=True, exist_ok=True)
    p = plist_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    domain = f"gui/{os.getuid()}"
    _launchctl("bootout", domain, str(p))                     # a reinstall replaces the old definition
    p.write_bytes(plist_bytes(base))
    res = _launchctl("bootstrap", domain, str(p))
    return {"installed": res.returncode == 0, "path": str(p), "error": res.stderr.strip() if res.returncode else None}


def uninstall() -> Dict[str, Any]:
    p = plist_path()
    _launchctl("bootout", f"gui/{os.getuid()}", str(p))
    p.unlink(missing_ok=True)
    return {"installed": False}


def is_installed() -> bool:
    return plist_path().exists() and _launchctl("print", f"gui/{os.getuid()}/{LABEL}").returncode == 0


def status(base: Path) -> Dict[str, Any]:
    d = Daily(base)
    st = d.state()
    sessions = st.get("sessions") or {}
    latest = sorted(sessions)[-1] if sessions else None
    return {"installed": is_installed(), "schedule_kst": [f"{h:02d}:{m:02d}" for h, m in SCHEDULE],
            "telegram": notify.telegram_status(), "capital_configured": bool(os.getenv("QPP_CAPITAL", "").strip()),
            "latest_session": latest, "steps": sessions.get(latest) if latest else None,
            "last_run": st.get("last_run"), "backup_dir": str(backup_root())}
