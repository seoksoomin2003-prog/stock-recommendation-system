"""Finding a stock among the scanned ones without asking the network: exact ticker, prefix, company name, and near misses.

The scanned universe (S&P 500 and the Korean top 300) is on the device with its names, so a mistyped ticker can be answered
with "did you mean" at once.  Before this the stock screen asked every provider about a ticker that does not exist, waited
two or three seconds a panel, and showed "unavailable".
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

LIMIT = 8
ORDER = {"EXACT": 0, "PREFIX": 1, "NAME_START": 2, "NAME": 3, "NEAR": 4}


_KEPT: Dict[int, tuple] = {}


def universe_of(terminal: Any, rows_of: Any) -> List[Dict[str, str]]:
    """The universe of both markets, built again only when a scan file changed (it was rebuilt, with two full readings of the
    scans, on every letter typed into the search box)."""
    def m(market):
        try:
            return (terminal.qsf.dir / f"latest_{market}.json").stat().st_mtime_ns
        except (OSError, AttributeError):
            return None
    key = (m("US"), m("KR"))
    hit = _KEPT.get(id(terminal))
    if hit is not None and hit[0] == key and None not in key:
        return hit[1]
    built = universe({mk: rows_of(terminal, mk) for mk in ("US", "KR")})
    _KEPT[id(terminal)] = (key, built)
    return built


def universe(rows_by_market: Dict[str, Iterable[Dict[str, Any]]]) -> List[Dict[str, str]]:
    """One entry per scanned stock (the rows carry each stock once per strategy)."""
    seen, out = set(), []
    for market, rows in rows_by_market.items():
        for r in rows or []:
            key = (market, r.get("ticker"))
            if r.get("ticker") and key not in seen:
                seen.add(key)
                out.append({"ticker": str(r["ticker"]), "name": str(r.get("name") or r["ticker"]), "market": market})
    return out


def distance(a: str, b: str, cap: int = 3) -> int:
    """Edit distance where swapping two neighbouring letters counts once (APPL -> AAPL is 1, AALP -> AAPL is 1)."""
    if abs(len(a) - len(b)) >= cap:
        return cap
    prev2: Optional[List[int]] = None
    prev = list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        cur = [i] + [0] * len(b)
        for j in range(1, len(b) + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
            if prev2 is not None and i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                cur[j] = min(cur[j], prev2[j - 2] + 1)
        prev2, prev = prev, cur
    return min(prev[-1], cap)


def suggest(stocks: List[Dict[str, str]], query: str, market: str = "US", limit: int = LIMIT) -> Dict[str, Any]:
    """``exact``: the scanned stock whose ticker is the query, if any.  ``items``: candidates, best first, the market on
    screen before the other.  A near miss is a ticker one edit away (two for five letters or more); codes of digits are
    matched by prefix only, since a wrong digit is another company."""
    q = " ".join(str(query or "").split())
    if not q:
        return {"query": q, "market": market, "exact": None, "items": []}
    up, low = q.upper(), q.lower()
    letters = up.isascii() and up.replace(".", "").replace("-", "").isalpha()
    found = []
    for s in stocks:
        t, name = s["ticker"].upper(), s["name"].lower()
        if t == up:
            kind = "EXACT"
        elif t.startswith(up):
            kind = "PREFIX"
        elif name.startswith(low):
            kind = "NAME_START"
        elif len(low) >= 2 and low in name:
            kind = "NAME"
        elif letters and t.isalpha() and 2 <= len(up) <= 6 and distance(up, t) <= (1 if len(up) <= 4 else 2):
            kind = "NEAR"
        else:
            continue
        found.append({**s, "match": kind})
    # among near misses a ticker of the same length comes first: APPL means AAPL before it means APP
    found.sort(key=lambda s: (ORDER[s["match"]], s["market"] != market, abs(len(s["ticker"]) - len(up)) if s["match"] == "NEAR" else 0, len(s["ticker"]), s["ticker"]))
    exact = next(({k: s[k] for k in ("ticker", "name", "market")} for s in found if s["match"] == "EXACT"), None)
    return {"query": q, "market": market, "exact": exact, "items": found[:limit]}
