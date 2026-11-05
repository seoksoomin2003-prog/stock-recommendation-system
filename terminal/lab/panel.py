"""Daily price panel for the lab: open, close, adj_close, volume per ticker on a common date index.

Stored as gzip JSON at data/lab/panel.json.gz (git-ignored).  Missing values are NaN in memory and
null on disk, never 0.  Prices come from Yahoo (free, delayed); the panel is fully re-downloaded at most
once per completed session so dividend/split adjustments stay consistent across history.
"""
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Callable, Dict, List, Optional

import numpy as np
import pandas as pd

FIELDS = ("open", "close", "adj_close", "volume")
CHUNK = 50
BENCH = "SPY"


MIN_ROW_COVERAGE = 0.90


def row_complete(p: "Panel", i: int) -> bool:
    """A session row is usable only when the benchmark and at least 90% of symbols have a close."""
    c = p.f("close")[i]
    return BENCH in p.col and bool(np.isfinite(c[p.col[BENCH]])) and float(np.isfinite(c).mean()) >= MIN_ROW_COVERAGE


class Panel:
    def __init__(self, dates: List[str], tickers: List[str], data: Dict[str, np.ndarray], meta: Dict):
        self.dates = list(dates)
        self.tickers = list(tickers)
        self.col = {t: j for j, t in enumerate(self.tickers)}
        self.idx = {d: i for i, d in enumerate(self.dates)}
        self.data = data            # field -> float array [len(dates), len(tickers)] with NaN for missing
        self.meta = meta

    # ------------------------------------------------------------------ access
    def f(self, field: str) -> np.ndarray:
        return self.data[field]

    def series(self, field: str, ticker: str) -> np.ndarray:
        return self.data[field][:, self.col[ticker]]

    @property
    def last(self) -> Optional[str]:
        return self.dates[-1] if self.dates else None

    def fingerprint(self) -> str:
        h = hashlib.sha256()
        h.update(json.dumps([self.dates[0] if self.dates else None, self.last, self.tickers]).encode())
        for k in FIELDS:
            h.update(np.round(np.nan_to_num(self.data[k], nan=-1.0), 6).astype("float64").tobytes())   # = stored precision
        return h.hexdigest()[:16]

    # ------------------------------------------------------------------ io
    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        enc = {k: [[None if not math.isfinite(v) else round(float(v), 6) for v in self.data[k][:, j]]
                   for j in range(len(self.tickers))] for k in FIELDS}
        body = json.dumps({"dates": self.dates, "tickers": self.tickers, "fields": enc, "meta": self.meta},
                          separators=(",", ":")).encode()
        tmp = path.with_name(path.name + ".tmp")
        with gzip.open(tmp, "wb", compresslevel=6) as fh:
            fh.write(body)
        os.replace(tmp, path)

    @classmethod
    def load(cls, path: Path) -> Optional["Panel"]:
        if not path.exists():
            return None
        try:
            with gzip.open(path, "rb") as fh:
                raw = json.loads(fh.read())
        except (OSError, ValueError):
            return None
        n = len(raw["dates"])
        data = {}
        for k in FIELDS:
            cols = raw["fields"][k]
            arr = np.full((n, len(raw["tickers"])), np.nan)
            for j, c in enumerate(cols):
                arr[:, j] = np.array(c, dtype=float)          # None -> NaN
            data[k] = arr
        return cls(raw["dates"], raw["tickers"], data, raw.get("meta") or {})

    @classmethod
    def from_frames(cls, frames: Dict[str, pd.DataFrame], meta: Dict) -> "Panel":
        """frames: ticker -> DataFrame indexed by date with columns open/close/adj_close/volume."""
        frames = {t: f for t, f in frames.items() if f is not None and not f.empty}
        idx = sorted(set().union(*[set(f.index) for f in frames.values()])) if frames else []
        dates = [pd.Timestamp(d).strftime("%Y-%m-%d") for d in idx]
        tickers = sorted(frames)
        data = {}
        for k in FIELDS:
            arr = np.full((len(idx), len(tickers)), np.nan)
            for j, t in enumerate(tickers):
                s = frames[t][k].reindex(idx).astype(float)
                arr[:, j] = s.values
            arr[~np.isfinite(arr)] = np.nan
            if k != "volume":
                arr[arr <= 0] = np.nan
            data[k] = arr
        return cls(dates, tickers, data, meta)


# ------------------------------------------------------------------ download
def _yf(chunk: List[str], period: str):
    import yfinance as yf
    return yf.download(chunk, period=period, interval="1d", auto_adjust=False, actions=False, progress=False,
                       group_by="column", threads=False)


def download(tickers: List[str], period: str = "6y", fetch: Callable = _yf,
             progress: Optional[Callable[[int, int], None]] = None) -> Dict[str, pd.DataFrame]:
    out: Dict[str, pd.DataFrame] = {}
    for i in range(0, len(tickers), CHUNK):
        chunk = tickers[i:i + CHUNK]
        df = None
        for _ in range(2):
            try:
                df = fetch(chunk, period)
                break
            except Exception:
                df = None
        if progress:
            progress(min(i + CHUNK, len(tickers)), len(tickers))
        if df is None or df.empty:
            continue
        if not isinstance(df.columns, pd.MultiIndex):
            df.columns = pd.MultiIndex.from_product([df.columns, chunk[:1]])
        for t in chunk:
            if ("Close", t) not in df.columns:
                continue
            sub = df.xs(t, axis=1, level=1)
            f = pd.DataFrame({"open": sub.get("Open"), "close": sub.get("Close"),
                              "adj_close": sub.get("Adj Close"), "volume": sub.get("Volume")})
            f = f[f["close"].notna()]
            if not f.empty:
                f.index = pd.to_datetime(f.index).tz_localize(None).normalize()
                out[t] = f
    return out
