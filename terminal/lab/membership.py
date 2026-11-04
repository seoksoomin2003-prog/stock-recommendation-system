"""Approximate point-in-time S&P 500 membership for the research simulation.

Wikipedia's constituents table lists each CURRENT member's "Date added".  The simulation only lets a stock
be picked from that date on, which removes the strongest survivorship effect (stocks selected in periods
BEFORE they joined the index, typically right after huge run-ups).  Stocks that left the index are still
missing (residual survivorship bias, stated on screen).  Cached at data/lab/membership.json.
"""
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, Optional

from terminal.sources import GENERIC_UA

URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
MAX_AGE_DAYS = 7
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}")


def _http_get(url: str) -> str:
    import requests
    r = requests.get(url, headers={"User-Agent": GENERIC_UA}, timeout=20)   # generic UA, no personal contact
    r.raise_for_status()
    return r.text


def parse(html: str) -> Dict[str, Optional[str]]:
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", {"id": "constituents"})
    if table is None:
        raise ValueError("constituents table not found")
    head = [c.get_text(" ", strip=True).lower() for c in table.find("tr").find_all(["th", "td"])]
    try:
        k = next(i for i, h in enumerate(head) if "date added" in h)
    except StopIteration:
        raise ValueError("'Date added' column not found")
    out = {}
    for row in table.find_all("tr")[1:]:
        cols = row.find_all("td")
        if len(cols) <= k:
            continue
        t = cols[0].get_text(strip=True).upper().replace(".", "-")
        d = cols[k].get_text(strip=True)
        out[t] = d[:10] if DATE_RE.match(d) else None
    if len(out) < 450:
        raise ValueError(f"too few constituents parsed ({len(out)})")
    return out


def load(path: Path, now: datetime, fetch: Callable[[str], str] = _http_get) -> Dict:
    """{'status', 'added': {ticker: 'YYYY-MM-DD'|None}, 'retrieved_at'}; refreshed weekly, STALE on failure."""
    old = None
    try:
        old = json.loads(path.read_text(encoding="utf-8"))
        age = (now - datetime.fromisoformat(old["retrieved_at"])).days
        if age <= MAX_AGE_DAYS:
            return {**old, "status": "REAL"}
    except (OSError, ValueError, KeyError):
        old = None
    try:
        added = parse(fetch(URL))
    except Exception as exc:
        if old:
            return {**old, "status": "STALE", "error": type(exc).__name__}
        return {"status": "UNAVAILABLE", "added": {}, "error": type(exc).__name__}
    rec = {"added": added, "retrieved_at": now.astimezone(timezone.utc).isoformat(),
           "source": "Wikipedia: List of S&P 500 companies (Date added)"}
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(rec), encoding="utf-8")
    tmp.replace(path)
    return {**rec, "status": "REAL"}
