"""QSF factor calculators.  Each returns (normalized 0..1, raw dict, explanation, source, as_of, status) or a
missing/not-applicable marker.  Absolute anchors are fixed research defaults; raw values are kept unchanged.

Correlated indicators are grouped: RSI and MACD share the 5-point momentum factor and moving averages sit only in
trend, so one underlying trend cannot collect full credit several times.
"""
import math
from typing import Any, Callable, Dict, List, Optional

from terminal.qsf import technicals


def ramp(x: Optional[float], lo: float, hi: float) -> Optional[float]:
    """Linear 0..1 between lo and hi (lo > hi means lower is better); clipped.  None stays None."""
    if x is None or not math.isfinite(x):
        return None
    return max(0.0, min(1.0, (x - lo) / (hi - lo)))


class Mean(float):
    """A mean that remembers how many of its inputs were there, so that coverage can tell a factor built from one figure of
    four from a factor built from all four (audit 2026-11-22: such a factor counted as fully covered)."""
    have: int
    total: int

    def __new__(cls, value: float, have: int, total: int) -> "Mean":
        out = float.__new__(cls, value)
        out.have, out.total = have, total
        return out


def mean(vals: List[Optional[float]]) -> Optional[float]:
    v = [x for x in vals if x is not None]
    return Mean(sum(v) / len(v), len(v), len(vals)) if v else None


def pct(x: Optional[float], d: int = 1) -> str:
    return "없음" if x is None else f"{x * 100:.{d}f}%"


def num(x: Optional[float], d: int = 2) -> str:
    return "없음" if x is None else f"{x:,.{d}f}"


def missing(reason: str) -> Dict[str, Any]:
    return {"status": "MISSING", "reason": reason}


def not_applicable(reason: str) -> Dict[str, Any]:
    return {"status": "NOT_APPLICABLE", "reason": reason}


def obs(norm: Optional[float], raw: Dict, text: str, source: str, as_of: Optional[str], status: str = "REAL") -> Dict:
    if norm is None:
        return missing(f"{text}: 계산 값 없음")
    out = {"status": status, "normalized": float(norm), "raw": raw, "explanation": text, "source": source, "as_of": as_of}
    if isinstance(norm, Mean) and norm.have < norm.total:
        out["inputs"] = {"have": norm.have, "total": norm.total}        # only when something was missing: a full factor stays as it was
    return out


PRICE = "일봉 가격 (Yahoo Finance, 지연)"


# ---------------------------------------------------------------------- technical
def trend_structure(c) -> Dict:
    t = c["tech"]
    if t["ma200"] is None or t["ma50"] is None:
        return missing("이동평균 이력 부족")
    checks = [t["close"] > t["ma200"], t["close"] > t["ma50"], t["ma50"] > t["ma200"],
              t["ma20"] > t["ma50"], (t["ma50_slope"] or 0) > 0, (t["ma200_slope"] or 0) > 0]
    return obs(sum(checks) / 6, {"ma20": t["ma20"], "ma50": t["ma50"], "ma200": t["ma200"], "ma50_slope": t["ma50_slope"],
                                 "ma200_slope": t["ma200_slope"]},
               f"추세 조건 6개 중 {sum(checks)}개 충족 (종가 {num(t['close'])}, 50일선 {num(t['ma50'])}, 200일선 {num(t['ma200'])})",
               PRICE, t["date"])


def relative_strength(c) -> Dict:
    t, rank = c["tech"], c.get("rs_rank")
    if rank is not None:
        return obs(rank, {"percentile": rank, "rel_126": t.get("rel_126")},
                   f"유니버스 6개월 수익률 상위 {(1 - rank) * 100:.0f}% 위치", PRICE, t["date"])
    rel = mean([t.get("rel_63"), t.get("rel_126")])
    return obs(ramp(rel, -0.15, 0.20), {"rel_63": t.get("rel_63"), "rel_126": t.get("rel_126"), "benchmark": c.get("bench_name")},
               f"{c.get('bench_name')} 대비 3개월 {pct(t.get('rel_63'))}, 6개월 {pct(t.get('rel_126'))}", PRICE, t["date"])


def momentum(c) -> Dict:
    t = c["tech"]
    r = t["rsi"]
    rsi_s = None if r is None else (ramp(r, 30, 55) if r < 55 else 1.0 if r <= 65 else ramp(r, 85, 65))
    macd_s = ramp(t["macd_hist_pct"], -0.01, 0.01)
    return obs(mean([rsi_s, macd_s]), {"rsi": r, "macd_hist_pct": t["macd_hist_pct"]},
               f"RSI {num(r, 0)}, MACD 히스토그램 {pct(t['macd_hist_pct'], 2)} (둘을 한 요인으로 합산)", PRICE, t["date"])


def breakout_volume(c) -> Dict:
    t = c["tech"]
    dist = ramp(t["dist_high"], -0.25, 0.0)
    vr = t["volume_ratio"]
    conf = None if vr is None else (ramp(vr, 1.0, 2.0) if t["breakout"] else ramp(vr, 1.5, 0.8) * 0.5)
    gap = None if t["gap_today"] is None else (0.3 if t["gap_today"] > 0.02 and not t["held_gap"] else 0.7)
    return obs(mean([dist, dist, conf, gap]), {"dist_high": t["dist_high"], "breakout": t["breakout"], "volume_ratio": vr,
                                               "gap_today": t["gap_today"], "held_gap": t["held_gap"]},
               f"52주 고점 대비 {pct(t['dist_high'])}, 20일 고점 돌파 {'예' if t['breakout'] else '아니오'}, 거래량 {num(vr)}배",
               PRICE, t["date"])


def volatility_structure(c) -> Dict:
    t = c["tech"]
    return obs(None if t["bandwidth_pct"] is None else 1 - t["bandwidth_pct"],
               {"bandwidth": t["bandwidth"], "bandwidth_pct": t["bandwidth_pct"]},
               f"볼린저 폭이 1년 중 하위 {pct(t['bandwidth_pct'], 0)} 수준 (좁을수록 변동성 수축)", PRICE, t["date"])


def long_trend(c) -> Dict:
    t = c["tech"]
    if t["ma200"] is None:
        return missing("200일선 이력 부족")
    pos = ramp(t["close"] / t["ma200"] - 1, -0.15, 0.15)
    slope = ramp(t["ma200_slope"], -0.05, 0.05)
    return obs(mean([pos, slope]), {"ma200": t["ma200"], "ma200_slope": t["ma200_slope"]},
               f"200일선 대비 {pct(t['close'] / t['ma200'] - 1)}, 200일선 3개월 기울기 {pct(t['ma200_slope'])}", PRICE, t["date"])


def momentum_persistence(c) -> Dict:
    t = c["tech"]
    return obs(mean([ramp(t["ret_12_1"], -0.10, 0.30), t["pos_month_share"]]),
               {"ret_12_1": t["ret_12_1"], "pos_month_share": t["pos_month_share"]},
               f"12-1개월 수익률 {pct(t['ret_12_1'])}, 상승한 달 비율 {pct(t['pos_month_share'], 0)}", PRICE, t["date"])


# ---------------------------------------------------------------------- fundamentals
def _rr(f: Dict, key: str, lo: float, hi: float) -> Optional[float]:
    """Sector percentile when the research candidate supplies one in ``f["rel"]``; otherwise the absolute anchor."""
    rel = (f.get("rel") or {}).get(key)
    return rel if rel is not None else ramp(f.get(key), lo, hi)


def _f(c) -> Optional[Dict]:
    f = c.get("fund")
    return f if f and f.get("status") in ("REAL", "STALE") else None


def _fobs(c, norm, raw, text) -> Dict:
    f = c["fund"]
    return obs(norm, raw, text, f.get("source", "재무제표"), f.get("filed"), f.get("status", "REAL"))


def _fund_missing(c) -> Dict:
    f = c.get("fund") or {}
    return missing(f.get("reason") or "재무 데이터 없음")


def earnings_revenue_quality(c) -> Dict:
    f = _f(c)
    if not f:
        return _fund_missing(c)
    return _fobs(c, mean([_rr(f, "rev_growth", -0.05, 0.20), _rr(f, "eps_growth", -0.10, 0.25), ramp(f.get("ocf_to_ni"), 0.5, 1.2)]),
                 {k: f.get(k) for k in ("rev_growth", "eps_growth", "ocf_to_ni")},
                 f"매출 성장 {pct(f.get('rev_growth'))}, EPS 성장 {pct(f.get('eps_growth'))}, 영업현금/순이익 {num(f.get('ocf_to_ni'))}")


def profitability(c) -> Dict:
    f = _f(c)
    if not f:
        return _fund_missing(c)
    return _fobs(c, mean([_rr(f, "roe", 0.0, 0.20), _rr(f, "op_margin", 0.0, 0.20)]),
                 {k: f.get(k) for k in ("roe", "op_margin")}, f"ROE {pct(f.get('roe'))}, 영업이익률 {pct(f.get('op_margin'))}")


def balance_sheet(c) -> Dict:
    f = _f(c)
    if not f:
        return _fund_missing(c)
    if f.get("is_financial"):
        return _fobs(c, ramp(f.get("equity_assets"), 0.04, 0.15), {"equity_assets": f.get("equity_assets")},
                     f"금융업 기준: 자기자본/자산 {pct(f.get('equity_assets'))}")
    return _fobs(c, mean([_rr(f, "debt_equity", 2.0, 0.3), ramp(f.get("current_ratio"), 0.8, 2.0)]),
                 {k: f.get(k) for k in ("debt_equity", "current_ratio")},
                 f"부채/자본 {num(f.get('debt_equity'))}, 유동비율 {num(f.get('current_ratio'))}")


def cash_flow_quality(c) -> Dict:
    f = _f(c)
    if not f:
        return _fund_missing(c)
    if f.get("is_financial"):
        return not_applicable("금융업은 현금흐름 품질을 같은 기준으로 비교하지 않습니다")
    if f.get("cash_flow_note"):
        return missing(f["cash_flow_note"])
    return _fobs(c, mean([ramp(f.get("ocf_to_ni"), 0.5, 1.2), _rr(f, "fcf_margin", -0.02, 0.15)]),
                 {k: f.get(k) for k in ("ocf_to_ni", "fcf_margin")},
                 f"영업현금/순이익 {num(f.get('ocf_to_ni'))}, FCF 마진 {pct(f.get('fcf_margin'))}")


def valuation(c) -> Dict:
    f = _f(c)
    if not f:
        return _fund_missing(c)
    pe, pb, fy = f.get("pe"), f.get("pb"), f.get("fcf_yield")
    if pe is None and pb is None and fy is None:
        return missing("밸류에이션 계산에 필요한 가격·재무 값 없음")
    pe_s = 0.0 if pe is not None and pe <= 0 else _rr(f, "pe", 40, 10)
    if f.get("is_financial"):
        return _fobs(c, mean([pe_s, _rr(f, "pb", 2.5, 0.8)]), {"pe": pe, "pb": pb}, f"금융업 기준: PER {num(pe, 1)}, PBR {num(pb, 2)}")
    return _fobs(c, mean([pe_s, _rr(f, "pb", 8, 1.5), _rr(f, "fcf_yield", 0.0, 0.07)]), {"pe": pe, "pb": pb, "fcf_yield": fy},
                 f"PER {num(pe, 1)}, PBR {num(pb, 2)}, FCF 수익률 {pct(fy)}")


def business_quality(c) -> Dict:
    f = _f(c)
    if not f:
        return _fund_missing(c)
    stable = None if f.get("roe_years_positive") is None else f["roe_years_positive"]
    return _fobs(c, mean([_rr(f, "roe", 0.03, 0.25), _rr(f, "op_margin", 0.0, 0.25), _rr(f, "gross_margin", 0.15, 0.60), stable]),
                 {k: f.get(k) for k in ("roe", "op_margin", "gross_margin", "roe_years_positive")},
                 f"ROE {pct(f.get('roe'))}, 영업이익률 {pct(f.get('op_margin'))}, 매출총이익률 {pct(f.get('gross_margin'))}, 흑자 지속 비율 {pct(stable, 0)}")


def growth_quality(c) -> Dict:
    f = _f(c)
    if not f:
        return _fund_missing(c)
    return _fobs(c, mean([_rr(f, "rev_cagr3", -0.02, 0.15), _rr(f, "eps_cagr3", -0.05, 0.20), _rr(f, "rev_growth", -0.05, 0.20)]),
                 {k: f.get(k) for k in ("rev_cagr3", "eps_cagr3", "rev_growth")},
                 f"3년 매출 CAGR {pct(f.get('rev_cagr3'))}, 3년 EPS CAGR {pct(f.get('eps_cagr3'))}, 최근 매출 성장 {pct(f.get('rev_growth'))}")


def free_cash_flow(c) -> Dict:
    f = _f(c)
    if not f:
        return _fund_missing(c)
    if f.get("is_financial"):
        return not_applicable("금융업은 FCF 기준을 적용하지 않습니다")
    if f.get("cash_flow_note"):
        return missing(f["cash_flow_note"])
    return _fobs(c, mean([_rr(f, "fcf_margin", -0.02, 0.18), f.get("fcf_years_positive")]),
                 {k: f.get(k) for k in ("fcf_margin", "fcf_years_positive")},
                 f"FCF 마진 {pct(f.get('fcf_margin'))}, FCF 흑자 연도 비율 {pct(f.get('fcf_years_positive'), 0)}")


def balance_dilution(c) -> Dict:
    f = _f(c)
    if not f:
        return _fund_missing(c)
    dil = ramp(f.get("share_change"), 0.05, -0.01)
    if f.get("is_financial"):
        return _fobs(c, mean([ramp(f.get("equity_assets"), 0.04, 0.15), dil]), {k: f.get(k) for k in ("equity_assets", "share_change")},
                     f"자기자본/자산 {pct(f.get('equity_assets'))}, 주식 수 변화 {pct(f.get('share_change'))}")
    return _fobs(c, mean([_rr(f, "debt_equity", 2.0, 0.3), dil]), {k: f.get(k) for k in ("debt_equity", "share_change")},
                 f"부채/자본 {num(f.get('debt_equity'))}, 주식 수 변화 {pct(f.get('share_change'))}")


# ---------------------------------------------------------------------- regime
def _series_factor(c, key: str, build: Callable) -> Dict:
    s = (c.get("regime") or {}).get(key)
    if not s or s.get("status") == "UNAVAILABLE":
        return missing((s or {}).get("reason") or f"{key} 데이터 없음")
    res = build(s)
    if res.get("status") not in ("MISSING",) and s.get("status") == "STALE":
        res["status"] = "STALE"
    return res


def vix_regime(c) -> Dict:
    return _series_factor(c, "vix", lambda s: obs(ramp(s["value"], 35, 12), {"vix": s["value"], "percentile_5y": s.get("percentile")},
                                                  f"VIX {num(s['value'], 1)} (최근 5년 상위 {pct(1 - (s.get('percentile') or 0), 0)})", s["source"], s["date"]))


def vix_term(c) -> Dict:
    return _series_factor(c, "vix_term", lambda s: obs(ramp(s["value"], 1.05, 0.85), {"vix_vix3m": s["value"]},
                                                       f"VIX/VIX3M {num(s['value'])} (1 초과면 단기 공포 우위)", s["source"], s["date"]))


def credit_spread(c) -> Dict:
    return _series_factor(c, "hy_spread", lambda s: obs(None if s.get("percentile") is None else 1 - s["percentile"],
                                                        {"spread": s["value"], "percentile": s.get("percentile"), "window_obs": s.get("n")},
                                                        f"하이일드 스프레드 {num(s['value'])}%, 가용 이력({s.get('n')}개 관측) 내 위치 {pct(s.get('percentile'), 0)}",
                                                        s["source"], s["date"]))


def index_trend_breadth(c) -> Dict:
    def build(s):
        b = (c.get("regime") or {}).get("breadth") or {}
        tr = sum([s["close"] > s["ma200"], s["ma50"] > s["ma200"], s["close"] > s["ma50"]]) / 3
        br = ramp(b.get("value"), 0.30, 0.70) if b.get("status") == "REAL" else None
        txt = f"{s['symbol']} 추세 조건 {tr * 3:.0f}/3" + (f", 200일선 위 종목 {pct(b.get('value'), 0)}" if br is not None else ", 시장 폭 없음")
        return obs(mean([tr, br]), {"close": s["close"], "ma50": s["ma50"], "ma200": s["ma200"], "breadth": b.get("value")}, txt, s["source"], s["date"])
    return _series_factor(c, "index", build)


def vkospi_regime(c) -> Dict:
    return _series_factor(c, "vkospi", lambda s: obs(ramp(s["value"], 35, 12), {"vkospi": s["value"]}, f"VKOSPI {num(s['value'], 1)}", s["source"], s["date"]))


def index_trend(c) -> Dict:
    def build(s):
        tr = sum([s["close"] > s["ma200"], s["ma50"] > s["ma200"], s["close"] > s["ma50"]]) / 3
        return obs(tr, {"close": s["close"], "ma50": s["ma50"], "ma200": s["ma200"]}, f"{s['symbol']} 추세 조건 {tr * 3:.0f}/3", s["source"], s["date"])
    return _series_factor(c, "index", build)


def breadth(c) -> Dict:
    return _series_factor(c, "breadth", lambda s: obs(ramp(s["value"], 0.30, 0.70), {"breadth": s["value"], "n": s.get("n")},
                                                      f"200일선 위 종목 {pct(s['value'], 0)} ({s.get('n')}종목 기준)", s["source"], s["date"]))


def usdkrw_regime(c) -> Dict:
    return _series_factor(c, "usdkrw", lambda s: obs(ramp(s["change_63"], 0.05, -0.03), {"usdkrw": s["value"], "change_63": s["change_63"]},
                                                     f"원/달러 {num(s['value'], 0)}, 3개월 변화 {pct(s['change_63'])} (원화 약세일수록 위험 회피)", s["source"], s["date"]))


def credit_liquidity(c) -> Dict:
    return _series_factor(c, "kr_credit", lambda s: obs(s.get("normalized"), {"value": s.get("value"), "percentile": s.get("percentile"), "window_obs": s.get("n")}, s.get("text", ""), s.get("source", ""), s.get("date")))


# ---------------------------------------------------------------------- risk
def risk_reward(c) -> Dict:
    lv, t = c["levels"], c["tech"]
    if lv.get("status") != "REAL":
        return missing(lv.get("reason", "손절·목표 기준 없음"))
    return obs(ramp(lv["reward_risk"], 1.0, 3.0), {"reward_risk": lv["reward_risk"], "stop": lv["stop"], "target": lv["target"], "cost_pct": lv["round_trip_cost_pct"]},
               f"비용 반영 손익비 {num(lv['reward_risk'])} (손절 {num(lv['stop'])}, 목표 {num(lv['target'])}, {lv['target_method']})", PRICE, t["date"])


def atr_risk(c) -> Dict:
    t = c["tech"]
    return obs(mean([ramp(t["atr_pct"], 0.06, 0.015), ramp(t["hist_vol"], 0.70, 0.20)]), {"atr_pct": t["atr_pct"], "hist_vol": t["hist_vol"]},
               f"ATR {pct(t['atr_pct'])}, 연환산 변동성 {pct(t['hist_vol'], 0)}", PRICE, t["date"])


def liquidity(c) -> Dict:
    t = c["tech"]
    adv = t["adv_value"]
    if adv is None or adv <= 0:
        return missing("거래대금 없음")
    lo, hi = (1e9, 5e10) if c["market"] == "KR" else (2e7, 5e8)
    unit = "원" if c["market"] == "KR" else "달러"
    return obs(ramp(math.log10(adv), math.log10(lo), math.log10(hi)), {"adv_value": adv}, f"20일 평균 거래대금 {adv:,.0f}{unit}", PRICE, t["date"])


def drawdown_gap(c) -> Dict:
    t = c["tech"]
    return obs(mean([ramp(t["max_drawdown_252"], -0.45, -0.10), ramp(t["max_gap_60"], 0.12, 0.01)]),
               {"max_drawdown_252": t["max_drawdown_252"], "max_gap_60": t["max_gap_60"]},
               f"1년 최대 낙폭 {pct(t['max_drawdown_252'])}, 60일 최대 갭 {pct(t['max_gap_60'])}", PRICE, t["date"])


def financial_resilience(c) -> Dict:
    f = _f(c)
    if not f:
        return _fund_missing(c)
    if f.get("is_financial"):
        return _fobs(c, ramp(f.get("equity_assets"), 0.04, 0.15), {"equity_assets": f.get("equity_assets")}, f"금융업 기준: 자기자본/자산 {pct(f.get('equity_assets'))}")
    return _fobs(c, mean([ramp(f.get("current_ratio"), 0.8, 2.0), ramp(f.get("interest_cover"), 1.5, 10), ramp(f.get("cash_debt"), 0.05, 0.8)]),
                 {k: f.get(k) for k in ("current_ratio", "interest_cover", "cash_debt")},
                 f"유동비율 {num(f.get('current_ratio'))}, 이자보상배율 {num(f.get('interest_cover'), 1)}, 현금/부채 {num(f.get('cash_debt'))}")


def downside_drawdown(c) -> Dict:
    t = c["tech"]
    return obs(mean([ramp(t["downside_vol"], 0.45, 0.12), ramp(t["max_drawdown_252"], -0.50, -0.12)]),
               {"downside_vol": t["downside_vol"], "max_drawdown_252": t["max_drawdown_252"]},
               f"하방 변동성 {pct(t['downside_vol'], 0)}, 1년 최대 낙폭 {pct(t['max_drawdown_252'])}", PRICE, t["date"])


def leverage(c) -> Dict:
    f = _f(c)
    if not f:
        return _fund_missing(c)
    if f.get("is_financial"):
        return not_applicable("금융업은 부채비율을 일반 기업 기준으로 평가하지 않습니다")
    return _fobs(c, _rr(f, "debt_equity", 2.5, 0.2), {"debt_equity": f.get("debt_equity")}, f"부채/자본 {num(f.get('debt_equity'))}")


# ---------------------------------------------------------------------- events
def _e(c) -> Optional[Dict]:
    e = c.get("events")
    return e if e and e.get("status") in ("REAL", "STALE") else None


def _emiss(c) -> Dict:
    return missing((c.get("events") or {}).get("reason") or "공시 데이터 없음")


def earnings_calendar(c) -> Dict:
    e = c.get("earnings") or {}
    if e.get("sessions") is None:
        return missing("다음 실적 발표일을 확인하지 못했습니다")
    if e.get("basis") == "ESTIMATE":
        when = "추정일이 지났고 아직 공시 없음" if e.get("overdue") else f"{e['sessions']}거래일 후"
        return obs(ramp(float(e["sessions"]), 2, 15), {"next_earnings": e.get("date"), "sessions": e["sessions"], "basis": "ESTIMATE", "from": e.get("from"), "overdue": bool(e.get("overdue"))},
                   f"다음 실적 발표 추정 {e.get('date')} ({when}, 작년 같은 분기 {e.get('from')} 기준)", e.get("source", "추정"), c["tech"]["date"])
    return obs(ramp(float(e["sessions"]), 2, 15), {"next_earnings": e.get("date"), "sessions": e["sessions"]},
               f"다음 실적 발표 {e.get('date')} ({e['sessions']}거래일 후)", e.get("source", "Yahoo 일정"), c["tech"]["date"])


def _event_list(ev: Dict, key: str) -> List[Dict]:
    return ev.get(key) or []


def material_disclosures(c) -> Dict:
    e = _e(c)
    if not e:
        return _emiss(c)
    neg, pos = _event_list(e, "negative"), _event_list(e, "positive")
    norm = max(0.0, min(1.0, 0.6 + 0.1 * len(pos) - 0.25 * len(neg)))
    names = ", ".join(x["label"] for x in (neg + pos)[:3]) or "주목할 공시 없음"
    return obs(norm, {"negative": len(neg), "positive": len(pos), "window_days": e.get("window_days")},
               f"최근 {e.get('window_days')}일 부정 {len(neg)}건, 긍정 {len(pos)}건 ({names})", e["source"], e.get("as_of"))


def insider_activity(c) -> Dict:
    e = _e(c)
    i = (e or {}).get("insider")
    if not e:
        return _emiss(c)
    if not i or i.get("status") != "REAL":
        return missing("내부자 공시를 해석할 수 없습니다")
    buy, sell = i["open_market_buy"], i["open_market_sell"]
    gross = buy + sell
    norm = 0.5 if gross == 0 else ramp((buy - sell) / gross, -1.0, 1.0)
    return obs(norm, i, f"최근 {i['window_days']}일 장내 매수 {buy:,.0f}, 장내 매도 {sell:,.0f} (보상·옵션·세금 원천징수 제외)", i.get("source", e["source"]), e.get("as_of"))


def governance(c) -> Dict:
    e = _e(c)
    if not e:
        return _emiss(c)
    g = _event_list(e, "governance")
    return obs(max(0.0, 0.8 - 0.3 * len(g)), {"issues": [x["label"] for x in g], "window_days": e.get("window_long_days")},
               "지배구조 경고 공시 없음" if not g else "경고 공시: " + ", ".join(x["label"] for x in g[:3]), e["source"], e.get("as_of"))


def material_events(c) -> Dict:
    e = _e(c)
    if not e:
        return _emiss(c)
    neg, pos = _event_list(e, "negative"), _event_list(e, "positive")
    return obs(max(0.0, min(1.0, 0.6 + 0.1 * len(pos) - 0.3 * len(neg))), {"negative": len(neg), "positive": len(pos)},
               f"중요 이벤트 부정 {len(neg)}건, 긍정 {len(pos)}건", e["source"], e.get("as_of"))


def insider_ownership(c) -> Dict:
    e = _e(c)
    i = (e or {}).get("insider") or {}
    f = c.get("fund") or {}
    own = f.get("insider_pct")
    net = None
    if i.get("status") == "REAL" and i["open_market_buy"] + i["open_market_sell"] > 0:
        net = ramp((i["open_market_buy"] - i["open_market_sell"]) / (i["open_market_buy"] + i["open_market_sell"]), -1, 1)
    return obs(mean([ramp(own, 0.0, 0.10), net]), {"insider_pct": own, "insider": i or None},
               f"내부자 지분 {pct(own)}, 장내 순매수 점수 {num(net)}", "Yahoo 지분 정보 + 내부자 공시", (e or {}).get("as_of"))


def capital_allocation(c) -> Dict:
    f = _f(c)
    if not f:
        return _fund_missing(c)
    return _fobs(c, mean([ramp(f.get("share_change"), 0.05, -0.02), 1.0 if f.get("returns_capital") else 0.4 if f.get("returns_capital") is not None else None]),
                 {k: f.get(k) for k in ("share_change", "returns_capital")},
                 f"주식 수 변화 {pct(f.get('share_change'))}, 자사주·배당 환원 {'있음' if f.get('returns_capital') else '없음' if f.get('returns_capital') is not None else '알 수 없음'}")


CALC: Dict[str, Callable] = {f.__name__: f for f in (
    trend_structure, relative_strength, momentum, breakout_volume, volatility_structure, long_trend, momentum_persistence,
    earnings_revenue_quality, profitability, balance_sheet, cash_flow_quality, valuation, business_quality, growth_quality,
    free_cash_flow, balance_dilution, vix_regime, vix_term, credit_spread, index_trend_breadth, vkospi_regime, index_trend,
    breadth, usdkrw_regime, credit_liquidity, risk_reward, atr_risk, liquidity, drawdown_gap, financial_resilience,
    downside_drawdown, leverage, earnings_calendar, material_disclosures, insider_activity, governance, material_events,
    insider_ownership, capital_allocation)}


__all__ = ["CALC", "ramp", "technicals"]
