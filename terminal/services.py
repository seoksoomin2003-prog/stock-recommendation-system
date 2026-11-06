"""Screen data for the terminal (TERMINAL-1 §2).  Every payload carries status / source / as-of.

The terminal only READS model artifacts (runs/, tracking/); it never writes to them.
"""
import json
import math
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from zoneinfo import ZoneInfo

from terminal import TERMINAL_VERSION, portfolio as pf, sources
from terminal.cache import FileCache

TTL = {"quote": 900, "chart": 900, "info": 20 * 3600, "facts": 20 * 3600, "filings": 3600, "macro": 6 * 3600}
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


class Terminal:
    def __init__(self, base_dir: Path = Path("."), src=sources, clock=None, now: Callable[[], datetime] = None):
        self.base = Path(base_dir)
        self.src = src
        self.cache = FileCache(self.base / "data" / "terminal" / "cache", **({"clock": clock} if clock else {}))
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.watchlist_file = self.base / "data" / "terminal" / "watchlist.json"
        self.journal = pf.Journal(self.base / "data" / "terminal" / "journal.jsonl")
        self.settings_file = self.base / "data" / "terminal" / "settings.json"
        from terminal.lab.service import Lab
        self.lab = Lab(self.base, now=self.now)
        self._qsf = None

    @property
    def qsf(self):
        if self._qsf is None:
            from terminal.qsf.service import QSF
            self._qsf = QSF(self.base, src=self.src, now=self.now, terminal=self)
        return self._qsf

    def qsf_evaluate(self, ticker: str, market: str = "US") -> Dict[str, Any]:
        if market == "KR":
            if not re.fullmatch(r"[0-9A-Z]{6}", (ticker or "").strip().upper()):
                raise ValueError("INVALID_TICKER")
            return self.qsf.evaluate(ticker.strip().upper(), "KR")
        if market != "US":
            raise ValueError("INVALID_MARKET")
        return self.qsf.evaluate(clean_ticker(ticker), "US")

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

    def _bar_status(self, last_date: Optional[str], cache_status: str) -> str:
        if cache_status != "REAL" or not last_date:
            return cache_status if cache_status != "REAL" else "UNAVAILABLE"
        age = (self.now().date() - datetime.strptime(last_date, "%Y-%m-%d").date()).days
        return "STALE" if age > STALE_DAYS else "REAL"

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
                      "status": self._bar_status(last["date"], res["status"])}
        return {"items": out, "cache": {k: res[k] for k in ("status", "fetched_at", "error")}}

    # ---------------------------------------------------------------- screens
    def overview(self, market: str = "US") -> Dict[str, Any]:
        layout = OVERVIEW_KR if market == "KR" else OVERVIEW
        syms = [s for _, g in layout for s, _ in g]
        q = self._quotes(syms, "overview" if market == "US" else "overview:KR", market)
        groups = [{"title": t, "items": [{**q["items"][s], "name": n, "ticker": s.split(".")[0] if s.endswith(".KS") else s} for s, n in g]} for t, g in layout]
        return {"market": market, "groups": groups, "cache": q["cache"], "source": "Yahoo Finance (일봉 종가, 지연)",
                "basis": "최근 일봉 종가 대비 전일 종가. 실시간이 아니며, 장중에는 '장중·미확정'으로 표시되는 지연 가격입니다."}

    def chart(self, ticker: str, rng: str = "1y") -> Dict[str, Any]:
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
                "status": self._bar_status(last["date"], res["status"]),
                "last": {"date": last["date"], "close": last["close"], "intraday": self._intraday(last["date"], market),
                         "change_pct": _pct(last["close"], rows[-2]["close"] if len(rows) > 1 else None),
                         "high_52w": hi52, "low_52w": lo52,
                         "vs_sma200_pct": _pct(last["close"], sma[200][-1])},
                "cache": {k: res[k] for k in ("status", "fetched_at", "error")},
                "source": "Yahoo Finance (분할 조정 일봉)"}

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

    def company(self, ticker: str) -> Dict[str, Any]:
        ticker = clean_ticker(ticker)
        market, sym = pf.market_of(ticker), self._sym(ticker)
        info = self.cache.cached(f"info:{sym}", TTL["info"], lambda: self.src.yahoo_info(sym))
        if market == "KR":
            c = self.qsf.kr_company(ticker)
            ident = c.get("ident") or {}
            data = {**(info["data"] or {}), "longName": ident.get("company_name") or (info["data"] or {}).get("longName"), "exchange": ident.get("market") or (info["data"] or {}).get("exchange")}
            return {"ticker": ticker, "market": "KR", "profile": {"status": info["status"], "data": data, "source": "Yahoo Finance quote summary, KRX 상장 목록", "fetched_at": info["fetched_at"]},
                    "fundamentals": self._kr_fundamentals(c)}
        out = {"ticker": ticker, "market": "US", "profile": {"status": info["status"], "data": info["data"] or {},
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
        return {"tickers": w, "items": [{**q["items"][sym[t]], "symbol": t, "name": self._kr_name(t)} for t in w], "cache": q["cache"],
                "source": "Yahoo Finance (일봉 종가, 지연)"}

    # ---------------------------------------------------------------- model (read-only)
    def _latest_scan(self) -> Optional[Dict[str, Any]]:
        """Latest full US market scan written by the frozen P6-11B pipeline (read-only)."""
        runs = self.base / "runs"
        if not runs.exists():
            return None
        for d in sorted((p for p in runs.iterdir() if p.is_dir()), reverse=True):
            v = d / "validation_result.json"
            if not v.exists():
                continue
            try:
                x = json.loads(v.read_text(encoding="utf-8"))
            except ValueError:
                continue
            if x.get("mode") == "market_scan" and x.get("validation_scope") == "full":
                return x
        return None

    def _model_kr(self) -> Dict[str, Any]:
        base = {"name": "KR-EXP-0.1", "status": "EXPERIMENTAL", "role": "한국 실험 모델, 예측력 미검증"}
        root, latest = self.base / "runs" / "KR", None
        for d in sorted((p for p in root.iterdir() if p.is_dir()), reverse=True) if root.exists() else []:
            try:
                x = json.loads((d / "validation_result.json").read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if x.get("validation_scope") == "full":
                latest = x
                break
        if latest:
            base.update(run_id=latest.get("run_id"), executed_at=latest.get("executed_at"), recommendation_status=latest.get("recommendation_status"),
                        capital=latest.get("capital_krw"), currency=latest.get("currency"),
                        top5=[{"recommendation_rank": r.get("rank"), "ticker": r.get("ticker"), "name": r.get("company_name"), "sector": r.get("industry"), "close": r.get("reference_close_krw"),
                               "alpha": r.get("score"), "target_weight": r.get("target_weight")} for r in latest.get("recommendations") or []])
        try:
            from markets.kr import tracking as krt
            d = self.base / "tracking" / "kr"
            trk = {"status": "REAL", "runs": len(krt.runs(d)), "observations": len(krt.observations(d))}
        except Exception as exc:
            trk = {"status": "UNAVAILABLE", "error": type(exc).__name__}
        return {"market": "KR", "baseline": base, "tracking": trk, "challengers": [], "challenger_note": "도전자 모델과 연구실은 아직 미국 전용입니다."}

    def model(self, market: str = "US") -> Dict[str, Any]:
        if market == "KR":
            return self._model_kr()
        latest = self._latest_scan()
        base = {"name": "P6-11B (MODEL_RANK_E)", "status": "FROZEN", "role": "기준 모델"}
        if latest:
            base.update(run_id=latest["run_id"], executed_at=latest.get("executed_at"),
                        recommendation_status=latest.get("recommendation_status"),
                        regime=latest.get("market_regime"), capital=latest.get("capital"),
                        currency=latest.get("currency"),
                        top5=[{k: r.get(k) for k in ("recommendation_rank", "ticker", "name", "sector", "close",
                                                     "alpha", "target_weight", "target_shares", "hard_stop",
                                                     "entry_1_weight", "entry_2_weight", "horizon_days",
                                                     "explanation")} for r in latest.get("recommendations") or []],
                        watchlist=[{k: r.get(k) for k in ("ticker", "name", "sector", "alpha", "final_status")}
                                   for r in (latest.get("watchlist") or [])[:10]])
        trk = {"status": "UNAVAILABLE"}
        try:
            from pipeline import prospective_tracking as pt
            s = pt.status(str(self.base / "tracking"))
            trk = {"status": "REAL", "runs": s["runs"], "observations": s["observations"],
                   "outcome_states": s.get("outcome_states"),
                   "latest_update": (s.get("latest_update") or {}).get("update_id")}
        except Exception as exc:
            trk = {"status": "UNAVAILABLE", "error": type(exc).__name__}
        return {"baseline": base, "tracking": trk, "challengers": [],
                "challenger_note": "도전자 모델 비교는 아래 표에 있습니다. 기준 모델(P6-11B)은 변경하지 않습니다."}

    # ---------------------------------------------------------------- portfolio (TERMINAL-2)
    def settings(self) -> Dict[str, float]:
        try:
            raw = json.loads(self.settings_file.read_text(encoding="utf-8"))
            return pf.clean_settings(raw, dict(pf.DEFAULT_SETTINGS))
        except (OSError, ValueError):
            return dict(pf.DEFAULT_SETTINGS)

    def settings_set(self, raw: Dict[str, Any]) -> Dict[str, float]:
        new = pf.clean_settings(raw or {}, self.settings())
        self.settings_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.settings_file.with_suffix(".tmp")
        tmp.write_text(json.dumps({**new, "updated_at": self.now().isoformat()}), encoding="utf-8")
        tmp.replace(self.settings_file)
        return new

    def capital(self, market: str = "US") -> Dict[str, Any]:
        """The capital the next scan will use.  An unusable value reads as not configured, never as a number."""
        from utils.runtime_config import CAPITAL_KEYS, CapitalNotConfigured, parse_capital
        raw = os.getenv(CAPITAL_KEYS[market], "").strip()
        try:
            amount = parse_capital(raw) if raw else None
        except CapitalNotConfigured:
            amount = None
        return {"market": market, "amount": amount, "currency": "KRW" if market == "KR" else "USD", "invalid": bool(raw) and amount is None}

    def capital_set(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        from utils.runtime_config import CapitalNotConfigured, set_capital
        market = (raw or {}).get("market", "US")
        if market not in ("US", "KR"):
            raise ValueError("시장은 US 또는 KR이어야 합니다.")
        try:
            set_capital(market, (raw or {}).get("amount"), self.base / ".env")
        except CapitalNotConfigured:
            raise ValueError("자본금은 0보다 큰 숫자로 입력하세요.") from None
        return self.capital(market)

    def _today_et(self):
        return self.now().astimezone(ZoneInfo("America/New_York")).date()

    def _today(self, market: str):
        return self.now().astimezone(ZoneInfo("Asia/Seoul")).date() if market == "KR" else self._today_et()

    def journal_add(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        raw = raw or {}
        market = pf.market_of(str(raw.get("ticker") or "").strip().upper()) if raw.get("ticker") else str(raw.get("market") or "US").upper()
        entry = pf.normalize(raw, self._today(market), clean_ticker)
        return {"entry": self.journal.append(entry, self.now())}

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

    def _valued(self, market: str = "US"):
        recs, integ, state = self._book(market)
        held = sorted(state["positions"])
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
        total = eq["KR"] + eq["US"] * rate if None not in (eq["KR"], eq["US"], rate) else None
        return {"krw": total, "us_equity": eq["US"], "kr_equity": eq["KR"], "usdkrw": rate, "fx_date": fx.get("date"),
                "us_krw": eq["US"] * rate if eq["US"] is not None and rate else None}

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

    def equity(self, market: str = "US") -> Dict[str, Any]:
        recs, integ, state = self._book(market)
        eff = pf.effective(recs)
        if not eff or integ["status"] != "OK":
            return {"points": [], "twr_pct": None, "bench_pct": None, "status": "UNAVAILABLE"}
        days = (self._today_et() - datetime.strptime(eff[0]["date"], "%Y-%m-%d").date()).days
        period = "1y" if days < 330 else "2y" if days < 700 else "5y" if days < 1800 else "10y"
        tickers = sorted({r["ticker"] for r in eff if r["kind"] in ("BUY", "SELL")})
        sym = {t: self._sym(t) for t in tickers}
        bench, bench_name = BENCH[market]
        syms = list(sym.values()) + ([bench] if bench not in sym.values() else [])
        res = self.cache.cached(f"eq:{period}:{','.join(syms)}", TTL["chart"],
                                lambda: self.src.yahoo_history(syms, period))
        hist = res["data"] or {}
        curve = pf.equity_curve(recs, {t: hist.get(sym[t]) or [] for t in tickers}, hist.get(bench) or [])
        return {**curve, "status": res["status"] if curve["points"] else "UNAVAILABLE",
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
        return {"version": TERMINAL_VERSION, "time_utc": self.now().isoformat(),
                "sec": sec_user_agent_status()["status"], "ecos": sources.ecos_status()}       # status words only, never values


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
