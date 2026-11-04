"""Screen data for the terminal (TERMINAL-1 §2).  Every payload carries status / source / as-of.

The terminal only READS model artifacts (runs/, tracking/); it never writes to them.
"""
import json
import math
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

    # ---------------------------------------------------------------- helpers
    def _intraday(self, last_date: Optional[str]) -> bool:
        """True when the last bar is today's US session and the regular close (16:00 ET, +15 min for data
        settlement) has not passed: the value is a delayed intraday price, not a final close."""
        if not last_date:
            return False
        et = self.now().astimezone(ZoneInfo("America/New_York"))
        return last_date == et.strftime("%Y-%m-%d") and (et.hour, et.minute) < (16, 15)

    def _bar_status(self, last_date: Optional[str], cache_status: str) -> str:
        if cache_status != "REAL" or not last_date:
            return cache_status if cache_status != "REAL" else "UNAVAILABLE"
        age = (self.now().date() - datetime.strptime(last_date, "%Y-%m-%d").date()).days
        return "STALE" if age > STALE_DAYS else "REAL"

    def _quotes(self, symbols: List[str], key: str) -> Dict[str, Any]:
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
                      "spark": [r["close"] for r in rows[-30:]], "intraday": self._intraday(last["date"]),
                      "status": self._bar_status(last["date"], res["status"])}
        return {"items": out, "cache": {k: res[k] for k in ("status", "fetched_at", "error")}}

    # ---------------------------------------------------------------- screens
    def overview(self) -> Dict[str, Any]:
        syms = [s for _, g in OVERVIEW for s, _ in g]
        q = self._quotes(syms, "overview")
        groups = [{"title": t, "items": [{**q["items"][s], "name": n} for s, n in g]} for t, g in OVERVIEW]
        return {"groups": groups, "cache": q["cache"], "source": "Yahoo Finance (일봉 종가, 지연)",
                "basis": "최근 일봉 종가 대비 전일 종가. 실시간이 아니며, 장중에는 '장중·미확정'으로 표시되는 지연 가격입니다."}

    def chart(self, ticker: str, rng: str = "1y") -> Dict[str, Any]:
        ticker = clean_ticker(ticker)
        period = {"3mo": "2y", "1y": "2y", "5y": "10y"}.get(rng)
        if not period:
            raise ValueError("INVALID_RANGE")
        res = self.cache.cached(f"chart:{ticker}:{period}", TTL["chart"],
                                lambda: self.src.yahoo_history([ticker], period))
        rows = (res["data"] or {}).get(ticker) or []
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
        return {"ticker": ticker, "range": rng, "bars": bars,
                "status": self._bar_status(last["date"], res["status"]),
                "last": {"date": last["date"], "close": last["close"], "intraday": self._intraday(last["date"]),
                         "change_pct": _pct(last["close"], rows[-2]["close"] if len(rows) > 1 else None),
                         "high_52w": hi52, "low_52w": lo52,
                         "vs_sma200_pct": _pct(last["close"], sma[200][-1])},
                "cache": {k: res[k] for k in ("status", "fetched_at", "error")},
                "source": "Yahoo Finance (분할 조정 일봉)"}

    def company(self, ticker: str) -> Dict[str, Any]:
        ticker = clean_ticker(ticker)
        info = self.cache.cached(f"info:{ticker}", TTL["info"], lambda: self.src.yahoo_info(ticker))
        out = {"ticker": ticker, "profile": {"status": info["status"], "data": info["data"] or {},
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
        res = self.cache.cached(f"facts:{cik}", TTL["facts"], lambda: self.src.sec_companyfacts(cik))
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

    def macro(self) -> Dict[str, Any]:
        start = (self.now() - timedelta(days=365 * 5 + 30)).strftime("%Y-%m-%d")
        out = []
        for sid, label, unit, kind in MACRO:
            res = self.cache.cached(f"fred:{sid}", TTL["macro"], lambda s=sid: self.src.fred_series(s, start))
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
            out.append(item)
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

    def watchlist_quotes(self) -> Dict[str, Any]:
        w = self.watchlist()
        if not w:
            return {"items": [], "tickers": []}
        q = self._quotes(w, "watch:" + ",".join(sorted(w)))
        return {"tickers": w, "items": [q["items"][t] for t in w], "cache": q["cache"],
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

    def model(self) -> Dict[str, Any]:
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

    def _today_et(self):
        return self.now().astimezone(ZoneInfo("America/New_York")).date()

    def journal_add(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        entry = pf.normalize(raw or {}, self._today_et(), clean_ticker)
        return {"entry": self.journal.append(entry, self.now())}

    def journal_void(self, ref: str) -> Dict[str, Any]:
        return {"entry": self.journal.append({"kind": "VOID", "ref": str(ref or "")}, self.now())}

    def _sector(self, ticker: str) -> Optional[str]:
        res = self.cache.cached(f"info:{ticker}", TTL["info"], lambda: self.src.yahoo_info(ticker))
        return (res["data"] or {}).get("sector")

    def _book(self):
        recs, integ = self.journal.read()
        try:
            state = pf.replay(recs)
        except pf.JournalError as exc:
            integ, state = {"status": "BROKEN", "reason": str(exc)}, pf.replay([])
        return recs, integ, state

    def _valued(self):
        recs, integ, state = self._book()
        held = sorted(state["positions"])
        q = self._quotes(held + ["KRW=X"], "pf:" + ",".join(held))
        quotes = {t: q["items"][t] for t in held}
        fx = q["items"].get("KRW=X") or {}
        val = pf.valuation(state, quotes, {t: self._sector(t) for t in held}, self.settings())
        return recs, integ, state, val, fx, q["cache"]

    def portfolio(self) -> Dict[str, Any]:
        recs, integ, state, val, fx, cache = self._valued()
        gone = pf.voided_ids(recs)
        journal = [{**r, "voided": r["id"] in gone} for r in
                   sorted(recs, key=lambda r: (r.get("date") or r["recorded_at"][:10], r["seq"]), reverse=True)]
        return {"integrity": integ, **val, "stats": pf.trade_stats(state["closed"]), "closed": state["closed"][::-1],
                "journal": journal, "settings": self.settings(),
                "fx": {"usdkrw": fx.get("close"), "date": fx.get("date"), "status": fx.get("status", "UNAVAILABLE")},
                "cache": cache, "source": "사용자 거래 기록 + Yahoo Finance 일봉 종가(지연)",
                "note": "주문 기능은 없습니다. 보유 현황은 직접 기록한 거래로만 계산합니다."}

    def equity(self) -> Dict[str, Any]:
        recs, integ, state = self._book()
        eff = pf.effective(recs)
        if not eff or integ["status"] != "OK":
            return {"points": [], "twr_pct": None, "bench_pct": None, "status": "UNAVAILABLE"}
        days = (self._today_et() - datetime.strptime(eff[0]["date"], "%Y-%m-%d").date()).days
        period = "1y" if days < 330 else "2y" if days < 700 else "5y" if days < 1800 else "10y"
        tickers = sorted({r["ticker"] for r in eff if r["kind"] in ("BUY", "SELL")})
        syms = tickers + (["SPY"] if "SPY" not in tickers else [])
        res = self.cache.cached(f"eq:{period}:{','.join(syms)}", TTL["chart"],
                                lambda: self.src.yahoo_history(syms, period))
        hist = res["data"] or {}
        curve = pf.equity_curve(recs, {t: hist.get(t) or [] for t in tickers}, hist.get("SPY") or [])
        return {**curve, "status": res["status"] if curve["points"] else "UNAVAILABLE",
                "fetched_at": res["fetched_at"], "source": "거래 기록 재계산 + Yahoo 일봉 종가, 비교 지수 SPY",
                "method": "시간가중수익률(TWR): 입출금 효과를 제외한 일별 수익률의 누적"}

    def sizing(self, ticker: str = "", entry=None, stop=None, equity=None) -> Dict[str, Any]:
        _, integ, state, val, _, _ = self._valued()
        st = self.settings()
        out: Dict[str, Any] = {"settings": st, "equity": val["summary"]["equity"], "cash": state["cash"]}
        last, a = None, None
        if ticker:
            t = clean_ticker(ticker)
            c = self.chart(t, "3mo")
            if c.get("bars"):
                last = c["last"]["close"]
                res = self.cache.cached(f"chart:{t}:2y", TTL["chart"], lambda: self.src.yahoo_history([t], "2y"))
                a = pf.atr((res["data"] or {}).get(t) or [])
            out.update(ticker=t, last_close=last, last_date=(c.get("last") or {}).get("date"), atr14=a,
                       suggested_stop=(last - 2 * a) if last is not None and a else None,
                       held_qty=(state["positions"].get(t) or {}).get("qty"))
        e = pf._opt_pos(entry, "진입가") or last
        s = pf._opt_pos(stop, "손절가") or out.get("suggested_stop")
        if e is None or s is None:
            out["result"] = None
            out["reason"] = "진입가와 손절가를 입력하세요 (종목 코드를 넣으면 최근 종가와 2 ATR 손절가를 제안합니다)."
            return out
        manual = pf._opt_pos(equity, "계좌 금액")
        if manual:                       # hypothetical account (e.g. before any trade is recorded): all cash
            out.update(equity=manual, cash=manual, equity_source="입력값")
        elif val["summary"]["equity"] is None:
            raise pf.JournalError("일부 보유 종목의 시세가 없어 계좌 평가액을 확정할 수 없습니다.")
        else:
            out["equity_source"] = "거래 기록"
        out["result"] = pf.position_size(out["equity"], out["cash"], e, s, st)
        out["stop_source"] = "입력값" if stop not in (None, "") else "2 ATR(14일) 제안값"
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
                "sec": sec_user_agent_status()["status"]}       # status word only, never the value


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
