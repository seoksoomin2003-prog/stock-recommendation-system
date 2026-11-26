"""Korean daily bars rebuilt from the official KRX daily snapshots (QSF-1.1.8, the user's decision of 2026-11-09).

Yahoo's Korean history had whole days missing, days that repeat the previous close while the stock moved, single bad prints and,
for a stock that moved boards, trading from before its listing (``price_audit``).  The KRX snapshots the program already keeps
(``research_data/krx``, one file per board and day) carry each day's raw open, high, low, close, volume and the change rate
``FLUC_RT``.  The rate is measured from the exchange's base price, which allows for splits and bonus issues, so chaining it gives a
split-adjusted series without any other source:

    P(last) = raw close of the last day;  P(day - 1) = P(day) / (1 + rate(day))

and each day's raw open, high, low and close are scaled by P / raw close; volume by the inverse, as Yahoo does.

* Days after the newest KRX snapshot (the exchange publishes the next morning) are taken from Yahoo, chained by Yahoo's own
  daily change from the last KRX day, and the whole series is then scaled so its last close equals Yahoo's latest close.
* Dividends: Yahoo's ``adj_close / close`` ratio for each date is kept, so total-return figures stay as before.
* A stock KRX does not list in the window (or no snapshot at all) keeps its Yahoo bars; ``source`` says which was used.

The snapshot panel is cached in ``data/qsf/krx_panel.npz``.  A new snapshot day is added to it; days that have left the window
are cut off when it is read.  It is built from nothing only when it cannot be continued (no file, an old layout, a day missing).
"""
from utils import fcntl_port as fcntl
import gzip
import json
import os
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

KRX = Path("research_data") / "krx"
BOARDS = ("KOSPI", "KOSDAQ")
CACHE = Path("data") / "qsf" / "krx_panel.npz"
WINDOW_DAYS = 800                     # calendar days, the same window the scan asks Yahoo for
OPEN, HIGH, LOW, CLOSE, RATE, VOLUME = range(6)
COLS = {OPEN: 3, HIGH: 4, LOW: 5, CLOSE: 6, RATE: 7, VOLUME: 8}       # positions in a snapshot row (``krx_history.FIELDS``)
SAME = 0.001


def _days_on_file(root: Path, first: str) -> List[str]:
    """Days with both boards on file from ``first``; half a day is not a day."""
    have = [{p.name[:10] for p in (root / b).glob("*.json.gz") if p.name[:10] >= first} for b in BOARDS]
    return sorted(have[0] & have[1])


def _f(x: Any) -> float:
    try:
        v = float(str(x).replace(",", ""))
    except (TypeError, ValueError):
        return np.nan
    return v


def build_panel(root: Path, days: List[str]) -> Dict[str, np.ndarray]:
    """One day is read into a small array and the day's lists are dropped before the next.  Holding every day's rows as Python
    lists took about 500 MB for 570 days (1.7 million lists of six numbers), in whichever process met a new day first."""
    per_day: List[Tuple[List[str], np.ndarray]] = []
    for day in days:
        rows: Dict[str, List[float]] = {}
        for b in BOARDS:
            with gzip.open(root / b / f"{day}.json.gz", "rt", encoding="utf-8") as fh:
                for r in json.load(fh):
                    rows[str(r[0])] = [_f(r[COLS[k]]) for k in range(6)]
        per_day.append((list(rows), np.array(list(rows.values()), dtype=np.float64).reshape(len(rows), 6)))
    codes = sorted({c for cs, _ in per_day for c in cs})
    col = {c: j for j, c in enumerate(codes)}
    data = np.full((6, len(days), len(codes)), np.nan, dtype=np.float64)
    seen = np.zeros((len(days), len(codes)), dtype=bool)        # the stock is in that day's file, whatever its values
    for n, (cs, vals) in enumerate(per_day):
        if cs:
            at = [col[c] for c in cs]
            data[:, n, at] = vals.T
            seen[n, at] = True
    return {"dates": np.array(days), "codes": np.array(codes), "data": data, "seen": seen}


def _stored(path: Path) -> Optional[Dict[str, Any]]:
    """The panel on file with its day-by-stock presence table; None for no file, a damaged one or the layout without that table."""
    try:
        with np.load(path, allow_pickle=False) as z:
            if "seen" not in z.files:
                return None
            got = {"dates": [str(x) for x in z["dates"]], "codes": [str(c) for c in z["codes"]], "data": z["data"], "seen": z["seen"]}
    except (OSError, ValueError, KeyError, EOFError):
        return None
    ok = got["data"].ndim == 3 and got["data"].shape == (6, len(got["dates"]), len(got["codes"])) and got["seen"].shape == got["data"].shape[1:]
    return got if ok else None


def _tail(st: Dict[str, Any], days: List[str]) -> Optional[Dict[str, np.ndarray]]:
    """The stored panel cut to ``days`` when they are its last days exactly: the same arrays a fresh build of ``days`` gives.
    The window's first day moves forward with the calendar, so on most days the stored panel has a few days too many at its
    start and nothing else differs.  A stock that was only in the days cut off is dropped, as a fresh build would not know it."""
    dates = st["dates"]
    if not days or len(days) > len(dates) or dates[len(dates) - len(days):] != days:
        return None
    k = len(dates) - len(days)
    if k == 0:
        return {"dates": np.array(dates), "codes": np.array(st["codes"]), "data": st["data"], "seen": st["seen"]}
    keep = st["seen"][k:].any(axis=0)
    if keep.all():                                          # the usual case: no stock dropped, so no copy of the arrays
        return {"dates": np.array(days), "codes": np.array(st["codes"]), "data": st["data"][:, k:, :], "seen": st["seen"][k:]}
    return {"dates": np.array(days), "codes": np.array(st["codes"])[keep], "data": st["data"][:, k:, :][:, :, keep], "seen": st["seen"][k:][:, keep]}


def _extended(root: Path, st: Dict[str, Any], days: List[str]) -> Optional[Dict[str, np.ndarray]]:
    """The stored panel continued to ``days`` by reading only the days it lacks, when those all come after its last day."""
    have = set(st["dates"])
    old = [d for d in days if d in have]
    new = [d for d in days if d not in have]
    if not old or not new or days != old + new or new[0] <= st["dates"][-1]:
        return None
    a = _tail(st, old)
    if a is None:
        return None
    b = build_panel(root, new)
    codes = sorted(set(map(str, a["codes"])) | set(map(str, b["codes"])))
    col = {c: j for j, c in enumerate(codes)}
    data = np.full((6, len(days), len(codes)), np.nan, dtype=np.float64)
    seen = np.zeros((len(days), len(codes)), dtype=bool)
    for part, start in ((a, 0), (b, len(old))):
        at = [col[str(c)] for c in part["codes"]]
        stop = start + len(part["dates"])
        data[:, start:stop, at] = part["data"]
        seen[start:stop, at] = part["seen"]
    return {"dates": np.array(days), "codes": np.array(codes), "data": data, "seen": seen}


def _view(p: Dict[str, np.ndarray]) -> Dict[str, Any]:
    return {"dates": [str(x) for x in p["dates"]], "codes": {str(c): j for j, c in enumerate(p["codes"])}, "data": p["data"]}


def _kept(path: Path, days: List[str]) -> Optional[Dict[str, Any]]:
    """The stored panel when ``days`` are its last days (all of it, or all but days that left the window)."""
    st = _stored(path)
    cut = _tail(st, days) if st else None
    return _view(cut) if cut else None


def panel(base: Path, today: Optional[date] = None) -> Optional[Dict[str, Any]]:
    """The cached snapshot panel, rebuilt when the days on file changed.  None without any snapshot."""
    root = Path(base) / KRX
    first = ((today or date.today()) - timedelta(days=WINDOW_DAYS)).isoformat()
    days = _days_on_file(root, first)
    if not days:
        return None
    path = Path(base) / CACHE
    kept = _kept(path, days)
    if kept:
        return kept
    path.parent.mkdir(parents=True, exist_ok=True)
    # The server and the daily job can both find the panel out of date.  They once shared one temp file: the slower one lost it,
    # failed, and its caller fell back to Yahoo bars without a word.  Now one builds while the other waits and then reads the result.
    with open(path.with_name(path.name + ".lock"), "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        st = _stored(path)
        cut = _tail(st, days) if st else None
        if cut:
            return _view(cut)
        built = (_extended(root, st, days) if st else None) or build_panel(root, days)      # new days only, when it can be continued
        tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp.npz")
        np.savez_compressed(tmp, **built)
        tmp.replace(path)
    return _view(built)


def rebuild(code: str, yahoo: List[Dict[str, Any]], pan: Optional[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """The stock's bars from KRX (plus Yahoo for days KRX has not published yet).  Returns (bars, info)."""
    j = pan["codes"].get(code) if pan else None
    if j is None:
        return yahoo, {"source": "YAHOO", "reason": "KRX 일별 자료에 없는 종목"}
    d = pan["data"][:, :, j]
    dates = pan["dates"]
    keep = [n for n in range(len(dates)) if np.isfinite(d[CLOSE, n]) and d[CLOSE, n] > 0]
    if not keep:
        return yahoo, {"source": "YAHOO", "reason": "KRX 일별 자료에 종가가 없음"}
    raw = d[CLOSE, keep]
    rate = d[RATE, keep] / 100
    p = np.empty(len(keep))
    p[-1] = raw[-1]
    for i in range(len(keep) - 1, 0, -1):
        step = 1 + rate[i] if np.isfinite(rate[i]) and rate[i] > -1 else raw[i] / raw[i - 1]
        p[i - 1] = p[i] / step
    k = p / raw
    by = {b["date"]: b for b in yahoo if b.get("close")}
    ratio, out = None, []
    first_ratio = next((b["adj_close"] / b["close"] for b in yahoo if b.get("close") and b.get("adj_close")), 1.0)
    for i, n in enumerate(keep):
        day = dates[n]
        y = by.get(day)
        if y and y.get("adj_close") and y.get("close"):
            ratio = y["adj_close"] / y["close"]
        c = raw[i] * k[i]
        o, h, lo, v = (d[x, n] for x in (OPEN, HIGH, LOW, VOLUME))
        o = o * k[i] if np.isfinite(o) and o > 0 else c                     # a halted day lists no trade: a flat bar
        h = max(h * k[i] if np.isfinite(h) and h > 0 else c, o, c)
        lo = min(lo * k[i] if np.isfinite(lo) and lo > 0 else c, o, c)
        out.append({"date": day, "open": float(o), "high": float(h), "low": float(lo), "close": float(c),
                    "adj_close": float(c * (ratio if ratio is not None else first_ratio)), "volume": float(v / k[i]) if np.isfinite(v) else None})
    last_krx = dates[keep[-1]]
    tail = [b for b in yahoo if b.get("close") and b["date"] > dates[-1]]          # only days KRX has not published yet
    anchor = by.get(last_krx)
    info = {"source": "KRX", "krx_last": last_krx, "tail_days": 0, "dropped_yahoo_days": sum(1 for b in yahoo if b.get("close") and b["date"] < out[0]["date"])}
    if tail and anchor and last_krx == dates[-1]:
        prev_y, prev = anchor, out[-1]
        for b in tail:
            g = b["close"] / prev_y["close"]
            c = prev["close"] * g
            s = c / b["close"]
            if b.get("adj_close"):
                ratio = b["adj_close"] / b["close"]
            out.append({"date": b["date"], "open": b["open"] * s if b.get("open") else c, "high": b["high"] * s if b.get("high") else c,
                        "low": b["low"] * s if b.get("low") else c, "close": c, "adj_close": c * (ratio if ratio is not None else first_ratio),
                        "volume": b["volume"] / s if b.get("volume") is not None else None})
            prev_y, prev = b, out[-1]
        scale = tail[-1]["close"] / out[-1]["close"]
        if abs(scale - 1) > 1e-9:                     # a corporate action inside the tail: put the series on today's basis
            for b in out:
                for key in ("open", "high", "low", "close", "adj_close"):
                    b[key] *= scale
                if b["volume"] is not None:
                    b["volume"] /= scale
        info.update(source="KRX+YAHOO", tail_days=len(tail))
    elif tail:
        info["tail_skipped"] = len(tail)               # Yahoo has no bar on the last KRX day to chain from
    return out, info


def summary(infos: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    kinds: Dict[str, int] = {}
    for i in infos.values():
        kinds[i["source"]] = kinds.get(i["source"], 0) + 1
    return {"stocks": len(infos), "by_source": kinds, "krx_last": max((i.get("krx_last") or "" for i in infos.values()), default=None) or None,
            "dropped_yahoo_days": sum(i.get("dropped_yahoo_days", 0) for i in infos.values())}
