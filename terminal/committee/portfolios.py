"""Six portfolios: one for each of the five engines, by its own way of building one, and the committee's (IC-1).

They do not share a ranking.  Each of the five takes the stocks its own engine would buy and sizes them its own way:

  BUFFETT        up to 12 quality compounders, sized by the business score (4-12%), what is left stays in cash
  MUNGER         up to 6 exceptional businesses, large positions (8-18%), nothing bought to fill a place
  GRAHAM         up to 20 cheap and sound stocks at 5% each: wide, equal, cash when there are fewer
  LYNCH          up to 12 growth stocks, no more than 4 of one kind of company
  DRUCKENMILLER  up to 8 stocks in an up-trend; the market's regime sets how much is invested at all

The committee's portfolio is neither the stocks all five share nor an average of their weights.  It takes the stocks the
committee decided to buy (also ones only one or two views support, when the committee found that case compelling), ranks
them by attractiveness after risk and data quality, sizes them by that over their volatility, and holds them to limits on
one stock, one sector and stocks that move together.  What does not fit the limits stays in cash.

A position already held is kept until its engine says sell: a small change in a score is not a trade.  Nothing here is an
order; no amount or share count is computed.  None of it has been tested on returns.

Since 2026-11-23 (user decisions, before the first record line):
  - a held position's weight follows its price (``drift``); it is no longer pulled back to a target or to the cap;
  - OVERWEIGHT: a held position grown to ``OVERWEIGHT_FACTOR`` times the cap or more is left as it is, and the portfolio
    says so with the rule's own answer (cut to the cap, the rest to cash).  A notice, not a trade;
  - FATAL: a stock with a severe filing, or whose permanent-loss risk (the Munger engine's inversion) is at that engine's
    avoid line or over, is in none of the six: not admitted, and taken out whole when held.  What it held stays in cash.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from terminal.committee import council
from terminal.committee import investors as iv
from terminal.committee.investors import BUY_SIDE, HOLD, SELL_SIDE, WAIT

OVERWEIGHT_FACTOR = 1.5             # a held position at this many times the cap or more raises the overweight notice
SPEC: Dict[str, Dict[str, Any]] = {
    "BUFFETT": {"name": "버핏식 포트폴리오", "objective": "좋은 사업을 오래 보유해 복리로 불린다", "max": 12, "sector": 3, "cap": 0.12, "sizing": "사업 점수에 비례(4~12%)"},
    "MUNGER": {"name": "멍거식 포트폴리오", "objective": "탁월한 사업 몇 개에 집중한다", "max": 6, "sector": 2, "cap": 0.18, "sizing": "확신에 비례(8~18%), 자리를 채우려고 사지 않음"},
    "GRAHAM": {"name": "그레이엄식 포트폴리오", "objective": "싸고 튼튼한 종목을 넓게 나눠 원금을 지킨다", "max": 20, "sector": 4, "cap": 0.05, "sizing": "같은 비중 5%씩, 종목이 모자라면 현금"},
    "LYNCH": {"name": "린치식 포트폴리오", "objective": "성장에 비해 값이 적당한 종목을 여러 종류로 담는다", "max": 12, "sector": 3, "cap": 0.10, "kind": 4, "sizing": "점수에 비례(5~10%), 한 종류의 회사는 4개까지"},
    "DRUCKENMILLER": {"name": "드러켄밀러식 포트폴리오", "objective": "시장·이익·추세가 맞는 곳에 크게, 아니면 현금", "max": 8, "sector": 3, "cap": 0.18, "sizing": "확신에 비례(8~18%), 시장 국면이 투자 비중을 정함"},
    "COMMITTEE": {"name": "투자위원회 포트폴리오", "objective": "다섯 관점이 찾은 기회를 위험을 따져 한 포트폴리오로", "max": 15, "sector": 3, "cap": 0.10, "sector_weight": 0.30, "sizing": "위험 조정 매력 ÷ 변동성, 종목 10%·업종 30% 한도"},
}
ORDER = tuple(SPEC)
C_CORRELATION, C_MIN_OBS = 0.85, 60
SAME_ISSUER = 0.95                  # two share classes of one company (GOOG, GOOGL) are one holding in any portfolio
D_EXPOSURE = ((35.0, 0.4), (50.0, 0.7))             # market state under 35: 40% invested; under 50: 70%; otherwise all
C_EXPOSURE = ((35.0, 0.6), (50.0, 0.8))


def exposure(state: Optional[float], steps: Any) -> float:
    """The share that may be invested at this market state.  A state that cannot be read is taken as "under 50", the step the
    order plan's own rule for an unknown day corresponds to (user decision 2026-11-23); until then it meant fully invested."""
    if state is None:
        return steps[-1][1]
    return next((share for limit, share in steps if state < limit), 1.0)


def correlation(a: Optional[List[float]], b: Optional[List[float]]) -> Optional[float]:
    if not a or not b:
        return None
    n = min(len(a), len(b))
    if n < C_MIN_OBS:
        return None
    x, y = a[-n:], b[-n:]
    mx, my = sum(x) / n, sum(y) / n
    sx, sy = sum((v - mx) ** 2 for v in x), sum((v - my) ** 2 for v in y)
    return None if sx <= 0 or sy <= 0 else sum((p - mx) * (q - my) for p, q in zip(x, y)) / (sx * sy) ** 0.5


def drift(previous: Optional[Dict[str, float]], move: Optional[Callable[[str], Optional[float]]]) -> Dict[str, float]:
    """Yesterday's weights after the prices moved: each holding grows or shrinks with its own price and the whole is measured
    again, cash included.  ``move(ticker)``: the price change since those weights were recorded, or None when unknown (the
    holding is then taken as unmoved).  Nothing is bought or sold here."""
    prev = dict(previous or {})
    if not prev or move is None:
        return prev
    grown = {}
    for t, w in prev.items():
        m = move(t)
        grown[t] = w * (1.0 + m) if m is not None and m > -1.0 else w
    whole = max(0.0, 1.0 - sum(prev.values())) + sum(grown.values())
    return {t: round(v / whole, 4) for t, v in grown.items()} if whole > 0 else prev


def fatal(e: Dict[str, Any]) -> Optional[str]:
    """Why this stock is in none of the six, or None.  A severe filing (bankruptcy, a delisting notice, embezzlement and the
    like, as the score engine's gate reads them), or the Munger engine's permanent-loss risk at its avoid line or over."""
    severe = (e.get("figures") or {}).get("severe") or []
    if severe:
        return f"심각 공시: {severe[0]}"
    risk = (((e.get("opinions") or {}).get("MUNGER") or {}).get("downside_risk") or {}).get("value")
    if risk is not None and risk >= iv.M_RISK_AVOID:
        return f"거꾸로 따져 본 영구 손실 위험 {risk:.0f}/100 (기준 {iv.M_RISK_AVOID:.0f} 이상)"
    return None


def _fit(weights: Dict[str, float], cap: float, total: float, held: Optional[Dict[str, float]] = None) -> Dict[str, float]:
    """A new position gets no more than ``cap`` and only what room is left under ``total``; a held one keeps the weight its
    price gave it (it is not pulled back to the cap: that is the overweight notice's business).  When the held ones alone are
    over ``total`` (the market's regime lowered it) they shrink together and nothing new is bought.  What is cut stays in cash."""
    held = held or {}
    old = {t: weights[t] for t in weights if t in held}
    new = {t: min(w, cap) for t, w in weights.items() if t not in held}
    s_old, s_new = sum(old.values()), sum(new.values())
    if s_old > total and s_old > 0:
        return {**{t: round(w * total / s_old, 4) for t, w in old.items()}, **{t: 0.0 for t in new}}
    room = max(0.0, total - s_old)
    scale = room / s_new if s_new > room and s_new > 0 else 1.0
    return {**{t: round(w, 4) for t, w in old.items()}, **{t: round(w * scale, 4) for t, w in new.items()}}


def _notices(key: str, rows: List[Dict[str, Any]], before: Dict[str, float]) -> List[Dict[str, Any]]:
    """The overweight notices of one portfolio.  ``before``: the weights as they were recorded (not yet moved by prices), to tell
    a holding that crossed the line today from one that has been over it."""
    cap, name = SPEC[key]["cap"], SPEC[key]["name"].replace(" 포트폴리오", "")
    line = OVERWEIGHT_FACTOR * cap
    out = []
    for r in rows:
        if r["status"] != "보유 유지" or r["weight"] < line:
            continue
        r["overweight"] = True
        out.append({"ticker": r["ticker"], "name": r["name"], "weight": r["weight"], "cap": cap, "line": round(line, 4), "to_cash": round(r["weight"] - cap, 4),
                    "new": before.get(r["ticker"], 0.0) < line,
                    "text": f"{name}: {r['name']}의 비중이 {r['weight'] * 100:.1f}%까지 커졌습니다(한 종목 한도 {cap * 100:.0f}%의 {OVERWEIGHT_FACTOR:g}배 이상). "
                            f"이 포트폴리오의 규칙은 {cap * 100:.0f}%로 줄이고 나머지 {(r['weight'] - cap) * 100:.1f}%p를 현금으로 두는 것입니다. 모의 포트폴리오는 그대로 두고 알리기만 합니다."})
    return out


def _row(key: str, e: Dict[str, Any], o: Dict[str, Any], weight: float, status: str) -> Dict[str, Any]:
    return {"ticker": e["ticker"], "name": e.get("name") or e["ticker"], "sector": e.get("sector"), "weight": weight, "score": o.get("score"), "confidence": o.get("confidence"),
            "recommendation": o["recommendation"] if "recommendation" in o else o["decision"], "recommendation_ko": o.get("recommendation_ko") or o.get("decision_ko"),
            "expected_return": o.get("expected_return"), "downside_risk": o.get("downside_risk"), "thesis": o.get("thesis"), "entry": (o.get("conditions") or {}).get("buy") or "; ".join(o.get("entry_conditions") or []),
            "exit": (o.get("conditions") or {}).get("sell") or "; ".join(o.get("exit_conditions") or []), "sizing": SPEC[key]["sizing"], "status": status, "as_of": e.get("as_of"),
            "category": o.get("category_ko")}


def investor_portfolio(key: str, book: Dict[str, Dict[str, Any]], previous: Optional[Dict[str, float]] = None, state: Optional[float] = None,
                       returns: Optional[Callable[[str], Optional[List[float]]]] = None, move: Optional[Callable[[str], Optional[float]]] = None) -> Dict[str, Any]:
    """One engine's portfolio.  ``book``: {ticker: {ticker, name, sector, as_of, opinions: {investor: result}}}.  ``previous``: {ticker: weight}.
    ``move``: each holding's price change since ``previous`` was recorded (``drift``)."""
    spec, before = SPEC[key], dict(previous or {})
    prev = drift(before, move)
    cands, exits, gone = [], [], []
    for t, e in book.items():
        o = e["opinions"][key]
        why = fatal(e)
        if why:                                         # in none of the six, whatever this engine says
            if t in prev:
                gone.append({"ticker": t, "name": e.get("name") or t, "weight": prev[t], "why": why})
                exits.append({"ticker": t, "name": e.get("name") or t, "why": f"치명적 훼손으로 전량 제외: {why}"})
            continue
        if o["recommendation"] in BUY_SIDE or (t in prev and o["recommendation"] in (HOLD, WAIT)):
            cands.append((t, e, o))
        elif t in prev:
            exits.append({"ticker": t, "name": e.get("name") or t, "why": f"{o['recommendation_ko']}: {o['opinion']}"})
    exits += [{"ticker": t, "name": t, "why": "이번 스캔 기록에 없는 종목"} for t in prev if t not in book]
    # held positions first (they are not sold to make room), then the engine's own score
    cands.sort(key=lambda c: (c[0] not in prev, -(c[2]["score"] or 0.0), c[0]))
    picked, sectors, kinds, skipped = [], {}, {}, 0
    for t, e, o in cands:
        sec, kind = e.get("sector"), o.get("category")
        full = len(picked) >= spec["max"] or (sec and sectors.get(sec, 0) >= spec["sector"]) or (key == "LYNCH" and kind and kinds.get(kind, 0) >= spec["kind"])
        if not full and returns is not None and t not in prev:
            mine = returns(t)
            full = any((correlation(mine, returns(p[0])) or 0.0) >= SAME_ISSUER for p in picked)
        if full and t not in prev:
            skipped += 1
            continue
        picked.append((t, e, o))
        if sec:
            sectors[sec] = sectors.get(sec, 0) + 1
        if kind:
            kinds[kind] = kinds.get(kind, 0) + 1
    raw = {t: (0.05 if key == "GRAHAM" else (o["suggested_weight"] or prev.get(t) or 0.05)) for t, e, o in picked}
    invest = exposure(state, D_EXPOSURE) if key == "DRUCKENMILLER" else 1.0
    weights = _fit({t: prev.get(t, w) for t, w in raw.items()}, spec["cap"], invest, prev)
    rows = [_row(key, e, o, weights[t], "보유 유지" if t in prev else "새로 편입") for t, e, o in picked]
    rows.sort(key=lambda r: (-r["weight"], r["ticker"]))
    return _wrap(key, rows, exits, skipped, {"exposure_limit": invest, "candidates": len(cands), "overweight": _notices(key, rows, before), "fatal": gone}, prev)


def committee_portfolio(book: Dict[str, Dict[str, Any]], previous: Optional[Dict[str, float]] = None, state: Optional[float] = None,
                        returns: Optional[Callable[[str], Optional[List[float]]]] = None, move: Optional[Callable[[str], Optional[float]]] = None) -> Dict[str, Any]:
    """The committee's own construction: its decisions, attractiveness after risk and data quality, volatility-sized, under limits."""
    spec, before = SPEC["COMMITTEE"], dict(previous or {})
    prev = drift(before, move)
    cands, exits, gone = [], [], []
    vols = sorted(e["figures"].get("hist_vol") for e in book.values() if e["figures"].get("hist_vol"))
    typical = vols[len(vols) // 2] if vols else 0.3
    for t, e in book.items():
        c = e["committee"]
        why = fatal(e)
        if why:
            if t in prev:
                gone.append({"ticker": t, "name": e.get("name") or t, "weight": prev[t], "why": why})
                exits.append({"ticker": t, "name": e.get("name") or t, "why": f"치명적 훼손으로 전량 제외: {why}"})
            continue
        buy = c["decision"] in BUY_SIDE + (council.CONDITIONAL_BUY,)
        if buy or (t in prev and c["decision"] in (HOLD, WAIT)):
            sc = c["scores"]
            if sc["attractiveness"] is None:
                continue
            utility = sc["attractiveness"] * (1.0 - (sc["downside"] or 50.0) / 200.0) * ((sc["data"] or 50.0) / 100.0) * (0.8 if c["decision"] == council.CONDITIONAL_BUY else 1.0)
            cands.append((t, e, c, utility, e["figures"].get("hist_vol") or typical))
        elif t in prev:
            exits.append({"ticker": t, "name": e.get("name") or t, "why": f"{c['decision_ko']}: {c['reasons'][0] if c['reasons'] else ''}"})
    exits += [{"ticker": t, "name": t, "why": "이번 스캔 기록에 없는 종목"} for t in prev if t not in book]
    cands.sort(key=lambda c: (c[0] not in prev, -c[3], c[0]))
    picked, sectors, skipped, together = [], {}, 0, []
    for t, e, c, u, vol in cands:
        sec = e.get("sector")
        twin = None
        if returns is not None and t not in prev:
            mine = returns(t)
            for p in picked:
                r = correlation(mine, returns(p[0]))
                if r is not None and r >= C_CORRELATION:
                    twin = (p[0], r)
                    break
        if t not in prev and (len(picked) >= spec["max"] or (sec and sectors.get(sec, 0) >= spec["sector"]) or twin):
            skipped += 1
            if twin:
                together.append({"ticker": t, "with": twin[0], "correlation": round(twin[1], 2)})
            continue
        picked.append((t, e, c, u, vol))
        if sec:
            sectors[sec] = sectors.get(sec, 0) + 1
    invest = exposure(state, C_EXPOSURE)
    score = {t: u / max(vol, 0.05) for t, _e, _c, u, vol in picked}
    total = sum(score.values())
    raw = {t: invest * s / total for t, s in score.items()} if total else {}
    weights = _fit({t: prev.get(t, w) for t, w in raw.items()}, spec["cap"], invest, prev)
    by_sector: Dict[str, float] = {}
    fresh: Dict[str, float] = {}
    for t, e, _c, _u, _v in picked:                       # one sector's share of the whole is limited too; the cut stays in cash
        sec = e.get("sector") or ""
        by_sector[sec] = by_sector.get(sec, 0.0) + weights[t]
        if t not in prev:
            fresh[sec] = fresh.get(sec, 0.0) + weights[t]
    for t, e, _c, _u, _v in picked:                       # only what is bought now gives way: a held position is not sold for the limit
        sec = e.get("sector") or ""
        over = by_sector.get(sec, 0.0) - spec["sector_weight"]
        if e.get("sector") and over > 0 and t not in prev and fresh.get(sec):
            weights[t] = round(weights[t] * max(0.0, fresh[sec] - over) / fresh[sec], 4)
    rows = []
    for t, e, c, u, vol in picked:
        row = _row("COMMITTEE", e, c, weights[t], "보유 유지" if t in prev else "새로 편입")
        row.update({"score": c["scores"]["attractiveness"], "confidence": c["scores"]["confidence"], "thesis": c["thesis"], "supporters": c["buyers"], "utility": round(u, 1), "volatility": round(vol, 3),
                    "downside_risk": {"value": c["scores"]["downside"], "basis": "위원회의 하방 위험 점수(0~100, 높을수록 위험)"}, "expected_return": {"value": None, "basis": "위원회는 기대수익률을 추정하지 않습니다"}})
        rows.append(row)
    rows.sort(key=lambda r: (-r["weight"], r["ticker"]))
    return _wrap("COMMITTEE", rows, exits, skipped, {"exposure_limit": invest, "candidates": len(cands), "moves_together": together[:10], "correlation_checked": returns is not None,
                                                     "overweight": _notices("COMMITTEE", rows, before), "fatal": gone}, prev)


def _wrap(key: str, rows: List[Dict[str, Any]], exits: List[Dict[str, Any]], skipped: int, extra: Dict[str, Any], prev: Dict[str, float]) -> Dict[str, Any]:
    spec = SPEC[key]
    invested = round(sum(r["weight"] for r in rows), 4)
    sectors: Dict[str, float] = {}
    for r in rows:
        sectors[r.get("sector") or "업종 미상"] = round(sectors.get(r.get("sector") or "업종 미상", 0.0) + r["weight"], 4)
    turnover = round(sum(abs(r["weight"] - prev.get(r["ticker"], 0.0)) for r in rows) + sum(w for t, w in prev.items() if t not in {r["ticker"] for r in rows}), 4)
    why_cash = []
    if not rows:
        why_cash.append("이 관점의 매수 조건을 채운 종목이 없습니다. 자리를 채우려고 사지 않습니다.")
    elif extra.get("exposure_limit", 1.0) < 1.0:
        why_cash.append(f"시장 국면 때문에 투자 비중을 {extra['exposure_limit'] * 100:.0f}%까지로 줄였습니다.")
    if rows and invested < extra.get("exposure_limit", 1.0) - 0.01:
        why_cash.append("조건을 채운 종목이 한도까지 채울 만큼 많지 않아 나머지는 현금입니다.")
    return {"key": key, "name": spec["name"], "objective": spec["objective"], "sizing": spec["sizing"], "rules": iv.RULES, "holdings": rows, "count": len(rows), "invested": invested,
            "cash": max(0.0, round(1.0 - invested, 4)), "cash_reasons": why_cash, "sectors": dict(sorted(sectors.items(), key=lambda kv: -kv[1])), "concentration": round(sum(r["weight"] ** 2 for r in rows), 4),
            "largest": rows[0]["weight"] if rows else 0.0, "exits": exits, "left_out_by_limits": skipped, "turnover": turnover, "limits": {"max": spec["max"], "per_sector": spec["sector"], "per_stock": spec["cap"]}, **extra}


def build(book: Dict[str, Dict[str, Any]], previous: Optional[Dict[str, Dict[str, float]]] = None, state: Optional[float] = None,
          returns: Optional[Callable[[str], Optional[List[float]]]] = None, move: Optional[Callable[[str], Optional[float]]] = None) -> Dict[str, Dict[str, Any]]:
    """All six, each from its own rule.  ``previous``: {portfolio: {ticker: weight}} of the last record, or nothing.
    ``move``: each stock's price change since that record, so the held weights follow their prices."""
    prev = previous or {}
    out = {key: investor_portfolio(key, book, prev.get(key), state, returns, move) for key in iv.ORDER}
    out["COMMITTEE"] = committee_portfolio(book, prev.get("COMMITTEE"), state, returns, move)
    return out


def interrupts(ports: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """{portfolio: {overweight: [...], fatal: [...]}} for the portfolios where one fired."""
    return {key: {"overweight": p.get("overweight") or [], "fatal": p.get("fatal") or []} for key, p in ports.items() if p.get("overweight") or p.get("fatal")}


def overlap(ports: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """How much two portfolios share: the stocks in both, and the weight they have in common."""
    out = []
    keys = list(ports)
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            wa, wb = ({r["ticker"]: r["weight"] for r in ports[k]["holdings"]} for k in (a, b))
            both = sorted(set(wa) & set(wb))
            out.append({"a": ports[a]["name"], "b": ports[b]["name"], "shared": both, "count": len(both), "weight": round(sum(min(wa[t], wb[t]) for t in both), 4)})
    return out
