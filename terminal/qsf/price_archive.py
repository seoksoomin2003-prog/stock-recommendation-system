"""Daily prices kept for every stock the forward record ever scored, so the record can still be scored after a stock leaves the scan.

The US price panel is rebuilt from today's S&P 500 list, and the Korean bar store from today's liquid universe.  A recorded stock that
leaves either one, or stops trading, would lose all its prices and drop out of the evaluation without a trace.  That drop is not
random: index removals and liquidity falls follow losses, takeovers follow gains.  This archive keeps those prices.

Rules:
- Only the prices are stored.  The ledger, the scores and the evaluation rules are not touched.
- A stock still in the scan takes its bars from there.  One that left is fetched from Yahoo by its own symbol.  One Yahoo no longer
  serves keeps the bars already stored, ending at its last trade.  Nothing is ever filled in.
- A newer series replaces an older one only when it reaches at least as far, so a shorter answer never erases stored days.
- One price basis per stock (review of 2026-11-17).  Each download is on that day's split and dividend basis.  Days older than
  the download's first day are kept from earlier downloads, so they are moved onto the new basis by the ratio of the two series
  on the days both have.  Without it a split or dividend after a day left the download window would sit between that day and
  the newer ones as a price jump.  No day had left a window before 2027-10-01, so nothing stored earlier needed repair.
- A file that exists but cannot be read is never taken for an empty archive: the update refuses, so it is not written over.
"""
from utils import fcntl_port as fcntl
import gzip
import json
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

from terminal.qsf.ledger import Ledger
from utils import durable

FOLDER = Path("data") / "qsf" / "price_archive"
START = "2026-10-01"            # a month before the first recorded session, 2026-11-04
FIELDS = ("date", "open", "close", "adj_close")
CHUNK = 50
REBASE_DAYS = 5         # the ratio of new to stored prices is the median over this many shared days: one bad bar cannot set it
REBASE_MIN = 1e-4       # a ratio this close to 1 is rounding, not a corporate action; the stored days are left as they are

Bars = List[Dict[str, Any]]


def path_of(base: Path, market: str) -> Path:
    return Path(base) / FOLDER / f"{market}.json.gz"


class Unreadable(RuntimeError):
    """The archive file is there and cannot be read (cut short or damaged).  It holds the only copy of the prices of stocks that
    stopped trading, so nothing may be written over it; a dated copy is in the backup folder (reports/RUNBOOK.md)."""


def read(base: Path, market: str, strict: bool = False) -> Dict[str, Dict[str, Any]]:
    """{} when there is no file yet.  An unreadable file is {} for a screen and ``Unreadable`` with ``strict`` (an update, or a
    reading that must not go ahead on fewer prices than were kept)."""
    p = path_of(base, market)
    if not p.exists():
        return {}
    try:
        with gzip.open(p, "rt", encoding="utf-8") as fh:
            return json.load(fh).get("tickers") or {}
    except (OSError, ValueError, EOFError) as exc:      # EOFError: a gzip file cut short
        if strict:
            raise Unreadable(f"PRICE_ARCHIVE_UNREADABLE: {p.name} ({type(exc).__name__})") from None
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


def basis_ratio(old: Bars, new: Bars) -> Dict[str, float]:
    """{"close": r, "adj_close": r}: new price over stored price on the first days both series have.  1.0 exactly when they agree
    to rounding or share no day (a gap between them: nothing to compare, the stored days stay as they are)."""
    stored = {b["date"]: b for b in old if b["date"] >= new[0]["date"]} if new else {}
    out = {}
    for k in ("close", "adj_close"):
        rs = [n[k] / stored[n["date"]][k] for n in new if n["date"] in stored and n.get(k) and stored[n["date"]].get(k)][:REBASE_DAYS]
        r = statistics.median(rs) if rs else 1.0
        out[k] = 1.0 if abs(r - 1.0) < REBASE_MIN else r
    return out


def merge(old: Bars, new: Bars) -> Bars:
    """The new series wins where it overlaps, but only when it reaches at least as far as what is stored.  The stored days before
    it are put on its price basis (``basis_ratio``): open and close by the close ratio, adj_close by its own."""
    new = _slim(new)
    if not new:
        return old
    if old and new[-1]["date"] < old[-1]["date"]:
        return old
    kept = [b for b in old if b["date"] < new[0]["date"]]
    r = basis_ratio(old, new) if kept else {"close": 1.0, "adj_close": 1.0}
    if r["close"] != 1.0 or r["adj_close"] != 1.0:
        by = {"open": r["close"], "close": r["close"], "adj_close": r["adj_close"]}
        kept = [{k: (v * by[k] if k in by and v is not None else v) for k, v in b.items()} for b in kept]
    return kept + new


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
        arch = read(base, market, strict=True)         # an unreadable file stops here: it is not written over
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
        durable.replace(tmp, target)
    left = sorted(t for t in tickers if (arch.get(t) or {}).get("via") != "SCAN")
    return {"status": "OK", "market": market, "recorded": len(tickers), **counts, "not_in_scan": left[:30]}


def loader(base: Path, market: str, source: Callable[[str], Bars], longest: bool = False) -> Callable[[str], Bars]:
    """The scan's bars when they reach at least as far as the archive's; otherwise the archive's.  Never a mix of the two.
    ``longest``: for a reading that looks back further than the scan keeps.  The Korean scan keeps about two years of bars and the
    long verdict reads over three; the archive holds every day since ``START``.  With it, the archive's bars are given when they
    are as fresh as the scan's and start earlier (found by the drill of 2026-11-16).  Such a reading refuses on an unreadable
    archive rather than go ahead on the scan's stocks alone."""
    arch = read(base, market, strict=longest)

    def load(t: str) -> Bars:
        own = source(t) or []
        kept = (arch.get(t) or {}).get("bars") or []
        if longest and own and kept and _last(kept) >= _last(own) and kept[0]["date"] < own[0]["date"]:
            return kept
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
