"""QSF data assembly and orchestration: single-stock evaluation, universe scan, recording, validation reports.

Markets stay isolated: the US path never reads Korean data and the reverse (no VIX or SPY in a Korean score).
P6-11B is read as a separate reference from its run artifacts and is never merged into a QSF score.
"""
import functools
import gzip
import hashlib
import json
import os
import threading
import time
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

from markets import session_data
from terminal import sources as default_sources
from terminal.cache import FileCache
from terminal.qsf import config, earnings_estimate, engine, events, fundamentals, holding, ledger, technicals
from terminal.qsf.views import ScreenViews, _n
from utils import nyse_calendar

_LAZY = threading.Lock()    # one thread at a time builds a thing the whole process then shares (the Korean stock list)
KRX_SHARE_DAYS_KEPT = 3     # listed-share tables kept in memory, newest first asked; the server once kept one per day for its whole life
KR_MIN_UNIVERSE = 200       # a whole-market Korean scan with fewer stocks than this is a partial day, not a day (the universe is 300)
# "facts": US annual statements are read again at each day's first run, so a new 10-K is scored the next morning (it waited up to 7 days).
# 20 hours, not 24: a copy stored at 07:15 must be old enough for the next day's 07:10 run.  Korean statements keep 7 days ("kr_facts").
REGIME_MEMO_SECONDS = 30 * 60        # how long the process reuses a computed regime; its inputs have their own cache times below
TTL = {"bars": 1800, "regime": 3600, "facts": 20 * 3600, "kr_facts": 7 * 86400, "subm": 20 * 3600, "info": 7 * 86400, "earn": 3 * 86400, "form4": 3650 * 86400}
REGIME_FRESH_DAYS = 5
EARN_NONE_TTL = 6 * 3600           # "the provider lists no date" is kept this long: each morning's scan still asks, a lookup or a retry an hour later does not
EARN_PAUSE_S = 15 * 60             # after the provider refuses for too many requests, earnings dates are not asked for this long
RATE_LIMITED = ("YFRateLimitError",)


def _stale(what: str, res: Dict[str, Any]) -> List[Dict[str, Any]]:
    """One entry when a stored copy stood in for a failed request (``FileCache`` status STALE): what it is, when it was fetched,
    how old it is and why the new request failed.  The score still reads the copy; the card and the record say that it did."""
    if (res or {}).get("status") != "STALE":
        return []
    age = res.get("age_s")
    return [{"what": what, "fetched_at": res.get("fetched_at"), "age_days": None if age is None else round(age / 86400, 1), "error": res.get("error")}]


def _kr_fund_key(code: str, fiscal_month: int) -> str:
    """December companies keep their stored statements; the few others were read with the wrong year and get a key of their own."""
    return f"krfund3:{code}" if fiscal_month == 12 else f"krfund3:{code}:fm{fiscal_month:02d}"
UNAVAILABLE_KR = {"vkospi": "VKOSPI는 합법적인 무료 공개 출처에서 안정적으로 받을 수 없어 사용하지 않습니다.",
                  "kr_credit": "한국은행 ECOS에서 회사채·국고채 금리를 받지 못했습니다(키가 없거나 응답 없음)."}
# Korean credit conditions, read the way the US high-yield spread is: 3-year AA- corporate yield less the 3-year treasury yield, daily,
# Bank of Korea ECOS table 817Y002, placed within its own last ten years.  A research default fixed in advance, not a fitted choice.
KR_CREDIT = {"stat": "817Y002", "corporate": "010300000", "treasury": "010200000", "years": 10, "min_rows": 250}


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


def _one_regime(scan):
    """A scan starts from a fresh regime and keeps it to the end, however long the scan runs: every stock of one recorded day is
    scored against the same market state."""
    @functools.wraps(scan)
    def run(self, *args, **kwargs):
        held, self._regime_hold = self._regime_hold, True
        self._regime.clear()
        self._regime_at.clear()
        try:
            return scan(self, *args, **kwargs)
        finally:
            self._regime_hold = held
    return run


class QSF(ScreenViews):
    def __init__(self, base: Path, src=default_sources, now: Callable[[], datetime] = None, terminal: Any = None, dart: Any = None, kr_master: Any = None):
        self.base = Path(base)
        self.src = src
        self.now = now or (lambda: datetime.now(timezone.utc))
        self._download_failures: List[str] = []           # price requests of the current US scan that failed outright
        self._download_chunks: Optional[int] = None
        self.dir = self.base / "data" / "qsf"
        self.cache = FileCache(self.dir / "cache")
        self._sector_memo: Dict[str, Any] = {}
        self.ledger = ledger.Ledger(self.base)
        self._terminal = terminal
        self._dart = dart
        self._kr_master = kr_master
        self._regime: Dict[str, Dict] = {}
        self._regime_at: Dict[str, datetime] = {}
        self._regime_hold = False
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
        return session_data.latest_complete_date(index_rows or [], self.now()) or (self.now().date() - timedelta(days=1)).isoformat()

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
            return session_data.enough(session_data.count_at((data or {}).values(), session), len(chunk))
        old = self.cache.read(key)
        if old is not None and ready(old["data"]):
            return old["data"]
        try:
            data = self.src.yahoo_history(chunk, "2y") or {}
        except Exception as exc:            # a cut connection (the Mac asleep, DNS) is told apart from a day Yahoo has not published
            self._download_failures.append(type(exc).__name__)
            return {}
        if not data:
            self._download_failures.append("EMPTY_REPLY")
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
        """Reused for ``REGIME_MEMO_SECONDS``, and for the whole of a scan.  It was once kept for the life of the process: a server
        left running past a session went on scoring single stocks against the old regime and the old Korean session (2026-11-15)."""
        hit, made = self._regime.get(market), self._regime_at.get(market)
        if hit is not None and (self._regime_hold or made is None or (self.now() - made).total_seconds() < REGIME_MEMO_SECONDS):
            return hit
        value = self._regime_us() if market == "US" else self._regime_kr()
        self._regime[market], self._regime_at[market] = value, self.now()
        return value

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

    def _kr_credit(self) -> Dict[str, Any]:
        """The spread's place in its own history; a narrow spread scores high.  Missing key, failed request or short history: UNAVAILABLE."""
        k = KR_CREDIT
        end = self.now().date()
        start = end - timedelta(days=365 * k["years"])

        def fetch():
            a, b = (self.src.ecos_series(k["stat"], "D", start.strftime("%Y%m%d"), end.strftime("%Y%m%d"), [k[name]]) for name in ("corporate", "treasury"))
            return {"corporate": a, "treasury": b}
        res = self.cache.cached("ecos:kr_credit_spread", TTL["regime"], fetch)
        data = res["data"] or {}
        gov = {d: v for d, v in data.get("treasury") or [] if v is not None}
        rows = [{"date": d, "close": v - gov[d]} for d, v in data.get("corporate") or [] if v is not None and d in gov]
        if len(rows) < k["min_rows"]:
            return {"status": "UNAVAILABLE", "reason": UNAVAILABLE_KR["kr_credit"] if not rows else "회사채 스프레드 이력 부족"}
        lv = self._level(rows)
        return {**lv, "normalized": 1 - lv["percentile"], "source": f"한국은행 ECOS {k['stat']} (회사채 3년 AA- − 국고채 3년, {rows[0]['date']}부터)",
                "text": f"회사채(AA-, 3년) − 국고채(3년) 스프레드 {lv['value']:.2f}%p, 최근 {k['years']}년({lv['n']}개 관측) 내 위치 {lv['percentile'] * 100:.0f}% (좁을수록 신용 여건 양호)"}

    def _regime_kr(self) -> Dict[str, Any]:
        # Yahoo's index series can skip a session that stocks have, so a large constituent also marks the calendar.
        hist = self._history(["^KS11", "^KQ11", "KRW=X", "005930.KS"], "2y")
        data = hist["data"] or {}
        session = self._session("KR", sorted((data.get("^KS11") or []) + (data.get("005930.KS") or []), key=lambda r: r["date"]))
        ks, fx = _clean(data.get("^KS11") or [], session), data.get("KRW=X") or []
        out: Dict[str, Any] = {"index": self._index(ks, "KOSPI"), "kosdaq": self._index(_clean(data.get("^KQ11") or [], session), "KOSDAQ"),
                               "vkospi": {"status": "UNAVAILABLE", "reason": UNAVAILABLE_KR["vkospi"]}, "kr_credit": self._kr_credit(),
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
        res = self.cache.cached(f"annual4:{default_sources.facts_key(ticker, cik)}", TTL["facts"], lambda: self._annual(ticker, cik))
        sres = self._us_subm_res(cik)
        subm = sres["data"]
        if res["data"] is None:
            return {"status": "UNAVAILABLE", "reason": f"SEC 재무 조회 실패 ({res.get('error')})", "cik": cik}
        info = self.cache.cached(f"info:{ticker}", TTL["info"], lambda: self.src.yahoo_info(ticker))["data"] or {}
        fin = fundamentals.is_financial_sic((subm or {}).get("sic"))
        m = fundamentals.metrics(res["data"], bars[-1]["close"], as_of, is_financial=fin, shares=fundamentals.us_total_shares(info, bars[-1]["close"], res["data"]), insider_pct=info.get("heldPercentInsiders"))
        old = _stale("SEC 재무제표", res)
        return {**m, "cik": cik, "name": fundamentals.us_display_name(info.get("longName"), info.get("shortName"), (subm or {}).get("name")), "sector": info.get("sector"),
                **({"stale_inputs": old} if old else {})}

    def _annual(self, ticker: str, cik: str) -> Dict[str, Any]:
        return fundamentals.drop_stale_series(fundamentals.extract_us(default_sources.facts_with_predecessors(ticker, cik, self.src.sec_companyfacts)))

    def _us_subm(self, cik: str) -> Optional[Dict[str, Any]]:
        return self._us_subm_res(cik)["data"]

    def _us_subm_res(self, cik: str) -> Dict[str, Any]:
        """The stored SEC filing list with its cache status, so a list that could not be refreshed is named as such."""
        def fetch():
            s = self.src.sec_submissions(cik)
            rows = events.recent_filings(s)
            # Banks file thousands of prospectuses, so the list is filtered by form rather than cut by position.
            return {"name": s.get("name"), "sic": s.get("sic"), "oldest": rows[-1]["date"] if rows else None, "truncated": bool((s.get("filings") or {}).get("files")), "filings": [r for r in rows if r["form"] in events.KEPT_FORMS]}
        return self.cache.cached(f"submforms:{cik}", TTL["subm"], fetch)

    def _us_events(self, cik: Optional[str], as_of: str) -> Dict[str, Any]:
        if not cik:
            return {"status": "UNAVAILABLE", "reason": "SEC CIK 없음"}
        sres = self._us_subm_res(cik)
        subm = sres["data"]
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
        old = _stale("SEC 공시 목록", sres)
        if old:
            ev["stale_inputs"] = old
        return ev

    def _earnings(self, ticker: str, market: str, as_of: str, code: Optional[str] = None, cik: Optional[str] = None) -> Dict[str, Any]:
        """Yahoo's calendar date when it has one ahead; otherwise an estimate from the company's own past dates, marked as such."""
        key = f"earn:{ticker}"

        def fetch():
            got = self.src.yahoo_earnings_dates(ticker)
            if got:
                return got
            # No date listed.  An empty answer is not stored by the cache, so about 200 Korean and 260 US stocks were asked again
            # at every scan and lookup.  It is stored as a marker instead, unless a date still ahead is on file: that case keeps
            # its old path (the stored date stays in use and the provider is asked again next time).
            kept = (self.cache.read(key) or {}).get("data")
            return [] if isinstance(kept, list) and any(d > as_of for d in kept) else {"none": True}
        kept = self.cache.read(key)
        none_on_file = bool(kept) and isinstance(kept.get("data"), dict)
        if getattr(self, "_earn_pause", 0.0) > time.time():        # the provider refused a moment ago: what is on file, no request
            days = (kept or {}).get("data")
        else:
            res = self.cache.cached(key, EARN_NONE_TTL if none_on_file else TTL["earn"], fetch)
            days = res["data"]
            if res.get("error") in RATE_LIMITED:
                self._earn_pause = time.time() + EARN_PAUSE_S
        if isinstance(days, dict):                         # the marker: asked, none listed
            days = []
        step = holding.stepper(market)

        def sessions_to(target: str) -> int:
            d, n, end = date.fromisoformat(as_of), 0, date.fromisoformat(target)
            while d < end and n < 300:
                d, n = step(d), n + 1
            return n
        nxt = next((d for d in (days or []) if d > as_of), None)
        if nxt:
            return {"date": nxt, "sessions": sessions_to(nxt), "source": "Yahoo 실적 일정 (회사 확정 전에는 추정치)"}
        try:
            past, source = self._past_result_dates(market, as_of, code, cik)
        except Exception:
            past, source = [], None
        est = earnings_estimate.next_estimate(past, as_of) if past else None
        if not est:
            return {"sessions": None}
        return {"date": est["date"], "sessions": 0 if est["overdue"] else sessions_to(est["date"]), "basis": "ESTIMATE", "from": est["from"], "overdue": est["overdue"], "source": source}

    def _past_result_dates(self, market: str, as_of: str, code: Optional[str], cik: Optional[str]) -> Tuple[List[str], Optional[str]]:
        """US: 8-K item 2.02 dates from the stored SEC list (no extra request).  Korea: preliminary results or, without any, periodic
        report dates from two DART list requests kept for a week, joined with the daily list so a new disclosure is seen the next day."""
        if market == "US":
            if not cik:
                return [], None
            return earnings_estimate.us_result_dates((self._us_subm(cik) or {}).get("filings")), "SEC 8-K 실적 공시일(항목 2.02) 기준 추정"
        if not code or not self.dart.configured:
            return [], None
        corp = self._corp_code(code)
        if not corp:
            return [], None
        end = as_of.replace("-", "")
        bgn = (date.fromisoformat(as_of) - timedelta(days=earnings_estimate.LOOKBACK_DAYS + 30)).strftime("%Y%m%d")

        def fetch_history():
            rows = []
            for extra in ({"pblntf_detail_ty": "I002"}, {"pblntf_ty": "A"}):         # fair disclosures (preliminary results), periodic reports
                body = self.dart._get("list.json", corp_code=corp, bgn_de=bgn, end_de=end, page_count=100, **extra).json()
                if body.get("status") not in ("000", "013"):                          # 013: no filing of that kind.  Anything else is not an answer
                    raise RuntimeError("DART list unavailable")
                rows += body.get("list") or []
            # a company with no such filing is stored as one empty row, so it is not asked again every scan
            return [{"report_nm": r.get("report_nm"), "rcept_dt": r.get("rcept_dt")} for r in rows] or [{"report_nm": "", "rcept_dt": ""}]
        rows = list(self.cache.cached(f"krearn:{corp}", TTL["kr_facts"], fetch_history)["data"] or [])
        daily = self.cache.read(f"krlist:{corp}")                                    # written by the day's filing check; read, never fetched here
        rows += [{"report_nm": r.get("report_nm"), "rcept_dt": r.get("rcept_dt")} for r in ((daily or {}).get("data") or [])]
        got = earnings_estimate.kr_result_dates(rows, as_of)
        return got["dates"], "DART 잠정실적 공시일 기준 추정" if got["kind"] == "PRELIMINARY" else "DART 정기보고서 제출일 기준 추정"

    # KR: every field below is OpenDART; without a key the factors stay missing, they are not scored as zero.
    @property
    def dart(self):
        if self._dart is None:
            from markets.kr.dart import OpenDartClient
            self._dart = OpenDartClient()
        return self._dart

    def _kr_master_file_time(self) -> Optional[int]:
        try:
            return (self.base / "data" / "kr" / "security_master" / "LATEST.json").stat().st_mtime_ns
        except OSError:
            return None

    def _kr_identity(self, code: str) -> Optional[Dict[str, Any]]:
        """The list is read once and shared.  A list this object read from disk is read again when a newer snapshot has been stored
        since (the morning scan stores one): the server kept its first list until it was restarted, so a newly listed stock stayed
        unknown.  A list handed in by the caller is never replaced."""
        with _LAZY:
            mine, on_file = getattr(self, "_kr_master_time", None), self._kr_master_file_time()
            if self._kr_master is None or (mine is not None and on_file is not None and on_file != mine):
                from markets.kr import security_master
                self._kr_master = security_master.load_master(self.base / "data" / "kr", now=self.now())["master"]
                self._kr_master_time = self._kr_master_file_time()        # after the load: loading can itself store a newer snapshot
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
        got = self._krx_share_cache.get(as_of)
        if got is None:
            from terminal.qsf import krx_history
            got = krx_history.listed_shares(self.base / "research_data" / "krx", as_of)
            while len(self._krx_share_cache) >= KRX_SHARE_DAYS_KEPT:
                self._krx_share_cache.pop(next(iter(self._krx_share_cache)), None)
            self._krx_share_cache[as_of] = got
        return got

    def _kr_fund_events(self, code: str, ident: Dict, bars: List[Dict], as_of: str) -> Dict[str, Any]:
        if not self.dart.configured:
            reason = "OPENDART_API_KEY가 없어 한국 재무·공시를 평가하지 않았습니다."
            return {"fund": {"status": "UNAVAILABLE", "reason": reason}, "events": {"status": "UNAVAILABLE", "reason": reason}}
        corp = self._corp_code(code)
        if not corp:
            return {"fund": {"status": "UNAVAILABLE", "reason": "DART 고유번호 없음"}, "events": {"status": "UNAVAILABLE", "reason": "DART 고유번호 없음"}}
        klass = ident.get("industry_class") or "NON_FINANCIAL"
        fm = fundamentals.fiscal_month_of(ident.get("fiscal_month"))
        res = self.cache.cached(_kr_fund_key(code, fm), TTL["kr_facts"], lambda: fundamentals.extract_kr(fundamentals.load_kr_statements(corp, code, klass, date.fromisoformat(as_of), self.dart, fiscal_month=fm)))
        info = self.cache.cached(f"info:{ident.get('yahoo_symbol')}", TTL["info"], lambda: self.src.yahoo_info(ident["yahoo_symbol"]))["data"] or {}
        fund = {"status": "UNAVAILABLE", "reason": f"DART 재무 조회 실패 ({res.get('error')})"}
        if res["data"]:
            fund = fundamentals.blank_mixed_cash_flow(fundamentals.metrics(res["data"], bars[-1]["close"], as_of, is_financial=fundamentals.is_financial_kr(klass, res["data"]), shares=self._krx_shares(as_of).get(code) or info.get("sharesOutstanding"),
                                                                           source="OpenDART 사업보고서", insider_pct=info.get("heldPercentInsiders")), code)
        def fetch_list():
            bgn = (date.fromisoformat(as_of) - timedelta(days=events.WINDOW_LONG)).strftime("%Y%m%d")
            r = self.dart._get("list.json", corp_code=corp, bgn_de=bgn, end_de=as_of.replace("-", ""), page_count=100).json()
            return r.get("list") or []
        rep = self.cache.cached(f"krlist:{corp}", TTL["subm"], fetch_list)
        ev = events.classify_kr(rep["data"], as_of) if rep["data"] is not None else {"status": "UNAVAILABLE", "reason": "DART 공시 조회 실패"}
        old_fund, old_list = _stale("DART 재무제표", res) if res["data"] else [], _stale("DART 공시 목록", rep)
        if old_fund:
            fund["stale_inputs"] = old_fund
        if old_list and rep["data"] is not None:
            ev["stale_inputs"] = old_list
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
        fm = fundamentals.fiscal_month_of(ident.get("fiscal_month"))
        res = self.cache.cached(_kr_fund_key(code, fm), TTL["kr_facts"], lambda: fundamentals.extract_kr(fundamentals.load_kr_statements(corp, code, klass, as_of, self.dart, fiscal_month=fm)))

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

    def _krx_bars(self, bars: Dict[str, List[Dict]]) -> Tuple[Dict[str, List[Dict]], Dict[str, Any]]:
        """Korean bars rebuilt from the KRX daily snapshots (``kr_bars``).  Without any snapshot the Yahoo bars stay, and the summary says so."""
        from terminal.qsf import kr_bars
        try:
            pan = kr_bars.panel(self.base, self.now().date())
        except Exception as exc:                                   # a broken cache must not stop scoring; the summary names it
            return bars, {"stocks": len(bars), "by_source": {"YAHOO": len(bars)}, "error": type(exc).__name__}
        out, infos = {}, {}
        for code, rows in bars.items():
            out[code], infos[code] = kr_bars.rebuild(code, rows, pan)
        return out, kr_bars.summary(infos)

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
            if market == "KR" and bars:
                bars = self._krx_bars({ticker: bars})[0][ticker]
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
            ctx["earnings"] = self._earnings(sym, market, session, code=ticker, cik=(ctx.get("fund") or {}).get("cik"))
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
        old = list((ctx.get("fund") or {}).get("stale_inputs") or []) + list((ctx.get("events") or {}).get("stale_inputs") or [])
        if old:                 # scored from stored copies because the new request failed: said on the card and in the record
            out["provenance"]["stale"] = old
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
        return {"status": "REAL", "ticker": ticker, "market": market, "name": ctx.get("name"), "rank_basis": ctx["rank_basis"], "high_risk": {"session": risky["session"]} if ticker in risky["codes"] else None,
                "risk_grade": self._risk_grade(ticker, market), "filing_events": self._filing_mark(self._filing_marks(market), ticker), "cards": cards, "held_strategy": own, "p6_reference": self.p6_reference(ticker) if market == "US" else None}

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
        self._download_failures, self._download_chunks = [], (len(symbols) + 99) // 100
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

    @_one_regime
    def scan(self, market: str = "US", tickers: Optional[List[str]] = None, record: bool = True, progress=None, side_files: bool = True,
             publish: bool = True) -> Dict[str, Any]:
        """``side_files=False`` (Korea): the scan leaves the live breadth and bar files alone, for a separate record that scores another
        set of stocks (``kr_cap_universe``).  It cannot be combined with ``record``.

        ``publish=False``: the scan is scored and recorded but the newest-scan file and its ranks stay as they are.  The command
        line passes it for a scan of named stocks, which would otherwise become "the scan" every screen and the news record read."""
        if record and not side_files:
            raise ValueError("a recorded scan writes its side files")
        started = time.time()
        self._download_failures, self._download_chunks = [], None          # only this scan's requests count
        whole_universe = not tickers
        if market == "US":
            tickers = tickers or sorted(set(self.terminal.lab.universe()["tickers"]) | {t for t in self.terminal.watchlist() if not t.startswith("^")})
            pre = self._us_scan_input(tickers, progress)
        else:
            tickers, pre = self._kr_scan_input(tickers, progress, side_files)
        day = self._session("US") if market == "US" else self.regime("KR").get("session")
        at_session = session_data.count_at((x["bars"] for x in pre.values()), day)
        # US needs its benchmark at the session.  KR's index can skip a day: its relative return is then missing, not faked.
        bench_ok = market != "US" or all(session_data.rows_at(x["bench"], day) for x in list(pre.values())[:1])
        behind = market == "KR" and day < self._last_weekday_done()
        # The Korean universe is built from the day's bars.  From a partial download it comes out with a handful of stocks, all of
        # them at the session, so the share check below passes: on 2026-11-11 a scan of two stocks was recorded as the day.
        small = market == "KR" and whole_universe and len(tickers) < KR_MIN_UNIVERSE
        # Korea, whole universe: the share is taken of the stocks asked for, not of those that came back.
        asked = max(len(tickers), getattr(self, "_kr_target", None) or 0) if market == "KR" and whole_universe else len(tickers)
        verdict = session_data.record_verdict(asked, at_session, self._download_failures, bench_ok, behind, small)
        if record and not verdict["ready"]:
            # Recording now would permanently store a day of blocked or partial snapshots.  Retried at the next slot.
            return {"status": "DATA_NOT_READY", "market": market, "session": day, "at_session": at_session, "tickers": len(tickers), "asked": asked, "rows": [], "errors": {},
                    "recorded_before": self.ledger.has_session(day, market), **self._not_ready_reason(pre, day, verdict)}
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
        aged = {c["ticker"]: max((x.get("age_days") or 0) for x in c["provenance"]["stale"]) for c in cards if c["provenance"].get("stale")}
        summary = {"status": "REAL" if cards else "UNAVAILABLE", "market": market, "session": session, "model_version": config.MODEL_VERSION, "tickers": len(tickers), "scored": len(cards), "errors": errors,
                   **({"stale_inputs": {"stocks": len(aged), "oldest_days": max(aged.values()), "tickers": sorted(aged)[:20]}} if aged else {}),
                   "elapsed_seconds": round(time.time() - started, 1), "ledger": rec, "generated_at": self.now().isoformat(),
                   **({"price_source": self._kr_bars_info} if market == "KR" and getattr(self, "_kr_bars_info", None) else {}),
                   **({"universe": self._kr_universe_info} if market == "KR" and getattr(self, "_kr_universe_info", None) else {}), "rows": sorted(rows, key=lambda r: -(r["score"] or -1))}
        if not record or not publish:
            return summary                  # a dry run leaves the published ranking alone
        self.dir.mkdir(parents=True, exist_ok=True)
        self._write_ranks(market, day, pre)
        tmp = self.dir / f"latest_{market}.json.tmp"
        tmp.write_text(json.dumps(summary, ensure_ascii=False, default=str), encoding="utf-8")
        os.replace(tmp, self.dir / f"latest_{market}.json")
        return summary

    def _not_ready_reason(self, pre: Dict[str, Dict], day: str, verdict: Dict[str, Any]) -> Dict[str, Any]:
        """Why a scan was not recorded, with what a person needs to tell the cases apart.  The reason itself is
        ``session_data.record_verdict``'s: DOWNLOAD_FAILED (requests failed outright, the day may well be published), KR_BEHIND,
        UNIVERSE_TOO_SMALL, NOT_PUBLISHED (replies came back without the session for too many stocks) or BENCHMARK_NOT_READY."""
        failed = list(getattr(self, "_download_failures", []) or [])
        last = Counter(_clean(x["bars"], day)[-1]["date"] for x in pre.values() if _clean(x["bars"], day))
        return {"reason": verdict["reason"], "download": {"chunks": getattr(self, "_download_chunks", None), "failed": len(failed), "kinds": dict(Counter(failed))},
                "last_dates": dict(last.most_common(3)), "no_bars": sum(1 for x in pre.values() if not _clean(x["bars"], day))}

    def _last_weekday_done(self) -> str:
        """Latest weekday whose KRX bar should be complete.  A holiday also lands here: no bar means no snapshot, which is right."""
        from markets.kr import calendar as krcal
        d = krcal.to_kst(self.now()).date()
        while d.weekday() >= 5 or not krcal.bar_is_complete(d.isoformat(), self.now()):
            d -= timedelta(days=1)
        return d.isoformat()

    def _kr_scan_input(self, tickers: Optional[List[str]], progress=None, side_files: bool = True):
        import pandas as pd
        from markets.kr import acquisition, security_master, universe
        from markets.kr.market_data import YahooKRProvider
        now = self.now()
        master = security_master.load_master(self.base / "data" / "kr", now=now)["master"]
        self._kr_master = master
        self._kr_master_time = self._kr_master_file_time()
        prov = YahooKRProvider()
        cache_dir = self.base / "data" / "kr" / "cache"
        idx = acquisition.index_bars(prov, *acquisition.window(now, 800), now)
        if idx["KOSPI"].empty:
            raise RuntimeError("KOSPI index bars unavailable")
        sessions = pd.DatetimeIndex(idx["KOSPI"].index)
        latest = pd.Timestamp(self.regime("KR")["session"])
        self._kr_universe_info = None
        if tickers:
            members = master[master["canonical_ticker"].isin(tickers)]
        elif config.KR_UNIVERSE == "MARKET_CAP":
            self._refresh_krx_days(latest.strftime("%Y-%m-%d"))
            codes, self._kr_universe_info = self.kr_market_cap_universe(latest.strftime("%Y-%m-%d"))
            known = set(master["canonical_ticker"])
            members = master.set_index("canonical_ticker").loc[[c for c in codes if c in known]].reset_index()
        else:
            members = self.kr_traded_value_universe(master, sessions, latest, now)
            self._kr_universe_info = {"rule": "TRADED_VALUE", "members": int(len(members))}
        hs, he = acquisition.window(now, 800)
        got = acquisition.bars(YahooKRProvider(), members, hs, he, now, cache_dir, "history", fresh_at=latest, whole=not tickers)
        hb = got["bars"]
        # The stocks asked for, and the requests that failed outright.  The scan used to count only the stocks it received: with
        # one request of fifty lost it scored 250 of 300, found all 250 at the session and recorded the day (user decision 2026-11-15).
        self._kr_target = None if tickers else int(len(members))
        self._download_chunks = (len(members) + 49) // 50
        self._download_failures += [str(e.get("error") or "EMPTY_REPLY") for e in got.get("events") or [] if e.get("kind") == "chunk_failed"]
        bars: Dict[str, List[Dict]] = {}
        for code, g in hb.groupby("ticker"):
            rows = g.sort_values("date")
            bars[code] = [{"date": pd.Timestamp(r.date).strftime("%Y-%m-%d"), "open": _n(r.open), "high": _n(r.high), "low": _n(r.low), "close": _n(r.close), "adj_close": _n(r.adj_close), "volume": _n(r.volume)}
                          for r in rows.itertuples() if _n(r.close)]
        session = latest.strftime("%Y-%m-%d")
        bars, self._kr_bars_info = self._krx_bars(bars)          # QSF-1.1.8: KRX official daily data, Yahoo only for days KRX has not published
        above = [b[-1]["close"] > np.mean([x["close"] for x in b[-200:]]) for b in bars.values() if len(b) >= 200 and b[-1]["date"] == session]
        # Breadth and the bar store describe the whole universe.  A scan of named stocks used to replace both: on 2026-11-15 a
        # two-stock comparison run left the Korean bar store with two stocks, and the map drew two of 300 until the next full scan.
        if len(above) >= 50 and side_files and not tickers:
            self.dir.mkdir(parents=True, exist_ok=True)
            source = "한국 시가총액 상위 300 (스캔 대상)" if (self._kr_universe_info or {}).get("rule") == "MARKET_CAP" else "한국 유동성 상위 유니버스 (Yahoo)"
            (self.dir / "breadth_KR.json").write_text(json.dumps({"status": "REAL", "value": float(np.mean(above)), "n": len(above), "date": session, "source": source}), encoding="utf-8")
            self._regime.pop("KR", None)
        if side_files and not tickers:
            tmp = self.dir / f"bars_KR.json.gz.{os.getpid()}.tmp"      # written whole, then swapped in: a run killed here leaves the old file
            with gzip.open(tmp, "wt", encoding="utf-8") as fh:
                json.dump(bars, fh)
            os.replace(tmp, self.dir / "bars_KR.json.gz")
        codes = [c for c in members["canonical_ticker"] if c in bars]
        bench = self._history(["^KS11", "^KQ11"])["data"] or {}
        all_rows = {**bars, **{k: v for k, v in bench.items()}}
        pre = self._prefetch(codes, all_rows, "^KS11", session)
        for c in codes:
            ident = master[master["canonical_ticker"] == c].iloc[0]
            pre[c]["bench"] = bench.get("^KQ11" if ident["market"] == "KOSDAQ" else "^KS11") or []
        return codes, pre

    # ------------------------------------------------------------------ Korean universes
    def kr_traded_value_universe(self, master, sessions, latest, now):
        """The 300 most traded stocks over 20 sessions: the live universe until QSF-1.2.1, kept for the record that still scores it."""
        import pandas as pd
        from markets.kr import acquisition, universe
        from markets.kr.market_data import YahooKRProvider
        elig = master[master["eligible"].astype(bool)]
        s, e = acquisition.window(now, 60)
        ub = acquisition.bars(YahooKRProvider(), elig, s, e, now, self.base / "data" / "kr" / "cache", "universe", fresh_at=latest)
        uni = universe.build(elig, ub["bars"], sessions[sessions >= pd.Timestamp(s)], latest)
        return master.set_index("canonical_ticker").loc[uni["members"]["ticker"]].reset_index()

    def kr_former_universe_codes(self) -> List[str]:
        """Codes of the former live universe for the current Korean session (reports/QSF_KR_TRADED_UNIVERSE_PROTOCOL.md)."""
        import pandas as pd
        from markets.kr import acquisition, security_master
        from markets.kr.market_data import YahooKRProvider
        now = self.now()
        master = security_master.load_master(self.base / "data" / "kr", now=now)["master"]
        idx = acquisition.index_bars(YahooKRProvider(), *acquisition.window(now, 800), now)
        if idx["KOSPI"].empty:
            raise RuntimeError("KOSPI index bars unavailable")
        latest = pd.Timestamp(self.regime("KR")["session"])
        return list(self.kr_traded_value_universe(master, pd.DatetimeIndex(idx["KOSPI"].index), latest, now)["canonical_ticker"])

    def kr_market_cap_universe(self, session: str) -> Tuple[List[str], Dict[str, Any]]:
        """The 300 largest eligible companies by market value on the newest KRX day on file up to ``session``, by the rule of the
        market-value record (``kr_cap_universe.members``).  No KRX day within KR_UNIVERSE_MAX_AGE_DAYS: no universe, and the scan
        is not run on something else instead."""
        from terminal.qsf import kr_cap_universe as cu, research_kr_live
        root = self.base / cu.KRX
        days = sorted((p.name[:10] for p in (root / "KOSPI").glob("*.json.gz") if p.name[:10] <= session), reverse=True)
        day = next((d for d in days[:15] if cu.day_rows(root, d)), None)
        if day is None or (date.fromisoformat(session) - date.fromisoformat(day)).days > config.KR_UNIVERSE_MAX_AGE_DAYS:
            raise RuntimeError("KRX daily data unavailable for the market-value universe")
        extra_file = self.base / research_kr_live.DATA / "industry.json"
        try:
            extra = json.loads(extra_file.read_text(encoding="utf-8")) if extra_file.exists() else {}
        except (OSError, ValueError):
            extra = {}
        klass_of = {**{c: v["class"] for c, v in extra.items()}, **research_kr_live._klass_from_master(self.base)}
        mem = cu.members(root, day, klass_of)
        return [m["code"] for m in mem], {"rule": "MARKET_CAP", "krx_day": day, "members": len(mem), "size": cu.SIZE, "same_day": day == session}

    def _refresh_krx_days(self, session: str) -> None:
        """Best effort, live source only: the session's own KRX day is usually published hours before the morning scan and not yet
        on file.  With it the universe and the last bar come from the exchange.  Any failure leaves what is on file."""
        key = os.environ.get("KRX_API_KEY")
        if self.src is not default_sources or not key:
            return
        try:
            import requests
            from terminal.qsf import kr_cap_universe as cu, krx_history as kh
            day = date.fromisoformat(session)
            kh.download(self.base / cu.KRX, key, requests.get, (day - timedelta(days=7)).isoformat(), session, log=lambda *_: None,
                        keep_empty_before=(day - timedelta(days=7)).isoformat())
        except Exception:
            pass


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
