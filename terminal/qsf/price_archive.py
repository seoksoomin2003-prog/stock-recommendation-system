"""Daily prices kept for every stock the forward record ever scored, so the record can still be scored after a stock leaves the scan.

The US price panel is rebuilt from today's S&P 500 list, and the Korean bar store from today's liquid universe.  A recorded stock that
leaves either one, or stops trading, would lose all its prices and drop out of the evaluation without a trace.  That drop is not
random: index removals and liquidity falls follow losses, takeovers follow gains.  This archive keeps those prices.

Rules:
- Only the prices are stored.  The ledger, the scores and the evaluation rules are not touched.
- A stock still in the scan takes its bars from there.  One that left is fetched from Yahoo by its own symbol.  One Yahoo no longer
  serves keeps the bars already stored, ending at its last trade.  Nothing is ever filled in.
- A newer series replaces an older one only when it reaches at least as far, so a shorter answer never erases stored days.
"""
import fcntl
import gzip
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

from terminal.qsf.ledger import Ledger

FOLDER = Path("data") / "qsf" / "price_archive"
START = "2026-10-01"            # a month before the first recorded session, 2026-11-04
FIELDS = ("date", "open", "close", "adj_close")
CHUNK = 50

Bars = List[Dict[str, Any]]


def path_of(base: Path, market: str) -> Path:
    return Path(base) / FOLDER / f"{market}.json.gz"


def read(base: Path, market: str) -> Dict[str, Dict[str, Any]]:
    try:
        with gzip.open(path_of(base, market), "rt", encoding="utf-8") as fh:
            return json.load(fh).get("tickers") or {}
    except (OSError, ValueError):
        return {}


def recorded(base: Path, market: str) -> List[str]:
    """Every ticker the ledger holds for the market, from all live shards."""
    return sorted(set(Ledger(base).snapshots(market, keep=lambda s: s.get("ticker") or None)))


def _slim(bars: Optional[Bars]) -> Bars:
    out = []
    for b in bars or []:
        if b.get("date") and b["date"] >= START and b.get("close"):
            out.append({k: b.get(k) for k in FIELDS})
    return out


def merge(old: Bars, new: Bars) -> Bars:
    """The new series wins where it overlaps, but only when it reaches at least as far as what is stored."""
    new = _slim(new)
    if not new:
        return old
    if old and new[-1]["date"] < old[-1]["date"]:
        return old
    return [b for b in old if b["date"] < new[0]["date"]] + new


def _last(bars: Optional[Bars]) -> str:
    return bars[-1]["date"] if bars else ""


def update(base: Path, market: str, source: Callable[[str], Bars], fetch: Callable[[List[str]], Dict[str, Bars]],
           symbol_of: Callable[[str], Iterable[str]], now: Callable[[], datetime] = lambda: datetime.now(timezone.utc)) -> Dict[str, Any]:
    """Refresh the archive for every recorded ticker.  ``source`` is the scan's own price store; ``fetch`` asks Yahoo for symbols
    the scan no longer carries; ``symbol_of`` gives the Yahoo symbols to try for a ticker, best first."""
    tickers = recorded(base, market)
    target = path_of(base, market)
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target.with_suffix(".lock"), "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        arch = read(base, market)
        counts = {"source": 0, "fetched": 0, "kept": 0, "none": 0}
        missing: List[str] = []
        for t in tickers:
            bars = _slim(source(t))
            entry = arch.get(t) or {}
            if bars and _last(bars) >= _last(entry.get("bars")):
                arch[t] = {**entry, "bars": merge(entry.get("bars") or [], bars), "via": "SCAN"}
                counts["source"] += 1
            else:
                missing.append(t)
        wanted: Dict[str, str] = {}
        for t in missing:
            for sym in [arch.get(t, {}).get("symbol")] + list(symbol_of(t)):
                if sym and sym not in wanted:
                    wanted[sym] = t
        got: Dict[str, Bars] = {}
        syms = list(wanted)
        for i in range(0, len(syms), CHUNK):
            try:
                got.update(fetch(syms[i:i + CHUNK]) or {})
            except Exception:           # the network failing leaves the stored bars as they are
                pass
        for t in missing:
            entry = arch.get(t) or {}
            best_sym, best = None, []
            for sym in [s for s, owner in wanted.items() if owner == t]:
                bars = _slim(got.get(sym))
                if _last(bars) > _last(best):
                    best_sym, best = sym, bars
            if best and _last(best) >= _last(entry.get("bars")):
                arch[t] = {**entry, "bars": merge(entry.get("bars") or [], best), "symbol": best_sym, "via": "YAHOO"}
                counts["fetched"] += 1
            elif entry.get("bars"):
                counts["kept"] += 1
            else:
                counts["none"] += 1
        doc = {"market": market, "updated_at": now().isoformat(), "start": START, "tickers": arch}
        tmp = target.with_suffix(".tmp")
        with gzip.open(tmp, "wt", encoding="utf-8") as fh:
            json.dump(doc, fh)
        os.replace(tmp, target)
    left = sorted(t for t in tickers if (arch.get(t) or {}).get("via") != "SCAN")
    return {"status": "OK", "market": market, "recorded": len(tickers), **counts, "not_in_scan": left[:30]}


def loader(base: Path, market: str, source: Callable[[str], Bars]) -> Callable[[str], Bars]:
    """The scan's bars when they reach at least as far as the archive's; otherwise the archive's.  Never a mix of the two."""
    arch = read(base, market)

    def load(t: str) -> Bars:
        own = source(t) or []
        kept = (arch.get(t) or {}).get("bars") or []
        return own if _last(own) >= _last(kept) else kept
    return load


def status(base: Path, market: str) -> Dict[str, Any]:
    """How many recorded stocks have prices, and from where.  Read only."""
    arch = read(base, market)
    tickers = recorded(base, market)
    via: Dict[str, int] = {}
    for t in tickers:
        v = (arch.get(t) or {}).get("via") or "NONE"
        via[v] = via.get(v, 0) + 1
    last = sorted({_last((arch.get(t) or {}).get("bars")) for t in tickers} - {""})
    return {"market": market, "recorded": len(tickers), "via": via, "newest": last[-1] if last else None,
            "stopped": sorted(t for t in tickers if arch.get(t) and last and _last(arch[t]["bars"]) < last[-1])[:30]}
