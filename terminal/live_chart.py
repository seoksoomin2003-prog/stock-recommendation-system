"""The chart during the session (user request 2026-11-25: "장중일 때 실시간으로 움직이게").

The terminal asks Yahoo for the day's one-minute bars (the same provider as every other price on this device; no server, no key)
and the chart screen asks again every ``REFRESH_S`` seconds while a session is open.  Yahoo's one-minute bars of US stocks arrive
within seconds; Korean bars may come later.  Nothing here assumes a delay: the age of the last bar is measured against the
clock and shown, so a late price is never shown as a current one.  Reference only, never a score.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

REFRESH_S = 30
LATE_MIN = 5            # a last bar older than this during an open session is named as late
# regular sessions, local time: (zone, open, close)
SESSIONS = {"US": ("America/New_York", (9, 30), (16, 0)), "KR": ("Asia/Seoul", (9, 0), (15, 30))}
SOURCE = "Yahoo Finance 1분봉"


def open_now(market: str, now: datetime) -> bool:
    """A weekday inside the regular session.  Holidays are not listed: on one the bars are the last session's and ``live`` is false."""
    zone, start, end = SESSIONS[market]
    local = now.astimezone(ZoneInfo(zone))
    return local.weekday() < 5 and start <= (local.hour, local.minute) < end


def _slots(market: str) -> int:
    _, (h0, m0), (h1, m1) = SESSIONS[market]
    return (h1 * 60 + m1) - (h0 * 60 + m0)


def _minute(time: str, market: str) -> int:
    """Minutes from the session's open, inside 0..slots-1 (a closing-auction print at the close sits on the last minute)."""
    _, (h0, m0), _ = SESSIONS[market]
    at = int(time[11:13]) * 60 + int(time[14:16]) - (h0 * 60 + m0)
    return min(max(at, 0), _slots(market) - 1)


def _pct(a: Optional[float], b: Optional[float]) -> Optional[float]:
    return None if a is None or not b else round((a / b - 1) * 100, 2)


def view(got: Dict[str, Any], market: str, now: datetime, cache: Dict[str, Any]) -> Dict[str, Any]:
    """The screen's answer from ``sources.yahoo_intraday``'s rows and the cache entry around them."""
    rows = got.get("rows") or []
    is_open = open_now(market, now)
    base = {"market": market, "open_now": is_open, "source": SOURCE, "refresh_s": REFRESH_S,
            "cache": {k: cache.get(k) for k in ("status", "fetched_at", "error")}}
    if not rows:
        return {**base, "status": "UNAVAILABLE", "bars": [], "live": False, "note": "1분봉을 받지 못했습니다."}
    zone = ZoneInfo(SESSIONS[market][0])
    session = rows[-1]["time"][:10]
    today = now.astimezone(zone).strftime("%Y-%m-%d")
    live = is_open and session == today
    last = rows[-1]
    age = round((now.timestamp() - last["ts"]) / 60, 1) if live else None
    closes = [r["close"] for r in rows]
    highs = [r["high"] if r.get("high") is not None else r["close"] for r in rows]
    lows = [r["low"] if r.get("low") is not None else r["close"] for r in rows]
    vols = [r["volume"] for r in rows if r.get("volume") is not None]
    prev = got.get("prev_close")
    clock = last["time"][11:16]
    if live:
        note = f"마지막 1분봉 {clock}, 약 {age:.0f}분 전 가격입니다." + (" Yahoo가 이 시장 가격을 늦게 주고 있어 지금 체결가와 다를 수 있습니다." if age > LATE_MIN else "")
    elif is_open:
        note = f"오늘 거래가 아직 없습니다(휴장일일 수 있음). {session} 마지막 거래일의 1분봉입니다."
    else:
        note = f"정규장이 열려 있지 않습니다. {session} 마지막 거래일의 1분봉입니다."
    status = "STALE" if cache.get("status") == "STALE" else "REAL"
    return {**base, "status": status, "live": live, "session": session, "age_min": age, "note": note,
            "bars": [{**r, "date": r["time"], "m": _minute(r["time"], market)} for r in rows], "slots": _slots(market),
            "open_hm": list(SESSIONS[market][1]),
            "last": {"time": last["time"], "close": last["close"], "prev_close": prev, "change_pct": _pct(last["close"], prev),
                     "open": rows[0].get("open"), "high": max(highs), "low": min(lows), "volume": sum(vols) if vols else None}}


def merge_daily(rows: List[Dict[str, Any]], v: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Daily bars with the open session's bar brought up to the last one-minute bar.  Only for a live view; the rest stays."""
    if not v.get("live") or not v.get("last"):
        return rows
    L, day = v["last"], v["session"]
    today = {"date": day, "open": L["open"], "high": L["high"], "low": L["low"], "close": L["close"], "volume": L["volume"]}
    if rows and rows[-1].get("date") == day:
        old = rows[-1]
        hi = [x for x in (old.get("high"), L["high"]) if x is not None]
        lo = [x for x in (old.get("low"), L["low"]) if x is not None]
        vol = [x for x in (old.get("volume"), L["volume"]) if x is not None]
        today = {**old, "open": old.get("open") if old.get("open") is not None else L["open"], "high": max(hi) if hi else None,
                 "low": min(lo) if lo else None, "close": L["close"], "volume": max(vol) if vol else None}
        return rows[:-1] + [today]
    if rows and rows[-1].get("date", "") > day:
        return rows
    return rows + [today]
