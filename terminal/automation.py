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
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from terminal import notify, storage
from utils import nyse_calendar

LABEL = "com.quantengine.daily"
# KST: the US close is 06:00-07:00.  Hourly from 07:10 (user decision, 2026-11-11): a run cut short while the Mac slept is retried
# within the hour it is awake again, and a finished day ends in seconds.  Before 07:10 the US session is not complete.
SCHEDULE = tuple((h, 10) for h in range(7, 24))
STEP_TIMEOUT = 45 * 60
STEP_TIMEOUTS = {"QSF": 90 * 60,                    # 21 to 26 minutes; 26 on a morning when a week's company data expired together (2026-11-13)
                 "SCAN_KR": 90 * 60,                # the Korean model scan downloads about 2,500 symbols on its first run of a day
                 "KR_FORWARD": 90 * 60}             # ten records in one process: 33 to 37 minutes on 2026-11-11..13, too near the 45
NETWORK_WAIT_S, NETWORK_POLL_S = 90, 5              # how long a run waits for the network before its first step
NETWORK_PROBE = "query1.finance.yahoo.com"          # the first host every chain needs; only its name is looked up
RETRY_QUICK_S = 300                                 # a step that failed sooner than this gets one more try at the end of the run
RUNNING_FILE = "running.json"                       # the run in progress: pid, step, steps done
CAFFEINATE = "/usr/bin/caffeinate"
SLEPT_NOTE_S = 120                                  # a step during which the Mac slept this long says so
HOLDINGS_EVERY_DAYS, HOLDINGS_FRESH_DAYS = 7, 90     # KODEX holdings: retry cadence while missing, and refresh age
KEEP_BACKUPS = 60
KEEP_SESSIONS = 40
FORWARD_STORES = ("krx_forward", "krx_forward_fund", "krx_forward_events", "us_challenger", "kr_swing_challenger", "kr_swing_prior", "kr_cap_universe", "kr_traded_universe", "kr_method", "regime_weights_kr", "regime_weights_us", "paper_book_kr", "paper_book_us", "forecast_kr", "forecast_us", "score_split_kr", "score_split_us", "turnover_book_kr", "turnover_book_us", "rank_book_kr", "rank_book_us")
KR_STEPS = ("QSF_KR", "NEWS_KR", "KR_FORWARD", "SCAN_KR")     # Korea trades on some days the US does not, and these must not wait for a US session
KST = timezone(timedelta(hours=9))
BACKUP_STALE_DAYS = 4                              # a long weekend with a holiday is three days without a new session
OK, FAILED, SKIPPED, WAITING = "OK", "FAILED", "SKIPPED", "WAITING"
STEP_NAMES = {"LAB": "도전자 기록", "SCAN": "P6-11B 스캔", "TRACK": "P6-20 추적 갱신", "QSF": "QSF 점수 기록(미국)", "QSF_KR": "QSF 점수 기록(한국)", "NEWS": "뉴스 기록(미국)", "NEWS_KR": "뉴스 기록(한국)", "KR_FORWARD": "한국 결합 점수 기록", "US_CHALLENGER": "미국 도전자 점수 기록",
              "SCAN_KR": "한국 모델 스캔(KR-EXP)",      # last before the backup, so its download never delays a morning record (user decision 2026-11-12).
              #                                        Morning, not evening: Yahoo has a day's Korean bars for only a part of the stocks until the next morning (2026-11-14)
              "BACKUP": "백업"}
BACKUP_GLOBS = ("data/terminal/journal.jsonl", "data/terminal/paper_journal.jsonl", "data/terminal/settings.json", "data/terminal/watchlist.json", "data/terminal/alerts.json", "data/terminal/alerts_log.jsonl",
                "data/lab/ledger.jsonl", "tracking/*.jsonl", "tracking/excluded_runs.json", "tracking/ledger/*.jsonl",
                "tracking/kr/*.jsonl", "tracking/kr/ledger/*.jsonl", "data/qsf/ledger/index.jsonl", "data/news/*/runs.jsonl", "research_data/krx_forward/index.jsonl", "research_data/krx_forward_fund/index.jsonl", "research_data/krx_forward_events/index.jsonl", "research_data/us_challenger/index.jsonl", "research_data/kr_swing_challenger/index.jsonl", "research_data/kr_swing_prior/index.jsonl", "research_data/kr_cap_universe/index.jsonl", "research_data/kr_traded_universe/index.jsonl", "research_data/kr_method/index.jsonl", "research_data/regime_weights_kr/index.jsonl", "research_data/regime_weights_us/index.jsonl", "research_data/paper_book_kr/index.jsonl", "research_data/paper_book_us/index.jsonl", "research_data/forecast_kr/index.jsonl", "research_data/forecast_us/index.jsonl", "research_data/score_split_kr/index.jsonl", "research_data/score_split_us/index.jsonl", "research_data/turnover_book_kr/index.jsonl", "research_data/turnover_book_us/index.jsonl", "reports/qsf/QSF_TURNOVER_*.json", "research_data/rank_book_kr/index.jsonl", "research_data/rank_book_us/index.jsonl", "reports/qsf/QSF_RANK_RULES_*.json", "data/qsf/top3/index.jsonl", "data/qsf/top3/*.json.gz",
                "data/qsf/price_archive/*.json.gz")


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
    # The separate records are write-once too.
    for src in sorted(p for name in FORWARD_STORES for p in (base / "research_data" / name).glob("*.json.gz")):
        dst = root / src.parent.name / src.name
        if not dst.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            if _sha(src) != _sha(dst):
                raise OSError("backup verification failed")
            n += 1
    # Daily news files grow only on a retry of the same day, so a copy of a different size is replaced.
    for src in sorted((base / "data" / "news").glob("*/*.jsonl.gz")):
        dst = root / "news" / src.parent.name / src.name
        if not dst.exists() or dst.stat().st_size != src.stat().st_size:
            dst.parent.mkdir(parents=True, exist_ok=True)
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


def _previous_weekday(day: date) -> date:
    d = day - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def backup_status(root: Optional[Path] = None, today: Optional[date] = None) -> Dict[str, Any]:
    root = Path(root or backup_root())
    folders = sorted(p.name for p in root.iterdir() if p.is_dir() and _is_date_name(p.name)) if root.exists() else []
    if not folders:
        return {"latest": None, "age_days": None, "copies": 0}
    return {"latest": folders[-1], "age_days": ((today or date.today()) - date.fromisoformat(folders[-1])).days, "copies": len(folders)}


def check_backup(root: Optional[Path] = None) -> Dict[str, Any]:
    """Restores the newest backup into a throw-away folder and runs each record's own verification on the copy.  Reads the backup and writes nothing there."""
    import tempfile
    from pipeline.prospective_ledger import verify_chain
    from terminal.qsf import kr_forward
    from terminal.qsf.ledger import Ledger
    root = Path(root or backup_root())
    latest = backup_status(root)["latest"]
    if not latest:
        return {"status": "NO_BACKUP", "latest": None, "checks": {}}
    with tempfile.TemporaryDirectory(prefix="qsf_restore_") as tmp:
        work = Path(tmp) / "restored"
        shutil.copytree(root / latest, work)
        (work / "data" / "qsf" / "ledger").mkdir(parents=True, exist_ok=True)
        for src in (root / "qsf_ledger").glob("*.jsonl.gz") if (root / "qsf_ledger").exists() else []:
            shutil.copy2(src, work / "data" / "qsf" / "ledger" / src.name)
        checks: Dict[str, Any] = {}
        for name in FORWARD_STORES:
            store = Path("research_data") / name
            (work / store).mkdir(parents=True, exist_ok=True)
            for src in (root / name).glob("*.json.gz") if (root / name).exists() else []:
                shutil.copy2(src, work / store / src.name)
            got = kr_forward.verify(work, store)
            checks[name] = {"status": got["status"], "sessions": got["sessions"], "bad": got["bad"]}
        got = Ledger(work).verify()
        checks["qsf_ledger"] = {"status": got["status"], "shards": got.get("shards")}
        for rel in ("tracking/ledger/observations.jsonl", "tracking/ledger/events.jsonl", "tracking/kr/ledger/observations.jsonl", "tracking/updates.jsonl", "tracking/kr/updates.jsonl"):
            if (work / rel).exists():
                got = verify_chain(work / rel)
                checks[rel] = {"status": "OK" if got["ok"] else "BROKEN", "rows": got["rows"], "problems": got["problems"][:5]}
    status = "OK" if all(c["status"] == "OK" for c in checks.values()) else "BROKEN"
    return {"status": status, "latest": latest, "checks": checks}


def _is_date_name(name: str) -> bool:
    """Only folders named like a date are ever pruned; anything else in the backup folder is left alone."""
    try:
        return datetime.strptime(name, "%Y-%m-%d").strftime("%Y-%m-%d") == name
    except ValueError:
        return False


def _online() -> bool:
    try:
        socket.getaddrinfo(NETWORK_PROBE, 443)
        return True
    except OSError:
        return False


class Daily:
    def __init__(self, base: Path, now: Callable[[], datetime] = None, runner: Callable = None,
                 telegram: Callable = None, macos: Callable = None, terminal: Any = None, backup_dir: Path = None,
                 clocks: Any = None, online: Callable[[], bool] = None, sleep: Callable[[float], None] = None,
                 kr_newest: Callable[[], Optional[str]] = None):
        self.base = Path(base)
        self.dir = self.base / "data" / "automation"
        self.state_file = self.dir / "state.json"
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.runner = runner or self._run_process
        self.telegram = telegram or notify.send_telegram
        self.macos = macos or notify.send_macos
        self._terminal = terminal
        self.backup_dir = backup_dir
        # wall time keeps running while the Mac sleeps, mach_absolute_time (time.monotonic) does not: the gap is time asleep
        self.clocks = clocks or (time.time, time.monotonic)
        # with a stand-in runner (tests) nothing goes out, so nothing waits for the network
        self.online = online or (_online if runner is None else (lambda: True))
        self.sleep = sleep or time.sleep
        # the newest Korean session the provider has, asked before the long model scan; a stand-in runner asks nothing
        self.kr_newest = kr_newest or (self._kr_newest_session if runner is None else (lambda: None))

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
                                      stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, timeout=STEP_TIMEOUTS.get(name, STEP_TIMEOUT)).returncode
            except subprocess.TimeoutExpired:
                fh.write("timeout\n")
                return 124

    def _lab_recorded(self, session: str) -> bool:
        from terminal.lab.service import Lab
        recs, integ = Lab(self.base, now=self.now).read_ledger()
        return integ["status"] == "OK" and any(r["signal_session"] == session for r in recs)

    def _timed_step(self, name: str, session: str) -> Dict[str, Any]:
        """A step, plus how long the Mac slept while it ran.  A sleeping Mac only runs in short maintenance wakes, so a step can take
        hours and its downloads get cut (2026-11-10).  A failure says so, so it is not read as a data or code problem."""
        wall, mono = (c() for c in self.clocks)
        res = self._step(name, session)
        wall_end, mono_end = (c() for c in self.clocks)
        res["seconds"] = round(mono_end - mono)                     # time awake; the retry in _run reads it
        slept = (wall_end - wall) - (mono_end - mono)
        if slept >= SLEPT_NOTE_S:
            res["slept_minutes"] = round(slept / 60)
            if res.get("status") == FAILED:
                res["detail"] = f"{res.get('detail') or '실패'} · 실행 중 맥이 약 {res['slept_minutes']}분 잠듦"
        return res

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
                return {"status": OK if rc == 0 else FAILED, "at": at, "detail": None if rc == 0 else "데이터 미준비" if rc == 3 else "다운로드 끊김" if rc == 4 else f"코드 {rc}"}
            if name == "QSF_KR":
                rc = self.runner(name, ["--market", "KR", "qsf", "scan"])
                if rc == 5:             # the morning after a Korean holiday: no new session, and the last one is in the ledger.  Not a failure
                    return {"status": WAITING, "at": at, "detail": "새 거래일 자료 없음(휴장일이거나 자료가 늦음) · 직전 거래일은 기록되어 있음"}
                return {"status": OK if rc == 0 else FAILED, "at": at, "detail": None if rc == 0 else "데이터 미준비" if rc == 3 else "다운로드 끊김" if rc == 4 else f"코드 {rc}"}
            if name in ("NEWS", "NEWS_KR"):
                rc = self.runner(name, ["news", "record"] if name == "NEWS" else ["--market", "KR", "news", "record"])
                return {"status": OK if rc == 0 else FAILED, "at": at, "detail": None if rc == 0 else "점수 기록 없음" if rc == 3 else f"코드 {rc}"}
            if name == "KR_FORWARD":                                # waiting is not a failure: the day may not be published yet
                rc = self.runner(name, ["qsf", "kr-forward-record"])
                return {"status": OK if rc == 0 else WAITING if rc == 3 else FAILED, "at": at, "detail": None if rc in (0, 3) else "KRX 키 없음" if rc == 4 else f"코드 {rc}"}
            if name == "US_CHALLENGER":                             # waiting is not a failure: the ledger may not have the session yet
                rc = self.runner(name, ["qsf", "us-challenger-record"])
                return {"status": OK if rc == 0 else WAITING if rc == 3 else FAILED, "at": at, "detail": None if rc in (0, 3) else f"코드 {rc}"}
            if name == "SCAN_KR":                                   # the experimental Korean model, then its paper outcomes
                if not os.getenv("QPP_CAPITAL_KRW", "").strip():
                    return {"status": SKIPPED, "at": at, "detail": "QPP_CAPITAL_KRW 미설정"}
                from terminal import model_scan
                if model_scan.started_here(self.base):
                    return {"status": WAITING, "at": at, "detail": "화면에서 시작한 스캔 실행 중"}
                day = _previous_weekday(self.now().astimezone(KST).date()).isoformat()      # the session a morning scan should score
                done = model_scan.scanned_session(self.base, day)
                again = None
                if done:                                            # the button already scanned today's session: not scanned twice
                    run = done
                else:
                    # A holiday, or a day the provider has not published: the scan would score the session before once more, and a
                    # waiting step would do so every hour.  So the newest session is asked first (two small requests), and a session
                    # already scanned is not scanned again.
                    newest = self.kr_newest()
                    again = model_scan.scan_of(self.base, newest) if newest and newest != day else None
                    run = again
                    if run is None:
                        rc = self.runner(name, ["--market", "KR", "scan"])
                        run = model_scan.run_since(self.base, at)
                        if run is None:                             # exit 1 is also "no valid recommendation", which did write a run
                            return {"status": FAILED, "at": at, "detail": f"코드 {rc}"}
                track = self.runner("TRACK_KR", ["--market", "KR", "tracking", "update"])
                behind = run.get("latest_session") != day
                mine = bool(done) and done.get("run_id") == (((self.state().get("sessions") or {}).get(session) or {}).get("SCAN_KR") or {}).get("scan_run")
                notes = [run.get("recommendation_status"), "앞서 스캔함(추적 갱신만 다시)" if mine else "화면에서 이미 스캔함" if done else "이미 스캔한 거래일이라 다시 스캔하지 않음" if again else None,
                         f"기준 거래일 {run.get('latest_session')}({day} 자료 아님: 휴장일이거나 자료가 늦음)" if behind else None,
                         None if track == 0 else f"추적 갱신 실패(코드 {track})"]
                # A failed tracking update is a failure, and is tried again: the scan itself is found above and not repeated.
                # A scan of an older session leaves the step waiting, so the day is scanned once its data is out.
                return {"status": FAILED if track != 0 else WAITING if behind else OK, "at": at, "detail": " · ".join(x for x in notes if x) or None,
                        "scan_run": run.get("run_id")}
            res = backup(self.base, session, self.backup_dir)
            return {"status": OK, "at": at, "detail": f"{res['files']}개 파일"}
        except Exception as exc:                                    # one failed step never stops the others
            return {"status": FAILED, "at": at, "detail": type(exc).__name__}

    def _kr_newest_session(self) -> Optional[str]:
        """The newest completed KRX session the provider shows, found the way the model scan finds it (index and anchor stock).
        None when it cannot be told; the scan then runs as before."""
        try:
            from markets import session_data
            from markets.kr import acquisition
            from markets.kr.market_data import YahooKRProvider
            prov, now = YahooKRProvider(), self.now()
            idx = acquisition.index_bars(prov, *acquisition.window(now, 30), now)
            try:
                anchor = prov.fetch_index(session_data.KR_ANCHOR, *acquisition.window(now, 30))
            except Exception:
                anchor = None
            return session_data.kr_calendar(idx["KOSPI"], anchor, now).latest.date().isoformat()
        except Exception:
            return None

    def _kr_holdings(self, st: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """KODEX holdings for the sector picks (``terminal.kr_etf_holdings``): tried at most once a week while the stored snapshot
        is missing or older than HOLDINGS_FRESH_DAYS.  The site may refuse scripted reads; the command then stops after one request
        and the picks keep their industry match.  A refusal is not a failure of the day's run and is not sent as an alert."""
        from terminal import kr_etf_holdings
        today = self.now().astimezone(KST).date()
        snap = kr_etf_holdings.status(self.base, today)
        if snap["status"] != "NONE" and snap["age_days"] <= HOLDINGS_FRESH_DAYS:
            return None
        last = (st.get("kr_holdings") or {}).get("day")
        if last and (today - date.fromisoformat(last)).days < HOLDINGS_EVERY_DAYS:
            return None
        try:
            rc = self.runner("KR_HOLDINGS", ["--market", "KR", "qsf", "kr-etf-holdings"])
        except Exception as exc:                                    # never stops the run
            rc = type(exc).__name__
        st["kr_holdings"] = {"day": today.isoformat(), "result": "OK" if rc == 0 else "NOT_SAVED", "code": rc}
        return st["kr_holdings"]

    def _cache_prune(self, st: Dict[str, Any], session: str) -> Optional[Dict[str, Any]]:
        """Once per session (user decision, 2026-11-09): remove scan price files older than the newest ``storage.KEEP_SESSIONS``
        sessions and cache entries no code reads (``storage.prune_cache``).  Only cache files; records and backups are never touched."""
        if (st.get("cache_prune") or {}).get("session") == session:
            return None
        try:
            res = storage.prune_cache(self.base, apply=True)
            st["cache_prune"] = {"session": session, "at": self.now().isoformat(),
                                 "removed": res["scanbars"]["removed"] + res["kr_bars"]["removed"] + res["temps"]["removed"] + res["superseded"]["removed"],
                                 "mb": round(res["scanbars"]["old_mb"] + res["kr_bars"]["old_mb"] + res["temps"]["mb"] + res["superseded"]["mb"], 1)}
        except Exception as exc:                                    # never stops the run
            st["cache_prune"] = {"session": session, "at": self.now().isoformat(), "error": type(exc).__name__}
        return st["cache_prune"]

    def _price_audit(self, st: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Checks the price history the day's scores read (``qsf.price_audit``): Korean bars against KRX, US bars against the NYSE
        calendar.  Read only, a few seconds; a failure is noted and never stops the run."""
        from terminal.qsf import price_audit
        try:
            st["price_audit"] = {"at": self.now().isoformat(), **price_audit.run(self.base, nyse_calendar.sessions_between, self.now())}
        except Exception as exc:                                    # never stops the run
            st["price_audit"] = {"at": self.now().isoformat(), "error": type(exc).__name__}
        return st["price_audit"]

    def _earnings_gap(self, st: Dict[str, Any], steps: Dict[str, Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Once (``qsf.earnings_gap``, decision-list item on the US earnings dates): at the first run on or after ``DUE`` whose US
        scores were recorded, count the US stocks without a next earnings date, note it in the decision list and tell the user.
        The count is taken once; an undelivered message is sent again at later runs.  Read only for scores and records."""
        from terminal.qsf import earnings_gap
        got = dict(st.get("earnings_gap") or {})
        if got.get("delivered") or self.now().astimezone(KST).date() < earnings_gap.DUE:
            return None
        try:
            if "blank" not in got:
                if (steps.get("QSF") or {}).get("status") != OK:
                    return None                                     # today's US scores are not in the ledger yet
                res = earnings_gap.count(self.base)
                if res is None:
                    return None
                got = {**res, "at": self.now().isoformat(), "noted": earnings_gap.write_note(self.base, res), "delivered": False}
                st["earnings_gap"] = got                            # the count stays even if telling fails below
            tg = self.telegram(earnings_gap.text(got))
            if tg["status"] == "NOT_CONFIGURED":
                tg = self.macos("미국 실적 발표일 빈칸 재집계", earnings_gap.short(got))
            got["delivered"] = tg["status"] == "SENT"
            got.pop("error", None)
        except Exception as exc:                                    # never stops the run
            got["error"] = type(exc).__name__
        st["earnings_gap"] = got
        return got

    def _turnover_reading(self, st: Dict[str, Any]) -> Dict[str, Any]:
        """The turnover rules' one reading per market (``qsf.turnover_book``, reports/QSF_TURNOVER_RULES_PROTOCOL.md)."""
        from terminal.qsf import turnover_book
        return self._rule_reading(st, "turnover_reading", turnover_book, "회전율 규칙 판정")

    def _rank_reading(self, st: Dict[str, Any]) -> Dict[str, Any]:
        """The rank rules' one reading per market (``qsf.rank_book``, reports/QSF_RANK_RULES_PROTOCOL.md)."""
        from terminal.qsf import rank_book
        return self._rule_reading(st, "rank_reading", rank_book, "순위 규칙 판정")

    def _rule_reading(self, st: Dict[str, Any], key: str, book: Any, title: str) -> Dict[str, Any]:
        """A comparison book's one reading per market: made by this run on the day the book has its 240 records, then told once.
        An undelivered notice is sent again at later runs; a record that cannot be read is told once and asked again each run.
        Never stops the run."""
        got = dict(st.get(key) or {})
        for market in ("KR", "US"):
            m = dict(got.get(market) or {})
            if m.get("delivered"):
                continue
            try:
                rep = book.read_when_due(self.base, market, self.now)
                if rep is None:
                    continue
                unread = rep.get("status") != "REAL"
                if unread and m.get("warned"):
                    continue
                tg = self.telegram(book.text(rep))
                if tg["status"] == "NOT_CONFIGURED":
                    tg = self.macos(title, book.short(rep))
                m = {"decision": rep.get("decision"), "at": self.now().isoformat(), "warned": unread and tg["status"] == "SENT", "delivered": not unread and tg["status"] == "SENT"}
            except Exception as exc:                                # never stops the run
                m["error"] = type(exc).__name__
            got[market] = m
        st[key] = got
        return got

    def _readings(self, st: Dict[str, Any]) -> Dict[str, Any]:
        """Every one-time reading that used to wait for a typed command (``qsf.readings``): on the day a reading's record is long
        enough this run asks the reading's own command, once a day, and tells the verdict once its report exists.  The command
        alone decides whether it reads; a refusal leaves no report and is asked again the next day.  After ``GIVE_UP`` tries the
        user is told once and the tries come a week apart.  Never stops the run."""
        from terminal.qsf import readings
        got = dict(st.get("readings") or {})
        today = self.now().astimezone(KST).date()
        for e in readings.REGISTRY:
            m = dict(got.get(e["key"]) or {})
            if m.get("delivered"):
                continue
            try:
                rep = readings.report(self.base, e)
                if rep is None:
                    last = date.fromisoformat(m["tried"]) if m.get("tried") else None
                    wait = readings.RETRY_DAYS if m.get("failed", 0) >= readings.GIVE_UP else 1
                    if (last is not None and (today - last).days < wait) or not readings.due(self.base, e):
                        continue
                    m.update(tried=today.isoformat(), rc=self.runner("READING", e["argv"]))
                    rep = readings.report(self.base, e)
                if rep is None:
                    m["failed"] = m.get("failed", 0) + 1
                    if m["failed"] >= readings.GIVE_UP and not m.get("warned"):
                        m["warned"] = self.telegram(readings.stuck_text(e, m["failed"]))["status"] == "SENT"
                else:
                    tg = self.telegram(readings.text(e, rep))
                    if tg["status"] == "NOT_CONFIGURED":
                        tg = self.macos("판정", f"{e['label']}: {readings.verdict(e, rep)}")
                    m.update(verdict=readings.verdict(e, rep), at=self.now().isoformat(), delivered=tg["status"] == "SENT")
                m.pop("error", None)
            except Exception as exc:                                # never stops the run
                m["error"] = type(exc).__name__
            got[e["key"]] = m
        st["readings"] = got
        return got

    def _scan_status(self) -> Optional[str]:
        runs = sorted((self.base / "runs").glob("*_market_scan_*"), key=lambda p: p.name)
        if not runs:
            return None
        try:
            return json.loads((runs[-1] / "execution_status.json").read_text(encoding="utf-8")).get("display_status")
        except (OSError, ValueError):
            return None

    # ------------------------------------------------------------------ alerts and gaps
    def _term(self):
        if self._terminal is None:
            from terminal.services import Terminal
            self._terminal = Terminal(self.base, now=self.now)
        return self._terminal

    def _rule_alerts(self) -> Dict[str, Any]:
        """The user's own alert rules (terminal alert center), checked on final daily closes."""
        from terminal import alert_rules
        if not any(r.get("status") == "ACTIVE" for r in alert_rules.Store(self.base / "data" / "terminal").rules()):
            return {"status": "NONE", "alerts": []}
        try:
            return {"status": "OK", **self._term().alert_check()}
        except Exception as exc:
            return {"status": "UNAVAILABLE", "error": type(exc).__name__, "alerts": []}

    def _alerts(self) -> Dict[str, Any]:
        try:
            self._term()
            pf = self._terminal.portfolio()
            kr = self._terminal.portfolio("KR")
        except Exception as exc:
            return {"status": "UNAVAILABLE", "error": type(exc).__name__, "items": [], "stale": []}
        if pf["integrity"]["status"] != "OK" or kr["integrity"]["status"] != "OK":
            return {"status": "INTEGRITY", "items": [], "stale": []}
        stale = [f"{h['ticker']} ({h['date'] or '시세 없음'})" for p in (pf, kr) for h in p["holdings"] if h["status"] != "REAL"]
        out = {"status": "OK", "items": list(pf["alerts"]) + [{**a, "text": "[한국] " + a["text"]} for a in kr["alerts"]], "stale": stale}
        for market, book in (("US", pf), ("KR", kr)):
            if not book["holdings"]:
                continue
            try:
                got = exit_alerts(self._terminal.portfolio_signals(market)["items"])
                out["items"] += [{**a, "text": "[한국] " + a["text"]} for a in got] if market == "KR" else got
            except Exception:
                out["signals_failed"] = True
        out["items"].sort(key=lambda a: {"bad": 0, "warn": 1, "info": 2}[a["level"]])
        return out

    def _commit_rules(self, rules: Dict[str, Any], delivered: bool) -> None:
        if rules.get("status") != "OK":
            return
        try:
            from terminal import alert_rules
            alert_rules.Store(self.base / "data" / "terminal").commit(rules["state"], rules["alerts"] if delivered else [], self.now().isoformat(timespec="seconds"))
        except OSError:
            pass                                        # the rule fires again next run: a repeat, never a silent loss

    def missing_sessions(self, session: str) -> List[str]:
        from terminal.lab.service import Lab
        recs, _ = Lab(self.base, now=self.now).read_ledger()
        have = {r["signal_session"] for r in recs}
        if not have:
            return []
        return [d.isoformat() for d in nyse_calendar.sessions_between(min(have), session) if d.isoformat() not in have]

    @staticmethod
    def compose(session: str, steps: Dict[str, Dict[str, Any]], alerts: Dict[str, Any], prev: List[str],
                missing: List[str], low_disk: Optional[str] = None, rules: Optional[Dict[str, Any]] = None) -> str:
        icon = {OK: "✅", FAILED: "❌", SKIPPED: "⏭"}
        lines = [f"📊 퀀트 터미널 일일 요약 (기준 거래일 {session})", "", "[작업]"]
        for name, label in STEP_NAMES.items():
            s = steps.get(name) or {}
            if name in ("KR_FORWARD", "US_CHALLENGER", "SCAN_KR") and s.get("status") != FAILED:      # no daily message over a record that is on track
                continue
            lines.append(f"{icon.get(s.get('status'), '·')} {label}" + (f": {s['detail']}" if s.get("detail") else ""))
        if any((steps.get(n) or {}).get("status") == FAILED for n in STEP_NAMES):
            lines.append("실패한 작업은 다음 예약 시각에 다시 시도합니다.")
        if low_disk:
            lines.append("⚠️ " + low_disk)
        if (steps.get("SCAN") or {}).get("status") == SKIPPED:
            lines.append("P6-11B는 오늘 기록이 없습니다. 모델 탭에서 자본금을 입력하면 매일 스캔합니다.")
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
        if alerts.get("signals_failed"):
            lines.append("⚠️ 보유 종목 판정을 계산하지 못했습니다.")
        if alerts.get("stale"):
            lines.append("오래되었거나 없는 시세로 계산: " + ", ".join(alerts["stale"]))
        if rules and rules.get("status") == "OK" and rules["alerts"]:
            mark = {"bad": "🚨", "warn": "⚠️", "info": "🔔"}
            lines += ["", "[내 알림 조건]"] + [f"{mark[a['level']]} {'[한국] ' if a.get('market') == 'KR' else ''}{a['text']}" for a in rules["alerts"]]
        elif rules and rules.get("status") == "UNAVAILABLE":
            lines += ["", "[내 알림 조건]", "⚠️ 알림 조건을 확인하지 못했습니다."]
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
            self._mark(None, 0, 0)
            try:
                out = self._run(resend)
            except Exception as exc:
                self._crash_notice(exc)
                self._attempt({"status": "ERROR", "type": type(exc).__name__})
                raise
            finally:
                (self.dir / RUNNING_FILE).unlink(missing_ok=True)
            self._attempt({"status": out["status"], "session": out.get("session")})
            return out

    def _wait_for_network(self) -> bool:
        """Up to NETWORK_WAIT_S for a name lookup to work.  launchd starts the job the moment the lid opens, before Wi-Fi is back."""
        waited = 0.0
        while not self.online():
            if waited >= NETWORK_WAIT_S:
                return False
            self.sleep(NETWORK_POLL_S)
            waited += NETWORK_POLL_S
        return True

    def _crash_notice(self, exc: BaseException) -> None:
        """One line when a run dies outside its steps; without it the job could stop every hour unseen.  Sent once per kind of
        failure a day, and never in the way of the failure itself."""
        try:
            kind, today = type(exc).__name__, self.now().astimezone(KST).date().isoformat()
            last = (self.state().get("last_attempt") or {})
            if last.get("status") == "ERROR" and last.get("type") == kind and str(last.get("at", ""))[:10] == self.now().date().isoformat():
                return
            text = f"퀀트 터미널 일일 작업이 단계 밖에서 멈췄습니다 ({today}, {kind}). 기록 화면의 '지금 수집'으로 다시 실행해 보세요."
            self.telegram(text)
            self.macos("퀀트 터미널 일일 작업 중단", kind)
        except Exception:
            pass

    def _mark(self, step: Optional[str], done: int, total: int) -> None:
        """What the run is doing now, for the screen.  A separate small file: the lock is not probed, so a status poll can never
        make a starting run think another one holds it."""
        self.dir.mkdir(parents=True, exist_ok=True)
        if step is None:
            self._started = self.now().isoformat()
        tmp = self.dir / (RUNNING_FILE + ".tmp")
        tmp.write_text(json.dumps({"pid": os.getpid(), "started_at": self._started, "step": step, "done": done, "total": total}), encoding="utf-8")
        tmp.replace(self.dir / RUNNING_FILE)

    def _attempt(self, res: Dict[str, Any]) -> None:
        """Every run that got the lock leaves its outcome, also one that found nothing to do."""
        st = self.state()
        st["last_attempt"] = {"at": self.now().isoformat(), **res}
        self._save(st)

    def _session_moved(self, session: str) -> bool:
        return nyse_calendar.latest_completed_session(self.now()).isoformat() != session

    def _run(self, resend: bool, restarted: bool = False) -> Dict[str, Any]:
        session = nyse_calendar.latest_completed_session(self.now()).isoformat()
        st = self.state()
        steps = st["sessions"].setdefault(session, {})
        pending = [n for n in STEP_NAMES if (steps.get(n) or {}).get("status") not in (OK, SKIPPED)]
        if "LAB" not in pending and not self._lab_recorded(session):
            pending.insert(0, "LAB")                # a voided or missing record is retried even if it once reported OK
        if (steps.get("SCAN") or {}).get("status") == SKIPPED and os.getenv("QPP_CAPITAL", "").strip():
            pending.append("SCAN")                  # a skipped scan runs as soon as capital is configured
        if (steps.get("SCAN_KR") or {}).get("status") == SKIPPED and os.getenv("QPP_CAPITAL_KRW", "").strip():
            pending.append("SCAN_KR")               # the same for the Korean model scan
        kr_day = _previous_weekday(self.now().astimezone(KST).date()).isoformat()
        if st.get("kr_day") != kr_day:              # once for each weekday, whether or not the US traded on it
            pending += [n for n in KR_STEPS if n not in pending]
        delivered = (st.get("notified") or {}).get("session") == session
        if not pending and delivered and not resend:
            return {"status": "UP_TO_DATE", "session": session}
        if pending and "BACKUP" not in pending:     # what the other steps just wrote is backed up today, not at the next session
            pending.append("BACKUP")
        order = list(STEP_NAMES)
        todo = sorted(set(pending), key=order.index)
        self._wait_for_network()
        for k, name in enumerate(todo):
            # A run can outlast its session: the lid closes mid-run and opens the next day.  Each step finds its own session, so
            # the steps left would record the new day while this run filed them, the backup and the message under the old one.
            # The run starts over for the new session instead; the old session's unfinished steps are not run (no backfill).
            if not restarted and self._session_moved(session):
                st["last_cut"] = {"at": self.now().isoformat(), "session": session, "before": name, "detail": "실행 중 새 거래일이 완료되어 새 거래일로 다시 시작"}
                self._save(st)
                return self._run(resend, restarted=True)
            self._mark(name, k, len(todo))
            steps[name] = self._timed_step(name, session)
            self._save(st)
        # A step that failed within minutes most likely met a network that was not up yet (lid just opened).  Waiting for the next
        # hourly firing can lose the day: the chain runs for about two hours and launchd drops the firings in between.  One more
        # try at the end; "data not ready" is left alone, since the provider will not have it a minute later either.
        for k, name in enumerate(todo):
            first = steps[name]
            if first.get("status") == FAILED and first.get("seconds", RETRY_QUICK_S) < RETRY_QUICK_S and first.get("detail") != "데이터 미준비" \
                    and (restarted or not self._session_moved(session)):
                self._mark(name, k, len(todo))
                steps[name] = {**self._timed_step(name, session), "retried": True}
                self._save(st)
        self._mark("WRAP_UP", len(todo), len(todo))
        st["kr_day"] = kr_day
        self._kr_holdings(st)
        self._cache_prune(st, session)
        self._price_audit(st)
        self._earnings_gap(st, steps)
        self._turnover_reading(st)
        self._rank_reading(st)
        self._save(st)
        alerts = self._alerts()
        prev = st.get("alerts") or []
        missing = self.missing_sessions(session)
        rules = self._rule_alerts()
        text = self.compose(session, steps, alerts, prev, missing, storage.low_disk_text(self.base), rules)
        sig = hashlib.sha256(text.encode("utf-8")).hexdigest()
        notified = st.get("notified") or {}
        out = {"status": "DONE", "session": session, "steps": steps, "telegram": None, "macos": None}
        sent = notified.get("signature") == sig            # the same text already went out: its rule alerts were delivered then
        if resend or notified.get("signature") != sig:
            out["telegram"] = self.telegram(text)
            failures = [STEP_NAMES[n] for n in STEP_NAMES if (steps.get(n) or {}).get("status") == FAILED]
            urgent = sum(1 for a in alerts["items"] if a["level"] == "bad")
            body = (f"실패: {', '.join(failures)}. " if failures else "") + f"경고 {len(alerts['items'])}건" + \
                   (f", 긴급 {urgent}건" if urgent else "") + (f", 알림 조건 {len(rules['alerts'])}건" if rules["alerts"] else "")
            out["macos"] = self.macos(f"퀀트 터미널 {session}", body)
            ok = out["telegram"]["status"] == "SENT" if out["telegram"]["status"] != "NOT_CONFIGURED" \
                else out["macos"]["status"] == "SENT"
            if ok:
                st["notified"] = {"session": session, "signature": sig, "at": self.now().isoformat()}
                st["alerts"] = sorted(_key(a) for a in alerts["items"])    # "new" clears only once actually delivered
                self._commit_rules(rules, delivered=True)
                sent = None
        if sent is not None and rules.get("status") == "OK" and (sent or not rules["alerts"]):
            self._commit_rules(rules, delivered=False)     # nothing new fired, or it fired in a message already delivered
        st["last_run"] = {"at": self.now().isoformat(), "session": session, "telegram": out["telegram"],
                          "macos": out["macos"], "missing_sessions": missing}
        self._save(st)
        self._readings(st)                  # after the day's summary went out: a reading that falls due can take minutes
        self._save(st)
        return out


# What reaches Telegram, as chosen by the user: readings that call for an action.  HOLD_AND_REVIEW stays on the screen.
EXIT_ALERTS = {"EXIT": ("bad", "청산 검토"), "THESIS_INVALIDATED": ("bad", "투자 논리 무효"), "REDUCE": ("warn", "비중 축소 검토"),
               "PARTIAL_TAKE_PROFIT": ("info", "일부 차익 실현 검토"), "TIME_STOP_REVIEW": ("warn", "시간 손절 재평가")}


def exit_alerts(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for s in items:
        if s.get("status") != "REAL" or s["exit"]["action"] not in EXIT_ALERTS:
            continue
        action = s["exit"]["action"]
        own = [c["code"] for c in s["exit"]["conditions"] if c["action"] == action]
        if own and set(own) <= {"STOP_BREACH", "CONCENTRATION"}:
            continue                       # the portfolio's own stop and weight alerts already say this
        level, label = EXIT_ALERTS[action]
        out.append({"level": level, "code": f"QSF_{action}", "ticker": s["ticker"], "text": f"{s['ticker']}: {label}. {s['exit']['reason']}"})
    return out


def _key(a: Dict[str, Any]) -> str:
    return f"{a['code']}:{a.get('ticker') or a['text']}"


# ---------------------------------------------------------------------- launchd
def plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def plist_bytes(base: Path) -> bytes:
    """A login shell supplies the user's environment: nothing secret is copied into the plist."""
    py = shlex.quote(sys.executable)
    awake = f"{CAFFEINATE} -i " if Path(CAFFEINATE).exists() else ""      # held against idle sleep while it runs, like a button run
    cmd = f"cd {shlex.quote(str(base))} && exec {awake}{py} app.py automation run"
    logs = base / "data" / "automation"
    return plistlib.dumps({
        "Label": LABEL, "ProgramArguments": ["/bin/zsh", "-lc", cmd], "RunAtLoad": True,
        "StartCalendarInterval": [{"Hour": h, "Minute": m} for h, m in SCHEDULE],
        "StandardOutPath": str(logs / "launchd.log"), "StandardErrorPath": str(logs / "launchd.log"),
        "ProcessType": "Background"})


LAUNCHCTL_PRINT_TIMEOUT_S = 5


def _launchctl(*args: str):
    """A status question (``print``) gives up after five seconds and then reads as "not loaded".  The status screen asks every
    three seconds while a job runs, and a ``launchctl`` that never answered held its request for good."""
    try:
        return subprocess.run(["launchctl", *args], capture_output=True, text=True, timeout=LAUNCHCTL_PRINT_TIMEOUT_S if args[:1] == ("print",) else None)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(["launchctl", *args], 124, "", "TIMEOUT")


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


def readings_state(base: Path) -> Dict[str, Any]:
    """What the daily job has tried and told about each one-time reading (``qsf.readings``)."""
    return Daily(base).state().get("readings") or {}


def status(base: Path) -> Dict[str, Any]:
    d = Daily(base)
    st = d.state()
    sessions = st.get("sessions") or {}
    latest = sorted(sessions)[-1] if sessions else None
    return {"installed": is_installed(), "schedule_kst": [f"{h:02d}:{m:02d}" for h, m in SCHEDULE],
            "schedule_text": f"{SCHEDULE[0][0]:02d}:{SCHEDULE[0][1]:02d}부터 {SCHEDULE[-1][0]:02d}:{SCHEDULE[-1][1]:02d}까지 매시간",
            "telegram": notify.telegram_status(), "capital_configured": bool(os.getenv("QPP_CAPITAL", "").strip()),
            "latest_session": latest, "steps": sessions.get(latest) if latest else None,
            "last_run": st.get("last_run"), "last_attempt": st.get("last_attempt"), "running": running(base), "earnings_gap": st.get("earnings_gap"),
            "step_names": {**STEP_NAMES, "WRAP_UP": "점검과 알림"}, "backup_dir": str(backup_root())}


def running(base: Path) -> Optional[Dict[str, Any]]:
    """The run in progress, scheduled or started from the screen; None when there is none.  A marker whose process is gone
    (a crash, a restart) does not count."""
    try:
        m = json.loads((Path(base) / "data" / "automation" / RUNNING_FILE).read_text(encoding="utf-8"))
        os.kill(int(m["pid"]), 0)
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return {k: m.get(k) for k in ("started_at", "step", "done", "total")}


def start_now(base: Path, popen: Callable = subprocess.Popen, now: Callable[[], datetime] = lambda: datetime.now(timezone.utc)) -> Dict[str, Any]:
    """Start the daily job now, from the screen.  It is the same job as the scheduled one: only steps not yet done for the
    session run, nothing is recorded from a day that is not ready, and a second run cannot start while one holds the lock.
    The process is detached from the server, and held awake against idle sleep while it runs (``caffeinate -i``)."""
    base = Path(base)
    if running(base):
        return {"status": "ALREADY_RUNNING", "running": running(base)}
    folder = base / "data" / "automation"
    folder.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, str(base / "app.py"), "automation", "run"]
    if Path(CAFFEINATE).exists():
        cmd = [CAFFEINATE, "-i", *cmd]
    with open(folder / "manual_run.log", "w", encoding="utf-8") as fh:
        popen(cmd, cwd=base, stdout=fh, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
    return {"status": "STARTED", "at": now().isoformat()}
