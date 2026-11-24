"""2026-11-25 user request: the chart moves during the session (terminal/live_chart.py, /api/chart/intraday, live=1 on the
chart analysis).  No network."""
import json
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from terminal import live_chart as lc, server, sources
from terminal.services import Terminal

ROOT = Path(__file__).resolve().parents[1]
NY, SEOUL = ZoneInfo("America/New_York"), ZoneInfo("Asia/Seoul")


def _rows(day, start_hm, n, tz, base=100.0):
    t0 = datetime(*day, *start_hm, tzinfo=tz)
    out = []
    for i in range(n):
        t = t0 + pd.Timedelta(minutes=i)
        out.append({"time": t.strftime("%Y-%m-%d %H:%M"), "ts": int(t.timestamp()), "open": base + i, "high": base + i + 0.5,
                    "low": base + i - 0.5, "close": base + i + 0.2, "volume": 10.0})
    return out


def test_open_hours_per_market():
    assert lc.open_now("US", datetime(2026, 11, 24, 10, 0, tzinfo=NY)) and not lc.open_now("US", datetime(2026, 11, 24, 16, 0, tzinfo=NY))
    assert lc.open_now("KR", datetime(2026, 11, 24, 9, 0, tzinfo=SEOUL)) and not lc.open_now("KR", datetime(2026, 11, 22, 10, 0, tzinfo=SEOUL))
    assert lc.REFRESH_S == 30 and lc._slots("US") == 390 and lc._slots("KR") == 390


def test_a_live_view_names_the_age_of_its_last_bar():
    rows = _rows((2026, 11, 24), (9, 30), 31, NY)
    now = datetime(2026, 11, 24, 10, 0, 40, tzinfo=NY)
    v = lc.view({"rows": rows, "prev_close": 100.0}, "US", now, {"status": "REAL", "fetched_at": "x"})
    assert v["live"] and v["status"] == "REAL" and v["age_min"] == 0.7 and "10:00" in v["note"] and "늦게" not in v["note"]
    assert v["bars"][0]["m"] == 0 and v["bars"][-1]["m"] == 30 and v["last"]["high"] == 130.5 and v["last"]["low"] == 99.5
    assert v["last"]["volume"] == 310.0 and v["last"]["change_pct"] == 30.2 and v["open_hm"] == [9, 30]
    late = lc.view({"rows": rows, "prev_close": 100.0}, "US", datetime(2026, 11, 24, 10, 25, tzinfo=NY), {"status": "REAL"})
    assert late["age_min"] == 25.0 and "늦게" in late["note"]                       # a late price is never shown as a current one


def test_a_closed_market_or_a_holiday_is_not_live():
    rows = _rows((2026, 11, 24), (9, 0), 10, SEOUL, 50000.0)
    closed = lc.view({"rows": rows}, "KR", datetime(2026, 11, 24, 20, 0, tzinfo=SEOUL), {"status": "REAL"})
    assert not closed["live"] and closed["age_min"] is None and "열려 있지 않습니다" in closed["note"]
    holiday = lc.view({"rows": rows}, "KR", datetime(2026, 11, 25, 10, 0, tzinfo=SEOUL), {"status": "REAL"})
    assert holiday["open_now"] and not holiday["live"] and "휴장일" in holiday["note"]
    empty = lc.view({"rows": []}, "KR", datetime(2026, 11, 24, 10, 0, tzinfo=SEOUL), {"status": "UNAVAILABLE"})
    assert empty["status"] == "UNAVAILABLE" and empty["bars"] == []
    assert lc.view({"rows": rows}, "KR", datetime(2026, 11, 24, 20, 0, tzinfo=SEOUL), {"status": "STALE"})["status"] == "STALE"


def test_the_daily_chart_takes_the_session_bar_up_to_the_last_minute():
    v = lc.view({"rows": _rows((2026, 11, 24), (9, 30), 31, NY)}, "US", datetime(2026, 11, 24, 10, 1, tzinfo=NY), {"status": "REAL"})
    daily = [{"date": "2026-11-21", "open": 90, "high": 95, "low": 89, "close": 94, "volume": 1000.0}]
    added = lc.merge_daily(daily, v)
    assert added[-1] == {"date": "2026-11-24", "open": 100.0, "high": 130.5, "low": 99.5, "close": 130.2, "volume": 310.0} and len(added) == 2
    stale = daily + [{"date": "2026-11-24", "open": 101.0, "high": 140.0, "low": 100.0, "close": 120.0, "volume": 5000.0}]
    got = lc.merge_daily(stale, v)[-1]
    assert got["open"] == 101.0 and got["high"] == 140.0 and got["low"] == 99.5 and got["close"] == 130.2 and got["volume"] == 5000.0
    closed = dict(v, live=False)
    assert lc.merge_daily(daily, closed) is daily


def test_yahoo_rows_are_read_without_inventing_prices():
    idx = pd.DatetimeIndex([pd.Timestamp("2026-11-24 09:30", tz=NY), pd.Timestamp("2026-11-24 09:31", tz=NY)])
    frame = pd.DataFrame({"Open": [1.0, 2.0], "High": [1.5, 2.5], "Low": [0.5, 1.5], "Close": [1.2, float("nan")], "Volume": [5, 6]}, index=idx)
    got = sources.yahoo_intraday("X", fetch=lambda s: (frame, {"chartPreviousClose": 1.1}))
    assert got["prev_close"] == 1.1 and len(got["rows"]) == 1 and got["rows"][0]["time"] == "2026-11-24 09:30"


class _Src:
    def __init__(self, rows):
        self.rows, self.asked = rows, 0

    def yahoo_intraday(self, sym):
        self.asked += 1
        return {"rows": self.rows, "prev_close": 100.0}

    def yahoo_history(self, symbols, period):
        days = pd.bdate_range(end="2026-11-21", periods=300)
        return {symbols[0]: [{"date": d.strftime("%Y-%m-%d"), "open": 90.0, "high": 91.0, "low": 89.0, "close": 90.0 + (i % 5), "volume": 1e6} for i, d in enumerate(days)]}


def test_the_routes_answer_and_the_analysis_merges_only_when_asked(tmp_path):
    now = datetime(2026, 11, 24, 10, 1, tzinfo=NY).astimezone(timezone.utc)
    src = _Src(_rows((2026, 11, 24), (9, 30), 31, NY))
    t = Terminal(tmp_path, src=src, now=lambda: now)
    routes = server.routes(t)
    got = routes[("GET", "/api/chart/intraday")]({"t": "AAPL"}, None)
    assert got["live"] and got["ticker"] == "AAPL" and "NaN" not in json.dumps(got)
    plain = routes[("GET", "/api/chart/analysis")]({"t": "AAPL", "range": "3mo"}, None)
    assert plain["live_now"] is None and plain["bars"][-1]["date"] == "2026-11-20"
    live = routes[("GET", "/api/chart/analysis")]({"t": "AAPL", "range": "3mo", "live": "1"}, None)
    assert live["live_now"]["live"] and live["bars"][-1]["date"] == "2026-11-24" and live["bars"][-1]["close"] == 130.2
    assert "1분봉으로 이어 그림" in live["source"] and src.asked == 1                    # the 20-second copy is shared


def test_the_screen_polls_one_timer_and_never_feeds_a_score():
    js = (ROOT / "terminal" / "static" / "chart.js").read_text(encoding="utf-8")
    assert '"1d": "오늘(1분봉)"' in js and "CHA_REFRESH_MS = 30000" in js and "clearInterval(cha.timer)" in js
    assert 'state.tab !== "chart" || document.hidden' in js and "&live=1" in js
    for path in list((ROOT / "terminal" / "qsf").rglob("*.py")) + list((ROOT / "terminal" / "committee").rglob("*.py")):
        assert "live_chart" not in path.read_text(encoding="utf-8"), path.name
