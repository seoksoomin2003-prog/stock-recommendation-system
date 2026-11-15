"""The three highest scores of every session, frozen before the entry open and tracked against the market.  Rules: reports/QSF_TOP3_TRACKING_PROTOCOL.md.

Each market and session is written once, with that day's full score list as the comparison group.  The ledger is only read: it
supplies the entry session and each stock's benchmark.  Returns are computed when read, from prices that exist by then.
"""
import fcntl
import gzip
import hashlib
import json
import os
import statistics
from datetime import datetime, time as clock, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

import numpy as np

from terminal.qsf import config, ledger as lg
from terminal.qsf.validate import rank

PROTOCOL = "reports/QSF_TOP3_TRACKING_PROTOCOL.md"
FOLDER = Path("data") / "qsf" / "top3"
FIRST = "2026-11-06"                    # the session whose entry is 2026-11-09, the first open after the user asked
TOP = 3
MIN_ROWS = {"US": 400, "KR": 200}       # fewer scored stocks than this in one strategy is a partial scan, not a day
HORIZONS = {"SWING": (1, 5, 10, 20), "LONG_TERM": (5, 21, 63)}
VERDICT_H = {"SWING": 5, "LONG_TERM": 21}
MIN_T = 2.0
GENESIS = "0" * 64
OPEN = {"US": (clock(9, 30), ZoneInfo("America/New_York")), "KR": (clock(9, 0), ZoneInfo("Asia/Seoul"))}


def entry_open(market: str, entry_session: str) -> datetime:
    t, tz = OPEN[market]
    return datetime.combine(datetime.fromisoformat(entry_session).date(), t, tz)


def _h(obj: Dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------- freezing
def build(latest: Dict[str, Any], snaps: List[Dict[str, Any]], market: str, at: datetime) -> Dict[str, Any]:
    """``latest``: the published scan.  ``snaps``: the ledger records of the same session (entry session and benchmark)."""
    session = latest["session"]
    meta = {s["ticker"]: s for s in snaps}
    entries = [s.get("entry_session") for s in snaps if s.get("entry_session")]
    if not entries:
        raise ValueError("NO_LEDGER_SESSION")
    entry = max(set(entries), key=entries.count)
    out: Dict[str, Any] = {}
    for strategy in config.STRATEGIES:
        rows = [r for r in latest.get("rows") or [] if r.get("strategy") == strategy and r.get("score") is not None
                and r.get("actionability") != "INSUFFICIENT_DATA" and r.get("data_date") == session]
        if len(rows) < MIN_ROWS[market]:
            raise ValueError("TOO_FEW_STOCKS")
        rows.sort(key=lambda r: (-r["score"], r["ticker"]))
        top = [{"rank": i + 1, "ticker": r["ticker"], "name": r.get("name"), "score": r["score"], "action": r.get("action"), "price": r.get("price"),
                "benchmark": (meta.get(r["ticker"]) or {}).get("benchmark")} for i, r in enumerate(rows[:TOP])]
        out[strategy] = {"top": top, "scores": [[r["ticker"], r["score"]] for r in rows]}
    return {"market": market, "session": session, "entry_session": entry, "model_version": latest.get("model_version"), "protocol": PROTOCOL,
            "recorded_at": at.isoformat(), "before_open": at < entry_open(market, entry), "strategies": out}


def _index(folder: Path) -> Tuple[List[Dict[str, Any]], str]:
    rows, prev, status = [], GENESIS, "OK"
    try:
        lines = (folder / "index.jsonl").read_text(encoding="utf-8").splitlines()
    except OSError:
        return [], "OK"
    for line in lines:
        try:
            r = json.loads(line)
        except ValueError:                          # a cut last line: the rows before it stay readable, and BROKEN stops new writes
            status = "BROKEN"
            break
        if r.get("prev_hash") != prev or _h({k: v for k, v in r.items() if k != "hash"}) != r.get("hash"):
            status = "BROKEN"
        prev = r.get("hash")
        rows.append(r)
    return rows, status


def write(base: Path, doc: Dict[str, Any]) -> bool:
    """Write-once.  A file left without its index line by a crash gets the line, with the file's own content."""
    folder = Path(base) / FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    with open(folder / "index.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        rows, status = _index(folder)
        if status != "OK":
            raise RuntimeError("top3 index integrity failure")
        if any(r["session"] == doc["session"] and r["market"] == doc["market"] for r in rows):
            return False
        p = folder / f"{doc['session']}_{doc['market']}.json.gz"
        if not p.exists():
            tmp = p.with_suffix(".tmp")
            with open(tmp, "wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as gz:
                gz.write(json.dumps(doc, ensure_ascii=False, sort_keys=True).encode("utf-8"))
            tmp.replace(p)
        with gzip.open(p, "rt", encoding="utf-8") as fh:
            kept = json.load(fh)
        row = {"session": kept["session"], "market": kept["market"], "file": p.name, "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
               "recorded_at": kept["recorded_at"], "before_open": kept["before_open"], "model_version": kept["model_version"],
               "prev_hash": rows[-1]["hash"] if rows else GENESIS}
        row["hash"] = _h(row)
        with open(folder / "index.jsonl", "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, sort_keys=True) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        return True


def freeze(base: Path, market: str, now: Callable[[], datetime] = lambda: datetime.now(timezone.utc), first: str = FIRST) -> Dict[str, Any]:
    """OK: the published scan's session is frozen (now or before).  WAITING: no usable scan or ledger session yet."""
    base = Path(base)
    try:
        latest = json.loads((base / "data" / "qsf" / f"latest_{market}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"status": "WAITING", "reason": "NO_SCAN"}
    if latest.get("status") != "REAL" or not latest.get("session"):
        return {"status": "WAITING", "reason": "NO_SCAN"}
    if latest["session"] < first:
        return {"status": "OK", "reason": "BEFORE_FIRST", "session": latest["session"]}
    led = lg.Ledger(base)
    if led.verify()["status"] != "OK":
        return {"status": "FAILED", "reason": "LEDGER_BROKEN"}
    snaps = [s for r in led._live_rows() if r["market"] == market and r["session"] == latest["session"] for s in led._load(r)]
    try:
        doc = build(latest, snaps, market, now())
    except ValueError as exc:
        return {"status": "WAITING", "reason": str(exc), "session": latest["session"]}
    wrote = write(base, doc)
    return {"status": "OK", "session": doc["session"], "written": wrote, "before_open": doc["before_open"] if wrote else None}


def read(base: Path, market: Optional[str] = None) -> Dict[str, Any]:
    folder = Path(base) / FOLDER
    rows, status = _index(folder)
    docs, bad = [], []
    for r in rows:
        p = folder / r["file"]
        if not p.exists() or hashlib.sha256(p.read_bytes()).hexdigest() != r["sha256"]:
            bad.append(r["file"])
            continue
        if market and r["market"] != market:
            continue
        with gzip.open(p, "rt", encoding="utf-8") as fh:
            docs.append(json.load(fh))
    return {"status": "OK" if status == "OK" and not bad else "BROKEN", "bad_files": bad, "docs": docs}


# ---------------------------------------------------------------------- outcomes
class _Prices:
    """Bars per ticker, loaded once, with their dates for the ledger's own outcome rule."""

    def __init__(self, loader: Callable[[str], List[Dict]]):
        self.loader, self.memo = loader, {}

    def get(self, t: str) -> Tuple[List[Dict], Optional[List[str]]]:
        if t not in self.memo:
            bars = self.loader(t) or []
            days = [b.get("date") for b in bars]
            self.memo[t] = (bars, days if all(isinstance(d, str) for d in days) and days == sorted(days) else None)
        return self.memo[t]

    def held(self, t: str, entry: str) -> int:
        """Sessions of this stock from the entry session to its newest bar."""
        bars, days = self.get(t)
        return sum(1 for b in bars if isinstance(b.get("date"), str) and b["date"] >= entry)


CALENDAR = {"US": "SPY", "KR": "^KS11"}   # whose sessions are the market calendar for a stock that stopped trading


def _out(px: _Prices, bench: _Prices, t: str, bsym: Optional[str], entry: str, h: int, cost: float, calendar: Optional[List[str]] = None) -> Optional[Dict[str, float]]:
    bars, days = px.get(t)
    return lg.outcome(bars, bench.get(bsym)[0] if bsym else [], entry, h, cost, entry, days, calendar=calendar)


def _spearman(x: List[float], y: List[float]) -> Optional[float]:
    if len(x) < 10:
        return None
    a, b = rank(np.array(x, dtype=float)), rank(np.array(y, dtype=float))
    if a.std() == 0 or b.std() == 0:
        return None
    return float(np.corrcoef(a, b)[0, 1])


def day_report(doc: Dict[str, Any], strategy: str, px: _Prices, bench: _Prices, cost: float, calendar: Optional[List[str]] = None) -> Dict[str, Any]:
    entry, part = doc["entry_session"], doc["strategies"][strategy]
    top = []
    for p in part["top"]:
        held = px.held(p["ticker"], entry)
        now = _out(px, bench, p["ticker"], p.get("benchmark"), entry, held, cost) if held else None
        top.append({**p, "so_far": now, "sessions_held": held,
                    "horizons": {str(h): _out(px, bench, p["ticker"], p.get("benchmark"), entry, h, cost, calendar) for h in HORIZONS[strategy]}})
    horizons = {}
    for h in HORIZONS[strategy]:
        got = [(s, o) for t, s in part["scores"] for o in [_out(px, bench, t, None, entry, h, cost, calendar)] if o]
        tops = [x["horizons"][str(h)] for x in top if x["horizons"][str(h)]]
        uni = statistics.mean(o["net"] for _, o in got) if got else None
        horizons[str(h)] = {"universe_n": len(got), "universe_mean_net": uni,
                            "top_mean_net": statistics.mean(o["net"] for o in tops) if tops else None,
                            "top_minus_universe": statistics.mean(o["net"] for o in tops) - uni if tops and uni is not None and len(tops) == len(top) else None,
                            "rank_corr": _spearman([s for s, _ in got], [o["gross"] for _, o in got])}
    return {"session": doc["session"], "entry_session": entry, "model_version": doc["model_version"], "before_open": doc["before_open"],
            "recorded_at": doc["recorded_at"], "top": top, "horizons": horizons}


def summarize(days: List[Dict[str, Any]], strategy: str) -> Dict[str, Any]:
    """Per model version, counted days only (frozen before the open)."""
    out: Dict[str, Any] = {}
    for version in sorted({d["model_version"] for d in days if d["before_open"]}):
        mine = sorted((d for d in days if d["before_open"] and d["model_version"] == version), key=lambda d: d["entry_session"])
        per_h = {}
        for h in HORIZONS[strategy]:
            picks = [x["horizons"][str(h)] for d in mine for x in d["top"] if x["horizons"][str(h)]]
            rel = [o["relative_net"] for o in picks if o["relative_net"] is not None]
            done = [d for d in mine if d["horizons"][str(h)]["universe_n"]]
            gap = [d["horizons"][str(h)]["top_minus_universe"] for d in done if d["horizons"][str(h)]["top_minus_universe"] is not None]
            ic = [d["horizons"][str(h)]["rank_corr"] for d in done if d["horizons"][str(h)]["rank_corr"] is not None]
            spaced = [d["horizons"][str(h)]["rank_corr"] for d in done[::h] if d["horizons"][str(h)]["rank_corr"] is not None]
            indep = len(done) / h
            t = None
            if len(spaced) >= 2 and statistics.stdev(spaced) > 0:
                t = statistics.mean(spaced) / (statistics.stdev(spaced) / len(spaced) ** 0.5)
            row = {"picks": len(picks), "sessions": len(done), "independent": indep, "beat_benchmark": sum(x > 0 for x in rel) / len(rel) if rel else None,
                   "mean_relative_net": statistics.mean(rel) if rel else None, "mean_top_minus_universe": statistics.mean(gap) if gap else None,
                   "mean_rank_corr": statistics.mean(ic) if ic else None, "spaced_rank_corr_t": t}
            if h == VERDICT_H[strategy]:
                if indep < config.MIN_INDEPENDENT:
                    row["verdict"] = f"판단 보류 (독립 표본 {indep:.1f}/{config.MIN_INDEPENDENT})"
                else:
                    good = row["mean_rank_corr"] is not None and row["mean_rank_corr"] > 0 and t is not None and t >= MIN_T
                    row["verdict"] = "점수 순위에 증거 있음" if good else "증거 없음"
            per_h[str(h)] = row
        out[version] = {"days": len(mine), "horizons": per_h}
    return out


def report(docs: List[Dict[str, Any]], market: str, loader: Callable[[str], List[Dict]], bench_loader: Callable[[str], List[Dict]],
           cost: Optional[float] = None) -> Dict[str, Any]:
    cost = config.round_trip_cost(market) if cost is None else cost
    px, bench = _Prices(loader), _Prices(bench_loader)
    calendar = sorted({b["date"] for b in bench.get(CALENDAR[market])[0] if isinstance(b.get("date"), str)}) or None
    out = {"market": market, "protocol": PROTOCOL, "cost_round_trip_pct": cost * 100, "verdict_horizon": VERDICT_H, "strategies": {}}
    for strategy in config.STRATEGIES:
        days = [day_report(d, strategy, px, bench, cost, calendar) for d in sorted(docs, key=lambda d: d["session"]) if d["market"] == market and strategy in d["strategies"]]
        out["strategies"][strategy] = {"summary": summarize(days, strategy), "days": days[::-1]}
    return out
