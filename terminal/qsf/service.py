"""QSF data assembly and orchestration: single-stock evaluation, universe scan, recording, validation reports.

Markets stay isolated: the US path never reads Korean data and the reverse (no VIX or SPY in a Korean score).
P6-11B is read as a separate reference from its run artifacts and is never merged into a QSF score.
"""
import gzip
import hashlib
import json
import os
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import numpy as np

from terminal import sources as default_sources
from terminal.cache import FileCache
from terminal.qsf import config, engine, events, fundamentals, holding, ledger, technicals
from utils import nyse_calendar

TTL = {"bars": 1800, "regime": 3600, "facts": 7 * 86400, "subm": 20 * 3600, "info": 7 * 86400, "earn": 3 * 86400, "form4": 3650 * 86400}
REGIME_FRESH_DAYS = 5
UNAVAILABLE_KR = {"vkospi": "VKOSPI는 합법적인 무료 공개 출처에서 안정적으로 받을 수 없어 사용하지 않습니다.",
                  "kr_credit": "한국 신용·유동성 지표의 검증된 무료 출처를 아직 연결하지 않았습니다."}


def _clean(rows: List[Dict], last: str) -> List[Dict]:
    return [r for r in rows if r["date"] <= last]


def _six_month_return(rows: List[Dict]) -> Optional[float]:
    """Return behind the universe rank; ``rows`` are already cut at the session."""
    if len(rows) > 126 and rows[-127].get("adj_close") and rows[-1].get("adj_close"):
        return rows[-1]["adj_close"] / rows[-127]["adj_close"] - 1
    return None


def _rank_in(ordered: List[float], value: float) -> float:
    return float(np.searchsorted(ordered, value, side="right") / len(ordered))


MIN_RANK_NAMES = 20


class QSF:
    def __init__(self, base: Path, src=default_sources, now: Callable[[], datetime] = None, terminal: Any = None, dart: Any = None, kr_master: Any = None):
        self.base = Path(base)
        self.src = src
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.dir = self.base / "data" / "qsf"
        self.cache = FileCache(self.dir / "cache")
        self.ledger = ledger.Ledger(self.base)
        self._terminal = terminal
        self._dart = dart
        self._kr_master = kr_master
        self._regime: Dict[str, Dict] = {}
        self._krx_share_cache: Dict[str, Dict[str, float]] = {}

    # ------------------------------------------------------------------ helpers
    @property
    def terminal(self):
        if self._terminal is None:
            from terminal.services import Terminal
            self._terminal = Terminal(self.base, now=self.now)
        return self._terminal

    def _session(self, market: str, index_rows: Optional[List[Dict]] = None) -> str:
        if market == "US":
            return nyse_calendar.latest_completed_session(self.now()).isoformat()
        from markets.kr import calendar as krcal
        days = [r["date"] for r in index_rows or [] if krcal.bar_is_complete(r["date"], self.now())]
        return days[-1] if days else (self.now().date() - timedelta(days=1)).isoformat()

    def _entry_date(self, market: str, session: str) -> date:
        if market == "US":
            return date.fromisoformat(nyse_calendar.classify_signal(self.now())["entry_session"])
        from markets.kr import calendar as krcal
        nb = date.fromisoformat(krcal.classify_signal(self.now())["entry_not_before"])
        return holding.on_or_after_session(nb, holding.next_session_kr)

    def _session_bars(self, chunk: List[str], session: str) -> Dict[str, List[Dict]]:
        """A chunk is cached for the day only once it reaches the session.  The key names its members, so a small test scan
        cannot stand in for a full one, and a partial Yahoo reply is retried at the next slot instead of being reused."""
        key = "scanbars:" + session + ":" + hashlib.sha256(",".join(chunk).encode()).hexdigest()[:16]

        def ready(data):
            return sum(1 for rows in (data or {}).values() if rows and _clean(rows, session) and _clean(rows, session)[-1]["date"] == session) >= 0.9 * len(chunk)
        old = self.cache.read(key)
        if old is not None and ready(old["data"]):
            return old["data"]
        try:
            data = self.src.yahoo_history(chunk, "2y") or {}
        except Exception:
            return {}
        if ready(data):
            self.cache.write(key, data)
        return data

    def _history(self, symbols: List[str], period: str = "2y") -> Dict[str, Any]:
        key = f"bars:{period}:{','.join(sorted(symbols))}"
        return self.cache.cached(key, TTL["bars"], lambda: self.src.yahoo_history(symbols, period))

    # ------------------------------------------------------------------ regime
    def _level(self, rows: List[Dict], key: str = "close") -> Dict[str, Any]:
        vals = np.array([r[key] for r in rows], dtype=float)
        last_date = rows[-1]["date"]
        age = (self.now().date() - date.fromisoformat(last_date)).days
        return {"status": "REAL" if age <= REGIME_FRESH_DAYS else "STALE", "value": float(vals[-1]), "date": last_date, "percentile": float((vals <= vals[-1]).mean()), "n": len(vals)}

    def _index(self, rows: List[Dict], symbol: str) -> Dict[str, Any]:
        if len(rows) < 200:
            return {"status": "UNAVAILABLE", "reason": f"{symbol} 이력 부족"}
        c = np.array([r["close"] for r in rows], dtype=float)
        return {**self._level(rows), "symbol": symbol, "close": float(c[-1]), "ma50": float(c[-50:].mean()), "ma200": float(c[-200:].mean()), "source": "Yahoo Finance"}

    def regime(self, market: str) -> Dict[str, Any]:
        if market in self._regime:
            return self._regime[market]
        return self._regime.setdefault(market, self._regime_us() if market == "US" else self._regime_kr())

    def _regime_us(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        hist = self._history(["^VIX", "^VIX3M", "SPY"], "5y")
        data = hist["data"] or {}
        session = self._session("US")
        vix, v3, spy = (_clean(data.get(s) or [], session) for s in ("^VIX", "^VIX3M", "SPY"))
        out["vix"] = {**self._level(vix), "source": "Yahoo ^VIX"} if vix else {"status": "UNAVAILABLE", "reason": "VIX 없음"}
        if vix and v3:
            m = {r["date"]: r["close"] for r in v3}
            pair = [(r["date"], r["close"] / m[r["date"]]) for r in vix if r["date"] in m]
            if pair:
                out["vix_term"] = {"status": "REAL", "value": pair[-1][1], "date": pair[-1][0], "source": "Yahoo ^VIX/^VIX3M"}
        out.setdefault("vix_term", {"status": "UNAVAILABLE", "reason": "VIX3M 없음"})
        out["index"] = self._index(spy, "SPY")
        start = (self.now().date() - timedelta(days=365 * 10)).isoformat()
        hy = self.cache.cached("fred:BAMLH0A0HYM2", TTL["regime"], lambda: self.src.fred_series("BAMLH0A0HYM2", start))
        rows = [{"date": d, "close": v} for d, v in (hy["data"] or []) if v is not None]
        if len(rows) >= 250:
            # FRED currently publishes only about three years of this ICE series: percentile uses what is actually returned.
            out["hy_spread"] = {**self._level(rows), "source": f"FRED BAMLH0A0HYM2 (가용 이력 {rows[0]['date']}부터)"}
        else:
            out["hy_spread"] = {"status": "UNAVAILABLE", "reason": "하이일드 스프레드 이력 부족"}
        out["breadth"] = self._us_breadth()
        return out

    def _us_breadth(self) -> Dict[str, Any]:
        p = self.terminal.lab.panel()
        if p is None or len(p.dates) < 200:
            return {"status": "UNAVAILABLE", "reason": "유니버스 가격 패널 없음"}
        from terminal.lab.panel import row_complete
        last = len(p.dates) - 1
        while last > 0 and not row_complete(p, last):      # never measure breadth on a partly published session
            last -= 1
        a = p.f("adj_close")[: last + 1]
        with np.errstate(invalid="ignore"):
            ma = np.nanmean(a[-200:], axis=0)
            ok = np.isfinite(a[-1]) & np.isfinite(ma)
        day = p.dates[last]
        return {"status": "REAL" if day == self._session("US") else "STALE", "value": float((a[-1][ok] > ma[ok]).mean()), "n": int(ok.sum()), "date": day, "source": "S&P 500 패널"}

    def _regime_kr(self) -> Dict[str, Any]:
        # Yahoo's index series can skip a session that stocks have, so a large constituent also marks the calendar.
        hist = self._history(["^KS11", "^KQ11", "KRW=X", "005930.KS"], "2y")
        data = hist["data"] or {}
        session = self._session("KR", sorted((data.get("^KS11") or []) + (data.get("005930.KS") or []), key=lambda r: r["date"]))
        ks, fx = _clean(data.get("^KS11") or [], session), data.get("KRW=X") or []
        out: Dict[str, Any] = {"index": self._index(ks, "KOSPI"), "kosdaq": self._index(_clean(data.get("^KQ11") or [], session), "KOSDAQ"),
                               "vkospi": {"status": "UNAVAILABLE", "reason": UNAVAILABLE_KR["vkospi"]}, "kr_credit": {"status": "UNAVAILABLE", "reason": UNAVAILABLE_KR["kr_credit"]},
                               "session": session}
        if len(fx) > 64:
            out["usdkrw"] = {**self._level(fx), "change_63": fx[-1]["close"] / fx[-64]["close"] - 1, "source": "Yahoo KRW=X"}
        else:
            out["usdkrw"] = {"status": "UNAVAILABLE", "reason": "원/달러 이력 부족"}
        out["breadth"] = {"status": "UNAVAILABLE", "reason": "한국 스캔을 실행하면 계산됩니다"}
        try:
            saved = json.loads((self.dir / "breadth_KR.json").read_text(encoding="utf-8"))
            if saved["date"] == session:
                out["breadth"] = saved
        except (OSError, ValueError, KeyError):
            pass
        return out

    # ------------------------------------------------------------------ fundamentals and events
    def _us_fund(self, ticker: str, bars: List[Dict], as_of: str) -> Dict[str, Any]:
        try:
            cik = self.src.sec_cik(ticker)
        except Exception as exc:
            return {"status": "UNAVAILABLE", "reason": f"SEC 식별 실패 ({type(exc).__name__})"}
        if not cik:
            return {"status": "UNAVAILABLE", "reason": "SEC CIK 없음 (ETF·지수이거나 미국 상장 기업이 아님)", "no_cik": True}
        res = self.cache.cached(f"annual2:{default_sources.facts_key(ticker, cik)}", TTL["facts"], lambda: self._annual(ticker, cik))
        subm = self._us_subm(cik)
        if res["data"] is None:
            return {"status": "UNAVAILABLE", "reason": f"SEC 재무 조회 실패 ({res.get('error')})", "cik": cik}
        info = self.cache.cached(f"info:{ticker}", TTL["info"], lambda: self.src.yahoo_info(ticker))["data"] or {}
        fin = fundamentals.is_financial_sic((subm or {}).get("sic"))
        m = fundamentals.metrics(res["data"], bars[-1]["close"], as_of, is_financial=fin, shares=fundamentals.us_total_shares(info, bars[-1]["close"], res["data"]), insider_pct=info.get("heldPercentInsiders"))
        return {**m, "cik": cik, "name": info.get("longName") or (subm or {}).get("name"), "sector": info.get("sector")}

    def _annual(self, ticker: str, cik: str) -> Dict[str, Any]:
        return fundamentals.drop_stale_series(fundamentals.extract_us(default_sources.facts_with_predecessors(ticker, cik, self.src.sec_companyfacts)))

    def _us_subm(self, cik: str) -> Optional[Dict[str, Any]]:
        def fetch():
            s = self.src.sec_submissions(cik)
            rows = events.recent_filings(s)
            # Banks file thousands of prospectuses, so the list is filtered by form rather than cut by position.
            return {"name": s.get("name"), "sic": s.get("sic"), "oldest": rows[-1]["date"] if rows else None, "truncated": bool((s.get("filings") or {}).get("files")), "filings": [r for r in rows if r["form"] in events.KEPT_FORMS]}
        return self.cache.cached(f"submforms:{cik}", TTL["subm"], fetch)["data"]

    def _us_events(self, cik: Optional[str], as_of: str) -> Dict[str, Any]:
        if not cik:
            return {"status": "UNAVAILABLE", "reason": "SEC CIK 없음"}
        subm = self._us_subm(cik)
        if not subm:
            return {"status": "UNAVAILABLE", "reason": "SEC 공시 조회 실패"}
        start = (date.fromisoformat(as_of) - timedelta(days=events.WINDOW)).isoformat()
        if subm.get("oldest") and subm["oldest"] > start and subm.get("truncated"):
            return {"status": "UNAVAILABLE", "reason": "SEC 최근 공시 목록이 90일을 덮지 못합니다."}
        transfers = []
        for f in events.listing_item_targets(subm["filings"], as_of):
            url = self.src.SEC_ARCHIVE.format(cik=int(cik), acc=f["accession"].replace("-", ""), doc=f["doc"].split("/")[-1])
            r = self.cache.cached(f"item301:{f['accession']}", TTL["form4"], lambda u=url: {"transfer": events.is_listing_transfer(self.src.sec_text(u))})
            if (r["data"] or {}).get("transfer"):      # text unreadable: the filing stays severe
                transfers.append(f["accession"])
        ev = events.classify_us(subm["filings"], as_of, transfers)
        parsed = []
        for f in events.form4_targets(subm["filings"], as_of):
            url = self.src.SEC_ARCHIVE.format(cik=int(cik), acc=f["accession"].replace("-", ""), doc=events.raw_form4_doc(f["doc"]))
            r = self.cache.cached(f"form4:{f['accession']}", TTL["form4"], lambda u=url: events.parse_form4(self.src.sec_text(u)))
            parsed.append(r["data"])
        ev["insider"] = events.insider_summary(parsed)
        return ev

    def _earnings(self, ticker: str, market: str, as_of: str) -> Dict[str, Any]:
        def fetch():
            return self.src.yahoo_earnings_dates(ticker)
        days = self.cache.cached(f"earn:{ticker}", TTL["earn"], fetch)["data"]
        nxt = next((d for d in (days or []) if d > as_of), None)
        if not nxt:
            return {"sessions": None}
        step, d, n = holding.stepper(market), date.fromisoformat(as_of), 0
        target = date.fromisoformat(nxt)
        while d < target and n < 300:
            d, n = step(d), n + 1
        return {"date": nxt, "sessions": n, "source": "Yahoo 실적 일정 (회사 확정 전에는 추정치)"}

    # KR: every field below is OpenDART; without a key the factors stay missing, they are not scored as zero.
    @property
    def dart(self):
        if self._dart is None:
            from markets.kr.dart import OpenDartClient
            self._dart = OpenDartClient()
        return self._dart

    def _kr_identity(self, code: str) -> Optional[Dict[str, Any]]:
        if self._kr_master is None:
            from markets.kr import security_master
            self._kr_master = security_master.load_master(self.base / "data" / "kr", now=self.now())["master"]
        hit = self._kr_master[self._kr_master["canonical_ticker"] == code]
        return None if hit.empty else hit.iloc[0].to_dict()

    def _corp_code(self, code: str) -> Optional[str]:
        def fetch():
            df = self.dart.corp_codes()
            col = "stock_code" if "stock_code" in df.columns else df.columns[0]
            return {str(r[col]).strip(): str(r["corp_code"]) for _, r in df.iterrows() if str(r[col]).strip()}
        return (self.cache.cached("dart:corpmap", 30 * 86400, fetch)["data"] or {}).get(code)

    def _krx_shares(self, as_of: str) -> Dict[str, float]:
        """Listed shares from the newest KRX snapshot up to ``as_of``.  Empty without one, and the caller then keeps Yahoo's count."""
        if as_of not in self._krx_share_cache:
            from terminal.qsf import krx_history
            self._krx_share_cache[as_of] = krx_history.listed_shares(self.base / "research_data" / "krx", as_of)
        return self._krx_share_cache[as_of]

    def _kr_fund_events(self, code: str, ident: Dict, bars: List[Dict], as_of: str) -> Dict[str, Any]:
        if not self.dart.configured:
            reason = "OPENDART_API_KEY가 없어 한국 재무·공시를 평가하지 않았습니다."
            return {"fund": {"status": "UNAVAILABLE", "reason": reason}, "events": {"status": "UNAVAILABLE", "reason": reason}}
        corp = self._corp_code(code)
        if not corp:
            return {"fund": {"status": "UNAVAILABLE", "reason": "DART 고유번호 없음"}, "events": {"status": "UNAVAILABLE", "reason": "DART 고유번호 없음"}}
        klass = ident.get("industry_class") or "NON_FINANCIAL"
        res = self.cache.cached(f"krfund2:{code}", TTL["facts"], lambda: fundamentals.extract_kr(fundamentals.load_kr_statements(corp, code, klass, date.fromisoformat(as_of), self.dart)))
        info = self.cache.cached(f"info:{ident.get('yahoo_symbol')}", TTL["info"], lambda: self.src.yahoo_info(ident["yahoo_symbol"]))["data"] or {}
        fund = {"status": "UNAVAILABLE", "reason": f"DART 재무 조회 실패 ({res.get('error')})"}
        if res["data"]:
            fund = fundamentals.blank_mixed_cash_flow(fundamentals.metrics(res["data"], bars[-1]["close"], as_of, is_financial=klass != "NON_FINANCIAL", shares=self._krx_shares(as_of).get(code) or info.get("sharesOutstanding"),
                                                                           source="OpenDART 사업보고서", insider_pct=info.get("heldPercentInsiders")), code)
        def fetch_list():
            bgn = (date.fromisoformat(as_of) - timedelta(days=events.WINDOW_LONG)).strftime("%Y%m%d")
            r = self.dart._get("list.json", corp_code=corp, bgn_de=bgn, end_de=as_of.replace("-", ""), page_count=100).json()
            return r.get("list") or []
        rep = self.cache.cached(f"krlist:{corp}", TTL["subm"], fetch_list)
        ev = events.classify_kr(rep["data"], as_of) if rep["data"] is not None else {"status": "UNAVAILABLE", "reason": "DART 공시 조회 실패"}
        return {"fund": fund, "events": ev}

    def kr_company(self, code: str) -> Dict[str, Any]:
        """Identity, annual statements and recent filings of one Korean company, for the stock screen."""
        ident = self._kr_identity(code)
        out: Dict[str, Any] = {"ident": ident, "annual": None, "reports": None}
        if not ident:
            out["reason"] = "상장 종목 목록에 없는 코드입니다 (ETF는 재무·공시가 없습니다)."
            return out
        if not self.dart.configured:
            out["reason"] = "OPENDART_API_KEY가 없어 재무·공시를 불러오지 않았습니다."
            return out
        corp = self._corp_code(code)
        if not corp:
            out["reason"] = "DART 고유번호를 찾지 못했습니다."
            return out
        as_of = self.now().date()
        klass = ident.get("industry_class") or "NON_FINANCIAL"
        res = self.cache.cached(f"krfund2:{code}", TTL["facts"], lambda: fundamentals.extract_kr(fundamentals.load_kr_statements(corp, code, klass, as_of, self.dart)))

        def fetch_list():
            bgn = (as_of - timedelta(days=events.WINDOW_LONG)).strftime("%Y%m%d")
            return self.dart._get("list.json", corp_code=corp, bgn_de=bgn, end_de=as_of.strftime("%Y%m%d"), page_count=100).json().get("list") or []
        rep = self.cache.cached(f"krlist:{corp}", TTL["subm"], fetch_list)
        out.update(annual=res["data"], annual_status=res["status"], annual_fetched=res["fetched_at"], reports=rep["data"], reports_status=rep["status"], reports_fetched=rep["fetched_at"])
        return out

    def kr_search(self, query: str, limit: int = 10) -> List[Dict[str, str]]:
        """Listed companies by Korean name, exact match first."""
        self._kr_identity("000000")               # loads the master
        df, q = self._kr_master, (query or "").strip()
        if not q:
            return []
        hit = df[df["company_name"].astype(str).str.contains(q, regex=False)]
        rows = sorted(hit.to_dict("records"), key=lambda r: (r["company_name"] != q, len(r["company_name"])))[:limit]
        return [{"ticker": r["canonical_ticker"], "name": r["company_name"], "market": r.get("market")} for r in rows]

    # ------------------------------------------------------------------ evaluation
    def _position(self, ticker: str, market: str = "US") -> Optional[Dict[str, Any]]:
        try:
            _, _, state = self.terminal._book(market)
        except Exception:
            return None
        p = state["positions"].get(ticker)
        if not p:
            return None
        plan = state["plans"].get(ticker) or {}
        # A position that became a swing later counts its time limit from that change.
        return {"avg_cost": p["avg"], "opened": p.get("style_since") or p["opened"], "qty": p["qty"], "stop": plan.get("stop"), "target": plan.get("target"), "style": p.get("style")}

    def context(self, ticker: str, market: str, prefetched: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        pre = prefetched or {}
        if market == "US":
            sym, bench_sym, ident, name = ticker, "SPY", None, None
        else:
            ident = self._kr_identity(ticker)
            if ident is None or not ident.get("yahoo_symbol"):
                return {"error": "UNKNOWN_SECURITY", "reason": "한국 거래소 종목 목록에서 찾을 수 없습니다."}
            sym, name = ident["yahoo_symbol"], ident.get("company_name")
            bench_sym = config.BENCHMARK["KR_KOSDAQ" if ident.get("market") == "KOSDAQ" else "KR_KOSPI"]
        scanning = "bars" in pre
        if scanning:
            bars, bench = pre["bars"], pre.get("bench")
        else:
            hist = self._history([sym, bench_sym])
            data = hist["data"] or {}
            bars, bench = data.get(sym) or [], data.get(bench_sym) or []
        regime = self.regime(market)
        session = self._session(market) if market == "US" else regime.get("session") or self._session("KR", bench)
        bars, bench = _clean(bars, session), _clean(bench or [], session)
        if not bars:
            return {"error": "NO_PRICE", "reason": "가격 이력을 받지 못했습니다."}
        if len(bars) < 30:
            return {"error": "SHORT_HISTORY", "reason": f"거래 이력이 {len(bars)}거래일뿐이라 점수를 내지 않습니다. 30거래일이 필요합니다."}
        # A scan brings its own rank.  The stock screen and held signals take theirs from the last scan of the same session.
        rs_rank, rank_basis = (pre.get("rs_rank"), None) if scanning else self._stored_rank(ticker, market, session, bars)
        ctx = {"market": market, "ticker": ticker, "symbol": sym, "bars": bars, "bench": bench, "bench_name": "SPY" if market == "US" else ("코스닥" if bench_sym == "^KQ11" else "코스피"),
               "benchmark": bench_sym, "regime": regime, "rs_rank": rs_rank, "rank_basis": rank_basis, "expected_session": session, "price_fresh": bars[-1]["date"] == session, "name": name, "identity_ok": True}
        ctx["tech"] = technicals.compute(bars, bench)
        ctx["levels"] = technicals.levels(ctx["tech"], market)
        if market == "US":
            ctx["fund"] = self._us_fund(ticker, bars, session)
            ctx["name"] = ctx["fund"].get("name")
            ctx["events"] = self._us_events(ctx["fund"].get("cik"), session)
        else:
            fe = self._kr_fund_events(ticker, ident, bars, session)
            ctx["fund"], ctx["events"] = fe["fund"], fe["events"]
        try:
            ctx["earnings"] = self._earnings(sym, market, session)
        except Exception:
            ctx["earnings"] = {"sessions": None}
        return ctx

    def card(self, ctx: Dict[str, Any], strategy: str, position: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        res = engine.score(ctx, strategy, held=bool(position))
        market, session = ctx["market"], ctx["expected_session"]
        entry_day = self._entry_date(market, session)
        entry = holding.entry_status(res, ctx)
        plan = holding.swing_plan(res, ctx, entry_day) if strategy == "SWING" else holding.long_plan(res, ctx, entry_day)
        out = {**res, "ticker": ctx["ticker"], "name": ctx.get("name"), "benchmark": ctx.get("benchmark"), "entry": entry, "entry_status": entry["status"], "entry_session": entry_day.isoformat(),
               "holding": plan, "what_would_change": holding.what_would_change(res), "recorded_at": self.now().isoformat(),
               "provenance": {"price": "Yahoo Finance 일봉", "price_date": res["data_date"], "fund": (ctx.get("fund") or {}).get("source"), "fund_filed": (ctx.get("fund") or {}).get("filed"),
                              "events": (ctx.get("events") or {}).get("source"), "regime": {k: (v or {}).get("date") for k, v in (ctx.get("regime") or {}).items() if isinstance(v, dict)}},
               "not_advice": "규칙에 따른 계산 결과입니다. 주문을 실행하지 않으며 투자 자문이 아닙니다."}
        out["why_summary"] = _why(out)
        if position:
            out["position"] = position
            out["exit"] = holding.evaluate_exit(res, ctx, position, self.now().date())
        prev = self.ledger.previous(market, ctx["ticker"], strategy, session)
        out["stability"] = ledger.stability(prev, out)
        return out

    def evaluate(self, ticker: str, market: str = "US", strategies=config.STRATEGIES) -> Dict[str, Any]:
        ctx = self.context(ticker, market)
        if ctx.get("error"):
            return {"status": "UNAVAILABLE", "ticker": ticker, "market": market, "reason": ctx["reason"]}
        pos = self._position(ticker, market)
        own = config.STYLE_TO_STRATEGY.get((pos or {}).get("style"))
        cards = {s: self.card(ctx, s, pos if own in (None, s) else None) for s in strategies}
        risky = self._high_risk(market)
        return {"status": "REAL", "ticker": ticker, "market": market, "name": ctx.get("name"), "rank_basis": ctx["rank_basis"], "high_risk": {"session": risky["session"]} if ticker in risky["codes"] else None, "filing_events": self._filing_mark(self._filing_marks(market), ticker), "cards": cards, "held_strategy": own, "p6_reference": self.p6_reference(ticker) if market == "US" else None}

    def signal(self, ticker: str, weight_pct: Optional[float] = None, max_weight_pct: Optional[float] = None, market: str = "US") -> Dict[str, Any]:
        """Score and exit reading of one held position, under the profile of its own style only."""
        pos = self._position(ticker, market)
        if not pos or not pos.get("style"):
            return {"status": "NO_STYLE", "ticker": ticker}
        ctx = self.context(ticker, market)
        if ctx.get("error"):
            return {"status": "UNAVAILABLE", "ticker": ticker, "reason": ctx["reason"]}
        strategy = config.STYLE_TO_STRATEGY[pos["style"]]
        c = self.card(ctx, strategy, {**pos, "weight_pct": weight_pct, "max_weight_pct": max_weight_pct})
        out = {"status": "REAL", "ticker": ticker, "style": pos["style"], "strategy": strategy, "rank_basis": ctx["rank_basis"], "filing_events": self._filing_mark(self._filing_marks(market), ticker), "score": c["score"], "band_label": c["band_label"], "confidence": c["confidence"],
               "coverage": c["coverage"], "data_date": c["data_date"], "gates": c["gates"], "exit": c["exit"], "earnings_date": (ctx.get("earnings") or {}).get("date")}
        if strategy == "SWING":
            step = holding.stepper(market)
            limit = holding.add_sessions(date.fromisoformat(pos["opened"]), config.SWING["time_stop"], step)
            d, left = self.now().date(), 0
            while d < limit:
                d, left = step(d), left + 1
            out.update(time_limit=limit.isoformat(), sessions_left=left)
        return out

    def p6_reference(self, ticker: str) -> Dict[str, Any]:
        """Read-only display from the latest P6-11B full scan.  Deliberately not an input to any QSF score."""
        latest = self.terminal._latest_scan()
        if not latest:
            return {"status": "UNAVAILABLE", "note": "P6-11B 전체 스캔 기록이 없습니다."}
        hit = next((r for r in latest.get("recommendations") or [] if r.get("ticker") == ticker), None)
        return {"status": "REAL", "run_id": latest.get("run_id"), "in_top5": bool(hit), "rank": hit.get("recommendation_rank") if hit else None,
                "note": "P6-11B는 별도 모델입니다. QSF 점수와 합치지 않습니다."}

    # ------------------------------------------------------------------ scan
    def _us_scan_input(self, tickers: List[str], progress=None) -> Dict[str, Dict]:
        session = self._session("US")
        symbols = sorted(set(tickers) | {"SPY"})
        bars: Dict[str, List[Dict]] = {}
        for i in range(0, len(symbols), 100):
            bars.update(self._session_bars(symbols[i:i + 100], session))
            if progress:
                progress("prices", min(i + 100, len(symbols)), len(symbols))
        return self._prefetch(tickers, bars, "SPY", session)

    @staticmethod
    def _prefetch(tickers: List[str], bars: Dict[str, List[Dict]], bench_sym: str, session: str, sym_of: Optional[Dict[str, str]] = None) -> Dict[str, Dict]:
        rets = {}
        for t in tickers:
            v = _six_month_return(_clean(bars.get((sym_of or {}).get(t, t)) or [], session))
            if v is not None:
                rets[t] = v
        ordered = sorted(rets.values())
        rank = {t: _rank_in(ordered, v) for t, v in rets.items()} if len(ordered) >= MIN_RANK_NAMES else {}
        return {t: {"bars": bars.get((sym_of or {}).get(t, t)) or [], "bench": bars.get(bench_sym) or [], "rs_rank": rank.get(t)} for t in tickers}

    def _write_ranks(self, market: str, session: str, pre: Dict[str, Dict]) -> None:
        """The returns this scan ranked, so the stock screen and held signals can read the same rank.  Too few names means no rank, as in the scan."""
        rets = {t: v for t, v in ((t, _six_month_return(_clean(x["bars"], session))) for t, x in pre.items()) if v is not None}
        if len(rets) < MIN_RANK_NAMES:
            return
        tmp = self.dir / f"ranks_{market}.json.tmp"
        tmp.write_text(json.dumps({"market": market, "session": session, "returns": rets}), encoding="utf-8")
        os.replace(tmp, self.dir / f"ranks_{market}.json")

    def _read_ranks(self, market: str, session: str) -> Optional[Dict[str, float]]:
        """Returns of the scan of this session.  Another session's or an unreadable file counts as no scan."""
        try:
            d = json.loads((self.dir / f"ranks_{market}.json").read_text(encoding="utf-8"))
            rets = {str(t): float(v) for t, v in d["returns"].items()}
            ok = d["market"] == market and d["session"] == session
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            return None
        return rets if ok and len(rets) >= MIN_RANK_NAMES and all(np.isfinite(v) for v in rets.values()) else None

    def _stored_rank(self, ticker: str, market: str, session: str, bars: List[Dict]):
        """Rank and how it was found.  Without a rank the relative strength factor uses its benchmark formula, and the screen says so."""
        rets = self._read_ranks(market, session)
        if rets is None:
            return None, "NO_SCAN"
        ordered = sorted(rets.values())
        if ticker in rets:                       # the scan's own number, so a separate price request cannot move the rank
            return _rank_in(ordered, rets[ticker]), "UNIVERSE"
        own = _six_month_return(bars)
        return (None, "SHORT_HISTORY") if own is None else (_rank_in(ordered, own), "OUTSIDE_UNIVERSE")

    def scan(self, market: str = "US", tickers: Optional[List[str]] = None, record: bool = True, progress=None) -> Dict[str, Any]:
        started = time.time()
        if market == "US":
            tickers = tickers or sorted(set(self.terminal.lab.universe()["tickers"]) | {t for t in self.terminal.watchlist() if not t.startswith("^")})
            pre = self._us_scan_input(tickers, progress)
        else:
            tickers, pre = self._kr_scan_input(tickers, progress)
        day = self._session("US") if market == "US" else self.regime("KR").get("session")
        at_session = sum(1 for x in pre.values() if (lambda r: r and r[-1]["date"] == day)(_clean(x["bars"], day)))
        # US needs its benchmark at the session.  KR's index can skip a day: its relative return is then missing, not faked.
        bench_ok = market != "US" or all((lambda r: r and r[-1]["date"] == day)(_clean(x["bench"], day)) for x in list(pre.values())[:1])
        behind = market == "KR" and day < self._last_weekday_done()
        if record and (not bench_ok or behind or at_session < 0.9 * max(len(tickers), 1)):
            # Recording now would permanently store a day of blocked or partial snapshots.  Retried at the next slot.
            return {"status": "DATA_NOT_READY", "market": market, "session": day, "at_session": at_session, "tickers": len(tickers), "rows": [], "errors": {}}
        rows, cards, errors = [], [], {}
        for k, t in enumerate(tickers, 1):
            try:
                ctx = self.context(t, market, pre.get(t))
                if ctx.get("error"):
                    errors[t] = ctx["error"]
                    continue
                pos = self._position(t, market)
                for s in config.STRATEGIES:
                    c = self.card(ctx, s, pos)
                    cards.append(c)
                    rows.append({k2: c.get(k2) for k2 in ("ticker", "name", "strategy", "score", "band", "band_label", "action", "action_label", "color", "actionability", "coverage", "confidence", "entry_status", "price", "data_date")}
                                | {"domains": {d: v["score_100"] for d, v in c["domains"].items()}, "gates": [g["code"] for g in c["gates"]]})
            except Exception as exc:                     # one bad ticker never stops a scan; the type is recorded
                errors[t] = type(exc).__name__
            if progress and k % 25 == 0:
                progress("scores", k, len(tickers))
        session = self._session("US") if market == "US" else self.regime("KR").get("session")
        rec = None
        if record and cards:
            rec = self.ledger.append(session, market, cards)
        summary = {"status": "REAL" if cards else "UNAVAILABLE", "market": market, "session": session, "model_version": config.MODEL_VERSION, "tickers": len(tickers), "scored": len(cards), "errors": errors,
                   "elapsed_seconds": round(time.time() - started, 1), "ledger": rec, "generated_at": self.now().isoformat(), "rows": sorted(rows, key=lambda r: -(r["score"] or -1))}
        if not record:
            return summary                  # a dry run leaves the published ranking alone
        self.dir.mkdir(parents=True, exist_ok=True)
        self._write_ranks(market, day, pre)
        tmp = self.dir / f"latest_{market}.json.tmp"
        tmp.write_text(json.dumps(summary, ensure_ascii=False, default=str), encoding="utf-8")
        os.replace(tmp, self.dir / f"latest_{market}.json")
        return summary

    def _last_weekday_done(self) -> str:
        """Latest weekday whose KRX bar should be complete.  A holiday also lands here: no bar means no snapshot, which is right."""
        from markets.kr import calendar as krcal
        d = krcal.to_kst(self.now()).date()
        while d.weekday() >= 5 or not krcal.bar_is_complete(d.isoformat(), self.now()):
            d -= timedelta(days=1)
        return d.isoformat()

    def _kr_scan_input(self, tickers: Optional[List[str]], progress=None):
        import pandas as pd
        from markets.kr import acquisition, security_master, universe
        from markets.kr.market_data import YahooKRProvider
        now = self.now()
        master = security_master.load_master(self.base / "data" / "kr", now=now)["master"]
        self._kr_master = master
        prov = YahooKRProvider()
        cache_dir = self.base / "data" / "kr" / "cache"
        idx = acquisition.index_bars(prov, *acquisition.window(now, 800), now)
        if idx["KOSPI"].empty:
            raise RuntimeError("KOSPI index bars unavailable")
        sessions = pd.DatetimeIndex(idx["KOSPI"].index)
        latest = pd.Timestamp(self.regime("KR")["session"])
        if tickers:
            members = master[master["canonical_ticker"].isin(tickers)]
        else:
            elig = master[master["eligible"].astype(bool)]
            s, e = acquisition.window(now, 60)
            ub = acquisition.bars(prov, elig, s, e, now, cache_dir, "universe")
            uni = universe.build(elig, ub["bars"], sessions[sessions >= pd.Timestamp(s)], latest)
            members = master.set_index("canonical_ticker").loc[uni["members"]["ticker"]].reset_index()
        hs, he = acquisition.window(now, 800)
        hb = acquisition.bars(YahooKRProvider(), members, hs, he, now, cache_dir, "history")["bars"]
        bars: Dict[str, List[Dict]] = {}
        for code, g in hb.groupby("ticker"):
            rows = g.sort_values("date")
            bars[code] = [{"date": pd.Timestamp(r.date).strftime("%Y-%m-%d"), "open": _n(r.open), "high": _n(r.high), "low": _n(r.low), "close": _n(r.close), "adj_close": _n(r.adj_close), "volume": _n(r.volume)}
                          for r in rows.itertuples() if _n(r.close)]
        session = latest.strftime("%Y-%m-%d")
        above = [b[-1]["close"] > np.mean([x["close"] for x in b[-200:]]) for b in bars.values() if len(b) >= 200 and b[-1]["date"] == session]
        if len(above) >= 50:
            self.dir.mkdir(parents=True, exist_ok=True)
            (self.dir / "breadth_KR.json").write_text(json.dumps({"status": "REAL", "value": float(np.mean(above)), "n": len(above), "date": session, "source": "한국 유동성 상위 유니버스 (Yahoo)"}), encoding="utf-8")
            self._regime.pop("KR", None)
        with gzip.open(self.dir / "bars_KR.json.gz", "wt", encoding="utf-8") as fh:
            json.dump(bars, fh)
        codes = [c for c in members["canonical_ticker"] if c in bars]
        bench = self._history(["^KS11", "^KQ11"])["data"] or {}
        all_rows = {**bars, **{k: v for k, v in bench.items()}}
        pre = self._prefetch(codes, all_rows, "^KS11", session)
        for c in codes:
            ident = master[master["canonical_ticker"] == c].iloc[0]
            pre[c]["bench"] = bench.get("^KQ11" if ident["market"] == "KOSDAQ" else "^KS11") or []
        return codes, pre

    # ------------------------------------------------------------------ reports
    def _high_risk(self, market: str) -> Dict[str, Any]:
        """Korean names only: that is where the pattern was seen.  Added when read, so no score or record contains it."""
        if market != "KR":
            return {"session": None, "codes": set()}
        from terminal.qsf import kr_forward
        try:
            found = kr_forward.high_risk(self.base)
        except (OSError, ValueError, KeyError):
            return {"session": None, "codes": set()}
        return {"session": found["session"], "codes": set(found["codes"])}

    def _filing_marks(self, market: str) -> Dict[str, Any]:
        """Korean filings of the last 252 sessions, from the separate record.  Added when read, so no score or record contains it."""
        empty = {"session": None, "financing": set(), "buyback": set()}
        if market != "KR":
            return empty
        from terminal.qsf import kr_events_forward
        try:
            found = kr_events_forward.marks(self.base)
        except (OSError, ValueError, KeyError):
            return empty
        return {"session": found["session"], "financing": set(found["financing"]), "buyback": set(found["buyback"])}

    @staticmethod
    def _filing_mark(found: Dict[str, Any], ticker: str) -> Optional[Dict[str, Any]]:
        financing, buyback = ticker in found["financing"], ticker in found["buyback"]
        return {"session": found["session"], "financing": financing, "buyback": buyback} if financing or buyback else None

    def latest(self, market: str = "US") -> Dict[str, Any]:
        try:
            out = json.loads((self.dir / f"latest_{market}.json").read_text(encoding="utf-8"))
            risky = self._high_risk(market)
            filed = self._filing_marks(market)
            for r in out.get("rows") or []:
                if r.get("ticker") in risky["codes"]:
                    r["high_risk"] = {"session": risky["session"]}
                mark = self._filing_mark(filed, r.get("ticker"))
                if mark:
                    r["filing_events"] = mark
            return out
        except (OSError, ValueError):
            return {"status": "UNAVAILABLE", "market": market, "rows": [], "reason": "아직 스캔 기록이 없습니다."}

    def _loader(self, market: str) -> Callable[[str], List[Dict]]:
        if market == "US":
            p = self.terminal.lab.panel()

            def load(t):
                if p is None or t not in p.col:
                    return []
                o, c, a = p.series("open", t), p.series("close", t), p.series("adj_close", t)
                return [{"date": d, "open": _n(o[i]), "close": _n(c[i]), "adj_close": _n(a[i])} for i, d in enumerate(p.dates)]
            return load
        try:
            with gzip.open(self.dir / "bars_KR.json.gz", "rt", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            data = {}
        return lambda t: data.get(t) or []

    def validation(self) -> Dict[str, Any]:
        out = {"integrity": self.ledger.verify(), "cohorts": {}, "correlations": {}}
        for market in config.MARKETS:
            snaps = self.ledger.snapshots(market=market)
            loader = self._loader(market)
            bench = loader("SPY") if market == "US" else (self._history(["^KS11"])["data"] or {}).get("^KS11") or []
            for s in config.STRATEGIES:
                key = f"{market}_{s}"
                out["cohorts"][key] = ledger.validate(snaps, market, s, loader, bench)
                out["correlations"][key] = ledger.factor_correlations([x for x in snaps if x["strategy"] == s])
        return out


def _n(v) -> Optional[float]:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return v if np.isfinite(v) else None


def _why(c: Dict[str, Any]) -> str:
    """One traceable sentence per action, built only from fields of this card (spec 17)."""
    if c["actionability"] == "INSUFFICIENT_DATA":
        return f"데이터 반영률 {c['coverage'] * 100:.0f}%로 기준에 못 미쳐 판단하지 않습니다. 빠진 요인: {', '.join(c['missing'][:4])}"
    head = f"{c['score']:.1f}점 ({c['band_label']})"
    good = c["top_positive"][0]["text"] if c["top_positive"] else "뚜렷한 강점 요인 없음"
    bad = c["top_negative"][0]["text"] if c["top_negative"] else "뚜렷한 약점 요인 없음"
    if c["actionability"] == "BLOCKED":
        return f"{head}이지만 위험 게이트로 차단: {c['gates'][0]['text']}"
    if c["action"] == "BUY":
        return f"{head}. 지금 진입을 보는 이유: {c['entry']['reason']} 강점: {good}"
    if c["action"] in ("HOLD", "WATCH"):
        inv = c["holding"].get("invalidation") or []
        return f"{head}. 유지되어야 할 조건: {inv[0] if inv else '없음'}. 약점: {bad}"
    return f"{head}. 주요 감점: {bad}"
