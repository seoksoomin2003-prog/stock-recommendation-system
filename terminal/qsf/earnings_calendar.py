"""Upcoming earnings dates for the scanned stocks, from what the scan already stored.  Read only: it asks no network.

The dates are Yahoo's.  Before a company confirms, Yahoo shows an estimate, so a date can move.  A stock with no stored
date is counted, never shown as having no earnings.
"""
from datetime import date
from typing import Any, Callable, Dict, Iterable, List, Optional

STALE_DAYS = 7          # the scan refreshes these every three days; older than a week means the scan stopped asking


def upcoming(rows: Iterable[Dict[str, Any]], read: Callable[[str], Optional[Dict[str, Any]]], today: date, now_ts: float, days: int = 14,
             held: Iterable[str] = (), watched: Iterable[str] = ()) -> Dict[str, Any]:
    by_ticker: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        t = r.get("ticker")
        if not t:
            continue
        cur = by_ticker.setdefault(t, {"ticker": t, "name": r.get("name"), "buy": []})
        if r.get("action") == "BUY":
            cur["buy"].append(r.get("strategy"))
    held, watched = set(held), set(watched)
    for t in sorted(held | watched):
        by_ticker.setdefault(t, {"ticker": t, "name": None, "buy": []})     # a holding outside the scan still gets its stored date
    items: List[Dict[str, Any]] = []
    no_date = stale = 0
    for t, info in by_ticker.items():
        rec = read(t)
        dates = sorted(str(d) for d in ((rec or {}).get("data") or []) if isinstance(d, str))
        nxt = next((d for d in dates if d >= today.isoformat()), None)
        if rec is None or nxt is None:
            no_date += 1
            continue
        try:
            away = (date.fromisoformat(nxt) - today).days
        except ValueError:
            no_date += 1
            continue
        age = (now_ts - float(rec.get("stored_at") or 0)) / 86400
        old = age > STALE_DAYS
        stale += old
        if away <= days:
            items.append({**info, "buy": sorted(x for x in info["buy"] if x), "date": nxt, "days_away": away, "held": t in held, "watched": t in watched,
                          "stored_days_ago": round(age, 1), "stale": old})
    items.sort(key=lambda x: (x["date"], not x["held"], not x["watched"], x["ticker"]))
    return {"status": "REAL", "today": today.isoformat(), "days": days, "checked": len(by_ticker), "no_date": no_date, "stale": stale, "items": items,
            "source": "Yahoo 실적 일정 (회사 확정 전에는 추정치)"}
