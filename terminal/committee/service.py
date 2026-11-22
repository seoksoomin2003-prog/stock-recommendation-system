"""The committee on the terminal's stored scan: what the screens, the assistant and the daily job ask for (IC-1).

Everything is read from the newest recorded scan (the ledger snapshots, the stored Yahoo record, the stored filing marks)
and from the committee's own daily record.  Nothing is fetched.  One session's work is done once and kept while neither
the ledger nor the record changes.  The six portfolios are made when a screen's button or a question asks, and when the
daily job writes its record; no tab makes them by being opened.
"""
from __future__ import annotations

import json
import statistics
from typing import Any, Callable, Dict, List, Optional

from terminal.committee import council, figures as fg, investors as iv, portfolios, record

_MEMO: Dict[Any, Any] = {}
BENCHMARKS = frozenset(("SPY", "^KS11", "^KQ11"))       # terminal/qsf/config.py BENCHMARK: the index fund the scan carries is not a stock to judge
RETURN_DAYS = 126
CARD_KEYS = ("investor", "name", "philosophy", "question", "score", "confidence", "coverage", "recommendation", "recommendation_ko", "held", "horizon", "valuation", "expected_return",
             "downside_risk", "positives", "negatives", "opinion", "thesis", "conditions", "suggested_weight", "action", "components", "missing", "evidence", "category_ko", "loss_risk",
             "regimes", "regimes_not_told", "profile", "method", "margin_of_safety", "fair_pe", "insufficient", "other_profile")


def _session_figures(terminal: Any, market: str, session: str) -> Dict[str, Dict[str, Any]]:
    from terminal import analyst_extra as ax
    from terminal import assistant
    snaps = [s for s in assistant._snaps(terminal, market, session) if s.get("data_date") == session]
    long_, swing = {s["ticker"]: s for s in snaps if s["strategy"] == "LONG_TERM"}, {s["ticker"]: s for s in snaps if s["strategy"] == "SWING"}
    rows = {r["ticker"]: r for r in assistant._rows(terminal, market)}
    try:
        sector = {r["ticker"]: ax.SECTOR_KO.get(r.get("sector"), r.get("sector")) for r in terminal.qsf.screen_rows(market).get("rows") or []}
    except Exception:
        sector = {}
    out = {}
    for t in sorted(set(long_) | set(swing)):
        if t in BENCHMARKS:
            continue
        base = long_.get(t) or swing.get(t) or {}
        try:
            info = terminal.qsf.stored_info(t, market)
        except Exception:
            info = {}
        try:
            deals = terminal.qsf.stored_deals(base.get("cik"), session) if market == "US" else []
        except Exception:
            deals = []
        f = fg.read(long_.get(t), swing.get(t), info, sector.get(t), ax.marks_of(rows.get(t) or {}), deals)
        f["name"] = (rows.get(t) or {}).get("name") or t
        out[t] = f
    return out


def context(figures: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """What one stock's engines need from the rest of the session: each sector's median relative strength, and where the
    session's financials stand on return on equity (a financial is judged among financials: user decision 2026-11-22)."""
    by: Dict[str, List[float]] = {}
    for f in figures.values():
        if f.get("sector") and f.get("rs") is not None:
            by.setdefault(f["sector"], []).append(f["rs"])
    fin = sorted(f["roe"] for f in figures.values() if f.get("kind") == "FINANCIAL" and f.get("roe") is not None)
    peers = {"n": len(fin), "median": statistics.median(fin), "top": fin[min(len(fin) - 1, int(len(fin) * 0.9))]} if fin else None      # the session's own financials
    return {"sector_rs": {k: statistics.median(v) for k, v in by.items() if len(v) >= 3}, "financial_roe": peers}


def judge(f: Dict[str, Any], held: Optional[Dict[str, bool]], ctx: Dict[str, Any]) -> Dict[str, Any]:
    opinions = iv.evaluate(f, held, ctx)
    return {"ticker": f.get("ticker"), "name": f.get("name") or f.get("ticker"), "sector": f.get("sector"), "as_of": f.get("as_of"), "figures": f,
            "opinions": {o["investor"]: o for o in opinions}, "committee": council.decide(f, opinions, bool((held or {}).get("COMMITTEE")))}


def _returns(terminal: Any, market: str) -> Callable[[str], Optional[List[float]]]:
    kept: Dict[str, Optional[List[float]]] = {}
    try:
        load = terminal.qsf._loader(market)
    except Exception:
        return lambda t: None

    def of(t: str) -> Optional[List[float]]:
        if t not in kept:
            try:
                closes = [b.get("adj_close") or b.get("close") for b in (load(t) or [])[-(RETURN_DAYS + 1):]]
                kept[t] = [b / a - 1.0 for a, b in zip(closes, closes[1:]) if a and b] or None
            except Exception:
                kept[t] = None
        return kept[t]
    return of


def session_work(terminal: Any, market: str) -> Optional[Dict[str, Any]]:
    """The newest session judged once: every stock's five opinions and the committee's decision.  No portfolio yet."""
    session = terminal.qsf.latest(market).get("session")
    if not session:
        return None
    key = ("work", str(terminal.base), market, session, terminal.qsf.ledger._index_stamp(), record.stamp(terminal.base, market))
    if key not in _MEMO:
        figures = _session_figures(terminal, market, session)
        ctx = context(figures)
        last = record.before(record.read(terminal.base, market), session)
        holds = record.held(last)
        book = {t: judge(f, {k: t in (holds.get(k) or {}) for k in portfolios.ORDER}, ctx) for t, f in figures.items()}
        if len(_MEMO) > 8:
            _MEMO.clear()
        state = next((f.get("market_state") for f in figures.values() if f.get("market_state") is not None), None)
        _MEMO[key] = {"session": session, "market": market, "book": book, "ctx": ctx, "holds": holds, "previous_session": (last or {}).get("session"), "state": state,
                      "regimes": iv.regimes(next(iter(figures.values()))) if figures else []}
    return _MEMO[key]


def six(terminal: Any, market: str) -> Optional[Dict[str, Any]]:
    """The six portfolios of the newest session.  Made when asked (a button, a question, the daily record), kept for the session."""
    work = session_work(terminal, market)
    if work is None:
        return None
    if "portfolios" not in work:
        work["portfolios"] = portfolios.build(work["book"], work["holds"], work["state"], _returns(terminal, market))
    return work


def _card(o: Dict[str, Any]) -> Dict[str, Any]:
    return {k: o[k] for k in CARD_KEYS if k in o}


def stock(terminal: Any, ticker: str, market: str, cards: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Five opinions and the committee's decision on one stock.  A scanned stock is read from the session's record; another one
    from the cards the score evaluation just made (``cards``: {LONG_TERM, SWING}), against the session's sector strengths."""
    work = session_work(terminal, market)
    entry = (work or {}).get("book", {}).get(ticker)
    source = "SCAN"
    if entry is None and cards and (cards.get("LONG_TERM") or cards.get("SWING")):
        try:
            info = terminal.qsf.stored_info(ticker, market)
        except Exception:
            info = {}
        sector = (info or {}).get("sector")
        try:
            from terminal import analyst_extra as ax
            sector = ax.SECTOR_KO.get(sector, sector)
        except Exception:
            pass
        f = fg.read(cards.get("LONG_TERM"), cards.get("SWING"), info, sector)
        f["ticker"], f["name"] = ticker, (info or {}).get("longName") or ticker
        entry, source = judge(f, None, (work or {}).get("ctx") or {}), "EVALUATION"
    if entry is None:
        return {"status": "NO_VIEW", "ticker": ticker, "market": market, "reason": "이 종목은 저장된 스캔 기록에 없어 다섯 관점이 읽을 수치가 없습니다."}
    return {"status": "OK", "rules": iv.RULES, "ticker": ticker, "market": market, "name": entry["name"], "sector": entry["sector"], "as_of": entry["as_of"], "source": source,
            "session": (work or {}).get("session"), "investors": [_card(entry["opinions"][k]) for k in iv.ORDER], "committee": entry["committee"], "note": iv.NOTE}


def stock_in_portfolios(terminal: Any, ticker: str, market: str) -> Dict[str, Any]:
    """Asked for at a stock: the six portfolios as they stand, and where this stock is in each (or why it is not)."""
    work = six(terminal, market)
    if work is None:
        return {"status": "NO_SCAN", "ticker": ticker, "market": market, "reason": "저장된 스캔 기록이 없습니다."}
    entry = work["book"].get(ticker)
    places = []
    for key in portfolios.ORDER:
        p = work["portfolios"][key]
        row = next((r for r in p["holdings"] if r["ticker"] == ticker), None)
        if entry is None:
            why = "이 종목은 스캔 대상이 아니라 포트폴리오 후보가 아닙니다."
        elif key == "COMMITTEE":
            why = f"위원회 판정 '{entry['committee']['decision_ko']}'" + ("" if row else ": " + (entry["committee"]["reasons"][0] if entry["committee"]["reasons"] else ""))
        else:
            o = entry["opinions"][key]
            why = f"{o['name']} 판정 '{o['recommendation_ko']}'" + ("" if row else f": {o['opinion']}")
        if entry is not None and row is None and (entry["committee"]["decision"] if key == "COMMITTEE" else entry["opinions"][key]["recommendation"]) in iv.BUY_SIDE + (council.CONDITIONAL_BUY,):
            why += " 매수 조건이지만 종목 수·업종·함께 움직이는 종목의 한도 때문에 들지 못했습니다."
        places.append({"key": key, "name": p["name"], "in": row is not None, "weight": row["weight"] if row else None, "why": why, "count": p["count"], "cash": p["cash"]})
    return {"status": "OK", "rules": iv.RULES, "ticker": ticker, "market": market, "name": (entry or {}).get("name") or ticker, "session": work["session"], "places": places,
            "portfolios": _ports_out(work), "note": iv.NOTE}


def _ports_out(work: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [work["portfolios"][k] for k in portfolios.ORDER]


def six_view(terminal: Any, market: str) -> Dict[str, Any]:
    work = six(terminal, market)
    if work is None:
        return {"status": "NO_SCAN", "market": market, "reason": "저장된 스캔 기록이 없습니다.", "portfolios": []}
    return {"status": "OK", "rules": iv.RULES, "market": market, "session": work["session"], "previous_session": work["previous_session"], "market_state": work["state"], "regimes": work["regimes"],
            "portfolios": _ports_out(work), "overlap": portfolios.overlap(work["portfolios"]), "note": iv.NOTE,
            "made": "지금 만들었습니다. 매일 작업이 그날의 여섯 포트폴리오를 기록하고, 다음 날은 그 기록을 보유 상태로 읽습니다." if work["previous_session"] else
            "지금 만들었습니다. 아직 매일 기록이 없어 모든 종목이 '새로 편입'입니다. 첫 기록 뒤부터 보유를 이어 갑니다."}


def compare(terminal: Any, market: str, tickers: Optional[List[str]] = None) -> Dict[str, Any]:
    """The five side by side: on the stocks asked for, or on the stocks the committee finds most attractive."""
    work = session_work(terminal, market)
    if work is None:
        return {"status": "NO_SCAN", "market": market, "reason": "저장된 스캔 기록이 없습니다.", "rows": []}
    book = work["book"]
    chosen = [t for t in (tickers or []) if t in book]
    if not chosen:
        ranked = sorted((e for e in book.values() if e["committee"]["scores"]["attractiveness"] is not None), key=lambda e: (-e["committee"]["scores"]["attractiveness"], e["ticker"]))
        chosen = [e["ticker"] for e in ranked[:20]]
    rows = []
    for t in chosen:
        e = book[t]
        rows.append({"ticker": t, "name": e["name"], "sector": e["sector"], "committee": e["committee"]["decision_ko"], "attractiveness": e["committee"]["scores"]["attractiveness"],
                     "agreement": e["committee"]["scores"]["agreement"], "growth": e["committee"]["scores"]["growth"], "downside": e["committee"]["scores"]["downside"],
                     "views": [{"name": o["name"], "recommendation_ko": o["recommendation_ko"], "recommendation": o["recommendation"], "score": o["score"], "valuation": o["valuation"], "horizon": o["horizon"]}
                               for o in (e["opinions"][k] for k in iv.ORDER)]})
    tally = {iv.PEOPLE[k][0]: {} for k in iv.ORDER}
    for e in book.values():
        for k in iv.ORDER:
            ko = e["opinions"][k]["recommendation_ko"]
            tally[iv.PEOPLE[k][0]][ko] = tally[iv.PEOPLE[k][0]].get(ko, 0) + 1
    return {"status": "OK", "rules": iv.RULES, "market": market, "session": work["session"], "rows": rows, "tally": tally, "judged": len(book), "note": iv.NOTE,
            "asked": bool(tickers), "not_found": [t for t in (tickers or []) if t not in book]}


def dashboard(terminal: Any, market: str) -> Dict[str, Any]:
    work = session_work(terminal, market)
    if work is None:
        return {"status": "NO_SCAN", "market": market, "reason": "저장된 스캔 기록이 없습니다."}
    book = work["book"]
    decisions: Dict[str, int] = {}
    risks: Dict[str, int] = {}
    kinds: Dict[str, int] = {}
    for e in book.values():
        c = e["committee"]
        decisions[c["decision_ko"]] = decisions.get(c["decision_ko"], 0) + 1
        for r in c["material_risks"]:
            risks[r["name"]] = risks.get(r["name"], 0) + 1
        for d in c["disagreements"]:
            kinds[d["kind_ko"]] = kinds.get(d["kind_ko"], 0) + 1
    buys = sorted((e for e in book.values() if e["committee"]["decision"] in iv.BUY_SIDE + (council.CONDITIONAL_BUY,)), key=lambda e: (-(e["committee"]["scores"]["attractiveness"] or 0), e["ticker"]))
    agree = [e["committee"]["scores"]["agreement"] for e in book.values() if e["committee"]["scores"]["agreement"] is not None]
    return {"status": "OK", "rules": iv.RULES, "market": market, "session": work["session"], "judged": len(book), "market_state": work["state"], "regimes": work["regimes"],
            "regimes_not_told": ["물가 상승·둔화 국면", "성장률과 정책 금리 국면"], "decisions": dict(sorted(decisions.items(), key=lambda kv: -kv[1])),
            "risks": dict(sorted(risks.items(), key=lambda kv: -kv[1])), "disagreements": dict(sorted(kinds.items(), key=lambda kv: -kv[1])),
            "average_agreement": round(sum(agree) / len(agree), 1) if agree else None,
            "top": [{"ticker": e["ticker"], "name": e["name"], "sector": e["sector"], "decision_ko": e["committee"]["decision_ko"], "attractiveness": e["committee"]["scores"]["attractiveness"],
                     "confidence": e["committee"]["scores"]["confidence"], "supporters": e["committee"]["buyers"], "strongest_for": e["committee"]["strongest_for"],
                     "strongest_against": e["committee"]["strongest_against"], "entry": e["committee"]["entry_conditions"][:1]} for e in buys[:12]],
            "buy_count": len(buys), "note": iv.NOTE}


def daily_record(terminal: Any, market: str) -> Dict[str, Any]:
    """The session's line of the record, written once (the daily job calls this after the scan is recorded)."""
    work = six(terminal, market)
    if work is None:
        return {"status": "NO_SESSION"}
    return record.append(terminal.base, market, work["session"], work["book"], work["portfolios"])


def _prices(terminal: Any, market: str) -> Any:
    """(price(ticker, session), benchmark(session)): closes from the stored bars, adjusted where the store has them."""
    from terminal.qsf import config
    try:
        load = terminal.qsf._loader(market)
    except Exception:
        load = lambda t: []          # noqa: E731
    closes: Dict[str, Dict[str, float]] = {}

    def price(t: str, session: str) -> Optional[float]:
        if t not in closes:
            try:
                closes[t] = {b["date"]: (b.get("adj_close") or b.get("close")) for b in load(t) or []}
            except Exception:
                closes[t] = {}
        return closes[t].get(session)
    bench = config.BENCHMARK["US"] if market == "US" else None

    def benchmark(session: str) -> Optional[float]:
        if bench:
            return price(bench, session)
        try:                      # Korea: the index close the scan itself stored that day
            from terminal import assistant
            snap = next((x for x in assistant._snaps(terminal, market, session) if x.get("data_date") == session), None)
            return fg.read(snap, None).get("index_close") if snap else None
        except Exception:
            return None
    return price, benchmark


def performance(terminal: Any, market: str) -> Dict[str, Any]:
    from terminal.committee import reading
    from terminal.qsf import config
    price, benchmark = _prices(terminal, market)
    out = record.performance(record.read(terminal.base, market), price, benchmark, config.round_trip_cost(market) / 2.0)
    try:
        read = json.loads((terminal.base / reading.REPORTS[market]).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        read = None
    out.update({"market": market, "rules": iv.RULES, "benchmark": "SPY" if market == "US" else "KOSPI(가격 지수, 배당 제외)", "names": {k: portfolios.SPEC[k]["name"] for k in portfolios.ORDER}, "note": iv.NOTE,
                "not_this": "과거로 거슬러 계산한 수익(백테스트)이 아니고, 실제 계좌의 수익도 아닙니다. 주문은 나가지 않습니다.",
                "reading": {"protocol": reading.PROTOCOL, "read_at": reading.READ_AT, "bar": reading.BAR, "left": max(reading.READ_AT + 2 - out["records"], 0),
                            "verdict": (read or {}).get("verdict"), "reasons": (read or {}).get("reasons") or [],
                            "rule": f"모의 하루 수익이 {reading.READ_AT}개가 되는 날 한 번, 지수 대비 초과수익의 t값이 ±{reading.BAR:g}을 넘는지 읽고 텔레그램으로 알립니다. 아무것도 자동으로 바뀌지 않습니다."}})
    return out


def paper_reading(terminal: Any, market: str) -> Dict[str, Any]:
    """The one reading at 240 paper days (terminal/committee/reading.py).  The daily job asks for it; it refuses until then."""
    from terminal.committee import reading
    from terminal.qsf import config
    price, benchmark = _prices(terminal, market)
    return reading.evaluate_once(terminal.base, market, price, benchmark, config.round_trip_cost(market) / 2.0)
