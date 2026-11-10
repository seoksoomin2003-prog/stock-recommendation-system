"""Bounded, cached KR data acquisition shared by the scan, evaluation and research (memory-safe:
long frames of a few hundred thousand rows; downloads in chunks of 50 with pacing)."""
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Dict, Optional

import pandas as pd

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


STALE_CACHE_SHARE = 0.8      # a stored download where fewer symbols than this reach the session asked for was taken too early


def _reaches(df: pd.DataFrame, session) -> bool:
    """True when most symbols in a stored download have a bar on ``session`` or later.  A complete download has it for every symbol
    (measured on six stored files: 100%); one taken while the provider was still publishing the day has it for a part (28% on
    2026-11-11 02:27 KST), and reusing that file for the rest of the day left the scan with two stocks."""
    if df.empty:
        return False
    last = df.groupby("ticker")["date"].max()
    return float((last >= pd.Timestamp(session)).mean()) >= STALE_CACHE_SHARE


def bars(provider: YahooKRProvider, securities: pd.DataFrame, start: str, end: str, now, cache_dir: Path,
         tag: str, fresh_at=None) -> Dict:
    """Validated canonical bars, incomplete (intraday) bars removed.  Cached per (symbols, window); the
    cache key includes ``end`` (the day after the latest complete session), so a new session refetches.

    ``fresh_at``: the session the caller is about to score.  A stored file that does not reach it for most symbols is not
    reused: it is downloaded again and replaced, so a run that came before the provider finished the day cannot pin the
    stale bars for every later run of the same day."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = _cache_file(cache_dir, tag, securities["yahoo_symbol"].tolist(), start, end)
    stale = False
    if path.exists():
        df = pd.read_csv(path, dtype={"ticker": str, "quality_flags": str, "quality_status": str}, parse_dates=["date"])
        df["quality_flags"] = df["quality_flags"].fillna("")
        if fresh_at is None or _reaches(df, fresh_at):
            return {"bars": df, "cache_hit": True, "file": str(path), "events": []}
        stale = True
    df = provider.fetch(securities, start, end)
    if not df.empty:
        df = krcal.drop_incomplete(df, now, date_col="date")
        df.to_csv(path, index=False, compression="gzip")
    return {"bars": df, "cache_hit": False, "stale_cache_found": stale, "file": str(path) if not df.empty else None,
            "events": list(provider.events)}


def window(now, calendar_days: int):
    n = krcal.to_kst(now)
    end = (n + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    start = (n - pd.Timedelta(days=calendar_days)).strftime("%Y-%m-%d")
    return start, end


def wide_adjusted(b: pd.DataFrame) -> pd.DataFrame:
    v = b[b["quality_status"] == "REAL"]
    return v.pivot_table(index="date", columns="ticker", values="adj_close", aggfunc="last").sort_index()
