"""Same-day check of one stock: what has happened since the score's session.  Shown beside the score and never added to it.

The score reads finished sessions only, so this is where today's price, new filings and headlines appear.  Filings count as
warnings only by the rules the score's own event reader uses, and each section fails alone: a missing one says so.
"""
import re
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from terminal import news, portfolio as pf
from terminal.qsf import events

NEWS_TTL = 900
MAX_FILINGS = 8
MAX_NEWS = 15
AVG_VOLUME_SESSIONS = 20
MIN_VOLUME_SESSIONS = 10
ZONES = {"US": "America/New_York", "KR": "Asia/Seoul"}
BENCH = {"US": ("SPY", "S&P 500 ETF(SPY)"), "KR": ("069500", "KODEX 200")}
LEVELS = (("severe", "bad"), ("negative", "warn"), ("governance", "warn"), ("positive", "info"))


def _pct(a: Optional[float], b: Optional[float]) -> Optional[float]:
    return (a / b - 1) * 100 if a is not None and b else None


def quote_section(chart: Dict[str, Any]) -> Dict[str, Any]:
    """``score_session`` is the last finished bar: an unfinished one is today's move, which the score has not seen."""
    bars = chart.get("bars") or []
    if not bars:
        return {"status": "UNAVAILABLE", "score_session": None}
    last, live = bars[-1], bool((chart.get("last") or {}).get("intraday"))
    prev = bars[-2] if len(bars) > 1 else None
    done = prev if live else last
    volumes = [b.get("volume") for b in bars[:-1][-AVG_VOLUME_SESSIONS:] if b.get("volume")]
    average = sum(volumes) / len(volumes) if len(volumes) >= MIN_VOLUME_SESSIONS else None
    return {"status": chart.get("status"), "date": last["date"], "price": last.get("close"), "intraday": live, "score_session": done["date"] if done else None,
            "change_pct": _pct(last.get("close"), prev.get("close")) if prev else None, "gap_pct": _pct(last.get("open"), prev.get("close")) if prev else None,
            "volume": last.get("volume"), "average_volume": average,
            "volume_ratio": last["volume"] / average if average and last.get("volume") and not live else None,   # a partial day against full days would read as quiet
            "fetched_at": (chart.get("cache") or {}).get("fetched_at"), "source": chart.get("source")}


def bench_section(chart: Dict[str, Any], date: Optional[str], name: str):
    """The market's move on the stock's own last day.  A provider can hold a stock's bar back while the market's has arrived: that gap is reported."""
    bars = chart.get("bars") or []
    if not bars or not date:
        return None, None, None
    at = next((n for n, b in enumerate(bars) if b["date"] == date), None)
    behind = sum(1 for b in bars if b["date"] > date)
    if at is None or at == 0:
        return None, behind, bars[-1]["date"]
    return {"name": name, "date": date, "change_pct": _pct(bars[at].get("close"), bars[at - 1].get("close"))}, behind, bars[-1]["date"]


def new_warnings(classified: Dict[str, Any], score_session: Optional[str]) -> List[Dict[str, str]]:
    """Events after the score's session: earlier ones are already in the score and its gates."""
    out = [{"level": level, "label": e["label"], "date": e["date"]} for key, level in LEVELS for e in classified.get(key) or []
           if score_session is None or e["date"] > score_session]
    return out


def _events(terminal: Any, ticker: str, market: str, today: str) -> Dict[str, Any]:
    if market == "US":
        return terminal.qsf._us_events(terminal._cik(ticker), today)
    reports = terminal.qsf.kr_company(ticker).get("reports")
    return {"status": "UNAVAILABLE"} if reports is None else events.classify_kr(reports, today)


def _name(terminal: Any, ticker: str, market: str) -> Optional[str]:
    hit = next((r.get("name") for r in terminal.qsf.latest(market).get("rows") or [] if r.get("ticker") == ticker and r.get("name")), None)
    if hit or market == "US":
        return hit
    return (terminal.qsf._kr_identity(ticker) or {}).get("name")


def build(terminal: Any, ticker: str, market: str = "US") -> Dict[str, Any]:
    ticker = (ticker or "").strip().upper()
    if not re.fullmatch(r"[0-9A-Z]{6}" if market == "KR" else r"[A-Z][A-Z0-9.\-]{0,9}", ticker) or pf.market_of(ticker) != market:
        raise ValueError("INVALID_TICKER")
    today = terminal.qsf.now().astimezone(ZoneInfo(ZONES[market])).date().isoformat()
    try:
        quote = quote_section(terminal.chart(ticker, "3mo"))
    except Exception as exc:
        quote = {"status": "UNAVAILABLE", "score_session": None, "error": type(exc).__name__}
    session = quote.get("score_session")

    bench_sym, bench_name = BENCH[market]
    bench = None
    try:
        bench, quote["behind_market"], quote["market_date"] = bench_section(terminal.chart(bench_sym, "3mo"), quote.get("date"), bench_name)
    except Exception:
        pass

    warnings, events_status = [], "UNAVAILABLE"
    try:
        classified = _events(terminal, ticker, market, today)
        events_status = classified.get("status", "UNAVAILABLE")
        if events_status == "REAL":
            warnings = new_warnings(classified, session)
    except Exception:
        pass

    try:
        f = terminal.filings(ticker)
        filings = {"status": f.get("status"), "fetched_at": f.get("fetched_at"), "source": f.get("source"), "reason": f.get("reason"),
                   "items": [x for x in f.get("items") or [] if session is None or (x.get("filing_date") or "") >= session][:MAX_FILINGS]}
    except Exception as exc:
        filings = {"status": "UNAVAILABLE", "reason": type(exc).__name__, "items": []}

    name = None
    try:
        name = _name(terminal, ticker, market)
    except Exception:
        pass
    if market == "KR" and not name:
        headlines = {"status": "UNAVAILABLE", "error": "NO_NAME", "items": []}      # a bare code finds unrelated articles
    else:
        res = terminal.cache.cached(f"news:{market}:{ticker}", NEWS_TTL, lambda: news.fetch(ticker, market, name))
        data = res.get("data") or {}
        headlines = {"status": res["status"], "fetched_at": res.get("fetched_at"), "error": res.get("error"), "provider": data.get("provider"), "items": (data.get("items") or [])[:MAX_NEWS]}

    return {"status": "REAL", "ticker": ticker, "market": market, "local_date": today, "score_session": session, "quote": quote, "bench": bench,
            "warnings": warnings, "events_status": events_status, "filings": filings, "news": headlines,
            "note": "이 패널은 점수에 포함되지 않습니다. 뉴스 제목의 호재·악재를 판단하지 않으며, 수익과의 관계도 검증되지 않았습니다."}
