"""Lab service: panel refresh, prospective challenger recording, comparison vs P6-11B, research simulation.

Prospective rules (TERMINAL-3 §3): the signal session is the latest COMPLETED NYSE session at record time;
one record per model per signal session (idempotent); no back-dating; the panel must end exactly on the
signal session.  The P6-20 tracking ledger is only read.
"""
import fcntl
import hashlib
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from terminal.lab import LAB_VERSION, backtest, compare, membership, models
from terminal.lab import panel as panel_mod
from terminal.lab.panel import BENCH, Panel
from utils import nyse_calendar

GENESIS = "0" * 64
CHALLENGERS = ("MOM_12_1", "LOWVOL_252", "TREND_SWING", "BASE_SPY", "BASE_EW")


def _hash(rec: Dict) -> str:
    body = {k: v for k, v in rec.items() if k != "hash"}
    return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


class LabError(ValueError):
    pass


class Lab:
    def __init__(self, base_dir: Path, now: Callable[[], datetime] = None, fetch: Callable = None,
                 universe_file: Optional[Path] = None):
        self.base = Path(base_dir)
        self.dir = self.base / "data" / "lab"
        self.ledger_file = self.dir / "ledger.jsonl"
        self.panel_file = self.dir / "panel.json.gz"
        self.bt_file = self.dir / "backtest.json"
        self.universe_file = Path(universe_file) if universe_file else self.base / "data" / "sp500_universe_cache.json"
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.fetch = fetch or panel_mod._yf
        self.membership_fetch = membership._http_get
        self._lock = threading.Lock()
        self._panel: Optional[Panel] = None
        self._panel_mtime = None
        self.job = {"state": "IDLE"}

    # ------------------------------------------------------------------ universe & panel
    def universe(self) -> Dict[str, Any]:
        try:
            d = json.loads(self.universe_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"status": "UNAVAILABLE", "tickers": []}
        tickers = sorted({str(t).upper().replace(".", "-") for t in d.get("tickers") or []})
        return {"status": "REAL" if tickers else "UNAVAILABLE", "tickers": tickers,
                "retrieved_at": d.get("retrieved_at"), "source": "S&P 500 구성 종목 (Wikipedia, 기존 유니버스 캐시)",
                "sha256": hashlib.sha256(",".join(tickers).encode()).hexdigest()[:16]}

    def panel(self) -> Optional[Panel]:
        try:
            m = self.panel_file.stat().st_mtime
        except OSError:
            return None
        if self._panel is None or m != self._panel_mtime:
            self._panel, self._panel_mtime = Panel.load(self.panel_file), m
        return self._panel

    def signal_session(self) -> str:
        return nyse_calendar.latest_completed_session(self.now()).isoformat()

    def refresh_panel(self, progress=None) -> Dict[str, Any]:
        u = self.universe()
        if not u["tickers"]:
            raise LabError("유니버스(S&P 500 구성 종목) 캐시가 없습니다. 먼저 'python app.py scan'을 한 번 실행하세요.")
        target = self.signal_session()
        cur = self.panel()
        if cur and cur.last == target and cur.meta.get("universe_sha256") == u["sha256"]:
            return {"status": "UP_TO_DATE", "last": cur.last, "tickers": len(cur.tickers)}
        frames = panel_mod.download(u["tickers"] + [BENCH], "6y", self.fetch, progress)
        if not frames or BENCH not in frames:
            raise LabError("Yahoo에서 가격을 받지 못했습니다 (네트워크 또는 제공자 오류).")
        p = Panel.from_frames(frames, {"universe_sha256": u["sha256"], "fetched_at": self.now().isoformat(),
                                       "requested": len(u["tickers"]) + 1, "received": len(frames),
                                       "source": "Yahoo Finance 일봉 (지연, auto_adjust=False)"})
        # A bar dated after the completed session (today's intraday bar) is dropped: never record on it.
        if p.last and p.last > target:
            keep = [i for i, d in enumerate(p.dates) if d <= target]
            p = Panel([p.dates[i] for i in keep], p.tickers, {k: v[keep] for k, v in p.data.items()}, p.meta)
        p.save(self.panel_file)
        self._panel, self._panel_mtime = p, self.panel_file.stat().st_mtime
        return {"status": "DOWNLOADED", "last": p.last, "tickers": len(p.tickers), "missing": p.meta["requested"] - len(frames)}

    # ------------------------------------------------------------------ ledger
    def read_ledger(self):
        recs, prev = [], GENESIS
        if not self.ledger_file.exists():
            return [], {"status": "OK", "records": 0}
        for n, line in enumerate(self.ledger_file.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except ValueError:
                return recs, {"status": "BROKEN", "line": n}
            if r.get("prev_hash") != prev or _hash(r) != r.get("hash"):
                return recs, {"status": "BROKEN", "line": n}
            recs.append(r)
            prev = r["hash"]
        return recs, {"status": "OK", "records": len(recs)}

    def record(self) -> Dict[str, Any]:
        """Append today's challenger signals (one per model per completed session)."""
        self.dir.mkdir(parents=True, exist_ok=True)
        with self._lock, open(self.dir / "ledger.lock", "w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)          # the daily job and the server button are separate processes
            p = self.panel()
            signal = self.signal_session()
            if p is None:
                raise LabError("가격 데이터가 없습니다. 먼저 데이터를 갱신하세요.")
            if p.last != signal:
                raise LabError(f"가격 데이터의 마지막 날짜({p.last})가 신호일({signal})과 달라 기록하지 않습니다.")
            recs, integ = self.read_ledger()
            if integ["status"] != "OK":
                raise LabError("도전자 기록 파일의 무결성 오류로 기록할 수 없습니다.")
            done = {(r["model"], r["signal_session"]) for r in recs}
            u = self.universe()
            i = p.idx[signal]
            # Entry = regular OPEN of the first session starting strictly after the record time (same rule as
            # P6-20): a record made during the session enters at the NEXT open, never at an open already past.
            phase = nyse_calendar.classify_signal(self.now())
            entry = phase["entry_session"]
            new, prev = [], recs[-1]["hash"] if recs else GENESIS
            for code in CHALLENGERS:
                if (code, signal) in done:
                    continue
                s = models.score(code, p, i, u["tickers"])
                rec = {"type": "SIGNAL", "model": code, "model_version": LAB_VERSION,
                       "params": models.MODELS[code]["params"], "common": models.COMMON,
                       "signal_session": signal, "entry_session": entry, "market_phase": phase["market_phase"],
                       "picks": s["picks"],
                       "eligible": s["eligible"], "universe_size": len(u["tickers"]),
                       "universe_sha256": u["sha256"], "panel_fingerprint": p.fingerprint(),
                       "recorded_at": self.now().astimezone(timezone.utc).isoformat(),
                       "seq": len(recs) + len(new) + 1, "prev_hash": prev}
                rec["hash"] = _hash(rec)
                prev = rec["hash"]
                new.append(rec)
            if new:
                self.dir.mkdir(parents=True, exist_ok=True)
                with open(self.ledger_file, "a", encoding="utf-8") as fh:
                    for r in new:
                        fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
                    fh.flush()
                    os.fsync(fh.fileno())
            return {"signal_session": signal, "entry_session": entry, "recorded": [r["model"] for r in new],
                    "already_recorded": sorted(c for c, s in done if s == signal)}

    def update(self, progress=None) -> Dict[str, Any]:
        pr = self.refresh_panel(progress)
        rec = self.record()
        self.bt_file.unlink(missing_ok=True)          # research results are recomputed for the new panel
        return {"panel": pr, "record": rec}

    def run_background(self) -> Dict[str, Any]:
        if self.job.get("state") == "RUNNING":
            return self.job
        self.job = {"state": "RUNNING", "started_at": self.now().isoformat(), "done": 0, "total": None}

        def prog(done, total):
            self.job.update(done=done, total=total)

        def work():
            try:
                res = self.update(prog)
                self.job = {"state": "DONE", "result": res, "finished_at": self.now().isoformat()}
            except LabError as exc:
                self.job = {"state": "FAILED", "error": str(exc)}
            except Exception as exc:          # provider/network: type only, never internals
                self.job = {"state": "FAILED", "error": f"예상치 못한 오류 ({type(exc).__name__})"}
        threading.Thread(target=work, daemon=True).start()
        return self.job

    # ------------------------------------------------------------------ comparison
    def p6_cohorts(self) -> Dict[str, Any]:
        """P6-11B PORTFOLIO_TOP5, VALID_PROSPECTIVE cohort only, first run per entry session (read-only)."""
        try:
            from pipeline import prospective_ledger as pl
            from pipeline import prospective_tracking as pt
            tdir = str(self.base / "tracking")
            recs = pl.read_observations(tdir)
        except Exception as exc:
            return {"status": "UNAVAILABLE", "error": type(exc).__name__, "cohorts": []}
        obs = [r for r in recs if r.get("record_type") == "OBSERVATION" and r.get("observation_class") == "PORTFOLIO_TOP5"]
        coh = pt._cohorts(obs, tdir) if obs else {}
        by_session: Dict[str, Dict[str, List[str]]] = {}
        stamp: Dict[str, Dict[str, str]] = {}
        for o in obs:
            if coh[o["observation_id"]]["cohort"] != "VALID_PROSPECTIVE":
                continue
            s = o["signal"]["entry_session"]
            by_session.setdefault(s, {}).setdefault(o["run_id"], []).append(o["ticker"])
            stamp.setdefault(s, {})[o["run_id"]] = o.get("recommendation_timestamp_utc") or o["run_id"]
        out = []
        for s in sorted(by_session):
            first = min(by_session[s], key=lambda rid: stamp[s][rid])
            out.append({"entry_session": s, "tickers": sorted(by_session[s][first]), "run_id": first,
                        "runs_that_session": len(by_session[s])})
        return {"status": "REAL", "cohorts": out}

    def comparison(self) -> Dict[str, Any]:
        recs, integ = self.read_ledger()
        cohorts: Dict[str, List[Dict]] = {"P6-11B": []}
        p6 = self.p6_cohorts()
        cohorts["P6-11B"] = p6["cohorts"]
        latest: Dict[str, Dict] = {}
        for code in CHALLENGERS:
            rs = [r for r in recs if r["model"] == code]
            cohorts[code] = [{"entry_session": r["entry_session"], "tickers": [x["ticker"] for x in r["picks"]]}
                             for r in rs]
            if rs:
                latest[code] = {"signal_session": rs[-1]["signal_session"], "entry_session": rs[-1]["entry_session"],
                                "picks": rs[-1]["picks"][:10], "eligible": rs[-1]["eligible"],
                                "n_picks": len(rs[-1]["picks"])}
        if p6["cohorts"]:
            c = p6["cohorts"][-1]
            latest["P6-11B"] = {"entry_session": c["entry_session"], "picks": [{"ticker": t} for t in c["tickers"]],
                                "n_picks": len(c["tickers"]), "run_id": c["run_id"]}
        p = self.panel()
        res = compare.compare(p, cohorts)
        meta = {code: models.MODELS[code] for code in CHALLENGERS}
        meta["P6-11B"] = {"name": "P6-11B (기준 모델)", "style": "스윙 (30일 재평가)",
                          "rule": "고정된 기준 모델의 TOP-5 (P6-20 유효 코호트, 진입일별 첫 실행)", "params": {}}
        order = ["P6-11B", "MOM_12_1", "LOWVOL_252", "TREND_SWING", "BASE_SPY", "BASE_EW"]
        return {"integrity": integ, "p6_status": p6["status"], "panel_last": p.last if p else None,
                "signal_session": self.signal_session(), "order": order, "models": meta, "results": res,
                "latest": latest, "horizons": list(compare.HORIZONS), "min_independent": compare.MIN_INDEPENDENT,
                "method": "진입일 시가 매수 → H거래일째 종가 매도, 배당 포함, 동일 비중, SPY 대비 초과수익. "
                          "모든 모델에 같은 기준을 적용합니다 (P6-11B 공식 성과는 P6-20 보고서).",
                "job": self.job}

    def status(self) -> Dict[str, Any]:
        recs, integ = self.read_ledger()
        p = self.panel()
        sessions = sorted({r["signal_session"] for r in recs})
        return {"version": LAB_VERSION, "integrity": integ, "records": len(recs), "sessions": len(sessions),
                "last_signal_session": sessions[-1] if sessions else None, "signal_session": self.signal_session(),
                "panel_last": p.last if p else None, "panel_tickers": len(p.tickers) if p else 0,
                "panel_meta": p.meta if p else None, "universe": {k: v for k, v in self.universe().items() if k != "tickers"},
                "job": self.job}

    # ------------------------------------------------------------------ research
    def research(self) -> Dict[str, Any]:
        p = self.panel()
        if p is None:
            return {"status": "UNAVAILABLE", "reason": "가격 데이터가 없습니다. 데이터를 먼저 갱신하세요."}
        fp = p.fingerprint() + ":" + backtest.SIM_VERSION
        try:
            cached = json.loads(self.bt_file.read_text(encoding="utf-8"))
            if cached.get("panel_fingerprint") == fp:
                return cached
        except (OSError, ValueError):
            pass
        u = self.universe()
        mem = membership.load(self.dir / "membership.json", self.now(), self.membership_fetch)
        added = mem["added"] if mem["status"] != "UNAVAILABLE" else None
        res = backtest.run_all(p, u["tickers"], added)
        if added is None:
            res["limitations"] = ["지수 편입일 정보를 받지 못해 현재 구성 종목을 전 기간에 적용했습니다. "
                                  "결과가 크게 부풀려져 있습니다."] + res["limitations"]
        res.update(status="REAL", panel_fingerprint=fp, panel_last=p.last, universe_size=len(u["tickers"]),
                   membership={"status": mem["status"], "retrieved_at": mem.get("retrieved_at"),
                               "source": mem.get("source"), "pit": added is not None},
                   models_meta={c: models.MODELS[c] for c in res["models"]},
                   method="매월 첫 거래일 교체(전일 종가까지의 데이터로 신호, 당일 시가 체결), 동일 비중, 배당 포함")
        for code, by_cost in res["models"].items():      # thin the NAV series for the screen (weekly points)
            for s in by_cost.values():
                if s.get("nav"):
                    s["dates"], s["nav"] = s["dates"][::5] + s["dates"][-1:], s["nav"][::5] + s["nav"][-1:]
        b = res["benchmark"]
        if b.get("nav"):
            b["dates"], b["nav"] = b["dates"][::5] + b["dates"][-1:], b["nav"][::5] + b["nav"][-1:]
        self.dir.mkdir(parents=True, exist_ok=True)
        tmp = self.bt_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(res, default=lambda x: None), encoding="utf-8")
        tmp.replace(self.bt_file)
        return res
