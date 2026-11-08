"""Rebuilds daily series from the pystock-data archive (CC BY-SA 4.0, (c) Chang-Hung Liang), which ends on 2017-03-31.

The archive holds Yahoo's old format: raw close, a dividend-and-split adjusted close, and files collected on different days, each
adjusted only up to its own day.  So returns are taken inside one file, and the series is rebuilt on today's basis: split-adjusted
OHLC, a total-return close, and a split list.  Archives are read from the tarball in memory and never unpacked to disk.
"""
import csv
import io
import tarfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

SOURCE_END = "2017-03-31"
MAX_GAP_MOVE = 0.5      # across a missing file the raw close is used only if it moved less than this; otherwise the series stops


def _num(x: Any) -> Optional[float]:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if v == v and v > 0 else None


def read_archives(tar_path: Path, wanted: Iterable[str]) -> List[Dict[str, Dict[str, Dict[str, float]]]]:
    """One {symbol: {date: row}} per inner archive, ordered by archive name (initial files first, then by day)."""
    want = set(wanted)
    out = []
    with tarfile.open(tar_path, "r:gz") as tf:
        members = sorted((m for m in tf.getmembers() if m.isfile() and m.name.endswith(".tar.gz")), key=lambda m: m.name.rsplit("/", 1)[-1])
        for m in members:
            batch: Dict[str, Dict[str, Dict[str, float]]] = {}
            with tarfile.open(fileobj=io.BytesIO(tf.extractfile(m).read()), mode="r:gz") as inner:
                for im in inner:
                    if not im.name.endswith("prices.csv"):
                        continue
                    for r in csv.DictReader(io.TextIOWrapper(inner.extractfile(im), encoding="utf-8")):
                        if r["symbol"] in want:
                            batch.setdefault(r["symbol"], {})[r["date"]] = r
            out.append(batch)
    return out


def split_ratio(close0: float, close1: float, adj0: float, adj1: float) -> float:
    """Shares after per share before, from the gap between the raw and adjusted moves.  Dividends never get this far from 1."""
    x = (close0 / close1) / (adj0 / adj1)
    return round(x, 3) if x >= 1.2 or x <= 0.8 else 1.0


def build_series(files: List[Dict[str, Dict[str, Any]]]) -> Dict[str, Any]:
    """``files``: one symbol's rows per archive, in archive order.  Returns the rebuilt series, oldest first, and any repairs."""
    last: Dict[str, Dict[str, Any]] = {}       # the row of a date from the newest file that has it as its own latest day, else the first seen
    ratio: Dict[str, float] = {}               # adj(t) / adj(t-1) taken inside one file
    split: Dict[str, float] = {}
    prev_of: Dict[str, str] = {}
    for rows in files:
        ds = sorted(d for d, r in rows.items() if _num(r.get("close")) and _num(r.get("adj_close")))
        for k, d in enumerate(ds):
            if d not in last or k == len(ds) - 1:
                last[d] = rows[d]
            if k:
                p, a, b = ds[k - 1], rows[ds[k - 1]], rows[d]
                ratio[d], prev_of[d] = _num(b["adj_close"]) / _num(a["adj_close"]), p
                s = split_ratio(_num(a["close"]), _num(b["close"]), _num(a["adj_close"]), _num(b["adj_close"]))
                if s != 1.0:
                    split[d] = s
    dates = sorted(last)
    keep, gaps, stopped = [], 0, None
    for k, d in enumerate(dates):
        if k and prev_of.get(d) != dates[k - 1]:
            move = _num(last[d]["close"]) / _num(last[dates[k - 1]]["close"]) - 1
            if abs(move) > MAX_GAP_MOVE:
                stopped = d
                break
            ratio[d], gaps = 1 + move, gaps + 1
            split.pop(d, None)
        keep.append(d)
    if not keep:
        return {"rows": [], "splits": [], "gaps": gaps, "stopped": stopped}
    rows_out: List[Dict[str, Any]] = []
    factor, total = 1.0, None
    for d in reversed(keep):
        r = last[d]
        c = _num(r["close"]) / factor
        total = c if total is None else total
        conv = lambda name: (_num(r.get(name)) / factor) if _num(r.get(name)) else None      # noqa: E731
        vol = _num(r.get("volume"))
        rows_out.append({"date": d, "open": conv("open"), "high": conv("high"), "low": conv("low"), "close": c, "adj_close": total, "volume": vol})
        if d in ratio and d != keep[0]:
            total = total / ratio[d]
        factor *= split.get(d, 1.0)
    rows_out.reverse()
    return {"rows": rows_out, "splits": [(d, split[d]) for d in keep if d in split and d != keep[0]], "gaps": gaps, "stopped": stopped}
