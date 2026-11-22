"""The figures the five investor engines read, each with where it came from and whether it is there.

Every figure is one the daily scan already stored in a ledger snapshot (a factor's ``raw``), or one field of the stored
Yahoo company record.  Nothing is fetched.  A figure is CONFIRMED, MISSING (it should be there and is not), or
NOT_APPLICABLE (it does not describe this kind of company: a bank has no current ratio).  A missing figure is never zero.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

CONFIRMED, MISSING, NOT_APPLICABLE, INVALID = "CONFIRMED", "MISSING", "NOT_APPLICABLE", "INVALID"
MAX_DIVIDEND_YIELD = 8.0          # per cent.  Above it the stored Yahoo figure has been a wrong record (Samsung Electronics 9.45 on 2026-11-20)
NO_EQUITY = 99.0          # terminal/qsf/fundamentals.py stores this as debt over equity when equity is zero or negative

# figure -> (the factors whose stored raw answers it, the key in that raw, how it is said in Korean)
SOURCES: Dict[str, Any] = {
    "pe": (("valuation",), "pe", "PER"), "pb": (("valuation",), "pb", "PBR"), "fcf_yield": (("valuation",), "fcf_yield", "잉여현금흐름 수익률"),
    "roe": (("business_quality", "profitability"), "roe", "ROE"), "op_margin": (("business_quality", "profitability"), "op_margin", "영업이익률"),
    "gross_margin": (("business_quality",), "gross_margin", "매출총이익률"), "profit_years": (("business_quality",), "roe_years_positive", "흑자 연도 비율"),
    "eps_cagr3": (("growth_quality",), "eps_cagr3", "3년 주당이익 성장"), "rev_cagr3": (("growth_quality",), "rev_cagr3", "3년 매출 성장"),
    "rev_growth": (("growth_quality", "earnings_revenue_quality"), "rev_growth", "최근 매출 성장"), "eps_growth": (("earnings_revenue_quality",), "eps_growth", "최근 주당이익 성장"),
    "ocf_to_ni": (("earnings_revenue_quality", "cash_flow_quality"), "ocf_to_ni", "영업현금흐름/순이익"),
    "fcf_margin": (("free_cash_flow", "cash_flow_quality"), "fcf_margin", "잉여현금흐름 마진"), "fcf_years": (("free_cash_flow",), "fcf_years_positive", "잉여현금흐름 흑자 연도 비율"),
    "debt_equity": (("balance_dilution", "leverage", "balance_sheet"), "debt_equity", "부채/자본"), "share_change": (("balance_dilution", "capital_allocation"), "share_change", "주식 수 변화"),
    "returns_capital": (("capital_allocation",), "returns_capital", "주주 환원"), "current_ratio": (("financial_resilience", "balance_sheet"), "current_ratio", "유동비율"),
    "cash_debt": (("financial_resilience",), "cash_debt", "현금/부채"), "interest_cover": (("financial_resilience",), "interest_cover", "이자보상배율"),
    "ma20": (("trend_structure",), "ma20", "20일선"), "ma50": (("trend_structure",), "ma50", "50일선"), "ma50_slope": (("trend_structure",), "ma50_slope", "50일선 기울기"),
    "ma200": (("long_trend", "trend_structure"), "ma200", "200일선"), "ma200_slope": (("long_trend", "trend_structure"), "ma200_slope", "200일선 기울기"),
    "rs": (("relative_strength",), "percentile", "상대 강도 백분위"), "rel_126": (("relative_strength",), "rel_126", "6개월 상대 수익"),
    "ret_12_1": (("momentum_persistence",), "ret_12_1", "12개월 수익"), "rsi": (("momentum",), "rsi", "RSI"),
    "dist_high": (("breakout_volume",), "dist_high", "고점 대비"), "volume_ratio": (("breakout_volume",), "volume_ratio", "거래량 배수"), "breakout": (("breakout_volume",), "breakout", "돌파"),
    "max_drawdown": (("downside_drawdown", "drawdown_gap"), "max_drawdown_252", "1년 최대 낙폭"), "downside_vol": (("downside_drawdown",), "downside_vol", "하방 변동성"),
    "hist_vol": (("atr_risk",), "hist_vol", "변동성"), "atr_pct": (("atr_risk",), "atr_pct", "ATR 비율"), "adv_value": (("liquidity",), "adv_value", "일평균 거래대금"),
    "reward_risk": (("risk_reward",), "reward_risk", "손익비"), "events_negative": (("material_events", "material_disclosures"), "negative", "부정 공시 수"),
    "events_positive": (("material_events", "material_disclosures"), "positive", "긍정 공시 수"), "insider_pct": (("insider_ownership",), "insider_pct", "내부자 지분"),
    "earnings_sessions": (("earnings_calendar",), "sessions", "실적 발표까지 거래일"),
    # the market's state: the same for every stock of a session
    "vix_pct": (("vix_regime",), "percentile_5y", "VIX 5년 백분위"), "credit_pct": (("credit_spread", "credit_liquidity"), "percentile", "신용 스프레드 백분위"),
    "breadth": (("index_trend_breadth", "breadth"), "breadth", "200일선 위 종목 비율"), "index_close": (("index_trend_breadth", "index_trend"), "close", "지수"),
    "index_ma200": (("index_trend_breadth", "index_trend"), "ma200", "지수 200일선"), "index_ma50": (("index_trend_breadth", "index_trend"), "ma50", "지수 50일선"),
}
INFO = {"market_cap": "marketCap", "dividend_yield": "dividendYield", "forward_pe": "forwardPE", "trailing_pe": "trailingPE", "beta": "beta", "industry": "industry"}
FINANCIAL = ("Financial Services", "금융")
REAL_ESTATE = ("Real Estate", "부동산")
ASSET_LIGHT = ("Technology", "Communication Services", "기술", "커뮤니케이션")
CYCLICAL = ("Energy", "Basic Materials", "에너지", "소재")
CYCLICAL_WORDS = ("semiconductor", "auto", "airline", "steel", "chemical", "homebuilding", "residential construction", "oil", "mining", "shipping", "marine", "building materials")
# a bank's or an insurer's balance sheet is its business: these figures do not describe it
# the score engine's own answer to "is this a bank or an insurer": it marks these factors not applicable for one (SIC code
# in the US, statement layout in Korea).  The Yahoo sector label "Financial Services" also holds card networks, exchanges
# and rating agencies, which earn margins like any other company (audit 2026-11-22, RED-06: 18 such stocks).
FINANCIAL_FACTORS = ("free_cash_flow", "leverage", "cash_flow_quality")
NOT_FOR_FINANCIALS = ("op_margin", "gross_margin", "fcf_margin", "fcf_years", "fcf_yield", "current_ratio", "debt_equity", "cash_debt", "interest_cover", "ocf_to_ni")


def read(long_snap: Optional[Dict[str, Any]], swing_snap: Optional[Dict[str, Any]] = None, info: Optional[Dict[str, Any]] = None,
         sector: Optional[str] = None, marks: Iterable[str] = (), deals: Iterable[Any] = ()) -> Dict[str, Any]:
    """{figure: value or None} with ``_status`` {figure: CONFIRMED | MISSING | NOT_APPLICABLE} and ``_source`` {figure: factor}."""
    raws: Dict[str, Dict[str, Any]] = {}
    told: List[bool] = []                       # what the score engine said about each factor that tells a financial apart
    for snap in (long_snap, swing_snap):
        for f in (snap or {}).get("factors") or []:
            if isinstance(f.get("raw"), dict) and f.get("factor") not in raws:
                raws[f["factor"]] = f["raw"]
            if f.get("factor") in FINANCIAL_FACTORS and f.get("status"):
                told.append(f["status"] == NOT_APPLICABLE)
    base = long_snap or swing_snap or {}
    d = info or {}
    financial = any(told) if told else sector in FINANCIAL          # the sector label only when the scan said nothing
    kind = "FINANCIAL" if financial else "REAL_ESTATE" if sector in REAL_ESTATE else "ASSET_LIGHT" if sector in ASSET_LIGHT else "GENERAL"
    out: Dict[str, Any] = {"ticker": base.get("ticker"), "market": base.get("market"), "as_of": base.get("data_date"), "sector": sector, "kind": kind,
                           "price": base.get("price"), "marks": list(marks), "deals": list(deals),
                           # the score engine's gate for a severe filing (bankruptcy, a delisting notice, embezzlement ...): the fatal rule of the portfolios reads it
                           "severe": list(dict.fromkeys(str(g.get("text") or g.get("code")) for snap in (long_snap, swing_snap) for g in (snap or {}).get("gates") or []
                                                        if isinstance(g, dict) and g.get("code") == "SEVERE_EVENT")),
                           "stop": (swing_snap or base).get("stop"), "target": (swing_snap or base).get("target")}
    status: Dict[str, str] = {}
    source: Dict[str, str] = {}
    for name, (factors, key, _ko) in SOURCES.items():
        got = next(((k, raws[k][key]) for k in factors if k in raws and raws[k].get(key) is not None), None)
        out[name] = None if got is None else got[1]
        source[name] = got[0] if got else factors[0]
        status[name] = CONFIRMED if got else MISSING
    for name, key in INFO.items():
        out[name] = d.get(key)
        source[name], status[name] = "yahoo_info", CONFIRMED if d.get(key) is not None else MISSING
    dy = out.get("dividend_yield")
    if dy is not None:                 # Yahoo gives it in per cent; an implausible one is dropped and said to be invalid, not used
        out["dividend_yield"], status["dividend_yield"] = (dy / 100.0, CONFIRMED) if 0 <= dy <= MAX_DIVIDEND_YIELD else (None, INVALID)
    gov = raws.get("governance")
    out["governance_issues"] = None if gov is None else len(gov.get("issues") or [])
    status["governance_issues"] = CONFIRMED if gov is not None else MISSING
    out["insider_buy"] = out["insider_sell"] = None
    for key in ("insider_ownership", "insider_activity"):
        raw = raws.get(key) or {}
        ins = raw.get("insider") if isinstance(raw.get("insider"), dict) else raw
        if ins.get("status") == "REAL" and out["insider_buy"] is None:
            out["insider_buy"], out["insider_sell"] = ins.get("open_market_buy"), ins.get("open_market_sell")
    status["insider_buy"] = CONFIRMED if out["insider_buy"] is not None else MISSING
    # the market state the program shows everywhere is the swing scan's (order_plan.market_state reads SWING first)
    regimes = [((s or {}).get("domains") or {}).get("REGIME") for s in (swing_snap, long_snap)]
    # read only when at least half of the state's factors had data, as the order plan reads it (MARKET_STATE_MIN_COVERAGE)
    out["market_state"] = next((r["score_100"] for r in regimes if isinstance(r, dict) and r.get("score_100") is not None
                                and (r.get("coverage") is None or r["coverage"] >= 0.5)), None)
    status["market_state"] = CONFIRMED if out["market_state"] is not None else MISSING
    # no equity: return on equity and price to book mean nothing, and the stored 99 is a mark, not a ratio
    out["no_equity"] = out.get("debt_equity") == NO_EQUITY
    if out["no_equity"]:
        out["debt_equity"] = None
    # a proxy for return on invested capital: income over equity plus debt.  ROIC itself is not in the stored figures.
    roe, de = out.get("roe"), out.get("debt_equity")
    out["roic"] = None if roe is None or (de is None and kind != "FINANCIAL") else roe if kind == "FINANCIAL" else roe / (1.0 + max(de, 0.0))
    status["roic"], source["roic"] = (CONFIRMED if out["roic"] is not None else MISSING), "business_quality"
    # next year's earnings against the last twelve months', from Yahoo's two price multiples (a consensus figure, not ours)
    tpe, fpe = out.get("trailing_pe"), out.get("forward_pe")
    out["forward_growth"] = tpe / fpe - 1.0 if tpe and fpe and tpe > 0 and fpe > 0 else None
    status["forward_growth"], source["forward_growth"] = (CONFIRMED if out["forward_growth"] is not None else MISSING), "yahoo_info"
    if kind == "FINANCIAL":
        for name in NOT_FOR_FINANCIALS:
            out[name], status[name] = None, NOT_APPLICABLE
    industry = str(out.get("industry") or "").lower()
    out["cyclical"] = sector in CYCLICAL or any(w in industry for w in CYCLICAL_WORDS)
    out["_status"], out["_source"] = status, source
    return out


def label(name: str) -> str:
    return SOURCES[name][2] if name in SOURCES else {"roic": "투하자본 수익률(근사)", "forward_growth": "다음 해 예상 이익 성장(야후 집계)", "market_cap": "시가총액", "dividend_yield": "배당수익률",
                                                      "market_state": "시장 상태", "governance_issues": "지배구조 경고", "insider_buy": "내부자 매수"}.get(name, name)


def pct(v: Optional[float], digits: int = 1) -> str:
    return "자료 없음" if v is None else f"{v * 100:.{digits}f}%"


def times(v: Optional[float], digits: int = 1) -> str:
    return "자료 없음" if v is None else f"{v:.{digits}f}배"


def band(v: Optional[float], low: float, high: float) -> Optional[float]:
    """0 at ``low`` and 1 at ``high``, straight between, held outside; ``low`` above ``high`` turns it round.  None stays None."""
    if v is None:
        return None
    if low == high:
        return 1.0 if v >= high else 0.0
    return max(0.0, min(1.0, (v - low) / (high - low)))


def blend(parts: List[Any]) -> Dict[str, Any]:
    """``parts``: (name, weight, value 0..1 or None, status).  The weighted mean of the parts that are there, 0-100.
    ``coverage``: the share of the applicable weight that was there (is the data complete?).  ``sure``: the same with a part
    that is not applicable counted as half missing: that is no gap in the data, but the judgement rests on fewer figures, so
    a bank judged on two figures is not as sure as a maker judged on six."""
    live = [(n, w, v) for n, w, v, st in parts if v is not None]
    asked = sum(w for _n, w, v, st in parts if st != NOT_APPLICABLE or v is not None)
    wide = sum(w * (0.5 if st == NOT_APPLICABLE and v is None else 1.0) for _n, w, v, st in parts)
    have = sum(w for _n, w, _v in live)
    return {"score": None if not have else 100.0 * sum(w * v for _n, w, v in live) / have, "coverage": (have / asked) if asked else 0.0, "sure": (have / wide) if wide else 0.0,
            "missing": [n for n, _w, v, st in parts if v is None and st != NOT_APPLICABLE], "not_applicable": [n for n, _w, v, st in parts if v is None and st == NOT_APPLICABLE]}


def part(f: Dict[str, Any], name: str, weight: float, low: float, high: float) -> Any:
    return (name, weight, band(f.get(name), low, high), f["_status"].get(name, MISSING))
