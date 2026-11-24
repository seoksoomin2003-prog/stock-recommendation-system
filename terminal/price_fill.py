"""The price a trade form fills in by itself (user request 2026-11-24).

A form names a ticker and a date; this picks the last daily close on or before that date from bars the program already
fetches for its charts (Korean stocks: the KRX copy the score uses; coins: the Binance four-hour closes times the won rate of
that day).  It is a suggestion the user can overwrite: a free delayed close, never the price an order was filled at.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence
from zoneinfo import ZoneInfo

STALE_DAYS = 5          # same as the chart: a close more than five calendar days before the asked day is shown as old
SPLIT_NOTE = "분할이 있었던 종목의 지난 날짜 가격은 분할 기준으로 조정된 값이라 그때 실제 체결가와 다를 수 있습니다."


def parse_day(text: Optional[str]) -> Optional[date]:
    """'' -> None (the newest close).  Anything that is not YYYY-MM-DD is refused, not guessed."""
    if not text:
        return None
    try:
        return datetime.strptime(str(text), "%Y-%m-%d").date()
    except ValueError:
        raise ValueError("INVALID_DATE") from None


def pick(rows: Sequence[Dict[str, Any]], want: Optional[date], today: date) -> Dict[str, Any]:
    """The last row dated on or before ``want`` (or the last row).  ``status`` is UNAVAILABLE when there is none, STALE when that
    row lies more than STALE_DAYS calendar days before the asked day (a halt, a delisting, a feed that stopped)."""
    ref = want or today
    keep = [r for r in rows if r.get("date") and r["date"] <= ref.isoformat() and r.get("close")]
    if not keep:
        return {"status": "UNAVAILABLE", "close": None, "date": None,
                "reason": "BEFORE_HISTORY" if rows and want else "NO_PRICE"}
    last = keep[-1]
    age = (ref - datetime.strptime(last["date"], "%Y-%m-%d").date()).days
    return {"status": "STALE" if age > STALE_DAYS else "REAL", "close": float(last["close"]), "date": last["date"],
            "exact": last["date"] == ref.isoformat()}


def kr_raw_closes(code: str, pan: Optional[Dict[str, Any]], close_row: int) -> List[Dict[str, Any]]:
    """A Korean stock's KRX closes as traded (not adjusted for later splits or rights issues), from the daily copy the score
    uses.  The chart shows adjusted bars; a trade form needs the price that was actually paid that day."""
    j = pan["codes"].get(code) if pan else None
    if j is None:
        return []
    closes, out = pan["data"][close_row, :, j], []
    for day, c in zip(pan["dates"], closes):
        c = float(c)
        if c == c and c > 0:                     # NaN != NaN: a halted or unlisted day has no close
            out.append({"date": day, "close": c})
    return out


def coin_close(bars, unit: float, bar_ms: int, want: Optional[date], today: date) -> Optional[Dict[str, Any]]:
    """The USDT close of the last four-hour bar that closed by the end of the asked Korean day (or the newest one).
    ``bars`` rows are [open_ms, open, high, low, close, volume]."""
    if bars is None or not len(bars):
        return None
    seoul = ZoneInfo("Asia/Seoul")
    end = datetime.combine((want or today) + timedelta(days=1), datetime.min.time(), tzinfo=seoul)
    end_ms = end.timestamp() * 1000
    ok = [b for b in bars if float(b[0]) + bar_ms <= end_ms and float(b[4]) > 0]
    if not ok:
        return None
    b = ok[-1]
    closed = datetime.fromtimestamp((float(b[0]) + bar_ms) / 1000, tz=timezone.utc).astimezone(seoul)
    return {"usd": float(b[4]) / unit, "date": closed.strftime("%Y-%m-%d"), "at": closed.strftime("%Y-%m-%d %H:%M")}


def fx_on(rows: List[Dict[str, Any]], day: str) -> Optional[Dict[str, Any]]:
    """The won-per-dollar close on or before ``day``."""
    keep = [r for r in rows if r.get("date") and r["date"] <= day and r.get("close")]
    return keep[-1] if keep else None
