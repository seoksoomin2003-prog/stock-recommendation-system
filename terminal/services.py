"""Screen data for the terminal (TERMINAL-1 §2).  Every payload carries status / source / as-of.

The terminal only READS model artifacts (runs/, tracking/); it never writes to them.
"""
import json
import math
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from terminal import TERMINAL_VERSION, alert_rules, chart_analysis, portfolio as pf, sources
from terminal.cache import FileCache
from terminal.services_model import ModelViews

TTL = {"quote": 900, "chart": 900, "intraday": 20, "info": 20 * 3600, "facts": 20 * 3600, "filings": 3600, "macro": 6 * 3600}
STALE_DAYS = 5          # a daily bar older than this many calendar days is shown as STALE

OVERVIEW = [
    ("지수", [("^GSPC", "S&P 500"), ("^IXIC", "나스닥 종합"), ("^DJI", "다우존스"), ("^RUT", "러셀 2000"),
             ("^VIX", "VIX 변동성")]),
    ("금리·환율·원자재", [("^TNX", "미 10년물 금리(%)"), ("DX-Y.NYB", "달러인덱스"), ("KRW=X", "원/달러"),
                    ("CL=F", "WTI 원유"), ("GC=F", "금")]),
    ("섹터 ETF", [("XLK", "기술"), ("XLF", "금융"), ("XLV", "헬스케어"), ("XLE", "에너지"), ("XLY", "임의소비재"),
                ("XLP", "필수소비재"), ("XLI", "산업재"), ("XLU", "유틸리티"), ("XLB", "소재"), ("XLRE", "부동산"),
                ("XLC", "커뮤니케이션")]),
]

MACRO = [  # FRED public-domain series only (no third-party copyright notice)
    ("DGS10", "미 10년물 국채금리", "%", "level"), ("DGS2", "미 2년물 국채금리", "%", "level"),
    ("T10Y2Y", "장단기 금리차(10년-2년)", "%p", "level"), ("DFF", "연방기금 실효금리", "%", "level"),
    ("CPIAUCSL", "소비자물가(CPI) 전년비", "%", "yoy"), ("UNRATE", "실업률", "%", "level"),
    ("PAYEMS", "비농업 고용(천 명)", "천 명", "level"), ("DEXKOUS", "원/달러 환율", "원", "level"),
]

FUNDAMENTALS = [  # (key, label, kind, unit, concepts in priority order) -- display only, not model inputs
    ("revenue", "매출", "flow", "USD", ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax",
                                         "SalesRevenueNet", "RevenuesNetOfInterestExpense"]),
    ("operating_income", "영업이익", "flow", "USD", ["OperatingIncomeLoss"]),
    ("net_income", "순이익", "flow", "USD", ["NetIncomeLoss"]),
    ("eps_diluted", "희석 EPS", "flow", "USD/shares", ["EarningsPerShareDiluted"]),
    ("cfo", "영업현금흐름", "flow", "USD", ["NetCashProvidedByUsedInOperatingActivities"]),
    ("capex", "설비투자", "flow", "USD", ["PaymentsToAcquirePropertyPlantAndEquipment"]),
    ("assets", "총자산", "instant", "USD", ["Assets"]),
    ("liabilities", "총부채", "instant", "USD", ["Liabilities"]),
    ("equity", "자본총계(지배)", "instant", "USD", ["StockholdersEquity"]),
    ("cash", "현금성자산", "instant", "USD", ["CashAndCashEquivalentsAtCarryingValue"]),
]

OVERVIEW_KR = [
    ("지수", [("^KS11", "코스피"), ("^KQ11", "코스닥"), ("^KS200", "코스피 200")]),
    ("환율·대표 ETF", [("KRW=X", "원/달러"), ("069500.KS", "KODEX 200")]),
    ("업종 ETF", [("091160.KS", "반도체"), ("305720.KS", "2차전지"), ("139260.KS", "IT"), ("091180.KS", "자동차"), ("244580.KS", "바이오"),
               ("091170.KS", "은행"), ("102970.KS", "증권"), ("140700.KS", "보험"), ("117460.KS", "에너지화학"), ("117680.KS", "철강"), ("117700.KS", "건설")]),
]
MACRO_KR = [  # Bank of Korea ECOS.  Codes checked against the API on 2026-11-05.
    ("BOK_RATE", "한국은행 기준금리", "%", "level", ("722Y001", "D", ("0101000",))),
    ("KTB3Y", "국고채 3년", "%", "level", ("817Y002", "D", ("010200000",))),
    ("KTB10Y", "국고채 10년", "%", "level", ("817Y002", "D", ("010210000",))),
    ("KR_CPI", "소비자물가 전년비", "%", "yoy", ("901Y009", "M", ("0",))),
    ("KR_UNEMP", "실업률", "%", "level", ("901Y027", "M", ("I61BC", "I28A"))),
]
BENCH = {"US": ("SPY", "SPY"), "KR": ("069500.KS", "KODEX 200")}

def _validation_note() -> str:
    from terminal.qsf import config as qsf_config
    return qsf_config.VALIDATION_NOTICE + " 주문을 실행하지 않습니다."


TICKER_RE = re.compile(r"^\^?[A-Z0-9][A-Z0-9.\-=]{0,14}$")      # AAPL, BRK.B, ^GSPC, KRW=X, CL=F


def clean_ticker(t: str) -> str:
    t = (t or "").strip().upper()
    if not TICKER_RE.match(t):
        raise ValueError("INVALID_TICKER")
    return t


def _rolling_corr(a: List[float], b: List[float], n: int) -> List[Optional[float]]:
    """Correlation of the last n daily returns at each day, aligned to the compare dates (the first date has no return: None)."""
    out: List[Optional[float]] = [None] * (len(a) + 1)
    for i in range(n, len(a) + 1):
        x, y = a[i - n:i], b[i - n:i]
        mx, my = sum(x) / n, sum(y) / n
        sx = math.sqrt(sum((p - mx) ** 2 for p in x))
        sy = math.sqrt(sum((q - my) ** 2 for q in y))
        out[i] = sum((p - mx) * (q - my) for p, q in zip(x, y)) / (sx * sy) if sx and sy else None
    return out


def _sma(values: List[float], n: int) -> List[Optional[float]]:
    out, s = [], 0.0
    for i, v in enumerate(values):
        s += v
        if i >= n:
            s -= values[i - n]
        out.append(round(s / n, 4) if i >= n - 1 else None)
    return out


def _pct(a, b) -> Optional[float]:
    """Percent change a vs b (e.g. 1.6 means +1.6%); None when either side is missing."""
    return (a / b - 1) * 100 if a is not None and b not in (None, 0) else None


def to_krw(value: Optional[float], currency: str, rate: Optional[float]) -> Optional[float]:
    """An amount in won: itself when it is won, times the day's rate when it is dollars; None when either is unknown (never 0)."""
    if value is None:
        return None
    if currency == "KRW":
        return value
    return value * rate if rate else None


class Terminal(ModelViews):
    def __init__(self, base_dir: Path = Path("."), src=sources, clock=None, now: Callable[[], datetime] = None):
        self.base = Path(base_dir)
        self.src = src
        self.cache = FileCache(self.base / "data" / "terminal" / "cache", **({"clock": clock} if clock else {}))
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.watchlist_file = self.base / "data" / "terminal" / "watchlist.json"
        self.journal = pf.Journal(self.base / "data" / "terminal" / "journal.jsonl")
        self.paper = pf.Journal(self.base / "data" / "terminal" / "paper_journal.jsonl")      # paper trades kept by hand; never the real account
        self.settings_file = self.base / "data" / "terminal" / "settings.json"
        from terminal.lab.service import Lab
        self.lab = Lab(self.base, now=self.now)
        self._qsf = None

    @property
    def qsf(self):
        if self._qsf is None:
            from terminal.qsf.service import QSF, _LAZY
            with _LAZY:                     # the first requests after a start arrive together; one scorer, with one set of memos
                if self._qsf is None:
                    self._qsf = QSF(self.base, src=self.src, now=self.now, terminal=self)
        return self._qsf

    def qsf_evaluate(self, ticker: str, market: str = "US") -> Dict[str, Any]:
        if market == "KR":
            if not re.fullmatch(r"[0-9A-Z]{6}", (ticker or "").strip().upper()):
                raise ValueError("INVALID_TICKER")
            code = ticker.strip().upper()
        elif market != "US":
            raise ValueError("INVALID_MARKET")
        else:
            code = clean_ticker(ticker)
        res = self.qsf.evaluate(code, market)
        if isinstance(res, dict) and res.get("cards"):
            from terminal.qsf import price_audit, rank_notes
            res = {**res, "price_audit": price_audit.for_stock(self.base, market, code),       # shown beside the score, never part of it
                   "cards": {k: {**c, "balance": rank_notes.balance(c.get("factors") or [])} for k, c in res["cards"].items()}}    # display only
        return res

    def rank_notes(self, market: str = "US") -> Dict[str, Any]:
        """For the ranking table and Today's candidates: each recorded stock's largest push up and down, its score at the session
        before, and its sector.  Read from the ledger snapshots of the newest scan; nothing is scored again."""
        from terminal.qsf import rank_notes
        latest = self.qsf.latest(market)
        session = latest.get("session")
        if latest.get("status") != "REAL" or not session:
            return {"status": "NO_SCAN", "market": market}
        memo = getattr(self, "_rank_notes_memo", None)
        if memo is None:
            memo = self._rank_notes_memo = {}
        key = (market, session, latest.get("generated_at"), self.qsf.ledger._index_stamp())
        if key not in memo:
            memo.clear() if len(memo) > 8 else None
            got = rank_notes.notes(self.qsf.ledger, market, session)
            sectors = {r["ticker"]: r.get("sector") for r in self.qsf.screen_rows(market).get("rows") or []}
            memo[key] = {"status": "REAL", "market": market, "session": session, "prev_session": next((v["prev_session"] for v in got.values()), None),
                         "rows": {f"{t}|{s}": v for (t, s), v in got.items()}, "sectors": sectors, "band_edges": rank_notes.band_edges(),
                         "daily_move": rank_notes.daily_move(self.qsf.ledger, market, session),
                         "note": "가점·감점은 중간(50점)에서 각 요인이 더하거나 뺀 점수입니다. 모든 요인의 값을 더하면 총점 − 50이 됩니다. 스캔이 원장에 남긴 값에서 읽었습니다."}
        return memo[key]

    def qsf_history(self, ticker: str, market: str = "US") -> Dict[str, Any]:
        """A stock's recorded scores, read from the ledger.  Same ticker checks as evaluation."""
        from terminal.qsf import history
        if market == "KR":
            code = (ticker or "").strip().upper()
            if not re.fullmatch(r"[0-9A-Z]{6}", code):
                raise ValueError("INVALID_TICKER")
            return history.history(self.qsf.ledger, "KR", code)
        if market != "US":
            raise ValueError("INVALID_MARKET")
        return history.history(self.qsf.ledger, "US", clean_ticker(ticker))

    # ---------------------------------------------------------------- helpers
    def _intraday(self, last_date: Optional[str], market: str = "US") -> bool:
        """True when the last bar is today's session and the regular close (16:00 ET or 15:30 KST, +15 min for data
        settlement) has not passed: the value is a delayed intraday price, not a final close."""
        if not last_date:
            return False
        if market == "KR":
            kst = self.now().astimezone(ZoneInfo("Asia/Seoul"))
            return last_date == kst.strftime("%Y-%m-%d") and (kst.hour, kst.minute) < (15, 45)
        et = self.now().astimezone(ZoneInfo("America/New_York"))
        return last_date == et.strftime("%Y-%m-%d") and (et.hour, et.minute) < (16, 15)

    def _bar_status(self, last_date: Optional[str], cache_status: str, symbol: str = "", newest: Optional[str] = None) -> str:
        """REAL only when the bar is the newest one its market should have by now (terminal/freshness.py): a reply that stopped a
        session or more earlier reads STALE, as it does on the score path.  ``newest``: the newest date among the Korean
        symbols of the same reply."""
        if cache_status != "REAL" or not last_date:
            return cache_status if cache_status != "REAL" else "UNAVAILABLE"
        age = (self.now().date() - datetime.strptime(last_date, "%Y-%m-%d").date()).days
        if age > STALE_DAYS:
            return "STALE"
        from terminal import freshness
        return "STALE" if freshness.behind(last_date, symbol, self.now(), newest_in_reply=newest) else "REAL"

    def _sym(self, ticker: str) -> str:
        """Yahoo symbol of a ticker.  A Korean code not on the listed-company master, such as an ETF, is tried on KOSPI."""
        if pf.market_of(ticker) == "US":
            return ticker
        try:
            ident = self.qsf._kr_identity(ticker)
        except Exception:
            ident = None
        return (ident or {}).get("yahoo_symbol") or f"{ticker}.KS"

    def _kr_name(self, ticker: str) -> Optional[str]:
        if pf.market_of(ticker) == "US":
            return None
        try:
            return (self.qsf._kr_identity(ticker) or {}).get("company_name")
        except Exception:
            return None

    def _quotes(self, symbols: List[str], key: str, market: str = "US") -> Dict[str, Any]:
        res = self.cache.cached(key, TTL["quote"], lambda: self.src.yahoo_history(symbols, "3mo"))
        data = res["data"] or {}
        out = {}
        from terminal import freshness
        newest = freshness.newest((s, (data.get(s) or [{}])[-1].get("date")) for s in symbols)
        for s in symbols:
            rows = data.get(s) or []
            if not rows:
                out[s] = {"symbol": s, "status": "UNAVAILABLE", "close": None, "change_pct": None,
                          "change_1m_pct": None, "date": None}
                continue
            last, prev = rows[-1], rows[-2] if len(rows) > 1 else None
            m1 = rows[-22] if len(rows) > 21 else None
            out[s] = {"symbol": s, "date": last["date"], "close": last["close"],
                      "change": (last["close"] - prev["close"]) if prev else None,
                      "change_pct": _pct(last["close"], prev["close"] if prev else None),
                      "change_1m_pct": _pct(last["close"], m1["close"] if m1 else None),
                      "spark": [r["close"] for r in rows[-30:]], "intraday": self._intraday(last["date"], market),
                      "status": self._bar_status(last["date"], res["status"], s, newest)}
        return {"items": out, "cache": {k: res[k] for k in ("status", "fetched_at", "error")}}

    # ---------------------------------------------------------------- screens
    def overview(self, market: str = "US") -> Dict[str, Any]:
        layout = OVERVIEW_KR if market == "KR" else OVERVIEW
        syms = [s for _, g in layout for s, _ in g]
        q = self._quotes(syms, "overview" if market == "US" else "overview:KR", market)
        groups = [{"title": t, "items": [{**q["items"][s], "name": n, "ticker": s.split(".")[0] if s.endswith(".KS") else s} for s, n in g]} for t, g in layout]
        return {"market": market, "groups": groups, "cache": q["cache"], "source": "Yahoo Finance (일봉 종가, 지연)",
                "basis": "최근 일봉 종가 대비 전일 종가. 실시간이 아니며, 장중에는 '장중·미확정'으로 표시되는 지연 가격입니다."}

    def chart(self, ticker: str, rng: str = "1y", live: str = "") -> Dict[str, Any]:
        """``live`` "1" (the stock screen, user request 2026-11-26): during an open session the last daily bar is brought up to
        the last one-minute bar, as the chart-analysis tab does (terminal/live_chart.py).  The age of that bar is in ``live_now``."""
        ticker = clean_ticker(ticker)
        period = {"3mo": "2y", "1y": "2y", "5y": "10y"}.get(rng)
        if not period:
            raise ValueError("INVALID_RANGE")
        market, sym = pf.market_of(ticker), self._sym(ticker)
        res = self.cache.cached(f"chart:{sym}:{period}", TTL["chart"],
                                lambda: self.src.yahoo_history([sym], period))
        rows = (res["data"] or {}).get(sym) or []
        if not rows:
            return {"ticker": ticker, "status": "UNAVAILABLE", "bars": [], "cache": res}
        now_live = None
        if live == "1":
            from terminal import live_chart
            if live_chart.open_now(market, self.now()):
                try:
                    v = self.intraday(ticker)
                    rows = live_chart.merge_daily(rows, v)
                    now_live = {k: v.get(k) for k in ("live", "note", "age_min", "session", "refresh_s")} | {"time": (v.get("last") or {}).get("time")}
                except Exception as exc:                 # the daily chart stands without it; the kind of failure is named
                    now_live = {"live": False, "note": f"1분봉을 받지 못해 일봉만 그렸습니다({type(exc).__name__}).", "refresh_s": live_chart.REFRESH_S}
        closes = [r["close"] for r in rows]
        sma = {n: _sma(closes, n) for n in (20, 50, 200)}
        keep = {"3mo": 63, "1y": 252, "5y": 1260}[rng]
        start = max(0, len(rows) - keep)
        bars = [{**r, "sma20": sma[20][i], "sma50": sma[50][i], "sma200": sma[200][i]}
                for i, r in enumerate(rows) if i >= start]
        last = rows[-1]
        hi52 = max(r["high"] or r["close"] for r in rows[-252:])
        lo52 = min(r["low"] or r["close"] for r in rows[-252:])
        return {"ticker": ticker, "market": market, "range": rng, "bars": bars,
                "status": self._bar_status(last["date"], res["status"], sym),
                "last": {"date": last["date"], "close": last["close"], "intraday": self._intraday(last["date"], market),
                         "change_pct": _pct(last["close"], rows[-2]["close"] if len(rows) > 1 else None),
                         "high_52w": hi52, "low_52w": lo52,
                         "vs_sma200_pct": _pct(last["close"], sma[200][-1])},
                "cache": {k: res[k] for k in ("status", "fetched_at", "error")}, "live_now": now_live,
                "source": "Yahoo Finance (분할 조정 일봉)" + (" · 오늘 일봉은 Yahoo 1분봉으로 이어 그림" if now_live and now_live.get("live") else "")}

    def price_on(self, ticker: str, day: str = "", market: str = "") -> Dict[str, Any]:
        """The close a trade form fills in (user request 2026-11-24): the last daily close on or before the form's date, from the
        same bars as the chart (Korean stocks rebuilt from the KRX copy).  A suggestion to overwrite, never a fill price."""
        from terminal import price_fill
        want = price_fill.parse_day(day)
        if market == "COIN":
            return self._coin_price_on(ticker, want)
        ticker = clean_ticker(ticker)
        mk, sym = pf.market_of(ticker), self._sym(ticker)
        res = self.cache.cached(f"chart:{sym}:2y", TTL["chart"], lambda: self.src.yahoo_history([sym], "2y"))
        rows, source = (res["data"] or {}).get(sym) or [], "Yahoo Finance 일봉 종가(분할 조정, 지연)"
        if mk == "KR":
            rows, source = self._kr_raw_rows(ticker, rows)
        today =self.now().astimezone(ZoneInfo("Asia/Seoul" if mk == "KR" else "America/New_York")).date()
        got = price_fill.pick(rows, want, today, symbol=sym, now=self.now())
        if res["status"] != "REAL" and got["status"] == "REAL":
            got["status"] = res["status"]
        return {"ticker": ticker, "market": mk, "asked": want.isoformat() if want else None, **got,
                "intraday": self._intraday(got["date"], mk), "currency": "KRW" if mk == "KR" else "USD", "source": source,
                "note": price_fill.SPLIT_NOTE if mk == "US" else None}

    def _kr_raw_rows(self, ticker: str, yahoo: List[Dict[str, Any]]) -> Any:
        """Korean closes as traded, from the KRX copy; days KRX has not published yet (today) come from Yahoo's quote."""
        from terminal import price_fill
        from terminal.qsf import kr_bars
        plain = "Yahoo Finance 일봉 종가(지연)"
        try:
            got = price_fill.kr_raw_closes(ticker, kr_bars.panel(self.base, self.now().date()), kr_bars.CLOSE)
        except Exception as exc:                       # a broken copy never stops the form; the line names the kind of failure only
            return yahoo, f"{plain} · 한국 거래소 일별 자료를 읽지 못함({type(exc).__name__})"
        if not got:
            return yahoo, f"{plain} · 한국 거래소 일별 자료에 없는 종목"
        last = got[-1]["date"]
        tail = [b for b in yahoo if b.get("close") and b["date"] > last]
        return got + tail, f"한국 거래소 종가(그날 실제 가격, {last}까지)" + (" · 그 뒤는 Yahoo 시세(지연)" if tail else "")

    def _coin_price_on(self, coin: str, want) -> Dict[str, Any]:
        """A coin's won price for the form: the Binance USDT close of the last four-hour bar of that Korean day, times the won rate
        of that day (the account's own method, so a form price and the account's price agree)."""
        from terminal import coin_bridge, coin_source, price_fill
        coin = str(coin or "").strip().upper()
        if not re.fullmatch(r"[A-Z0-9]{1,15}", coin):
            raise ValueError("INVALID_TICKER")
        base = {"ticker": coin, "market": "COIN", "asked": want.isoformat() if want else None, "currency": "KRW",
                "source": "바이낸스 USDT 4시간봉 종가 × 원/달러 환율(국내 거래소 가격과 몇 % 다를 수 있음)", "note": None, "intraday": False}
        try:
            doc = coin_source.load(self.base)
        except Exception as exc:                                   # the coin part never stops a form
            doc = {"error": type(exc).__name__}
        bars = (doc.get("arrays") or {}).get("bars") or {}
        sym = {coin_bridge.coin_of(s): s for s in bars}.get(coin)
        today = self.now().astimezone(ZoneInfo("Asia/Seoul")).date()
        got = price_fill.coin_close(bars.get(sym) if sym else None, coin_bridge.unit_of(sym) if sym else 1.0, coin_bridge.BAR_MS, want, today)
        if not got:
            return {**base, "status": "UNAVAILABLE", "close": None, "date": None, "reason": "NOT_COVERED" if not sym else "BEFORE_HISTORY"}
        fx = self.cache.cached("chart:KRW=X:2y", TTL["chart"], lambda: self.src.yahoo_history(["KRW=X"], "2y"))
        rate = price_fill.fx_on((fx["data"] or {}).get("KRW=X") or [], got["date"])
        if not rate:
            return {**base, "status": "UNAVAILABLE", "close": None, "date": got["date"], "reason": "NO_RATE"}
        ref = want or today
        old = (ref - datetime.strptime(got["date"], "%Y-%m-%d").date()).days > price_fill.STALE_DAYS or bool(doc.get("error"))
        return {**base, "status": "STALE" if old else "REAL", "close": got["usd"] * rate["close"], "date": got["date"], "at": got["at"],
                "exact": got["date"] == ref.isoformat(), "usd": got["usd"], "usdkrw": rate["close"], "fx_date": rate["date"]}

    COMPARE_INDEX = {"^GSPC": "S&P 500", "^IXIC": "나스닥 종합", "^KS11": "코스피", "^KQ11": "코스닥"}
    COMPARE_MAX = 8
    ROLLING_WINDOW, ROLLING_SHORT = 60, 20          # sessions in the moving correlation; the short one for a three-month view

    def intraday(self, ticker: str) -> Dict[str, Any]:
        """The open (or the last) session's one-minute bars for the chart screen (terminal/live_chart.py).  Reference only."""
        from terminal import live_chart
        ticker = clean_ticker(ticker)
        sym, market = self._chart_sym(ticker)
        res = self.cache.cached(f"intra:{sym}", TTL["intraday"], lambda: self.src.yahoo_intraday(sym))
        return {**live_chart.view(res["data"] or {}, market, self.now(), res), "ticker": ticker, "name": self.COMPARE_INDEX.get(ticker)}

    def _chart_sym(self, ticker: str) -> Tuple[str, str]:
        sym = ticker if ticker in self.COMPARE_INDEX else self._sym(ticker)
        market = "KR" if ticker in ("^KS11", "^KQ11") else "US" if ticker in self.COMPARE_INDEX else pf.market_of(ticker)
        return sym, market

    def chart_analysis(self, ticker: str, rng: str = "1y", ma: str = "", live: str = "") -> Dict[str, Any]:
        """The chart-analysis tab (CHART-1): classic indicators and signals on one stock or index.  Reference only, never a score.
        ``live`` "1": during an open session the last daily bar is brought up to the last one-minute bar (terminal/live_chart.py)."""
        ticker = clean_ticker(ticker)
        period, keep = chart_analysis.RANGES.get(rng, (None, None))
        if not period:
            raise ValueError("INVALID_RANGE")
        sym, market = self._chart_sym(ticker)
        periods = chart_analysis.ma_periods(ma, market)
        res = self.cache.cached(f"chart:{sym}:{period}", TTL["chart"], lambda: self.src.yahoo_history([sym], period))
        rows, source = (res["data"] or {}).get(sym) or [], "Yahoo Finance (분할 조정 일봉, 지연)"
        if market == "KR" and ticker not in self.COMPARE_INDEX and rows:
            rows, source = self._kr_chart_rows(ticker, rows, period)
        now_live = None
        if live == "1" and rows:
            from terminal import live_chart
            if live_chart.open_now(market, self.now()):
                try:
                    v = self.intraday(ticker)
                    rows = live_chart.merge_daily(rows, v)
                    now_live = {k: v.get(k) for k in ("live", "note", "age_min", "session", "refresh_s")} | {"time": (v.get("last") or {}).get("time")}
                except Exception as exc:                 # the daily chart stands without it; the kind of failure is named
                    now_live = {"live": False, "note": f"1분봉을 받지 못해 일봉만 그렸습니다({type(exc).__name__}).", "refresh_s": live_chart.REFRESH_S}
                if now_live.get("live"):
                    source += " · 오늘 일봉은 Yahoo 1분봉으로 이어 그림"
        out = chart_analysis.analyse(rows, market, keep, periods)
        bars = out["bars"]
        status = self._bar_status(bars[-1]["date"], res["status"], sym) if bars else "UNAVAILABLE"
        return {**out, "ticker": ticker, "name": self.COMPARE_INDEX.get(ticker), "market": market, "range": rng, "status": status,
                "intraday": self._intraday(bars[-1]["date"], market) if bars else None, "short_history": bool(bars) and len(bars) < keep,
                "settings": chart_analysis.settings(), "cache": {k: res.get(k) for k in ("status", "fetched_at", "error")}, "source": source,
                "live_now": now_live, "plan_lines": self._plan_lines(ticker, market)}

    def _plan_lines(self, ticker: str, market: str) -> Optional[Dict[str, Any]]:
        """The swing plan's levels of the newest recorded card, for the chart (UI audit item 4): stop, target and the zone the
        entry rule waits for or reads as met.  Read from the record, display only; None for an index or a stock not in the scan."""
        try:
            from terminal import assistant
            from terminal.qsf import ledger as ledger_mod
            session = self.qsf.screen_rows(market).get("session")
            snap = next((s for s in ledger_mod.session_snaps(self.qsf.ledger, market, session) if s.get("ticker") == ticker and s.get("strategy") == "SWING"), None) if session else None
            if not snap or not snap.get("stop"):
                return None
            zone = assistant.pullback_zone(snap) if snap.get("entry_status") == "WAIT_FOR_PULLBACK" else None
            return {"session": session, "stop": snap.get("stop"), "target": snap.get("target"), "zone": zone, "entry_status": snap.get("entry_status"),
                    "note": "스윙 카드의 계획 값입니다(손절 기준, 목표 기준, 눌림을 기다리는 구간). 시험하지 않은 규칙 값이고 주문이 아닙니다."}
        except Exception:
            return None

    def _kr_chart_rows(self, ticker: str, rows: List[Dict[str, Any]], period: str) -> Any:
        """A Korean stock's bars rebuilt from the KRX daily copy the score uses (QSF-1.1.8: Yahoo's Korean history has missing days and
        bad prints).  The copy holds about two years, so only the ranges fetched as two years use it; a longer range, a stock the copy
        does not list, or a copy that cannot be read keeps Yahoo's bars, and the source line says which."""
        yahoo = "Yahoo Finance (분할 조정 일봉, 지연)"
        if period != "2y":
            return rows, yahoo + " · 한국 거래소 일별 자료는 약 2년치뿐이라 3년 이상은 Yahoo 일봉입니다"
        from terminal.qsf import kr_bars
        try:
            rebuilt, info = kr_bars.rebuild(ticker, rows, kr_bars.panel(self.base, self.now().date()))
        except Exception as exc:                       # a broken copy never stops the chart; the line names the kind of failure only
            return rows, f"{yahoo} · 한국 거래소 일별 자료를 읽지 못함({type(exc).__name__})"
        if not str(info.get("source", "")).startswith("KRX"):
            return rows, f"{yahoo} · {info.get('reason') or '한국 거래소 일별 자료 없음'}"
        tail = f", 그 뒤 {info['tail_days']}일은 Yahoo로 이음" if info.get("tail_days") else ""
        return rebuilt, f"한국 거래소 일별 시세로 다시 만든 일봉(점수와 같은 자료, {info.get('krx_last')}까지{tail})"

    def compare(self, tickers: str, rng: str = "1y") -> Dict[str, Any]:
        """Several stocks and indices from one common start, as total return (dividend-adjusted closes) in each one's own currency.
        Days are those all of them traded; a stock without prices is listed as missing, never drawn as flat."""
        period, keep = {"3mo": ("2y", 63), "1y": ("2y", 252), "5y": ("10y", 1260)}.get(rng, (None, None))
        if not period:
            raise ValueError("INVALID_RANGE")
        names = []
        for raw in (tickers or "").split(","):
            t = raw.strip().upper()
            if not t:
                continue
            t = clean_ticker(t)
            if t not in names:
                names.append(t)
        if not names:
            raise ValueError("INVALID_TICKER")
        names = names[:self.COMPARE_MAX]
        series, missing, fetched = {}, [], []
        for t in names:
            sym = t if t in self.COMPARE_INDEX else self._sym(t)
            res = self.cache.cached(f"chart:{sym}:{period}", TTL["chart"], lambda sym=sym: self.src.yahoo_history([sym], period))
            rows = [r for r in ((res["data"] or {}).get(sym) or []) if isinstance(r.get("adj_close") or r.get("close"), (int, float))]
            if len(rows) < 2:
                missing.append(t)
                continue
            series[t] = {r["date"]: (r.get("adj_close") or r["close"]) for r in rows[-keep - 1:]}
            fetched.append(res.get("fetched_at"))
        if not series:
            return {"status": "UNAVAILABLE", "range": rng, "series": [], "missing": missing}
        common = sorted(set.intersection(*[set(v) for v in series.values()]))
        if len(common) < 2:
            return {"status": "UNAVAILABLE", "range": rng, "series": [], "missing": missing, "reason": "NO_COMMON_DAYS"}
        out = []
        for t, m in series.items():
            vals = [m[d] for d in common]
            peak, mdd = vals[0], 0.0
            for v in vals:
                peak = max(peak, v)
                mdd = min(mdd, v / peak - 1)
            rets = [vals[i] / vals[i - 1] - 1 for i in range(1, len(vals))]
            mean = sum(rets) / len(rets)
            vol = math.sqrt(sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)) * math.sqrt(252) if len(rets) > 1 else None
            out.append({"ticker": t, "name": self.COMPARE_INDEX.get(t), "market": "KR" if t in ("^KS11", "^KQ11") else ("US" if t in self.COMPARE_INDEX else pf.market_of(t)),
                        "points": [v / vals[0] - 1 for v in vals], "total_return": vals[-1] / vals[0] - 1, "volatility": vol, "max_drawdown": mdd, "_rets": rets})
        corr = []
        for a in out:
            row = []
            for b in out:
                x, y = a["_rets"], b["_rets"]
                mx, my = sum(x) / len(x), sum(y) / len(y)
                sxy = sum((p - mx) * (q - my) for p, q in zip(x, y))
                sx, sy = math.sqrt(sum((p - mx) ** 2 for p in x)), math.sqrt(sum((q - my) ** 2 for q in y))
                row.append(sxy / (sx * sy) if sx and sy else None)
            corr.append(row)
        window = self.ROLLING_WINDOW if len(common) - 1 >= 2 * self.ROLLING_WINDOW else self.ROLLING_SHORT
        rolling = [{"ticker": o["ticker"], "points": _rolling_corr(out[0]["_rets"], o["_rets"], window)} for o in out[1:]] if len(common) - 1 > window else []
        for o in out:
            o.pop("_rets")
        mixed = len({o["market"] for o in out}) > 1
        return {"status": "REAL", "range": rng, "dates": common, "series": out, "correlation": corr, "missing": missing, "mixed_markets": mixed,
                "rolling": rolling, "rolling_window": window, "rolling_base": out[0]["ticker"],
                "fetched_at": min((f for f in fetched if f), default=None), "source": "Yahoo Finance 일봉 (배당 조정 종가, 지연)",
                "basis": "모두가 거래한 날만 씁니다. 수익률은 각 종목의 통화 기준이며 환율은 반영하지 않습니다."}

    ROTATION = {
        "US": ("SPY", "S&P 500 (SPY)", [("XLK", "기술"), ("XLF", "금융"), ("XLV", "헬스케어"), ("XLY", "경기소비재"), ("XLP", "필수소비재"), ("XLI", "산업재"),
                                       ("XLB", "소재"), ("XLE", "에너지"), ("XLU", "유틸리티"), ("XLRE", "부동산"), ("XLC", "커뮤니케이션")]),
        "KR": ("^KS11", "코스피", [("091160.KS", "반도체"), ("091170.KS", "은행"), ("102970.KS", "증권"), ("091180.KS", "자동차"), ("117460.KS", "에너지화학"),
                                  ("117680.KS", "철강"), ("117700.KS", "건설"), ("102960.KS", "기계장비"), ("266420.KS", "헬스케어"), ("266390.KS", "경기소비재"),
                                  ("266410.KS", "필수소비재"), ("140710.KS", "운송"), ("305720.KS", "2차전지"), ("140700.KS", "보험"),
                                  ("494670.KS", "조선"), ("315270.KS", "커뮤니케이션")]),
    }
    RRG_WINDOW, RRG_MOM, RRG_TAIL = 10, 5, 8

    def rotation(self, market: str = "US") -> Dict[str, Any]:
        """Sector funds against the market on weekly closes, as relative strength and its momentum (a public approximation of the
        relative rotation graph, not the licensed JdK formula).  ratio = 100 x (fund/market) / its 10-week mean;
        momentum = 100 x ratio / its 5-week mean.  Above 100 on both is leading.  A fund without prices is listed as missing."""
        bench, bench_name, funds = self.ROTATION[market]
        syms = [bench] + [f for f, _ in funds]
        res = self.cache.cached(f"rotation:{market}:2y", TTL["chart"], lambda: self.src.yahoo_history(syms, "2y"))
        data = res["data"] or {}

        def weekly(rows):
            out = {}
            for r in rows or []:
                v = r.get("adj_close") or r.get("close")
                if isinstance(v, (int, float)) and v > 0:
                    y, w, _ = datetime.strptime(r["date"], "%Y-%m-%d").isocalendar()
                    out[(y, w)] = (r["date"], v)          # the last session of each week wins
            return out
        bw = weekly(data.get(bench))
        if len(bw) < self.RRG_WINDOW + self.RRG_MOM + self.RRG_TAIL:
            return {"status": "UNAVAILABLE", "market": market, "funds": [], "reason": "NO_BENCHMARK"}
        items, missing = [], []
        for sym, name in funds:
            fw = weekly(data.get(sym))
            weeks = sorted(set(fw) & set(bw))
            if len(weeks) < self.RRG_WINDOW + self.RRG_MOM + self.RRG_TAIL:
                missing.append(name)
                continue
            rs = [fw[k][1] / bw[k][1] for k in weeks]
            ratio = [None] * len(rs)
            for i in range(self.RRG_WINDOW - 1, len(rs)):
                ratio[i] = 100 * rs[i] / (sum(rs[i - self.RRG_WINDOW + 1:i + 1]) / self.RRG_WINDOW)
            pts = []
            for i in range(len(rs)):
                win = ratio[max(0, i - self.RRG_MOM + 1):i + 1]
                if ratio[i] is None or len(win) < self.RRG_MOM or any(v is None for v in win):
                    continue
                pts.append({"date": fw[weeks[i]][0], "ratio": ratio[i], "momentum": 100 * ratio[i] / (sum(win) / self.RRG_MOM)})
            tail = pts[-self.RRG_TAIL:]
            last = tail[-1]
            quad = ("LEADING" if last["momentum"] >= 100 else "WEAKENING") if last["ratio"] >= 100 else ("IMPROVING" if last["momentum"] >= 100 else "LAGGING")
            rel = {k: (rs[-1] / rs[-1 - n] - 1 if len(rs) > n else None) for k, n in (("4w", 4), ("13w", 13))}
            items.append({"symbol": sym, "name": name, "tail": tail, "quadrant": quad, "relative": rel})
        return {"status": "REAL" if items else "UNAVAILABLE", "market": market, "benchmark": bench_name, "funds": items, "missing": missing,
                "as_of": max((i["tail"][-1]["date"] for i in items), default=None), "fetched_at": res.get("fetched_at"),
                "source": "Yahoo Finance 일봉 (배당 조정 종가, 지연) · 미국 SPDR 업종 ETF / 한국 KODEX 업종 ETF(조선·커뮤니케이션은 TIGER)",
                "method": f"주간 종가. 상대강도 비율 = 100 × (ETF/지수) ÷ 최근 {self.RRG_WINDOW}주 평균, 모멘텀 = 100 × 비율 ÷ 최근 {self.RRG_MOM}주 평균. 공개된 근사식이며 RRG 원 공식과 다릅니다."}

    def _kr_fundamentals(self, c: Dict[str, Any]) -> Dict[str, Any]:
        if not c.get("annual"):
            return {"status": "UNAVAILABLE", "reason": c.get("reason") or "DART 재무 데이터가 없습니다."}
        bases = c["annual"].get("_bases") or []
        rows, years = [], set()
        for key, label, unit in (("revenue", "매출", "KRW"), ("op_income", "영업이익", "KRW"), ("net_income", "순이익", "KRW"), ("eps", "기본 EPS", "KRW/shares"),
                                 ("ocf", "영업현금흐름", "KRW"), ("assets", "총자산", "KRW"), ("liabilities", "총부채", "KRW"), ("equity", "자본총계(지배)", "KRW"), ("cash", "현금성자산", "KRW")):
            vals = {r["end"]: r["val"] for r in c["annual"].get(key) or []}
            years |= set(vals)
            rows.append({"key": key, "label": label, "unit": unit, "values": vals})
        return {"status": c["annual_status"], "years": sorted(years)[-5:], "rows": rows, "fetched_at": c["annual_fetched"], "source": "OpenDART 사업보고서 (열 = 회계연도 종료일)",
                "note": "재무제표 기준: " + (" → ".join("연결" if b == "CONSOLIDATED" else "별도" for b in bases) or "확인 불가") + ". 표시용 요약입니다."}

    @staticmethod
    def _dividend_check(data: Dict[str, Any]) -> Dict[str, Any]:
        """Marks a dividend yield the investment committee rejects as a wrong Yahoo record (above its limit), so the stock page does not
        show it as a fact.  Same limit as the committee; the value itself is passed on unchanged and never used here."""
        from terminal.committee.figures import MAX_DIVIDEND_YIELD
        dy = data.get("dividendYield")
        if isinstance(dy, (int, float)) and not 0 <= dy <= MAX_DIVIDEND_YIELD:
            return {**data, "dividendYieldSuspect": True, "dividendYieldLimit": MAX_DIVIDEND_YIELD}
        return data

    def company(self, ticker: str) -> Dict[str, Any]:
        ticker = clean_ticker(ticker)
        market, sym = pf.market_of(ticker), self._sym(ticker)
        info = self.cache.cached(f"info:{sym}", TTL["info"], lambda: self.src.yahoo_info(sym))
        if market == "KR":
            c = self.qsf.kr_company(ticker)
            ident = c.get("ident") or {}
            data = {**(info["data"] or {}), "longName": ident.get("company_name") or (info["data"] or {}).get("longName"), "exchange": ident.get("market") or (info["data"] or {}).get("exchange")}
            return {"ticker": ticker, "market": "KR", "profile": {"status": info["status"], "data": self._dividend_check(data), "source": "Yahoo Finance quote summary, KRX 상장 목록", "fetched_at": info["fetched_at"]},
                    "fundamentals": self._kr_fundamentals(c)}
        out = {"ticker": ticker, "market": "US", "profile": {"status": info["status"], "data": self._dividend_check(info["data"] or {}),
                                             "source": "Yahoo Finance quote summary", "fetched_at": info["fetched_at"]}}
        out["fundamentals"] = self._fundamentals(ticker)
        return out

    def _cik(self, ticker: str) -> Optional[str]:
        try:
            return self.src.sec_cik(ticker)
        except Exception:
            return None

    def _fundamentals(self, ticker: str) -> Dict[str, Any]:
        cik = self._cik(ticker)
        if not cik:
            return {"status": "UNAVAILABLE", "reason": "SEC CIK를 찾을 수 없습니다 (미국 상장 기업이 아니거나 ETF/지수)."}
        res = self.cache.cached(f"facts:{sources.facts_key(ticker, cik)}", TTL["facts"], lambda: sources.facts_with_predecessors(ticker, cik, self.src.sec_companyfacts))
        if res["data"] is None:
            reason = ("SEC_USER_AGENT가 설정되지 않아 SEC를 조회하지 않았습니다." if res["error"] == "SecNotConfigured"
                      else f"SEC 조회 실패 ({res['error']})")
            return {"status": "UNAVAILABLE", "reason": reason, "cik": cik}
        table = annual_table(res["data"])
        return {"status": res["status"], "cik": cik, "fetched_at": res["fetched_at"], **table,
                "source": "SEC EDGAR companyfacts (10-K 회계연도, 열 = 회계연도 종료일)",
                "note": "표시용 재무 요약입니다. P6-11B 모델 입력(P6-20-A 규칙)과 별개입니다."}

    def filings(self, ticker: str, limit: int = 20) -> Dict[str, Any]:
        ticker = clean_ticker(ticker)
        if pf.market_of(ticker) == "KR":
            c = self.qsf.kr_company(ticker)
            if c.get("reports") is None:
                return {"status": "UNAVAILABLE", "market": "KR", "reason": c.get("reason") or "DART 공시를 불러오지 못했습니다.", "items": []}
            items = [{"form": r.get("report_nm", "").strip(), "filing_date": f"{r['rcept_dt'][:4]}-{r['rcept_dt'][4:6]}-{r['rcept_dt'][6:8]}" if r.get("rcept_dt") else None,
                      "description": r.get("flr_nm"), "url": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={r['rcept_no']}" if r.get("rcept_no") else None} for r in c["reports"][:limit]]
            return {"status": c["reports_status"], "market": "KR", "items": items, "fetched_at": c["reports_fetched"], "source": "OpenDART 공시 목록"}
        cik = self._cik(ticker)
        if not cik:
            return {"status": "UNAVAILABLE", "reason": "SEC CIK를 찾을 수 없습니다.", "items": []}
        res = self.cache.cached(f"subm:{cik}", TTL["filings"], lambda: self.src.sec_submissions(cik))
        if res["data"] is None:
            return {"status": "UNAVAILABLE", "items": [], "reason": (
                "SEC_USER_AGENT가 설정되지 않아 SEC를 조회하지 않았습니다." if res["error"] == "SecNotConfigured"
                else f"SEC 조회 실패 ({res['error']})")}
        rec = (res["data"].get("filings") or {}).get("recent") or {}
        def col(name, i):
            v = rec.get(name) or []
            return (v[i] or None) if i < len(v) else None

        items = []
        for i in range(min(limit, len(rec.get("accessionNumber") or []))):
            acc, doc = rec["accessionNumber"][i], col("primaryDocument", i)
            items.append({"form": col("form", i), "filing_date": col("filingDate", i),
                          "accepted": col("acceptanceDateTime", i), "description": col("primaryDocDescription", i),
                          "url": sources.SEC_ARCHIVE.format(cik=int(cik), acc=acc.replace("-", ""), doc=doc)
                          if doc else None})
        return {"status": res["status"], "cik": cik, "company": res["data"].get("name"), "items": items,
                "fetched_at": res["fetched_at"], "source": "SEC EDGAR submissions"}

    def _macro_kr(self) -> Dict[str, Any]:
        configured = sources.ecos_status() == "CONFIGURED"
        start, end, out = self.now() - timedelta(days=365 * 6 + 30), self.now(), []
        for sid, label, unit, kind, (stat, cycle, items) in MACRO_KR:
            fmt = "%Y%m%d" if cycle == "D" else "%Y%m"
            res = {"data": None, "status": "UNAVAILABLE", "fetched_at": None}
            if configured:
                res = self.cache.cached(f"ecos:{sid}", TTL["macro"], lambda st=stat, c=cycle, it=items, f=fmt: self.src.ecos_series(st, c, start.strftime(f), end.strftime(f), it))
            out.append(self._macro_item(sid, label, unit, kind, res))
        by = {m["id"]: dict(map(tuple, m["series"])) for m in out}
        days = sorted(set(by["KTB10Y"]) & set(by["KTB3Y"]))
        status = next((m["status"] for m in out if m["id"] == "KTB10Y"), "UNAVAILABLE")
        out.insert(3, self._macro_item("KTB10Y-3Y", "장단기 금리차 (10년−3년)", "%p", "level",
                                       {"data": [[d, by["KTB10Y"][d] - by["KTB3Y"][d]] for d in days], "status": status, "fetched_at": out[2]["fetched_at"]}))
        fx = self.cache.cached("chart:KRW=X:2y", TTL["chart"], lambda: self.src.yahoo_history(["KRW=X"], "2y"))
        rows = (fx["data"] or {}).get("KRW=X") or []
        out.append(self._macro_item("KRW=X", "원/달러 환율", "원", "level",
                                    {"data": [[r["date"], r["close"]] for r in rows], "status": fx["status"], "fetched_at": fx["fetched_at"]}))
        return {"market": "KR", "items": out, "configured": configured,
                "reason": None if configured else "ECOS_API_KEY가 없습니다. https://ecos.bok.or.kr/api/ 에서 무료로 발급받아 .env에 넣으세요.",
                "source": "한국은행 경제통계시스템(ECOS)"}

    def _macro_item(self, sid: str, label: str, unit: str, kind: str, res: Dict[str, Any]) -> Dict[str, Any]:
        pts = [p for p in (res["data"] or []) if p[1] is not None]
        if kind == "yoy":
            by = {p[0]: p[1] for p in pts}
            pts = [[d, (v / by[f"{int(d[:4]) - 1}{d[4:]}"] - 1) * 100] for d, v in pts
                   if f"{int(d[:4]) - 1}{d[4:]}" in by]
        item = {"id": sid, "label": label, "unit": unit, "status": res["status"], "fetched_at": res["fetched_at"]}
        if pts:
            item.update(date=pts[-1][0], value=pts[-1][1], previous=pts[-2][1] if len(pts) > 1 else None,
                        value_1y_ago=next((v for d, v in reversed(pts) if d <= _minus_year(pts[-1][0])), None),
                        series=pts[-260:])
        else:
            item.update(status="UNAVAILABLE", value=None, series=[])
        return item

    def macro(self, market: str = "US") -> Dict[str, Any]:
        if market == "KR":
            return self._macro_kr()
        start = (self.now() - timedelta(days=365 * 5 + 30)).strftime("%Y-%m-%d")
        out = []
        for sid, label, unit, kind in MACRO:
            res = self.cache.cached(f"fred:{sid}", TTL["macro"], lambda s=sid: self.src.fred_series(s, start))
            out.append(self._macro_item(sid, label, unit, kind, res))
        return {"items": out, "source": "FRED, Federal Reserve Bank of St. Louis (개인·비상업적 이용, 출처 표시)"}

    # ---------------------------------------------------------------- watchlist
    # ---------------------------------------------------------------- alert rules (TERMINAL alert center)
    @property
    def alert_store(self) -> "alert_rules.Store":
        return alert_rules.Store(self.base / "data" / "terminal")

    def alerts_view(self) -> Dict[str, Any]:
        rules = self.alert_store.rules()
        return {"rules": [{**r, "name": alert_rules.describe(r)} for r in rules], "log": self.alert_store.log(),
                "types": alert_rules.TYPES, "basis": "하루 한 번 자동 실행 때 일봉 종가로 확인해 텔레그램·맥 알림으로 보냅니다. 실시간 알림이 아니며 주문은 실행하지 않습니다."}

    def alert_add(self, body: Dict[str, Any]) -> Dict[str, Any]:
        body = dict(body or {})
        if body.get("ticker"):
            body["ticker"] = clean_ticker(body["ticker"])
        rule = self.alert_store.add(alert_rules.validate(body, pf.market_of))
        return {"rule": {**rule, "name": alert_rules.describe(rule)}}

    def alert_remove(self, rule_id: str) -> Dict[str, Any]:
        return {"removed": self.alert_store.remove(str(rule_id or ""))}

    def alert_rearm(self, rule_id: str) -> Dict[str, Any]:
        return {"rearmed": self.alert_store.rearm(str(rule_id or ""))}

    def _final_bars(self, tickers: List[str], market: str) -> Dict[str, Dict[str, Any]]:
        """Last FINAL daily close per ticker (a delayed intraday bar is dropped), with the close before it.  Old bars are left out."""
        if not tickers:
            return {}
        sym = {t: self._sym(t) for t in tickers}
        res = self.cache.cached("alertbars:" + ",".join(sorted(sym.values())), TTL["quote"], lambda: self.src.yahoo_history(sorted(set(sym.values())), "3mo"))
        data, out = res["data"] or {}, {}
        for t, s in sym.items():
            rows = [r for r in data.get(s) or [] if isinstance(r.get("close"), (int, float)) and math.isfinite(r["close"])]
            if rows and self._intraday(rows[-1]["date"], market):
                rows = rows[:-1]
            if not rows or self._bar_status(rows[-1]["date"], "REAL", s) != "REAL":        # a price that stopped is not judged
                continue
            out[t] = {"date": rows[-1]["date"], "close": rows[-1]["close"], "prev_close": rows[-2]["close"] if len(rows) > 1 else None}
        return out

    def alert_check(self) -> Dict[str, Any]:
        """Evaluate every active rule now.  Nothing is stored or sent: the daily run does that once the message is delivered."""
        rules = [r for r in self.alert_store.rules() if r.get("status") == "ACTIVE"]
        markets = sorted({r["market"] for r in rules})
        watched: Dict[str, List[str]] = {}
        for m in markets:
            held = [h["ticker"] for h in self.portfolio(m).get("holdings") or []]
            watched[m] = list(dict.fromkeys(held + [t for t in self.watchlist() if pf.market_of(t) == m]))
        def who(r):
            return [r["ticker"]] if r["ticker"] else watched.get(r["market"], [])
        bars: Dict[str, Any] = {}
        for m in markets:
            need = sorted({t for r in rules if r["market"] == m and r["type"] in ("PRICE_ABOVE", "PRICE_BELOW", "MOVE") for t in who(r)})
            bars.update(self._final_bars(need, m))
        bands = {}
        for m in markets:
            if any(r["market"] == m and r["type"] == "BAND_CHANGE" for r in rules):
                latest = self.qsf.latest(m)
                by = {}
                for row in latest.get("rows") or []:
                    by.setdefault(row.get("ticker"), {})[row.get("strategy")] = {k: row.get(k) for k in ("band", "band_label", "score")}
                bands[m] = {"session": latest.get("session"), "by_ticker": by}
        earnings = {}
        for t in sorted({t for r in rules if r["type"] == "EARNINGS_SOON" for t in who(r)}):
            rec = self.qsf.cache.read(f"earn:{self._sym(t)}")          # what the scan already fetched; nothing is downloaded here
            if rec and isinstance(rec.get("data"), list):
                earnings[t] = rec["data"]
        today = self.now().astimezone(ZoneInfo("Asia/Seoul")).date().isoformat()
        alerts, state, notes = alert_rules.evaluate(rules, {"bars": bars, "watched": watched, "bands": bands, "earnings": earnings, "today": today})
        return {"alerts": alerts, "state": state, "notes": notes, "checked_at": self.now().isoformat(timespec="seconds"), "rules": len(rules)}

    def econ_calendar(self, market: str = "US", days: int = 60) -> Dict[str, Any]:
        """Official policy and data release dates (both countries), with the stored earnings dates of holdings and watchlist."""
        from terminal import econ_calendar
        out = econ_calendar.upcoming(self.now().astimezone(ZoneInfo("Asia/Seoul")).date(), days)
        try:
            e = self.qsf.earnings_upcoming(market, days)
            out["earnings"] = [i for i in e.get("items") or [] if i.get("held") or i.get("watched")]
            out["earnings_status"] = e.get("status")
        except Exception as exc:
            out["earnings"], out["earnings_status"] = [], f"UNAVAILABLE ({type(exc).__name__})"
        try:                    # ex-dividend dates of holdings and watchlist, from the stored Yahoo records (reference, not official)
            out["dividends"] = self.qsf.dividends_upcoming(market, days).get("items") or []
        except Exception:
            out["dividends"] = []
        return out

    def sector_picks(self, market: str, fund: str) -> Dict[str, Any]:
        """Top scores inside one rotation fund.  Korean funds use the stored KODEX holdings when a snapshot exists."""
        from terminal import kr_etf_holdings
        from terminal.qsf import sector_picks
        held, stale = None, False
        if market == "KR":
            held = kr_etf_holdings.members(self.base, sector_picks.fund_code(fund))
            stale = kr_etf_holdings.status(self.base, self.now().date()).get("status") == "STALE"
        return sector_picks.picks(self.qsf.screen_rows(market), market, fund, held, stale)

    def watchlist(self) -> List[str]:
        try:
            return json.loads(self.watchlist_file.read_text(encoding="utf-8"))["tickers"]
        except (OSError, ValueError, KeyError):
            return ["AAPL", "MSFT", "NVDA", "SPY"]

    def _save_watchlist(self, tickers: List[str]) -> None:
        self.watchlist_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.watchlist_file.with_suffix(".tmp")
        tmp.write_text(json.dumps({"tickers": tickers, "updated_at": self.now().isoformat()}), encoding="utf-8")
        tmp.replace(self.watchlist_file)

    def watchlist_add(self, ticker: str) -> List[str]:
        t, w = clean_ticker(ticker), self.watchlist()
        if t not in w:
            if len(w) >= 100:
                raise ValueError("WATCHLIST_FULL")
            w.append(t)
            self._save_watchlist(w)
        return w

    def watchlist_remove(self, ticker: str) -> List[str]:
        t = clean_ticker(ticker)
        w = [x for x in self.watchlist() if x != t]
        self._save_watchlist(w)
        return w

    def watchlist_quotes(self, market: str = "US") -> Dict[str, Any]:
        w = [t for t in self.watchlist() if pf.market_of(t) == market]
        if not w:
            return {"items": [], "tickers": []}
        sym = {t: self._sym(t) for t in w}
        q = self._quotes(list(sym.values()), "watch:" + ",".join(sorted(sym.values())), market)
        scan = self._scan_scores(market)
        return {"tickers": w, "items": [{**q["items"][sym[t]], "symbol": t, "name": self._kr_name(t), "qsf": scan["by_ticker"].get(t)} for t in w], "cache": q["cache"],
                "source": "Yahoo Finance (일봉 종가, 지연)", "qsf_scan": {k: scan[k] for k in ("status", "session", "model_version")}}


    def _today_et(self):
        return self.now().astimezone(ZoneInfo("America/New_York")).date()

    def _today(self, market: str):
        return self.now().astimezone(ZoneInfo("Asia/Seoul")).date() if market in ("KR", "COIN") else self._today_et()

    def journal_add(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        raw = raw or {}
        asked = str(raw.get("market") or "").upper()
        # a coin entry says so itself (BTC, SOL and LINK are not told apart from stock tickers by their look)
        market = "COIN" if asked == "COIN" else pf.market_of(str(raw.get("ticker") or "").strip().upper()) if raw.get("ticker") else asked or "US"
        entry = pf.normalize(raw, self._today(market), clean_ticker)
        return {"entry": self.journal.append(entry, self.now())}

    # ---------------------------------------------------------------- paper trades kept by hand (terminal/paper_trade.py)
    def paper_trades(self, market: str = "US") -> Dict[str, Any]:
        from terminal import paper_trade
        recs, integ = self.paper.read()

        def quote(held: List[str]) -> Dict[str, Dict[str, Any]]:
            sym = {t: self._sym(t) for t in held}
            q = self._quotes(list(sym.values()), "paper:" + ",".join(sym.values()), market)
            return {t: q["items"][sym[t]] for t in held}
        return paper_trade.view(recs, integ, market, quote, self._kr_name, self._today(market))

    def paper_add(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        from terminal import paper_trade
        raw = raw or {}
        market = pf.market_of(str(raw.get("ticker") or "").strip().upper()) if raw.get("ticker") else str(raw.get("market") or "US").upper()
        return {"entry": self.paper.append(paper_trade.prepare(raw, self._today(market if market in pf.STOCK_MARKETS else "US"), clean_ticker), self.now())}

    def paper_void(self, ref: str) -> Dict[str, Any]:
        return {"entry": self.paper.append({"kind": "VOID", "ref": str(ref or "")}, self.now())}

    def paper_fee(self, q: Dict[str, Any]) -> Dict[str, Any]:
        """The fee a buy or sell of this size would get, for the form's preview.  Nothing is recorded."""
        from terminal import paper_trade
        side = str(q.get("side") or "BUY").upper()
        market = str(q.get("market") or "US").upper()
        if side not in ("BUY", "SELL") or market not in pf.STOCK_MARKETS:
            raise ValueError("매수 또는 매도, 시장은 US 또는 KR이어야 합니다.")
        value = pf._pos(q.get("qty"), "수량") * pf._pos(q.get("price"), "가격")
        return {"market": market, "side": side, "value": value, **paper_trade.toss_fee(market, value, side)}

    def portfolio_signals(self, market: str = "US") -> Dict[str, Any]:
        """QSF reading of each holding, kept apart from /api/portfolio because the first run reads filings."""
        _, integ, _, val, _, _ = self._valued(market)
        st, items = self.settings(), []
        for h in val["holdings"]:
            try:
                items.append(self.qsf.signal(h["ticker"], h["weight_pct"], pf.limits_for(h["style"], st, market)["max_position_pct"], market))
            except Exception as exc:              # one unreadable stock never hides the others
                items.append({"status": "UNAVAILABLE", "ticker": h["ticker"], "reason": type(exc).__name__})
        return {"status": integ["status"], "items": items, "note": _validation_note()}

    def journal_void(self, ref: str) -> Dict[str, Any]:
        return {"entry": self.journal.append({"kind": "VOID", "ref": str(ref or "")}, self.now())}

    def _sector(self, ticker: str) -> Optional[str]:
        """A holding's sector for the sector limit.  Korean stocks use the exchange industry's broad sector (the same one the
        screens show); a code missing from the master has none, it is never filled from Yahoo."""
        if pf.market_of(ticker) == "KR":
            try:
                return self.qsf.kr_sector(ticker).get("sector")
            except Exception:
                return None
        sym = self._sym(ticker)
        res = self.cache.cached(f"info:{sym}", TTL["info"], lambda: self.src.yahoo_info(sym))
        return (res["data"] or {}).get("sector")

    def _book(self, market: str = "US"):
        all_recs, integ = self.journal.read()
        recs = pf.for_market(all_recs, market)
        try:
            state = pf.replay(recs)
        except pf.JournalError as exc:
            integ, state = {"status": "BROKEN", "reason": str(exc)}, pf.replay([])
        return recs, integ, state

    def _coin_quotes(self, coins: List[str]) -> Dict[str, Any]:
        """A won price per coin: the Binance USDT close of the last four-hour bar times the day's won per dollar.  It is not a
        Korean exchange's price (those run a few per cent apart), and only the thirty most traded coins have one."""
        from terminal import coin_bridge, coin_source
        fx = (self._quotes(["KRW=X"], "pf:fx", "US")["items"].get("KRW=X") or {})
        try:
            # Coins on file: ask for the newest bars.  None: read what is stored and ask nobody (the account page of a user
            # without coins asked Binance some sixty times inside the request, assessment 2026-11-23).
            doc = coin_source.load(self.base) if coins else coin_source.stored(self.base)
        except Exception as exc:                                   # the coin part never stops the stock accounts
            doc = {"error": type(exc).__name__}
        bars = (doc.get("arrays") or {}).get("bars") or {}
        by = {coin_bridge.coin_of(s): s for s in bars}
        rate, out = fx.get("close"), {}
        for c in coins:
            s = by.get(c)
            rows = bars.get(s) if s else None
            if rows is None or not len(rows) or not rate:
                out[c] = {"close": None, "status": "UNAVAILABLE", "reason": "NO_RATE" if s and not rate else "NOT_COVERED"}
                continue
            unit = coin_bridge.unit_of(s)
            usd = float(rows[-1, 4]) / unit
            if not math.isfinite(usd) or usd <= 0:                 # a value that is not a price is no price
                out[c] = {"close": None, "status": "UNAVAILABLE", "reason": "BAD_VALUE"}
                continue
            day = float(rows[-7, 4]) / unit if len(rows) >= 7 and math.isfinite(float(rows[-7, 4])) and float(rows[-7, 4]) > 0 else None          # six four-hour bars back: a day
            when = datetime.fromtimestamp((float(rows[-1, 0]) + coin_bridge.BAR_MS) / 1000, tz=timezone.utc)
            out[c] = {"close": usd * rate, "usd": usd, "date": when.astimezone(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d"), "status": "STALE" if doc.get("error") else "REAL",
                      "change_pct": (usd / day - 1) * 100 if day else None}
        return {"items": out, "fx": fx, "covered": sorted(by), "names": {c: coin_bridge.NAMES_KO.get(c) for c in by}, "error": doc.get("error")}

    def _valued(self, market: str = "US", coin_got: Optional[Dict[str, Any]] = None):
        recs, integ, state = self._book(market)
        held = sorted(state["positions"])
        if market == "COIN":
            got = coin_got or self._coin_quotes(held)
            val = pf.valuation(state, got["items"], {t: None for t in held}, self.settings(), market)
            val["alerts"], val["sectors"] = [], {}                 # no limit of this program is defined for coins
            for h in val["holdings"]:
                h["name"] = got["names"].get(h["ticker"])
                h["usd"] = (got["items"].get(h["ticker"]) or {}).get("usd")
            return recs, integ, state, val, got["fx"], None
        sym = {t: self._sym(t) for t in held}
        q = self._quotes(list(sym.values()) + ["KRW=X"], "pf:" + ",".join(sym.values()), market)
        quotes = {t: q["items"][sym[t]] for t in held}
        fx = q["items"].get("KRW=X") or {}
        val = pf.valuation(state, quotes, {t: self._sector(t) for t in held}, self.settings(), market)
        for h in val["holdings"]:
            h["name"] = self._kr_name(h["ticker"])
        return recs, integ, state, val, fx, q["cache"]

    def _total(self, market: str, val: Dict[str, Any], fx: Dict[str, Any]) -> Dict[str, Any]:
        """Both accounts in won.  A missing price or rate leaves the total empty rather than understated."""
        other = "KR" if market == "US" else "US"
        eq = {market: val["summary"]["equity"], other: self._valued(other)[3]["summary"]["equity"]}
        rate = fx.get("close")
        us = to_krw(eq["US"], "USD", rate)
        total = eq["KR"] + us if None not in (eq["KR"], us) else None
        return {"krw": total, "us_equity": eq["US"], "kr_equity": eq["KR"], "usdkrw": rate, "fx_date": fx.get("date"), "us_krw": us}

    ACCOUNTS = (("US", "미국 주식", "USD"), ("KR", "한국 주식", "KRW"), ("COIN", "코인", "KRW"))

    def account(self) -> Dict[str, Any]:
        """The three accounts on one page (user request 2026-11-23).  Each keeps its own currency, cash and limits; this view adds
        them up in won (and in dollars) at the day's rate.  A missing price or rate leaves a total empty rather than understated."""
        all_recs, integ = self.journal.read()
        gone = pf.voided_ids(all_recs)
        parts, rows, rate, fx_date = [], [], None, None
        keys = ("equity", "equity_known", "cash", "market_value", "market_value_known", "complete", "missing_prices", "unrealized", "realized", "day_pnl", "net_deposits", "total_pnl")
        coins = self._coin_quotes(sorted(self._book("COIN")[2]["positions"]))          # one reading for the page: prices, covered list, error
        for market, label, cur in self.ACCOUNTS:
            recs, integ_m, _, val, fx, _ = self._valued(market, coins)
            if fx.get("close"):
                rate, fx_date = fx["close"], fx.get("date")
            parts.append({"market": market, "label": label, "currency": cur, "records": len(recs), "integrity": integ_m["status"], **{k: val["summary"].get(k) for k in keys}})
            rows += [{**h, "market": market, "currency": cur} for h in val["holdings"]]

        def won(v: Optional[float], cur: str) -> Optional[float]:
            return to_krw(v, cur, rate)
        for p in parts:
            for k in ("equity", "cash", "market_value", "total_pnl", "net_deposits", "day_pnl"):
                p[f"{k}_krw"] = won(p[k], p["currency"])
        used = [p for p in parts if p["records"]]
        def total(key: str) -> Optional[float]:
            vals = [p[f"{key}_krw"] for p in used]
            return sum(vals) if vals and None not in vals else None if vals else 0.0
        krw = total("equity")
        for h in rows:
            h["value_krw"] = won(h["value"], h["currency"])
            h["weight_total_pct"] = h["value_krw"] / krw * 100 if krw and h["value_krw"] is not None else None
        rows.sort(key=lambda h: (-(h["value_krw"] or 0.0), h["market"], h["ticker"]))
        journal = [{**r, "market": r.get("market", "US"), "voided": r["id"] in gone}
                   for r in sorted(all_recs, key=lambda r: (r.get("date") or r["recorded_at"][:10], r["seq"]), reverse=True)]
        sums = {k: total(k) for k in ("equity", "cash", "market_value", "total_pnl", "net_deposits", "day_pnl")}
        return {"integrity": integ, "accounts": parts, "holdings": rows, "journal": journal[:300], "journal_count": len(journal),
                "total": {"krw": krw, "usd": krw / rate if krw is not None and rate else None, "usdkrw": rate, "fx_date": fx_date, **{f"{k}_krw": v for k, v in sums.items() if k != "equity"},
                          "missing": [f"{p['label']}: {', '.join(p['missing_prices'])}" for p in used if p["missing_prices"]]},
                "coins": [{"coin": c, "name": coins["names"].get(c)} for c in coins["covered"]], "coin_error": coins["error"],
                "notes": ["미국 계좌는 달러, 한국 계좌와 코인은 원화로 적습니다. 합계는 그날 환율로 바꿔 더한 값입니다.",
                          "달러 계좌의 손익은 달러로 계산한 손익을 오늘 환율로 바꾼 값입니다. 환율이 움직여 생긴 손익은 들어 있지 않습니다.",
                          "코인의 지금 가격은 바이낸스의 달러(USDT) 가격에 환율을 곱한 값입니다. 국내 거래소 가격과 몇 % 다를 수 있고, 거래가 많은 30종만 가격이 있습니다.",
                          "위험 한도와 주문 계획은 시장별로 따로 계산합니다(한국이 더 엄격). 코인에는 이 프로그램의 한도와 점검이 없습니다.",
                          "주문 기능은 없습니다. 보유 현황은 직접 적은 기록으로만 계산합니다."]}

    def portfolio(self, market: str = "US") -> Dict[str, Any]:
        recs, integ, state, val, fx, cache = self._valued(market)
        gone = pf.voided_ids(recs)
        journal = [{**r, "voided": r["id"] in gone} for r in
                   sorted(recs, key=lambda r: (r.get("date") or r["recorded_at"][:10], r["seq"]), reverse=True)]
        return {"market": market, "integrity": integ, **val, "total": self._total(market, val, fx), "stats": pf.trade_stats(state["closed"]), "closed": state["closed"][::-1],
                "stats_by_style": {s: pf.trade_stats([c for c in state["closed"] if c.get("style") == s]) for s in pf.STYLES},
                "journal": journal, "settings": self.settings(),
                "fx": {"usdkrw": fx.get("close"), "date": fx.get("date"), "status": fx.get("status", "UNAVAILABLE")},
                "cache": cache, "source": "사용자 거래 기록 + Yahoo Finance 일봉 종가(지연)", "benchmark": BENCH[market][1],
                "note": "주문 기능은 없습니다. 보유 현황은 직접 기록한 거래로만 계산합니다."}

    def portfolio_risk(self, market: str = "US") -> Dict[str, Any]:
        """Beta, volatility, one-day loss at the 5% tail, each holding's share of the risk and their correlations, on the past year
        with today's weights held fixed.  Read only; a description of the mix, not a forecast."""
        from terminal import portfolio_risk
        _, integ, _, val, _, _ = self._valued(market)
        eq = val["summary"].get("equity")
        held = [h for h in val["holdings"] if h.get("weight_pct") is not None]
        if integ["status"] != "OK" or not held or not eq:
            return {"status": "UNAVAILABLE", "market": market, "reason": "NO_HOLDINGS" if not held else "INCOMPLETE_VALUATION"}
        bench, bench_name = BENCH[market]
        hist, fetched = {}, []
        for t in [h["ticker"] for h in held] + [bench]:
            sym = bench if t == bench else self._sym(t)
            res = self.cache.cached(f"chart:{sym}:2y", TTL["chart"], lambda sym=sym: self.src.yahoo_history([sym], "2y"))
            hist[t] = (res["data"] or {}).get(sym) or []
            fetched.append(res.get("fetched_at"))
        out = portfolio_risk.analyse({h["ticker"]: h["weight_pct"] / 100 for h in held}, hist, hist[bench], eq)
        names = {h["ticker"]: h.get("name") for h in held}
        for h in out.get("holdings") or []:
            h["name"] = names.get(h["ticker"])
        return {**out, "market": market, "benchmark": bench_name, "equity": eq, "fetched_at": min((f for f in fetched if f), default=None),
                "source": "사용자 거래 기록 + Yahoo Finance 일봉 (배당 조정 종가, 지연)",
                "basis": "지금 비중을 지난 1년 동안 그대로 들고 있었다고 가정한 계산입니다. 현금은 수익 0으로 봅니다. 앞으로의 손실 한도나 예측이 아닙니다."}

    def equity(self, market: str = "US") -> Dict[str, Any]:
        recs, integ, state = self._book(market)
        eff = pf.effective(recs)
        if not eff or integ["status"] != "OK":
            return {"points": [], "twr_pct": None, "bench_pct": None, "status": "UNAVAILABLE"}
        days = (self._today_et() - datetime.strptime(eff[0]["date"], "%Y-%m-%d").date()).days
        period = "1y" if days < 330 else "2y" if days < 700 else "5y" if days < 1800 else "10y"
        tickers = sorted({r["ticker"] for r in eff if r["kind"] in ("BUY", "SELL", "HOLD")})
        sym = {t: self._sym(t) for t in tickers}
        bench, bench_name = BENCH[market]
        syms = list(sym.values()) + ([bench] if bench not in sym.values() else [])
        res = self.cache.cached(f"eq:{period}:{','.join(syms)}", TTL["chart"],
                                lambda: self.src.yahoo_history(syms, period))
        hist = res["data"] or {}
        curve = pf.equity_curve(recs, {t: hist.get(sym[t]) or [] for t in tickers}, hist.get(bench) or [])
        from terminal import journal_yardstick as jy                 # each sale beside the same money in the index fund (user decision 2026-11-25)
        marked = jy.mark(state["closed"], hist.get(bench) or [])
        return {**curve, "yardstick": {**jy.summary(marked, bench_name), "trades": marked[::-1][:50]}, "status": res["status"] if curve["points"] else "UNAVAILABLE",
                "fetched_at": res["fetched_at"], "source": f"거래 기록 재계산 + Yahoo 일봉 종가, 비교 지수 {bench_name}",
                "benchmark": bench_name, "method": "시간가중수익률(TWR): 입출금 효과를 제외한 일별 수익률의 누적"}

    def sizing(self, ticker: str = "", entry=None, stop=None, equity=None, style=None, market: str = "US") -> Dict[str, Any]:
        market = pf.market_of(clean_ticker(ticker)) if ticker else market
        _, integ, state, val, _, _ = self._valued(market)
        style = pf._style(style) or (state["positions"].get(clean_ticker(ticker)) or {}).get("style") if ticker else pf._style(style)
        st = pf.limits_for(style, self.settings(), market)
        atr_n = st.get(f"stop_atr_{(style or 'SWING').lower()}", 2.0)
        out: Dict[str, Any] = {"market": market, "settings": st, "style": style, "stop_atr": atr_n, "equity": val["summary"]["equity"], "cash": state["cash"]}
        last, a = None, None
        if ticker:
            t = clean_ticker(ticker)
            c = self.chart(t, "3mo")
            if c.get("bars"):
                last = c["last"]["close"]
                sym = self._sym(t)
                res = self.cache.cached(f"chart:{sym}:2y", TTL["chart"], lambda: self.src.yahoo_history([sym], "2y"))
                a = pf.atr((res["data"] or {}).get(sym) or [])
            out.update(ticker=t, last_close=last, last_date=(c.get("last") or {}).get("date"), atr14=a,
                       suggested_stop=(last - atr_n * a) if last is not None and a else None,
                       held_qty=(state["positions"].get(t) or {}).get("qty"))
        e = pf._opt_pos(entry, "진입가") or last
        s = pf._opt_pos(stop, "손절가") or out.get("suggested_stop")
        if e is None or s is None:
            out["result"] = None
            out["reason"] = f"진입가와 손절가를 입력하세요 (종목 코드를 넣으면 최근 종가와 {atr_n:g} ATR 손절가를 제안합니다)."
            return out
        manual = pf._opt_pos(equity, "계좌 금액")
        if manual:                       # hypothetical account (e.g. before any trade is recorded): all cash
            out.update(equity=manual, cash=manual, equity_source="입력값")
        elif val["summary"]["equity"] is None:
            raise pf.JournalError("일부 보유 종목의 시세가 없어 계좌 평가액을 확정할 수 없습니다.")
        else:
            out["equity_source"] = "거래 기록"
        out["result"] = pf.position_size(out["equity"], out["cash"], e, s, st)
        out["stop_source"] = "입력값" if stop not in (None, "") else f"{atr_n:g} ATR(14일) 제안값"
        return out

    def order_plan(self, market: str = "US") -> Dict[str, Any]:
        """The newest scan's entry candidates fitted to the recorded account by its own limits.  Read only: no order is sent
        and nothing is written to the journal."""
        from terminal.qsf import order_plan as op
        note = "주문을 보내지 않습니다. 참고용 계획이고 투자 자문이 아닙니다. 지정가 상한은 '이 가격 위로는 따라가지 않는다'는 기준입니다."
        latest = self.qsf.screen_rows(market)
        session = latest.get("session")
        if latest.get("status") != "REAL" or not session:
            return {"status": "NO_SCAN", "market": market, "note": note}
        info = {r["ticker"]: {"name": r.get("name"), "sector": r.get("sector")} for r in latest.get("rows") or []}
        st = self.settings()
        snaps = op.session_snaps(self.qsf.ledger, market, session)
        cands, mstate = op.candidates(snaps, session, info, st), op.state_for_plan(snaps, market, session)
        # the user's stance for this market: which candidates the plan keeps and how large its orders are (terminal/qsf/stance.py).
        # NORMAL changes nothing.  The paper book and the comparison books never read it.
        from terminal.qsf import stance as qsf_stance
        level = qsf_stance.level(self.base, market)
        cands, sized, stance_shown = qsf_stance.for_plan(cands, mstate, qsf_stance.marks(snaps, level), level, op.STRATEGY_OF)
        # cards the buy check itself waits on leave the REAL plan only (terminal/qsf/plan_checks.py, user decisions 2026-11-26)
        from terminal.qsf import plan_checks
        cands, checks = plan_checks.split(cands, snaps, op.STRATEGY_OF)
        _, integ, state, val, _, _ = self._valued(market)
        equity = val["summary"]["equity"]
        if not equity or equity <= 0:
            return {"status": "NO_ACCOUNT", "market": market, "session": session, "candidates": len(cands), "candidates_by": op.count_by(cands), "note": note, "market_state": mstate, "stance": stance_shown, "plan_checks": checks,
                    "timing_note": op.TIMING_NOTE[market], "reason": "계좌 평가액이 없습니다. '내 계좌'에 입금·거래를 기록하면 그 계좌 기준으로 계획을 보여 줍니다."}
        account = {"equity": equity, "cash": state["cash"],
                   "positions": {h["ticker"]: {"style": h.get("style"), "value": h.get("value") or 0.0, "sector": h.get("sector")} for h in val["holdings"]}}
        from terminal.qsf import holding, rank_book, turnover_book
        rules = turnover_book.active_rules(self.base, market)       # in force only after the reading said ADOPT, or by the user's .env switch
        blocked = turnover_book.loss_sales(state.get("closed") or [], market, session, holding.stepper(market), rules["reentry_wait"]) if rules else None
        rank = rank_book.active_rules(self.base, market)             # the same for the rank rules: an entry only inside the day's top share
        outside = op.outside_top(cands, op.ahead_share(snaps, session), rank["entry_top"]) if rank else None
        plan = op.build(cands, account, market, st, sized, blocked=blocked, outside=outside, risk_at_limit=True)      # the risk limit at the limit price (user decision 2026-11-26)
        for o in plan["orders"]:            # the price an order can carry: the cap rounded down to the price step (display only)
            o["limit_order"] = op.order_price(market, o["limit"])
        plan["totals"] = op.totals(plan["orders"], equity)          # display only: the sum of the new orders, and the risk at the limit price
        # what the market state alone asked for stays readable apart from the stance
        plan.update(size_factor=float(mstate.get("size_factor") or 1.0), new_exposure_cap=mstate.get("new_exposure_cap"), stance=stance_shown,
                    market_state={k: mstate.get(k) for k in op.STATE_SHOWN})
        bands = op.annotate(plan["orders"], {r["ticker"]: r["deal"] for r in latest.get("rows") or [] if r.get("deal")},
                            bands={(c["ticker"], c["style"]): c.get("band") for c in cands})          # display only
        return {"status": "REAL", "session": session, "equity": equity, "cash": state["cash"], "integrity": integ["status"], "note": note, "timing_note": op.TIMING_NOTE[market], "turnover_rules": bool(rules),
                "rank_rules": bool(rank), "reentry_wait": blocked or {}, "bands": bands, "plan_checks": checks, **plan}

    def market_state(self, market: str = "US") -> Dict[str, Any]:
        """The market state of the newest recorded scan: the regime factors, apart from every score.  Read only."""
        from terminal.qsf import order_plan as op
        session = self.qsf.latest(market).get("session")
        if not session:
            return {"status": "NO_SCAN", "market": market}
        memo = getattr(self, "_market_state_memo", None)
        if memo is None:
            memo = self._market_state_memo = {}
        key = (market, session, self.qsf.ledger._index_stamp())
        if key not in memo:
            memo.clear() if len(memo) > 8 else None
            memo[key] = op.market_state(op.session_snaps(self.qsf.ledger, market, session), market, session)
        got = memo[key]
        return {"status": "REAL", **got} if got else {"status": "NO_RECORD", "market": market, "session": session}

    def model_plan(self) -> Dict[str, Any]:
        latest = self._latest_scan()
        if not latest:
            return {"status": "UNAVAILABLE", "items": [], "reason": "기록된 미국 전체 스캔이 없습니다."}
        _, _, state, val, _, _ = self._valued()
        eq = val["summary"]["equity"]
        age = None
        try:
            age = (self.now() - datetime.fromisoformat(latest["executed_at"])).days
        except (KeyError, TypeError, ValueError):
            pass
        items = []
        for r in latest.get("recommendations") or []:
            close = r.get("close")
            held = (state["positions"].get(r.get("ticker")) or {}).get("qty")

            def sh(w):
                return math.floor(w * eq / close) if eq and close and w is not None else None
            items.append({"rank": r.get("recommendation_rank"), "ticker": r.get("ticker"), "name": r.get("name"),
                          "sector": r.get("sector"), "close": close, "last_bar": r.get("last_bar"),
                          "target_weight": r.get("target_weight"), "target_shares": sh(r.get("target_weight")),
                          "entry1_shares": sh(r.get("entry_1_weight")), "hard_stop": r.get("hard_stop"),
                          "horizon_days": r.get("horizon_days"), "held_qty": held,
                          "explanation": r.get("explanation")})
        return {"status": "STALE" if age is not None and age > 3 else "REAL", "age_days": age,
                "run_id": latest.get("run_id"), "executed_at": latest.get("executed_at"),
                "recommendation_status": latest.get("recommendation_status"), "equity": eq, "items": items,
                "disclaimer": "P6-11B가 기록한 계획(목표 비중·1차 진입 비중·손절가)을 내 계좌 규모로 환산한 값입니다. "
                              "수익을 보장하지 않으며 매매 권유가 아닙니다."}

    def health(self) -> Dict[str, Any]:
        from utils.runtime_config import sec_user_agent_status
        return {"version": TERMINAL_VERSION, "time_utc": self.now().isoformat(), "screen": screen_stamp(),
                "sec": sec_user_agent_status()["status"], "ecos": sources.ecos_status()}       # status words only, never values


def screen_stamp() -> str:
    """A short mark of the screen files as they are on disk now.  A page that was loaded before an update holds an older mark,
    which is how it learns that it should be loaded again."""
    import hashlib
    root = Path(__file__).resolve().parent / "static"
    parts = sorted((p.name, p.stat().st_size, int(p.stat().st_mtime)) for p in root.iterdir() if p.is_file() and p.suffix in (".html", ".js", ".css"))
    return hashlib.sha256(repr(parts).encode()).hexdigest()[:12]


def _minus_year(d: str) -> str:
    return f"{int(d[:4]) - 1}{d[4:]}"


def annual_table(facts: Dict[str, Any], years: int = 5) -> Dict[str, Any]:
    """Display table keyed by fiscal-year END date from 10-K filings.  Flows need a ~1-year duration
    (350-380 days); instants are the balance at that end date.  For a repeated period the latest-filed
    value wins.  Per year, concepts are tried in priority order (the concept used is reported)."""
    gaap = (facts.get("facts") or {}).get("us-gaap") or {}
    rows = []
    for key, label, kind, unit, concepts in FUNDAMENTALS:
        vals, used = {}, {}
        for c in concepts:
            best = {}
            for e in ((gaap.get(c) or {}).get("units") or {}).get(unit, []):
                if e.get("form") not in ("10-K", "10-K/A") or sources._num(e.get("val")) is None or not e.get("end"):
                    continue
                if kind == "flow":
                    try:
                        days = (datetime.strptime(e["end"], "%Y-%m-%d") - datetime.strptime(e["start"], "%Y-%m-%d")).days
                    except (KeyError, TypeError, ValueError):
                        continue
                    if not 350 <= days <= 380:
                        continue
                if e["end"] not in best or (e.get("filed") or "") > (best[e["end"]].get("filed") or ""):
                    best[e["end"]] = e
            for end, e in best.items():
                if end not in vals:
                    vals[end], used[end] = sources._num(e["val"]), c
        rows.append({"key": key, "label": label, "unit": unit, "values": vals, "concepts": used})
    by = {r["key"]: r["values"] for r in rows}
    anchor = set(by["revenue"]) | set(by["net_income"])          # fiscal years = periods with a P&L
    yrs = sorted(anchor)[-years:]
    derived = []
    for k, label, f in (("fcf", "잉여현금흐름(영업CF-설비투자)", lambda y: _sub(by["cfo"].get(y), by["capex"].get(y))),
                        ("op_margin", "영업이익률", lambda y: _div(by["operating_income"].get(y), by["revenue"].get(y))),
                        ("net_margin", "순이익률", lambda y: _div(by["net_income"].get(y), by["revenue"].get(y))),
                        ("debt_ratio", "부채비율(부채/자본)", lambda y: _div(by["liabilities"].get(y), by["equity"].get(y)))):
        derived.append({"key": k, "label": label, "unit": "ratio" if k != "fcf" else "USD",
                        "values": {y: f(y) for y in yrs}})
    for r in rows + derived:
        r["values"] = {y: r["values"].get(y) for y in yrs}
        r["concepts"] = {y: r.get("concepts", {}).get(y) for y in yrs} if "concepts" in r else {}
    return {"years": yrs, "rows": rows + derived}


def _sub(a, b):
    return a - b if a is not None and b is not None else None


def _div(a, b):
    return a / b if a is not None and b not in (None, 0) else None
