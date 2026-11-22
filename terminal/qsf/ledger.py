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
import os
import statistics
import sys
import threading
from array import array
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

from terminal.qsf import config
from utils import durable

GENESIS = "0" * 64
FIELDS = ("market", "ticker", "strategy", "model_version", "spec_version", "profile", "score", "band", "action", "actionability", "coverage",
          "confidence", "held", "data_date", "price", "benchmark", "recorded_at", "entry_session", "entry_status", "holding", "gates", "provenance",
          # from QSF-1.5.2 on (earlier lines do not have them and are not rewritten): why a band or a confidence is what it is
          "input_coverage", "conservative_score", "band_held_back")


def snapshot(card: Dict[str, Any]) -> Dict[str, Any]:
    """The stored record: full factor trace (raw, normalized, contribution, status, source, date) without the indicator dump."""
    rec = {k: card.get(k) for k in FIELDS}
    rec["domains"] = {d: {"points": v["points"], "score_100": v["score_100"], "coverage": v["coverage"], **({"reference": True} if v.get("reference") else {})} for d, v in card["domains"].items()}
    rec["factors"] = [{**{k: f.get(k) for k in ("factor", "domain", "weight", "status", "raw", "normalized", "contribution", "source", "as_of", "reason")},
                       **({"scored": False, "reference_weight": f.get("reference_weight")} if f.get("scored") is False else {})} for f in card["factors"]]
    rec["target"], rec["stop"] = card["levels"].get("target"), card["levels"].get("stop")
    if card.get("cik"):             # US, from 2026-11-17: a ticker can be renamed or handed to another company; the SEC number cannot
        rec["cik"] = card["cik"]
    if card.get("fund_period"):     # from 2026-11-23: the score on annual statements and on trailing four quarters (reports/QSF_FUND_PERIOD_PROTOCOL.md)
        rec["fund_period"] = card["fund_period"]
    return rec


LIGHT = ("market", "ticker", "strategy", "model_version", "score", "actionability", "data_date", "entry_session")


def light(s: Dict[str, Any]) -> Dict[str, Any]:
    """What the validation report reads of a snapshot: the fields ``validate`` uses and the factors' normalized values, packed.
    A full snapshot takes about 34 KB in memory (measured 2026-11-15: 8,050 US snapshots, 270 MB); the report read every one
    of every session at once, which grows by about 35 MB a US session.  This is under 1 KB."""
    fs = [f for f in s.get("factors") or [] if f.get("normalized") is not None]
    return {**{k: s.get(k) for k in LIGHT}, "norm": (tuple(sys.intern(str(f["factor"])) for f in fs), array("d", [f["normalized"] for f in fs]))}


def _norm_of(s: Dict[str, Any]):
    if "norm" in s:
        return s["norm"]
    fs = [f for f in s["factors"] if f.get("normalized") is not None]
    return [f["factor"] for f in fs], [f["normalized"] for f in fs]


SIDE_VERSION = 1
SIDE_FIELDS = ("model_version", "score", "band", "action", "actionability", "confidence", "entry_status", "price", "data_date")
PREV_KEPT = 2                       # shards whose "previous" view stays in memory: the newest prior one of each market


def _side_row(s: Dict[str, Any]) -> Dict[str, Any]:
    return {**{k: s.get(k) for k in SIDE_FIELDS}, "domains": {d: {"score_100": (v or {}).get("score_100")} for d, v in (s.get("domains") or {}).items()}}


def _prev_view(s: Dict[str, Any]) -> Dict[str, Any]:
    """What ``stability`` reads of an earlier snapshot, and nothing else."""
    it = sys.intern
    return {"score": s.get("score"), "model_version": s.get("model_version"), "data_date": s.get("data_date"),
            "band": s.get("band"), "actionability": s.get("actionability"),          # the buy band's buffer reads the band the stock was recorded in (QSF-1.5.0)
            "factors": [{"factor": it(str(f["factor"])), "status": it(str(f["status"])) if isinstance(f.get("status"), str) else f.get("status"),
                         "source": it(f["source"]) if isinstance(f.get("source"), str) else f.get("source"), "contribution": f.get("contribution")}
                        for f in s.get("factors") or []]}


class Ledger:
    def __init__(self, root: Path):
        self.dir = Path(root) / "data" / "qsf" / "ledger"
        self.index = self.dir / "index.jsonl"
        self.side_dir = self.dir.parent / "ledger_side"
        self._guard = threading.Lock()
        self._rows_memo: Optional[Tuple[Any, List[Dict[str, Any]]]] = None
        self._members_memo: Dict[str, Tuple[Any, Dict[Tuple[str, str], List[int]]]] = {}
        self._prev_memo: Dict[str, Dict[Tuple[str, str], Dict[str, Any]]] = {}
        self._verify_memo: Optional[Tuple[Any, Dict[str, Any]]] = None

    def read_index(self) -> Dict[str, Any]:
        rows, prev, status = [], GENESIS, "OK"
        try:
            lines = self.index.read_text(encoding="utf-8").splitlines()
        except OSError:
            return {"rows": [], "status": "OK"}
        for line in lines:
            try:
                r = json.loads(line)
            except ValueError:                      # a line cut short by a full disk or a power loss: the rows before it stay readable,
                status = "BROKEN"                   # and BROKEN stops every append until it is repaired
                break
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

    def has_session(self, session: str, market: str) -> bool:
        """Whether a shard in effect holds ``session`` of ``market``.  Reads the index only."""
        try:
            return any(r.get("session") == session and r.get("market") == market for r in self._live_rows())
        except Exception:
            return False

    def _load(self, row: Dict[str, Any]) -> List[Dict[str, Any]]:
        with gzip.open(self.dir / row["file"], "rt", encoding="utf-8") as fh:
            return [json.loads(x) for x in fh]

    # ------------------------------------------------------------------ cheap readings of immutable shards
    # A shard never changes once written, so what is derived from it can be kept: in a small file beside the ledger, named by the
    # shard's own hash, and in memory.  Before, one stock's history parsed every shard of its market in full on every view (0.7 s
    # with 8 US sessions, and one more shard each trading day), and each card of a scan parsed the previous session's shard again.
    def _index_stamp(self):
        try:
            st = self.index.stat()
            return st.st_mtime_ns, st.st_size
        except OSError:
            return None

    def _rows(self) -> List[Dict[str, Any]]:
        """``_live_rows`` kept until the index file changes.  For readers only: ``append`` and ``void_shard`` read the file itself."""
        stamp = self._index_stamp()
        memo = self._rows_memo
        if memo is None or memo[0] != stamp or stamp is None:
            memo = self._rows_memo = (stamp, self._live_rows())
        return memo[1]

    def side(self, row: Dict[str, Any]) -> Dict[str, Dict[str, Dict[str, Any]]]:
        """ticker -> strategy -> the few scalar fields of that snapshot (``SIDE_FIELDS`` and each domain's score).  Read from the
        side file when it exists; otherwise built from the shard, and stored only when the shard still has the hash the index
        recorded, so a damaged shard can never leave a side file behind."""
        p = self.side_dir / f"{row['file']}.{str(row.get('sha256'))[:16]}.v{SIDE_VERSION}.json.gz"
        try:
            with gzip.open(p, "rt", encoding="utf-8") as fh:
                d = json.load(fh)
            if d.get("v") == SIDE_VERSION and isinstance(d.get("rows"), dict):
                return d["rows"]
        except (OSError, ValueError, EOFError, AttributeError):
            pass
        raw = (self.dir / row["file"]).read_bytes()
        rows: Dict[str, Dict[str, Dict[str, Any]]] = {}
        for line in gzip.decompress(raw).decode("utf-8").splitlines():
            s = json.loads(line)
            rows.setdefault(s["ticker"], {}).setdefault(s["strategy"], _side_row(s))       # the first record stands, as everywhere
        if hashlib.sha256(raw).hexdigest() == row.get("sha256"):
            try:
                self.side_dir.mkdir(parents=True, exist_ok=True)
                tmp = p.with_name(f"{p.name}.{os.getpid()}.{threading.get_ident()}.tmp")
                with open(tmp, "wb") as out, gzip.GzipFile(fileobj=out, mode="wb", mtime=0) as gz:
                    gz.write(json.dumps({"v": SIDE_VERSION, "file": row["file"], "rows": rows}, ensure_ascii=False).encode("utf-8"))
                os.replace(tmp, p)
            except OSError:                             # a full or read-only disk: the reading still succeeds, it is only not kept
                pass
        return rows

    def _members(self, market: str, rows: List[Dict[str, Any]]) -> Dict[Tuple[str, str], List[int]]:
        """(ticker, strategy) -> positions in ``rows`` of the shards that hold it, in index order."""
        stamp = self._index_stamp()
        memo = self._members_memo.get(market)
        if memo is None or memo[0] != stamp or stamp is None:
            where: Dict[Tuple[str, str], List[int]] = {}
            for i, r in enumerate(rows):
                if r["market"] == market:
                    for t, by in self.side(r).items():
                        for s in by:
                            where.setdefault((t, s), []).append(i)
            memo = self._members_memo[market] = (stamp, where)
        return memo[1]

    def _previous_of(self, row: Dict[str, Any]) -> Dict[Tuple[str, str], Dict[str, Any]]:
        got = self._prev_memo.get(row["file"])
        if got is None:
            got = {}
            for s in self._load(row):
                got.setdefault((s["ticker"], s["strategy"]), _prev_view(s))
            while len(self._prev_memo) >= PREV_KEPT:
                self._prev_memo.pop(next(iter(self._prev_memo)))
            self._prev_memo[row["file"]] = got
        return got

    def verified(self) -> Dict[str, Any]:
        """``verify`` reused while the index and every shard keep their size and write time.  A file that is rewritten, cut short or
        removed changes one of them and is hashed again; the daily check and ``qsf verify`` always hash everything."""
        rows = self.read_index()["rows"]
        stamp = [self._index_stamp()]
        for r in rows:
            if r.get("type") == "VOID":
                continue
            try:
                st = (self.dir / r["file"]).stat()
                stamp.append((r["file"], st.st_mtime_ns, st.st_size))
            except OSError:
                stamp.append((r["file"], None, None))
        memo, key = self._verify_memo, tuple(stamp)
        if memo is None or memo[0] != key or key[0] is None:
            memo = self._verify_memo = (key, self.verify())
        return memo[1]

    def snapshots(self, market: Optional[str] = None, strategy: Optional[str] = None, ticker: Optional[str] = None,
                  keep: Optional[Callable[[Dict[str, Any]], Any]] = None) -> List[Any]:
        """``keep``: applied to each snapshot as its shard is read, so only what the caller needs stays in memory; a snapshot it
        maps to None is left out."""
        out = []
        for r in self._live_rows():
            if market and r["market"] != market:
                continue
            got = (s for s in self._load(r) if (not strategy or s["strategy"] == strategy) and (not ticker or s["ticker"] == ticker))
            out += list(got) if keep is None else [k for k in map(keep, got) if k is not None]
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
            durable.replace(tmp, self.dir / name)       # on the disk before the index line that vouches for it
            row = {"seq": seq, "session": session, "market": market, "file": name, "sha256": hashlib.sha256((self.dir / name).read_bytes()).hexdigest(),
                   "records": len(new), "model_version": config.MODEL_VERSION, "prev_hash": idx["rows"][-1]["hash"] if idx["rows"] else GENESIS}
            row["hash"] = _hash(row)
            with open(self.index, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, sort_keys=True) + "\n")
                fh.flush()
                os.fsync(fh.fileno())               # the line is on the disk before the shard counts as recorded
            return {"recorded": len(new), "already": len(done), "file": name}

    def session_before(self, market: str, session: str) -> Optional[str]:
        """The newest recorded session earlier than ``session``."""
        return max((r["session"] for r in self._live_rows() if r["market"] == market and r["session"] < session), default=None)

    def recent_sessions(self, market: str, before: str, n: int) -> List[str]:
        """The last ``n`` recorded sessions of the market earlier than ``before``, oldest first (read from the kept index rows)."""
        with self._guard:
            return sorted({r["session"] for r in self._rows() if r["market"] == market and r["session"] < before})[-n:]

    def of_session(self, market: str, session: str, strategy: str) -> List[Dict[str, Any]]:
        return [s for r in self._live_rows() if r["market"] == market and r["session"] == session for s in self._load(r) if s["strategy"] == strategy]

    def previous(self, market: str, ticker: str, strategy: str, before: str) -> Optional[Dict[str, Any]]:
        """The stock's newest snapshot of an earlier session, reduced to what ``stability`` reads (score, version, data date and
        each factor's status, source and contribution).  The shard is the same one the full walk found: the newest in index order
        that holds the stock under this strategy.  A stock the ledger never held costs no shard reading at all."""
        with self._guard:
            rows = self._rows()
            for i in reversed(self._members(market, rows).get((ticker, strategy), ())):
                if rows[i]["session"] < before:
                    return self._previous_of(rows[i]).get((ticker, strategy))
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
    rows = [_norm_of(s) for s in snaps]             # (factor names, values) of each snapshot, full or ``light``
    names = sorted({k for keys, _ in rows for k in keys})
    col = {k: j for j, k in enumerate(names)}
    vals, have = np.zeros((len(rows), len(names))), np.zeros((len(rows), len(names)), dtype=bool)
    for n, (keys, values) in enumerate(rows):
        for k, v in zip(keys, values):
            vals[n, col[k]], have[n, col[k]] = v, True
    pairs = []
    for i, a in enumerate(names):
        for j in range(i + 1, len(names)):
            both = have[:, i] & have[:, j]
            count = int(both.sum())
            if count < min_obs:
                continue
            arr = np.column_stack((vals[both, i], vals[both, j]))      # the same two columns, in snapshot order, that a list of pairs gave
            if arr[:, 0].std() == 0 or arr[:, 1].std() == 0:
                continue
            c = float(np.corrcoef(arr[:, 0], arr[:, 1])[0, 1])
            if abs(c) >= flag:
                pairs.append({"a": a, "b": names[j], "corr": c, "n": count})
    return {"status": "REAL" if rows and len(rows) >= min_obs else "INSUFFICIENT", "observations": len(rows), "high_pairs": sorted(pairs, key=lambda p: -abs(p["corr"]))}


# ---------------------------------------------------------------------- forward outcomes
STOP_GAP = 5          # market sessions with no bar after a stock's last one before it counts as no longer trading (a lag of a day or two is not)


def _stopped_exit(path: List[Dict[str, Any]], idx: int, h: int, calendar: List[str]) -> Optional[Tuple[Dict[str, Any], str]]:
    """The last traded bar of a stock that stopped trading inside the horizon, and the horizon's last market session.
    Approved by the user on 2026-11-08: such a stock is sold at its last trade and held as cash to the horizon, as in the research tests
    and the US challenger record.  None when the horizon has not ended on the market calendar, or the stock may only be lagging."""
    j = bisect.bisect_left(calendar, path[idx]["date"])
    if j >= len(calendar) or calendar[j] != path[idx]["date"] or j + h - 1 >= len(calendar):
        return None
    horizon_end = calendar[j + h - 1]
    last = next((b for b in reversed(path[idx:]) if b.get("adj_close") and b.get("close") and b["date"] <= horizon_end), None)
    if last is None or any(b.get("adj_close") and b["date"] > last["date"] for b in path[idx:]):
        return None                    # it traded again later: a gap, not a stop
    if len(calendar) - bisect.bisect_right(calendar, last["date"]) < STOP_GAP:
        return None
    return last, horizon_end


def outcome(path: List[Dict[str, Any]], bench: List[Dict[str, Any]], signal_session: str, h: int, cost: float, entry_session: Optional[str] = None,
            dates: Optional[List[str]] = None, bench_by_date: Optional[Dict[str, Dict[str, Any]]] = None,
            calendar: Optional[List[str]] = None) -> Optional[Dict[str, float]]:
    """Bars must be dated.  Entry is the open (dividend-adjusted basis) of the recorded entry session, or the next bar for a
    historical check; a snapshot can never enter at an open that passed before it was written.  Exit is the h-th bar's close.
    With ``calendar`` (the market's sessions, in order), a stock that stopped trading before its h-th bar exits at its last trade and
    is compared with the benchmark over the whole horizon; it carries ``stopped``.  Without it, such a stock stays None as before.
    None until matured, or when a price is missing: never zero.
    None too when the series starts after the entry (review of 2026-11-17): the search below would land on the series' first bar
    and report the return of some later window as this record's.  It could not happen while every price store reached back
    past the first record (2026-11-03); the Korean scan keeps 800 days, so it would have from about 2029-01.
    ``dates`` (the bars' dates, in order) and ``bench_by_date`` only save repeating the same work across many snapshots; the answer is the same without them."""
    first = dates[0] if dates else path[0]["date"] if path else None
    if first is None or first > (entry_session or signal_session):
        return None
    if dates is not None:
        idx = bisect.bisect_left(dates, entry_session) if entry_session else bisect.bisect_right(dates, signal_session)
    else:
        idx = next((i for i, b in enumerate(path) if (b["date"] >= entry_session if entry_session else b["date"] > signal_session)), None)
    if idx is None or idx >= len(path):
        return None
    start = path[idx]
    if not start.get("open") or not start.get("close") or not start.get("adj_close"):
        return None
    end, bench_end, stopped = (path[idx + h - 1] if idx + h - 1 < len(path) else None), None, False
    if (end is None or not end.get("adj_close")) and calendar:
        got = _stopped_exit(path, idx, h, calendar)
        if got:
            end, bench_end, stopped = got[0], got[1], True
    if end is None or not end.get("adj_close"):
        return None
    adj_open = start["open"] * start["adj_close"] / start["close"]
    gross = end["adj_close"] / adj_open - 1
    window = [b for b in path[idx:idx + h] if b["date"] <= end["date"]]
    low = min(b["adj_close"] for b in window if b.get("adj_close"))
    bmap = bench_by_date if bench_by_date is not None else {b["date"]: b for b in bench}
    bs, be = bmap.get(start["date"]), bmap.get(bench_end or end["date"])
    rel = None
    if bs and be and bs.get("open") and bs.get("adj_close") and be.get("adj_close"):
        rel = gross - (be["adj_close"] / (bs["open"] * bs["adj_close"] / bs["close"]) - 1)
    out = {"gross": gross, "net": gross - cost, "relative_net": rel - cost if rel is not None else None, "worst": low / adj_open - 1,
           "entry_date": start["date"], "exit_date": end["date"]}
    if stopped:
        out["stopped"] = True
    return out


def bucket_of(score: float) -> str:
    for lo, hi in config.BUCKETS:
        if lo <= score < hi:
            return f"{lo:g}-{min(hi, 100):.0f}"
    return "100"


def validate(snaps: List[Dict[str, Any]], market: str, strategy: str, loader: Callable[[str], List[Dict]], bench: List[Dict], cost: Optional[float] = None,
             benches: Optional[Dict[str, List[Dict]]] = None) -> Dict[str, Any]:
    """Bucket report for ONE cohort.  Below the independence minimum the verdict stays 'no verdict', whatever the numbers say.
    ``benches``: {a snapshot's recorded benchmark: its bars}; a stock is compared with the index it was recorded against."""
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
    versions: Dict[str, int] = {}
    for s in cohort:
        versions[str(s.get("model_version"))] = versions.get(str(s.get("model_version")), 0) + 1
    out["model_versions"] = dict(sorted(versions.items()))        # a cohort spanning several versions measures a mix, and says so
    cache: Dict[str, Tuple[List[Dict], Optional[List[str]]]] = {}
    bench_by_date = {b["date"]: b for b in bench}
    calendar = sorted(bench_by_date)          # the market's sessions: a recorded stock that stopped trading exits at its last trade
    own = {k: (v, {b["date"]: b for b in v}) for k, v in (benches or {}).items() if v}
    for h in horizons:
        buckets: Dict[str, List[Dict[str, float]]] = {}
        matured = set()
        for s in cohort:
            if s["ticker"] not in cache:
                bars = loader(s["ticker"]) or []
                days = [b.get("date") for b in bars]
                ok = all(isinstance(d, str) for d in days) and days == sorted(days)
                cache[s["ticker"]] = (bars, days if ok else None)      # bars out of order or without a date take the plain scan
            path, days = cache[s["ticker"]]
            its, its_by_date = own.get(s.get("benchmark")) or (bench, bench_by_date)
            o = outcome(path, its, s["data_date"], h, cost, s.get("entry_session"), days, its_by_date, calendar)
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
