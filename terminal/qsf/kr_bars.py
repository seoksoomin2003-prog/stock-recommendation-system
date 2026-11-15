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

The snapshot panel is cached in ``data/qsf/krx_panel.npz`` and rebuilt when a new snapshot day appears.
"""
import fcntl
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
    for n, (cs, vals) in enumerate(per_day):
        if cs:
            data[:, n, [col[c] for c in cs]] = vals.T
    return {"dates": np.array(days), "codes": np.array(codes), "data": data}


def _kept(path: Path, days: List[str]) -> Optional[Dict[str, Any]]:
    """The stored panel when it covers exactly ``days``."""
    try:
        with np.load(path, allow_pickle=False) as z:
            if list(z["dates"]) == days:
                return {"dates": [str(x) for x in z["dates"]], "codes": {str(c): j for j, c in enumerate(z["codes"])}, "data": z["data"]}
    except (OSError, ValueError, KeyError, EOFError):
        pass
    return None


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
        kept = _kept(path, days)
        if kept:
            return kept
        built = build_panel(root, days)
        tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp.npz")
        np.savez_compressed(tmp, **built)
        tmp.replace(path)
    return {"dates": list(days), "codes": {str(c): j for j, c in enumerate(built["codes"])}, "data": built["data"]}


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
