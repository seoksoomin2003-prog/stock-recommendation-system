"""Immutable score snapshots and prospective validation.

Each batch is an immutable gzip shard; ``index.jsonl`` is an append-only hash chain over the shards.  Market and strategy
cohorts are never pooled.  Later reassessments are new snapshots; an original is never rewritten.  Outcomes are computed
when reading, from prices that exist by then: entry at the session after the signal (open), exit at the close H sessions later.
"""
import bisect
import fcntl
import gzip
import hashlib
import json
import statistics
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

from terminal.qsf import config

GENESIS = "0" * 64
FIELDS = ("market", "ticker", "strategy", "model_version", "spec_version", "profile", "score", "band", "action", "actionability", "coverage",
          "confidence", "held", "data_date", "price", "benchmark", "recorded_at", "entry_session", "entry_status", "holding", "gates", "provenance")


def snapshot(card: Dict[str, Any]) -> Dict[str, Any]:
    """The stored record: full factor trace (raw, normalized, contribution, status, source, date) without the indicator dump."""
    rec = {k: card.get(k) for k in FIELDS}
    rec["domains"] = {d: {"points": v["points"], "score_100": v["score_100"], "coverage": v["coverage"]} for d, v in card["domains"].items()}
    rec["factors"] = [{k: f.get(k) for k in ("factor", "domain", "weight", "status", "raw", "normalized", "contribution", "source", "as_of", "reason")} for f in card["factors"]]
    rec["target"], rec["stop"] = card["levels"].get("target"), card["levels"].get("stop")
    return rec


class Ledger:
    def __init__(self, root: Path):
        self.dir = Path(root) / "data" / "qsf" / "ledger"
        self.index = self.dir / "index.jsonl"

    def read_index(self) -> Dict[str, Any]:
        rows, prev, status = [], GENESIS, "OK"
        try:
            lines = self.index.read_text(encoding="utf-8").splitlines()
        except OSError:
            return {"rows": [], "status": "OK"}
        for line in lines:
            r = json.loads(line)
            body = {k: v for k, v in r.items() if k != "hash"}
            if r["prev_hash"] != prev or _hash(body) != r["hash"]:
                status = "BROKEN"
            prev = r["hash"]
            rows.append(r)
        return {"rows": rows, "status": status}

    def verify(self) -> Dict[str, Any]:
        idx = self.read_index()
        bad = []
        for r in idx["rows"]:
            if r.get("type") == "VOID":
                continue
            p = self.dir / r["file"]
            if not p.exists() or hashlib.sha256(p.read_bytes()).hexdigest() != r["sha256"]:
                bad.append(r["file"])
        return {"status": "OK" if idx["status"] == "OK" and not bad else "BROKEN", "shards": sum(1 for r in idx["rows"] if r.get("type") != "VOID"), "voided": sum(1 for r in idx["rows"] if r.get("type") == "VOID"), "bad_files": bad}

    def _live_rows(self) -> List[Dict[str, Any]]:
        """Shards in effect: a voided shard stays on disk and in backups but is left out of every reading."""
        rows = self.read_index()["rows"]
        void = {r["file"] for r in rows if r.get("type") == "VOID"}
        return [r for r in rows if r.get("type") != "VOID" and r["file"] not in void]

    def void_shard(self, name: str, reason: str) -> Dict[str, Any]:
        """Append a VOID row for a shard recorded from bad data.  Nothing is deleted."""
        with open(self.dir / "ledger.lock", "w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            idx = self.read_index()
            if idx["status"] != "OK" or not any(r["file"] == name for r in idx["rows"]):
                raise RuntimeError("cannot void: unknown shard or broken index")
            row = {"type": "VOID", "seq": len(idx["rows"]) + 1, "file": name, "reason": reason, "prev_hash": idx["rows"][-1]["hash"]}
            row["hash"] = _hash(row)
            with open(self.index, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            return {"voided": name}

    def _load(self, row: Dict[str, Any]) -> List[Dict[str, Any]]:
        with gzip.open(self.dir / row["file"], "rt", encoding="utf-8") as fh:
            return [json.loads(x) for x in fh]

    def snapshots(self, market: Optional[str] = None, strategy: Optional[str] = None, ticker: Optional[str] = None) -> List[Dict[str, Any]]:
        out = []
        for r in self._live_rows():
            if market and r["market"] != market:
                continue
            out += [s for s in self._load(r) if (not strategy or s["strategy"] == strategy) and (not ticker or s["ticker"] == ticker)]
        return out

    def append(self, session: str, market: str, cards: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Add snapshots for a session; a (ticker, strategy) already stored for that session is kept, not replaced."""
        self.dir.mkdir(parents=True, exist_ok=True)
        with open(self.dir / "ledger.lock", "w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            idx = self.read_index()
            if idx["status"] != "OK":
                raise RuntimeError("QSF ledger integrity failure")
            done = set()
            for r in self._live_rows():
                if r["session"] == session and r["market"] == market:
                    done |= {(s["ticker"], s["strategy"]) for s in self._load(r)}
            new = [c for c in cards if (c["ticker"], c["strategy"]) not in done]
            if not new:
                return {"recorded": 0, "already": len(done)}
            seq = len(idx["rows"]) + 1
            name = f"{session}_{market}_{seq:06d}.jsonl.gz"
            payload = "\n".join(json.dumps(snapshot(c), ensure_ascii=False, sort_keys=True, default=str) for c in new) + "\n"
            tmp = self.dir / (name + ".tmp")
            with open(tmp, "wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as gz:
                gz.write(payload.encode("utf-8"))
            tmp.replace(self.dir / name)
            row = {"seq": seq, "session": session, "market": market, "file": name, "sha256": hashlib.sha256((self.dir / name).read_bytes()).hexdigest(),
                   "records": len(new), "model_version": config.MODEL_VERSION, "prev_hash": idx["rows"][-1]["hash"] if idx["rows"] else GENESIS}
            row["hash"] = _hash(row)
            with open(self.index, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, sort_keys=True) + "\n")
            return {"recorded": len(new), "already": len(done), "file": name}

    def previous(self, market: str, ticker: str, strategy: str, before: str) -> Optional[Dict[str, Any]]:
        for r in reversed(self._live_rows()):
            if r["market"] == market and r["session"] < before:
                hit = next((s for s in self._load(r) if s["ticker"] == ticker and s["strategy"] == strategy), None)
                if hit:
                    return hit
        return None


def _hash(obj: Dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True).encode("utf-8")).hexdigest()


def stability(prev: Optional[Dict[str, Any]], cur: Dict[str, Any], big: float = 10.0) -> Dict[str, Any]:
    """Separates a change from new information from one caused by a provider, coverage or model change."""
    if not prev or prev.get("score") is None or cur.get("score") is None:
        return {"status": "NO_PREVIOUS"}
    delta = cur["score"] - prev["score"]
    before = {f["factor"]: f for f in prev["factors"]}
    moves, status_changes = [], []
    for f in cur["factors"]:
        b = before.get(f["factor"])
        if not b:
            continue
        if b["status"] != f["status"] or (b.get("source") != f.get("source") and f.get("source")):
            status_changes.append(f["factor"])
        if f.get("contribution") is not None and b.get("contribution") is not None:
            moves.append((f["factor"], f["contribution"] - b["contribution"]))
    moves.sort(key=lambda x: -abs(x[1]))
    cause = "MODEL_CHANGE" if prev.get("model_version") != cur.get("model_version") else "DATA_QUALITY_OR_PROVIDER" if status_changes else "NEW_INFORMATION"
    return {"status": "REAL", "previous_date": prev.get("data_date"), "previous_score": prev["score"], "delta": delta, "large": abs(delta) >= big, "cause": cause,
            "status_changes": status_changes, "top_moves": [{"factor": k, "change": v} for k, v in moves[:3]]}


def factor_correlations(snaps: List[Dict[str, Any]], min_obs: int = 30, flag: float = 0.7) -> Dict[str, Any]:
    """Diagnostics from stored past snapshots only, per cohort.  Never feeds back into a score."""
    rows = [{f["factor"]: f["normalized"] for f in s["factors"] if f.get("normalized") is not None} for s in snaps]
    names = sorted({k for r in rows for k in r})
    pairs = []
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            x = [(r[a], r[b]) for r in rows if a in r and b in r]
            if len(x) < min_obs:
                continue
            arr = np.array(x)
            if arr[:, 0].std() == 0 or arr[:, 1].std() == 0:
                continue
            c = float(np.corrcoef(arr[:, 0], arr[:, 1])[0, 1])
            if abs(c) >= flag:
                pairs.append({"a": a, "b": b, "corr": c, "n": len(x)})
    return {"status": "REAL" if rows and len(rows) >= min_obs else "INSUFFICIENT", "observations": len(rows), "high_pairs": sorted(pairs, key=lambda p: -abs(p["corr"]))}


# ---------------------------------------------------------------------- forward outcomes
def outcome(path: List[Dict[str, Any]], bench: List[Dict[str, Any]], signal_session: str, h: int, cost: float, entry_session: Optional[str] = None,
            dates: Optional[List[str]] = None, bench_by_date: Optional[Dict[str, Dict[str, Any]]] = None) -> Optional[Dict[str, float]]:
    """Bars must be dated.  Entry is the open (dividend-adjusted basis) of the recorded entry session, or the next bar for a
    historical check; a snapshot can never enter at an open that passed before it was written.  Exit is the h-th bar's close.
    None until matured, or when a price is missing: never zero.
    ``dates`` (the bars' dates, in order) and ``bench_by_date`` only save repeating the same work across many snapshots; the answer is the same without them."""
    if dates is not None:
        idx = bisect.bisect_left(dates, entry_session) if entry_session else bisect.bisect_right(dates, signal_session)
    else:
        idx = next((i for i, b in enumerate(path) if (b["date"] >= entry_session if entry_session else b["date"] > signal_session)), None)
    if idx is None or idx + h - 1 >= len(path):
        return None
    start, end = path[idx], path[idx + h - 1]
    if not start.get("open") or not start.get("close") or not end.get("adj_close") or not start.get("adj_close"):
        return None
    adj_open = start["open"] * start["adj_close"] / start["close"]
    gross = end["adj_close"] / adj_open - 1
    window = path[idx:idx + h]
    low = min(b["adj_close"] for b in window if b.get("adj_close"))
    bmap = bench_by_date if bench_by_date is not None else {b["date"]: b for b in bench}
    bs, be = bmap.get(start["date"]), bmap.get(end["date"])
    rel = None
    if bs and be and bs.get("open") and bs.get("adj_close") and be.get("adj_close"):
        rel = gross - (be["adj_close"] / (bs["open"] * bs["adj_close"] / bs["close"]) - 1)
    return {"gross": gross, "net": gross - cost, "relative_net": rel - cost if rel is not None else None, "worst": low / adj_open - 1,
            "entry_date": start["date"], "exit_date": end["date"]}


def bucket_of(score: float) -> str:
    for lo, hi in config.BUCKETS:
        if lo <= score < hi:
            return f"{lo:g}-{min(hi, 100):.0f}"
    return "100"


def validate(snaps: List[Dict[str, Any]], market: str, strategy: str, loader: Callable[[str], List[Dict]], bench: List[Dict], cost: Optional[float] = None) -> Dict[str, Any]:
    """Bucket report for ONE cohort.  Below the independence minimum the verdict stays 'no verdict', whatever the numbers say."""
    cost = config.round_trip_cost(market) if cost is None else cost
    horizons = config.SWING_HORIZONS if strategy == "SWING" else tuple(m * 21 for m in config.LONG_HORIZONS_MONTHS)
    cohort = [s for s in snaps if s["market"] == market and s["strategy"] == strategy and s.get("score") is not None and s.get("actionability") != "INSUFFICIENT_DATA"]
    sessions = sorted({s["data_date"] for s in cohort})
    picks_by_session: Dict[str, set] = {}
    for s in cohort:
        if s["score"] >= 70:
            picks_by_session.setdefault(s["data_date"], set()).add(s["ticker"])
    turnover = []
    ordered = sorted(picks_by_session)
    for a, b in zip(ordered, ordered[1:]):
        u = picks_by_session[a] | picks_by_session[b]
        turnover.append(len(picks_by_session[a] ^ picks_by_session[b]) / len(u) if u else 0.0)
    out = {"market": market, "strategy": strategy, "snapshots": len(cohort), "sessions": len(sessions), "cost_round_trip_pct": cost * 100, "cost_basis": config.COSTS[market]["basis"],
           "mean_turnover_70plus": statistics.mean(turnover) if turnover else None, "horizons": {}}
    cache: Dict[str, Tuple[List[Dict], Optional[List[str]]]] = {}
    bench_by_date = {b["date"]: b for b in bench}
    for h in horizons:
        buckets: Dict[str, List[Dict[str, float]]] = {}
        matured = set()
        for s in cohort:
            if s["ticker"] not in cache:
                bars = loader(s["ticker"]) or []
                days = [b["date"] for b in bars]
                cache[s["ticker"]] = (bars, days if days == sorted(days) else None)      # bars out of order take the plain scan
            path, days = cache[s["ticker"]]
            o = outcome(path, bench, s["data_date"], h, cost, s.get("entry_session"), days, bench_by_date)
            if o:
                buckets.setdefault(bucket_of(s["score"]), []).append(o)
                matured.add(s["data_date"])
        indep = len(matured) / h
        table = {}
        for lo, hi in config.BUCKETS:
            key = f"{lo:g}-{min(hi, 100):.0f}"
            rows = buckets.get(key) or []
            rel = [r["relative_net"] for r in rows if r["relative_net"] is not None]
            net = [r["net"] for r in rows]
            table[key] = {"n": len(rows), "mean_net": statistics.mean(net) if net else None, "median_net": statistics.median(net) if net else None,
                          "mean_relative_net": statistics.mean(rel) if rel else None, "win_rate_vs_benchmark": sum(x > 0 for x in rel) / len(rel) if rel else None,
                          "mean_gross": statistics.mean(r["gross"] for r in rows) if rows else None, "mean_worst": statistics.mean(r["worst"] for r in rows) if rows else None,
                          "mean_net_double_cost": statistics.mean(r["gross"] - 2 * cost for r in rows) if rows else None,
                          "p10_net": float(np.percentile(net, 10)) if net else None, "p90_net": float(np.percentile(net, 90)) if net else None}
        out["horizons"][str(h)] = {"matured_sessions": len(matured), "independent_samples": indep, "buckets": table,
                                   "verdict": "판단 보류 (독립 표본 부족)" if indep < config.MIN_INDEPENDENT else "표본 충족: 구간 차이를 해석할 수 있음"}
    return out
