"""Bounded, cached KR data acquisition shared by the scan, evaluation and research (memory-safe:
long frames of a few hundred thousand rows; downloads in chunks of 50 with pacing)."""
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Dict, Optional

import pandas as pd

from markets import session_data
from markets.kr import calendar as krcal
from markets.kr.market_data import YahooKRProvider, validate_rows

BENCHMARKS = {"KOSPI": "^KS11", "KOSDAQ": "^KQ11"}


def _cache_file(cache_dir: Path, tag: str, symbols, start: str, end: str) -> Path:
    h = hashlib.sha256((",".join(sorted(symbols)) + start + end).encode()).hexdigest()[:12]
    return cache_dir / f"{tag}_{start}_{end}_{h}.csv.gz"


def index_bars(provider: YahooKRProvider, start: str, end: str, now) -> Dict[str, pd.DataFrame]:
    out = {}
    for mkt, sym in BENCHMARKS.items():
        df = provider.fetch_index(sym, start, end)
        out[mkt] = krcal.drop_incomplete(df, now) if not df.empty else df
    return out


STALE_CACHE_SHARE = session_data.STORE_REUSE_SHARE      # the rule and its measurements live in markets/session_data.py
_reaches = session_data.store_reaches


def bars(provider: YahooKRProvider, securities: pd.DataFrame, start: str, end: str, now, cache_dir: Path,
         tag: str, fresh_at=None, whole: bool = False) -> Dict:
    """Validated canonical bars, incomplete (intraday) bars removed.  Cached per (symbols, window); the
    cache key includes ``end`` (the day after the latest complete session), so a new session refetches.

    ``fresh_at``: the session the caller is about to score.  A stored file that does not reach it for most symbols is not
    reused: it is downloaded again and replaced, so a run that came before the provider finished the day cannot pin the
    stale bars for every later run of the same day.

    ``whole``: the caller needs every symbol (the score scan's own universe).  A download in which a request failed outright
    is then returned but not stored, so the next run asks again instead of reusing a file with a part of the stocks."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = _cache_file(cache_dir, tag, securities["yahoo_symbol"].tolist(), start, end)
    stale = False
    if path.exists():
        try:
            df = pd.read_csv(path, dtype={"ticker": str, "quality_flags": str, "quality_status": str}, parse_dates=["date"])
        except (OSError, EOFError, ValueError):      # a file cut short by a killed run: fetched again, as if it were not there
            df = None
        if df is not None:
            df["quality_flags"] = df["quality_flags"].fillna("")
            if fresh_at is None or _reaches(df, fresh_at):
                return {"bars": df, "cache_hit": True, "file": str(path), "events": []}
        stale = True
    df = provider.fetch(securities, start, end)
    partial = whole and any(e.get("kind") == "chunk_failed" for e in provider.events)
    if not df.empty:
        df = krcal.drop_incomplete(df, now, date_col="date")
        if not partial:
            tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
            df.to_csv(tmp, index=False, compression="gzip")
            os.replace(tmp, path)
    return {"bars": df, "cache_hit": False, "stale_cache_found": stale, "file": str(path) if not df.empty and not partial else None,
            "events": list(provider.events)}


def window(now, calendar_days: int):
    n = krcal.to_kst(now)
    end = (n + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    start = (n - pd.Timedelta(days=calendar_days)).strftime("%Y-%m-%d")
    return start, end


def wide_adjusted(b: pd.DataFrame) -> pd.DataFrame:
    v = b[b["quality_status"] == "REAL"]
    return v.pivot_table(index="date", columns="ticker", values="adj_close", aggfunc="last").sort_index()
