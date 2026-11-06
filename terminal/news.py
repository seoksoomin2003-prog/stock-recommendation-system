"""Free news headlines for the same-day check, and a daily record of them.

Headlines are shown and stored as they arrive.  They feed no score, and nothing here judges a headline good or bad: free
history of what was known when does not exist, so any such reading could only be tested on what this record collects.
Every ticker in the scan is recorded, not only the ones looked up, because looked-up names would be a biased sample.
Only the title, link, source and time are stored, never the article.
"""
import gzip
import hashlib
import html
import json
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlencode

import requests

from terminal.sources import GENERIC_UA

YAHOO_RSS = "https://feeds.finance.yahoo.com/rss/2.0/headline"
GOOGLE_RSS = "https://news.google.com/rss/search"
MAX_ITEMS = 20
TIMEOUT = 15
PAUSE_S = 0.6
ABORT_AFTER = 15           # consecutive failures: the feed is down or refusing us, so stop asking
MIN_OK_SHARE = 0.5
SEEN_DAYS = 45


class FeedRefused(RuntimeError):
    """The provider asked us to slow down or stop.  Never retried within a run."""


def parse_rss(xml_bytes: bytes, provider: str, limit: int = MAX_ITEMS) -> List[Dict[str, Any]]:
    """Newest first.  An item without a usable title or an http(s) link is dropped; an unreadable time stays None."""
    if b"<!DOCTYPE" in xml_bytes[:2048].upper() or b"<!ENTITY" in xml_bytes[:2048].upper():
        raise ValueError("RSS_WITH_DTD")      # feeds have no need for one, and entity expansion is a known attack
    out = []
    for item in ET.fromstring(xml_bytes).iter("item"):
        title = re.sub(r"\s+", " ", html.unescape(item.findtext("title") or "")).strip()
        link = (item.findtext("link") or "").strip()
        if not title or not re.match(r"https?://", link, re.I):
            continue
        source = (item.findtext("source") or "").strip() or None
        if source and title.endswith(f" - {source}"):
            title = title[: -len(source) - 3].strip()
        out.append({"title": title, "link": link, "published": _utc(item.findtext("pubDate")), "source": source or provider, "provider": provider})
    out.sort(key=lambda r: r["published"] or "", reverse=True)
    return out[:limit]


def _utc(text: Optional[str]) -> Optional[str]:
    try:
        d = parsedate_to_datetime((text or "").strip())
    except (TypeError, ValueError):
        return None
    return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).astimezone(timezone.utc).isoformat()


def feed_url(ticker: str, market: str, name: Optional[str] = None) -> str:
    if market == "US":
        return f"{YAHOO_RSS}?{urlencode({'s': ticker, 'region': 'US', 'lang': 'en-US'})}"
    return f"{GOOGLE_RSS}?{urlencode({'q': f'{chr(34)}{name or ticker}{chr(34)} when:7d', 'hl': 'ko', 'gl': 'KR', 'ceid': 'KR:ko'})}"


def fetch(ticker: str, market: str, name: Optional[str] = None, http=requests) -> Dict[str, Any]:
    """``items`` may be empty: a quiet stock is not a failed feed.  Failures raise, so the cache can label them."""
    provider = "Yahoo Finance" if market == "US" else "Google 뉴스"
    r = http.get(feed_url(ticker, market, name), headers={"User-Agent": GENERIC_UA}, timeout=TIMEOUT)
    if r.status_code in (403, 429, 503):
        raise FeedRefused(str(r.status_code))
    r.raise_for_status()
    return {"items": parse_rss(r.content, provider), "provider": provider}


def universe(base: Path, market: str) -> List[Dict[str, Any]]:
    try:
        rows = json.loads((Path(base) / "data" / "qsf" / f"latest_{market}.json").read_text(encoding="utf-8")).get("rows") or []
    except (OSError, ValueError):
        return []
    return list({r["ticker"]: {"ticker": r["ticker"], "name": r.get("name")} for r in rows}.values())


def record(base: Path, market: str, http=requests, now: Optional[Callable[[], datetime]] = None, sleep: Callable[[float], None] = time.sleep, pause: float = PAUSE_S) -> Dict[str, Any]:
    """Append headlines not seen before.  Nothing is backfilled: ``first_seen_at`` is when this record first knew of one."""
    at = (now or (lambda: datetime.now(timezone.utc)))()
    names = universe(base, market)
    if not names:
        return {"status": "NO_UNIVERSE", "market": market, "tickers": 0}
    folder = Path(base) / "data" / "news" / market
    folder.mkdir(parents=True, exist_ok=True)
    seen_file = folder / "seen.json"
    try:
        seen = json.loads(seen_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        seen = {}
    day, fresh, ok, failed, streak, stop = at.date().isoformat(), [], 0, 0, 0, None
    for i, row in enumerate(names):
        if i:
            sleep(pause)
        try:
            items = fetch(row["ticker"], market, row.get("name"), http)["items"]
        except FeedRefused as exc:
            failed, stop = failed + 1, f"REFUSED_{exc}"
            break
        except Exception:
            failed, streak = failed + 1, streak + 1
            if streak >= ABORT_AFTER:
                stop = "TOO_MANY_FAILURES"
                break
            continue
        ok, streak = ok + 1, 0
        for it in items:
            key = hashlib.sha256(f"{row['ticker']}|{it['link']}".encode()).hexdigest()[:16]
            if key not in seen:
                seen[key] = day
                fresh.append({"first_seen_at": at.isoformat(), "market": market, "ticker": row["ticker"], **it})
    if fresh:
        with gzip.open(folder / f"{day}.jsonl.gz", "at", encoding="utf-8") as fh:
            fh.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in fresh)
    cut = (at.date() - timedelta(days=SEEN_DAYS)).isoformat()
    tmp = seen_file.with_suffix(".tmp")
    tmp.write_text(json.dumps({k: v for k, v in seen.items() if v >= cut}), encoding="utf-8")
    tmp.replace(seen_file)
    good = stop is None and ok / len(names) >= MIN_OK_SHARE
    out = {"status": "OK" if good else "FAILED", "market": market, "at": at.isoformat(), "tickers": len(names), "ok": ok, "failed": failed,
           "not_asked": len(names) - ok - failed, "new_items": len(fresh), "stopped": stop}
    with open(folder / "runs.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps(out, ensure_ascii=False) + "\n")
    return out
