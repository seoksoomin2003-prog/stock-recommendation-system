"""What the score screen reads besides a score: marks, the newest stored scan, peers, the heat map, upcoming earnings, the
price archive, the frozen top three and the stored validation reports.

These methods were the last third of ``QSF`` in ``service.py`` until 2026-11-14 and are unchanged; ``QSF`` inherits them.  Nothing
here scores a stock or writes a record of a score: they read what the scan stored (or a provider, for display) and shape it for a
screen.  They use the scorer's own state (``self.base``, ``self.cache``, ``self.ledger``, ``self.src``, ...) and its methods.
"""
import gzip
import json
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import numpy as np

from terminal.qsf import config, ledger


_MEMO_GUARD = threading.Lock()         # guards the table of per-report locks, never a computation


def _n(v) -> Optional[float]:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return v if np.isfinite(v) else None


class ScreenViews:
    """Mixed into ``QSF``; see the module text."""

    # ------------------------------------------------------------------ reports
    def _risk_grade(self, ticker: str, market: str) -> Optional[Dict[str, Any]]:
        """The stock's risk grade on the newest KR-M1 record, with the stored test's numbers.  Reference only: it feeds no score."""
        if market != "KR":
            return None
        try:
            from terminal.qsf import kr_method
            view = kr_method.risk_view(self.base)
        except Exception:
            return None
        row = (view.get("rows") or {}).get(ticker)
        return None if view.get("status") != "REAL" or not row else {**row, "name": view["names"].get(row["grade"]), "session": view["session"], "test": view["test"]}

    def _high_risk(self, market: str) -> Dict[str, Any]:
        """Korean names only: that is where the pattern was seen.  Added when read, so no score or record contains it."""
        if market != "KR":
            return {"session": None, "codes": set(), "ranked": set()}
        from terminal.qsf import kr_forward
        try:
            found = kr_forward.high_risk(self.base)
        except (OSError, ValueError, KeyError):
            return {"session": None, "codes": set(), "ranked": set()}
        return {"session": found["session"], "codes": set(found["codes"]), "ranked": set(found.get("ranked") or ())}

    def _filing_marks(self, market: str) -> Dict[str, Any]:
        """Korean filings of the last 252 sessions, from the separate record.  Added when read, so no score or record contains it."""
        empty = {"session": None, "financing": set(), "buyback": set(), "known": set()}
        if market != "KR":
            return empty
        from terminal.qsf import kr_events_forward
        try:
            found = kr_events_forward.marks(self.base)
        except (OSError, ValueError, KeyError):
            return empty
        return {"session": found["session"], "financing": set(found["financing"]), "buyback": set(found["buyback"]), "known": set(found["known"])}

    @staticmethod
    def _filing_mark(found: Dict[str, Any], ticker: str) -> Optional[Dict[str, Any]]:
        financing, buyback = ticker in found["financing"], ticker in found["buyback"]
        return {"session": found["session"], "financing": financing, "buyback": buyback} if financing or buyback else None

    def latest(self, market: str = "US") -> Dict[str, Any]:
        try:
            out = json.loads((self.dir / f"latest_{market}.json").read_text(encoding="utf-8"))
            risky = self._high_risk(market)
            filed = self._filing_marks(market)
            from terminal.qsf import price_audit
            audit = price_audit.load(self.base, market) or {}
            checked = audit.get("stocks") if audit.get("session") == out.get("session") else None   # an older check says nothing about this scan
            for r in out.get("rows") or []:
                a = (checked or {}).get(r.get("ticker"))
                if a and a["level"] in ("warn", "bad"):
                    r["price_audit"] = {"level": a["level"], "text": "최근 1년 시세 이력: " + ", ".join(f"{price_audit.KIND_TEXT[k]} {n}일" for k, n in sorted(a["counts"].items()))}
                if r.get("ticker") in risky["codes"]:
                    r["high_risk"] = {"session": risky["session"]}
                elif r.get("ticker") not in (risky.get("ranked") or ()):
                    r["high_risk_unknown"] = True   # never ranked (no record, no value, or a US stock): unknown, not low
                mark = self._filing_mark(filed, r.get("ticker"))
                if mark:
                    r["filing_events"] = mark
                elif not (filed["session"] and r.get("ticker") in filed["known"]):
                    r["filing_unknown"] = True      # not on the record, or no record at all: unknown, not a no
            return out
        except (OSError, ValueError):
            return {"status": "UNAVAILABLE", "market": market, "rows": [], "reason": "아직 스캔 기록이 없습니다."}

    def _kr_industries(self) -> Dict[str, Dict[str, Optional[str]]]:
        """KRX KIND industry and this project's broad sector (``terminal.kr_sectors``) per code, from the newest stored master
        snapshot.  Read only: an old snapshot is still read, never refetched."""
        from terminal import kr_sectors
        sdir = self.base / "data" / "kr" / "security_master"
        try:
            meta = json.loads((sdir / "LATEST.json").read_text(encoding="utf-8"))
            import pandas as pd
            df = pd.read_csv(sdir / meta["file"], dtype=str, usecols=lambda c: c in ("canonical_ticker", "industry", "company_name"))
            codes, industries = df["canonical_ticker"], df["industry"]
        except (OSError, ValueError, KeyError):
            return {}
        names = df["company_name"] if "company_name" in df else [None] * len(df)
        return {c: {"industry": i, "sector": kr_sectors.broad_sector(c, i, n if isinstance(n, str) else None)}
                for c, i, n in zip(codes, industries, names) if isinstance(c, str) and isinstance(i, str) and i.strip()}

    def kr_sector(self, code: str) -> Dict[str, Optional[str]]:
        """Broad sector and KRX industry of any listed Korean code (held stocks need not be in the scan)."""
        try:
            stamp = (self.base / "data" / "kr" / "security_master" / "LATEST.json").stat().st_mtime
        except OSError:
            stamp = None
        memo = getattr(self, "_memo_kr_master", None)
        if not memo or memo[0] != stamp:                   # a new master snapshot is read again
            memo = self._memo_kr_master = (stamp, self._kr_industries())
        return memo[1].get(code) or {"industry": None, "sector": None}

    PEER_METRICS = {"valuation": ("pe", "pb", "fcf_yield"), "business_quality": ("op_margin", "roe"), "growth_quality": ("rev_cagr3",),
                    "balance_dilution": ("debt_equity",)}
    PEER_DOMAINS = ("TECHNICAL", "FUNDAMENTAL", "RISK", "EVENTS")
    PEER_MIN = 6

    @staticmethod
    def grade(q: Optional[float]) -> Optional[str]:
        if q is None:
            return None
        return "A" if q >= 0.8 else "B" if q >= 0.6 else "C" if q >= 0.4 else "D" if q >= 0.2 else "F"

    def peers(self, ticker: str, market: str = "US") -> Dict[str, Any]:
        """The stock beside the scanned stocks of its industry: scores, the ratios the score itself read, and where each score part
        stands inside the group as a letter.  Read only.  Ratios come only from ledger records of the live model version."""
        return self._memo(f"peers:{market}:{ticker}", self._stamp([]), lambda: self._peers(ticker, market))

    def _ratios(self, market: str) -> Dict[str, Any]:
        def build():
            mine = lambda s: s.get("strategy") == "LONG_TERM" and s.get("model_version") == config.MODEL_VERSION      # noqa: E731
            # Which day is the newest comes from the shards' side files (a few fields per snapshot); only the shards holding that
            # day are then read whole.  Both passes used to parse every shard of the market: 1.4 s with 8 sessions, growing daily.
            shards = [r for r in self.ledger._live_rows() if r["market"] == market]
            dates_of = [[v["LONG_TERM"]["data_date"] for v in self.ledger.side(r).values()
                         if "LONG_TERM" in v and v["LONG_TERM"].get("model_version") == config.MODEL_VERSION] for r in shards]
            days = [d for ds in dates_of for d in ds]
            if not days:
                return {"session": None, "rows": {}}
            session = max(days)
            snaps = [s for r, ds in zip(shards, dates_of) if session in ds for s in self.ledger._load(r) if mine(s) and s["data_date"] == session]
            rows = {}
            for s in snaps:
                if s["data_date"] != session:
                    continue
                vals = {}
                for f in s.get("factors") or []:
                    for k in self.PEER_METRICS.get(f.get("factor"), ()):
                        v = (f.get("raw") or {}).get(k) if f.get("status") == "REAL" else None
                        vals[k] = v if isinstance(v, (int, float)) and np.isfinite(v) else None
                rows[s["ticker"]] = vals
            return {"session": session, "rows": rows}
        return self._memo(f"ratios:{market}", self._stamp([]), build)

    def _peers(self, ticker: str, market: str) -> Dict[str, Any]:
        heat = {"SWING": {i["ticker"]: i for i in self.heatmap(market, "SWING").get("items") or []}}     # market value and change do not depend on the strategy
        out = self.screen_rows(market)
        rows = {(r["ticker"], r["strategy"]): r for r in out.get("rows") or []}
        if (ticker, "SWING") not in rows and (ticker, "LONG_TERM") not in rows:
            return {"status": "NOT_SCANNED", "ticker": ticker, "market": market}
        me = rows.get((ticker, "SWING")) or rows.get((ticker, "LONG_TERM"))
        sector, mine = me.get("sector"), me.get("industry")
        group, basis = sector, "업종"
        same = [t for (t, st), r in rows.items() if st == me["strategy"] and r.get("industry") == mine] if mine else []
        if mine and len(same) >= self.PEER_MIN:                 # the detailed industry when it has enough scanned members
            group, basis = mine, "세부 업종"
        members = sorted({t for (t, st), r in rows.items() if (r.get("sector") == sector if basis == "업종" else r.get("industry") == group)})
        if not group:
            members = [ticker]
        ratios = self._ratios(market)
        table = []
        for t in members:
            sw, lt = rows.get((t, "SWING")) or {}, rows.get((t, "LONG_TERM")) or {}
            h = heat["SWING"].get(t) or {}
            table.append({"ticker": t, "name": sw.get("name") or lt.get("name"), "market_cap": h.get("market_cap"), "change_1m": (h.get("change") or {}).get("1m"),
                          "swing": sw.get("score"), "long": lt.get("score"), "swing_band": sw.get("band_label"), "long_band": lt.get("band_label"),
                          "ratios": ratios["rows"].get(t), "domains": {"SWING": sw.get("domains") or {}, "LONG_TERM": lt.get("domains") or {}}})
        grades = {}
        for st, key in (("SWING", "swing"), ("LONG_TERM", "long")):
            parts = {}
            for d in ("SCORE",) + self.PEER_DOMAINS:
                vals = [(r[key] if d == "SCORE" else r["domains"][st].get(d)) for r in table]
                mine_v = next((v for r, v in zip(table, vals) if r["ticker"] == ticker), None)
                pool = [v for v in vals if isinstance(v, (int, float))]
                if mine_v is None or len(pool) < self.PEER_MIN:
                    parts[d] = {"value": mine_v, "percentile": None, "grade": None, "n": len(pool)}
                    continue
                q = (sum(v < mine_v for v in pool) + 0.5 * sum(v == mine_v for v in pool)) / len(pool)
                parts[d] = {"value": mine_v, "percentile": q, "grade": self.grade(q), "n": len(pool)}
            grades[st] = parts
        for r in table:
            r.pop("domains")
        table.sort(key=lambda r: -(r["market_cap"] or 0))
        return {"status": "REAL", "ticker": ticker, "market": market, "group": group, "basis": basis, "peers": table, "grades": grades,
                "session": out.get("session"), "model_version": out.get("model_version"), "ratio_session": ratios["session"], "ratio_version": config.MODEL_VERSION,
                "basis_note": "같은 업종 스캔 종목 안에서의 상대 위치입니다(A 상위 20%, F 하위 20%). 미래 수익으로 검증된 등급이 아닙니다."}

    HEAT_SPANS = {"1d": 1, "5d": 5, "1m": 21}
    HEAT_TAIL = 64                    # rows read per stock for the map: three times the longest span, so gaps rarely force a full read

    def heatmap(self, market: str = "US", strategy: str = "SWING") -> Dict[str, Any]:
        """Every scanned stock with its sector, market value, price change and score, for the market map.  Read only, from what is
        stored: the scan, its own price store, Yahoo company data already cached (US) and the KRX listing (KR).  A missing value stays
        missing; a stock without a market value is listed, not drawn."""
        if strategy not in config.STRATEGIES:
            raise ValueError("INVALID_STRATEGY")
        return self._memo(f"heat:{market}:{strategy}", self._stamp([]), lambda: self._heatmap(market, strategy))

    def _heatmap(self, market: str, strategy: str) -> Dict[str, Any]:
        out = self.screen_rows(market)
        if out.get("status") != "REAL":
            return {"status": out.get("status") or "UNAVAILABLE", "market": market, "items": [], "reason": out.get("reason")}
        session, load = out.get("session"), self._scan_loader(market)
        tail = (lambda t: load.tail(t, self.HEAT_TAIL)) if hasattr(load, "tail") else load     # only the US loader builds rows; Korea's is a lookup
        shares: Dict[str, float] = {}
        if market == "KR":
            try:
                shares = self._krx_shares(session) or {}            # KRX listed shares (10 days old at most) times the scan close
            except Exception:
                shares = {}
        items = []
        for r in out.get("rows") or []:
            if r.get("strategy") != strategy:
                continue
            t = r["ticker"]
            bars = [b for b in tail(t) or [] if _n(b.get("close"))]
            if len(bars) <= max(self.HEAT_SPANS.values()):         # too few valid closes in the tail: the whole series, as before
                bars = [b for b in load(t) or [] if _n(b.get("close"))]
            fresh = bool(bars) and bars[-1]["date"] == session
            change = {k: (bars[-1]["close"] / bars[-1 - n]["close"] - 1 if fresh and len(bars) > n else None) for k, n in self.HEAT_SPANS.items()}
            cap = shares.get(t) * bars[-1]["close"] if market == "KR" and fresh and shares.get(t) else None
            if market == "US":
                info = (self.cache.read(f"info:{t}") or {}).get("data") or {}
                cap = _n(info.get("marketCap"))
            items.append({"ticker": t, "name": r.get("name"), "sector": r.get("sector"), "market_cap": cap if cap and cap > 0 else None,
                          "score": r.get("score"), "band": r.get("band"), "band_label": r.get("band_label"), "change": change})
        return {"status": "REAL", "market": market, "strategy": strategy, "session": session, "model_version": out.get("model_version"), "items": items,
                "without_cap": sorted(i["ticker"] for i in items if i["market_cap"] is None),
                "source": "QSF 스캔 · 스캔 일봉 · " + ("KRX 상장 주식 수 × 스캔 종가" if market == "KR" else "Yahoo 회사 정보 시가총액(저장된 값)"),
                "basis": "등락은 스캔 거래일 종가 기준입니다. 시가총액이 없는 종목은 지도에서 빠지고 목록에만 남습니다."}

    def _sector_of(self, market: str, ticker: str, kr_industry: Optional[Dict[str, Dict[str, Optional[str]]]] = None) -> Dict[str, Optional[str]]:
        """Sector and industry from what is already stored.  Never asks the network, and a stock with no stored sector has none.
        Korea uses the exchange's own Korean industry, which every listed stock has, grouped into a broad sector; Yahoo's sector for
        Korea is missing for some and does not map onto the exchange's industries, so the two are never mixed."""
        if market == "KR" and kr_industry is not None:
            return kr_industry.get(ticker) or {"sector": None, "industry": None}
        for key in ([f"info:{ticker}"] if market == "US" else [f"info:{ticker}.KS", f"info:{ticker}.KQ"]):
            data = (self.cache.read(key) or {}).get("data") or {}
            if data.get("sector"):
                return {"sector": str(data["sector"]), "industry": str(data["industry"]) if data.get("industry") else None}
        return {"sector": None, "industry": None}

    def earnings_upcoming(self, market: str = "US", days: int = 14) -> Dict[str, Any]:
        """Stored earnings dates of the scanned stocks, holdings and watchlist.  Never asks the network."""
        from zoneinfo import ZoneInfo

        from terminal import portfolio as pf
        from terminal.qsf import earnings_calendar
        out = self.latest(market)
        if out.get("status") != "REAL":
            return {"status": out.get("status") or "UNAVAILABLE", "items": [], "reason": out.get("reason")}
        held: set = set()
        watched: set = set()
        try:
            held = set(self.terminal._book(market)[2]["positions"])
        except Exception:
            pass
        try:
            watched = {t for t in self.terminal.watchlist() if pf.market_of(t) == market}
        except Exception:
            pass

        def read(t: str):
            for key in ([f"earn:{t}"] if market == "US" else [f"earn:{t}.KS", f"earn:{t}.KQ"]):
                rec = self.cache.read(key)
                if rec is not None:
                    return rec
            return None
        now = self.now()
        today = now.astimezone(ZoneInfo("America/New_York" if market == "US" else "Asia/Seoul")).date()
        res = earnings_calendar.upcoming(out.get("rows") or [], read, today, now.timestamp(), days, held, watched)
        return {**res, "market": market, "session": out.get("session")}

    def screen_rows(self, market: str = "US") -> Dict[str, Any]:
        """The newest scan with each stock's sector and industry.  Added when read, so no score or record contains it."""
        out = self.latest(market)
        memo = self._sector_memo.get(market)
        if not memo or memo[0] != out.get("generated_at"):
            kr = (self._kr_industries() or None) if market == "KR" else None     # no stored master: Yahoo sectors, as before
            memo = self._sector_memo[market] = (out.get("generated_at"), {t: self._sector_of(market, t, kr) for t in {r.get("ticker") for r in out.get("rows") or []}})
        for r in out.get("rows") or []:
            got = memo[1].get(r.get("ticker")) or {}
            r["sector"], r["industry"] = got.get("sector"), got.get("industry")
        return out

    def _loader(self, market: str) -> Callable[[str], List[Dict]]:
        """The scan's prices, with the archived prices of recorded stocks that have left the scan (``price_archive``)."""
        from terminal.qsf import price_archive
        return price_archive.loader(self.base, market, self._scan_loader(market))

    def archive_prices(self, market: str) -> Dict[str, Any]:
        """Keep the prices of every recorded stock, including those the scan no longer carries.  Writes only the price archive."""
        from terminal.qsf import price_archive
        if market == "US":
            symbol_of = lambda t: [t]                                                       # noqa: E731
        else:
            master = self._kr_master
            if master is None:
                try:
                    from markets.kr import security_master
                    master = security_master.load_master(self.base / "data" / "kr", now=self.now())["master"]
                except Exception:
                    master = None
            known = {} if master is None else {c: y for c, y in zip(master["canonical_ticker"], master["yahoo_symbol"]) if isinstance(y, str) and y}

            def symbol_of(t):
                return [known[t]] if t in known else [f"{t}.KS", f"{t}.KQ"]
        return price_archive.update(self.base, market, self._scan_loader(market), lambda syms: self.src.yahoo_history(syms, "1y"), symbol_of, self.now)

    def _scan_loader(self, market: str) -> Callable[[str], List[Dict]]:
        """The US loader also has ``tail(ticker, n)``: the newest ``n`` rows only.  A reader of a few recent closes need not build
        six years of rows for each of 500 stocks."""
        if market == "US":
            p = self.terminal.lab.panel()

            def rows(t, first):
                if p is None or t not in p.col:
                    return []
                o, c, a = p.series("open", t), p.series("close", t), p.series("adj_close", t)
                return [{"date": p.dates[i], "open": _n(o[i]), "close": _n(c[i]), "adj_close": _n(a[i])} for i in range(first, len(p.dates))]

            def load(t):
                return rows(t, 0)
            load.tail = lambda t, n: rows(t, max(0, len(p.dates) - n)) if p is not None else []
            return load
        try:
            with gzip.open(self.dir / "bars_KR.json.gz", "rt", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError, EOFError):          # EOFError: a gzip cut short
            data = {}
        return lambda t: data.get(t) or []

    # ------------------------------------------------------------------ read-only reports, reused while their inputs stay the same
    def _stamp(self, cache_keys: List[str]) -> tuple:
        """What the reports read: the ledger, the top-three record, both price stores and the index caches, plus the date.
        Any write to one of them, or a new day, gives a new stamp and the report is computed again."""
        def m(path):
            try:
                return Path(path).stat().st_mtime_ns
            except OSError:
                return None
        from terminal.qsf import price_archive, top_picks
        files = [self.ledger.index, self.base / top_picks.FOLDER / "index.jsonl", self.dir / "bars_KR.json.gz", self.terminal.lab.panel_file,
                 price_archive.path_of(self.base, "US"), price_archive.path_of(self.base, "KR")]
        return tuple(m(f) for f in files) + tuple(m(self.cache._path(k)) for k in cache_keys) + (self.now().date().isoformat(),)

    def _memo(self, name: str, stamp: tuple, compute: Callable[[], Dict[str, Any]]) -> Dict[str, Any]:
        """One computation per report at a time: a second request for a report that is being computed waits for it and takes its
        result, instead of reading the whole ledger again beside the first."""
        memos = self.__dict__.setdefault("_memos", {})
        hit = memos.get(name)
        if hit is not None and hit[0] == stamp:
            return hit[1]
        with _MEMO_GUARD:
            lock = self.__dict__.setdefault("_memo_locks", {}).setdefault(name, threading.RLock())
        with lock:
            hit = memos.get(name)
            if hit is not None and hit[0] == stamp:
                return hit[1]
            out = compute()
            memos[name] = (stamp, out)
            return out

    def top3(self, market: str = "US") -> Dict[str, Any]:
        """The frozen top three of each session and how they did since.  Read only; reused until an input changes."""
        return self._memo(f"top3:{market}", self._stamp(["bars:2y:^KQ11,^KS11"]), lambda: self._top3(market))

    def _top3(self, market: str) -> Dict[str, Any]:
        from terminal.qsf import top_picks
        got = top_picks.read(self.base, market)
        if got["status"] != "OK":
            return {"status": "UNAVAILABLE", "market": market, "reason": "INTEGRITY", "bad_files": got["bad_files"]}
        if not got["docs"]:
            return {"status": "NO_RECORD", "market": market, "first": top_picks.FIRST, "protocol": top_picks.PROTOCOL}
        loader = self._loader(market)
        if market == "US":
            bench_loader = loader
        else:
            idx = self._history(["^KS11", "^KQ11"])["data"] or {}

            def bench_loader(s):
                return idx.get(s) or []
        return {"status": "REAL", **top_picks.report(got["docs"], market, loader, bench_loader)}

    def validation(self) -> Dict[str, Any]:
        """Reused until an input changes."""
        return self._memo("validation", self._stamp(["bars:2y:^KS11"]), self._validation)

    def _validation(self) -> Dict[str, Any]:
        out = {"integrity": self.ledger.verify(), "cohorts": {}, "correlations": {}}
        for market in config.MARKETS:
            snaps = self.ledger.snapshots(market=market, keep=ledger.light)       # the report reads a few fields of each snapshot
            loader = self._loader(market)
            bench = loader("SPY") if market == "US" else (self._history(["^KS11"])["data"] or {}).get("^KS11") or []
            for s in config.STRATEGIES:
                key = f"{market}_{s}"
                out["cohorts"][key] = ledger.validate(snaps, market, s, loader, bench)
                out["correlations"][key] = ledger.factor_correlations([x for x in snaps if x["strategy"] == s])
        return out
