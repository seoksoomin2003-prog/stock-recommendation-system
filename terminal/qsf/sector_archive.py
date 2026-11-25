"""Each scanned stock's sector, kept once a month with its date (user decision 2026-11-25, score audit roadmap P3-4).

The ledger keeps no sector.  The long-term verdict's reference line ("the score less its sector's mean", reports/
QSF_AFTER_VERDICT_RULES_2026_11_25.md section 4) is read in about 2030; without a dated copy it would use the sectors of that
day, and a company that changed its business in between would be read under the wrong one.

This is an input kept as it was, not a record of a score: nothing is scored, no return is read, no verdict depends on a file
here (a missing month falls back to the classification of the day of the reading, and the report says which it used).  It asks
no network: the sectors are the ones the day's scan already shows (``views.screen_rows``).  One small file a market a month.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

FOLDER = Path("data") / "qsf" / "sector_archive"
MARKETS = ("US", "KR")
MIN_STOCKS = 50                 # fewer classified stocks than this is not a scan's worth: nothing is written and the next run tries again


def path(base: Path, market: str, month: str) -> Path:
    return Path(base) / FOLDER / f"{market}_{month}.json"


def _scan_rows(base: Path, market: str) -> Dict[str, Any]:
    from terminal.qsf.service import QSF
    return QSF(Path(base)).screen_rows(market)


def save_when_due(base: Path, now: datetime, rows_of: Optional[Callable[[str], Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Write this month's file of each market when it is not there yet.  {market: "KEPT" | "WRITTEN" | "TOO_FEW" | error type}."""
    from utils import durable
    month, out = now.astimezone(timezone.utc).strftime("%Y-%m"), {}
    for market in MARKETS:
        target = path(base, market, month)
        if target.exists():
            out[market] = "KEPT"
            continue
        try:
            scan = (rows_of or (lambda m: _scan_rows(base, m)))(market) or {}
            got = {str(r["ticker"]): {"sector": r.get("sector"), "industry": r.get("industry")} for r in scan.get("rows") or [] if r.get("ticker") and r.get("sector")}
            if len(got) < MIN_STOCKS:
                out[market] = "TOO_FEW"
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            durable.write_text(target, json.dumps({"market": market, "month": month, "saved_at": now.astimezone(timezone.utc).isoformat(), "session": scan.get("session"),
                                                   "stocks": len(got), "sectors": dict(sorted(got.items()))}, ensure_ascii=False, indent=1))
            out[market] = "WRITTEN"
        except Exception as exc:                     # never stops the caller; the type is the whole message
            out[market] = type(exc).__name__
    return out


def months(base: Path, market: str) -> List[str]:
    return sorted(p.stem.split("_", 1)[1] for p in (Path(base) / FOLDER).glob(f"{market}_*.json"))


def lookup(base: Path, market: str) -> Callable[[str, Optional[str]], Optional[str]]:
    """``sector(ticker, day)``: the sector on the newest kept file of a month at or before ``day``'s month.  None when no file is
    that old, the file cannot be read, or the stock is not in it: the caller then uses what it has, and says so."""
    have, books = months(base, market), {}

    def book(month: str) -> Dict[str, Any]:
        if month not in books:
            try:
                books[month] = json.loads(path(base, market, month).read_text(encoding="utf-8")).get("sectors") or {}
            except (OSError, ValueError, AttributeError):
                books[month] = {}
        return books[month]

    def sector(ticker: str, day: Optional[str] = None) -> Optional[str]:
        at = [m for m in have if not day or m <= str(day)[:7]]
        return ((book(at[-1]).get(ticker) or {}).get("sector") if at else None)
    return sector
