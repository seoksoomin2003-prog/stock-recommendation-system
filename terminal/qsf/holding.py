"""Entry assessment, holding-period plan and exit evaluation.  Deterministic rules; every horizon, level and action
carries the reason that produced it.  All durations are research hypotheses, not proven optimal periods."""
import math
from datetime import date, datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

from terminal.qsf import config, deal_pin
from utils import nyse_calendar


def next_session_us(d: date) -> date:
    return nyse_calendar.next_session(d)


def next_session_kr(d: date) -> date:
    """KR: weekdays only, matching the KR market config's next-session rule (holidays observed from index bars)."""
    d += timedelta(days=1)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def stepper(market: str) -> Callable[[date], date]:
    return next_session_us if market == "US" else next_session_kr


def add_sessions(start: date, n: int, step: Callable[[date], date]) -> date:
    d = start
    for _ in range(n):
        d = step(d)
    return d


def add_months(d: date, months: int) -> date:
    y, m = d.year + (d.month - 1 + months) // 12, (d.month - 1 + months) % 12 + 1
    last = [31, 29 if y % 4 == 0 and (y % 100 or y % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1]
    return date(y, m, min(d.day, last))


def on_or_after_session(d: date, step: Callable[[date], date]) -> date:
    return step(d - timedelta(days=1))


def _factor(res: Dict, fid: str) -> Optional[float]:
    return next((r["normalized"] for r in res["factors"] if r["factor"] == fid), None)


def _f(ctx: Dict, key: str):
    return (ctx.get("fund") or {}).get(key)


# ---------------------------------------------------------------------- entry
def entry_status(res: Dict, ctx: Dict) -> Dict[str, Any]:
    t, lv, strategy = res["tech"], res["levels"], res["strategy"]
    e = ctx.get("earnings") or {}
    atr = t.get("atr")
    if res["actionability"] == "INSUFFICIENT_DATA":
        return {"status": "NO_VALID_ENTRY_SETUP", "reason": "데이터가 부족해 진입을 평가할 수 없습니다.", "zone": None}
    if res["actionability"] == "BLOCKED":
        return {"status": "NO_VALID_ENTRY_SETUP", "reason": "위험 게이트: " + res["gates"][0]["text"], "zone": None}
    if (res["score"] or 0) < 55:
        return {"status": "NO_VALID_ENTRY_SETUP", "reason": f"점수 {res['score']:.1f}점이 관찰 기준 55점 미만입니다.", "zone": None}
    pin = res.get("deal_pin")
    if pin:                         # held near a deal price (deal_pin, 2026-11-24): the room above is the deal price, whatever the score
        return {"status": "NO_VALID_ENTRY_SETUP", "reason": f"합병 절차로 가격이 묶인 종목입니다({pin['label']} {pin['date']}, 최근 20거래일 변동성 연 {pin['vol20']:.1f}%). 오를 여지가 인수 가격까지뿐이라 진입을 찾지 않습니다.", "zone": None}
    if res.get("band_held_back"):
        # The buy band was taken back because the score reaches it only with a factor absent (QSF-1.5.1).  Until QSF-1.5.3 the
        # entry rule did not read that: the card left the buy band and stayed "enter now" in the order plan, while '사도 돼?'
        # said wait (assessment 2026-11-25; user decision "주문 계획에서 빼기").
        cs = res.get("conservative_score")
        return {"status": "NO_VALID_ENTRY_SETUP", "zone": None,
                "reason": "자료가 빠진 요인을 중간값으로 보면 " + (f"{cs:.1f}점으로 " if cs is not None else "")
                          + "상위 구간 기준에 못 미쳐 구간을 낮춘 종목입니다. 빠진 자료가 채워질 때까지 진입을 판단하지 않습니다."}
    if strategy == "LONG_TERM":
        v = _factor(res, "valuation")
        if v is None:
            # The rule below reads the valuation.  Without one it used to say "the valuation does not block entry": the same stock
            # read "overvalued" with its figures and "enter now" without them (assessment 2026-11-23; user decision).
            return {"status": "NO_VALID_ENTRY_SETUP", "reason": "밸류에이션 자료가 없어 진입을 판단하지 않습니다. 자료가 없다는 것은 값이 적당하다는 뜻이 아닙니다.", "zone": None}
        if v is not None and v < 0.25:
            # Until 2026-11-22 this stopped only a good business at a poor valuation: a poor valuation with a poor business went
            # through as "the valuation does not block entry" (assessment 2026-11-22; user decision "구멍만 막기").
            q = _factor(res, "business_quality")
            why = (f"사업 품질은 좋지만 밸류에이션 점수가 {v * 100:.0f}/100으로 낮습니다." if (q or 0) >= 0.6 else
                   f"밸류에이션 점수가 {v * 100:.0f}/100으로 낮고, 사업 품질 점수도 {'없음' if q is None else f'{q * 100:.0f}/100'}입니다.")
            return {"status": "OVERVALUED_AT_CURRENT_PRICE", "reason": why, "zone": None}
        if e.get("sessions") is not None and e["sessions"] <= config.EARNINGS_BLOCK_SESSIONS:
            return {"status": "WAIT_FOR_EARNINGS", "reason": f"실적 발표 {e['date']} 이후 숫자를 확인하고 판단합니다.", "zone": None}
        zone = _zone(t["close"], atr, 1.0)
        return {"status": "ENTRY_NOW", "reason": f"점수 {res['score']:.1f}점이고 밸류에이션이 진입을 막는 수준이 아닙니다. 막는 조건이 없다는 뜻이고 좋은 때라는 뜻은 아닙니다.", "zone": zone}
    if e.get("sessions") is not None and e["sessions"] <= 5:
        return {"status": "WAIT_FOR_EARNINGS", "reason": f"실적 발표 {e['date']}가 {e['sessions']}거래일 뒤라 최소 보유 기간과 겹칩니다.", "zone": None}
    if lv.get("status") != "REAL":
        return {"status": "NO_VALID_ENTRY_SETUP", "reason": lv.get("reason"), "zone": None}
    rr, need = lv["reward_risk"], config.SWING["min_reward_risk"]
    if t["breakout"] and (t["volume_ratio"] or 0) < 1.2:
        return {"status": "WAIT_FOR_BREAKOUT_CONFIRMATION", "reason": f"20일 고점을 넘었지만 거래량이 평균의 {t['volume_ratio'] or 0:.2f}배로 확인되지 않았습니다.",
                "zone": None}
    if rr is None or rr < need:
        pull = t.get("ma20") or (t["close"] - atr)
        why = (f"위에 저항선이 없어 목표가를 {config.SWING['projection_atr']:g} ATR 위로 잡는데, 그러면 지금 가격에서의 손익비({0 if rr is None else rr:.2f})는 계산상 기준 {need:g}에 닿지 않습니다. "
               "신고가 근처를 따라가지 않고 20일선 부근의 눌림을 기다리는 규칙입니다." if not t.get("resistance") else
               f"현재 가격의 손익비 {0 if rr is None else rr:.2f}가 기준 {need:g} 미만입니다. 20일선 부근이면 손익비가 개선됩니다.")
        return {"status": "WAIT_FOR_PULLBACK", "reason": why, "zone": _zone(pull, atr, 0.5)}
    return {"status": "ENTRY_NOW", "reason": f"점수 {res['score']:.1f}점, 비용 반영 손익비 {rr:.2f}, 추세 요인 {(_factor(res, 'trend_structure') or 0) * 100:.0f}/100입니다.",
            "zone": _zone(t["close"], atr, 0.5)}


def _zone(center: float, atr: Optional[float], width: float) -> Optional[Dict[str, float]]:
    return None if not atr else {"low": center - width * atr, "high": center + width * atr * 0.5}


# ---------------------------------------------------------------------- swing horizon
def swing_plan(res: Dict, ctx: Dict, entry_date: date) -> Dict[str, Any]:
    t, lv, p = res["tech"], res["levels"], config.SWING
    step = stepper(res["market"])
    reasons: List[str] = []
    base = (p["min"] + p["max"]) // 2
    if lv.get("status") == "REAL" and t.get("atr"):
        # Sessions to cover the distance: ATR measures a day's range, a trend covers roughly a third of it net per day.
        dist = (lv["target"] - lv["entry"]) / t["atr"]
        base = int(round(dist * 3))
        reasons.append(f"목표까지 {dist:.1f} ATR ÷ 하루 약 1/3 ATR 순진행 = 약 {base}거래일")
    else:
        reasons.append("목표 기준이 없어 기본값(5~20일의 중간)을 씁니다")
    expected = max(p["min"], min(p["max"], base))
    if expected != base:
        reasons.append(f"초기 정책 범위 {p['min']}~{p['max']}일로 제한")
    trend, mom = _factor(res, "trend_structure"), _factor(res, "momentum")
    persistent = trend is not None and mom is not None and trend >= 0.8 and mom >= 0.6
    high_vol = (t.get("atr_pct") or 0) > 0.05
    if persistent and expected < p["max"]:
        expected = min(p["max"], expected + 5)
        reasons.append("추세와 모멘텀이 모두 강해 5일 연장")
    if high_vol and expected > p["min"]:
        expected = max(p["min"], expected - 5)
        reasons.append(f"ATR {t['atr_pct'] * 100:.1f}%로 변동성이 커 5일 단축")
    e = ctx.get("earnings") or {}
    if e.get("sessions") is not None and e["sessions"] > 0 and e["sessions"] <= expected:
        expected = max(1, e["sessions"] - 1)
        reasons.append(f"실적 발표 {e['date']} 전에 재평가하도록 단축")
    low, high = max(1, min(p["min"], expected)), max(expected, min(p["max"], expected + 5))
    return {"strategy": "SWING", "entry_date": entry_date.isoformat(), "expected_sessions": expected, "range_sessions": [low, high],
            "first_review": add_sessions(entry_date, p["review_every"], step).isoformat(), "review_every_sessions": p["review_every"],
            "expected_exit": add_sessions(entry_date, expected, step).isoformat(),
            "time_stop_review": add_sessions(entry_date, p["time_stop"], step).isoformat(),
            "time_stop_note": "이 날짜에 자동 매도하지 않습니다. 논리가 유효한지 재평가합니다.",
            "stop": lv.get("stop"), "target": lv.get("target"), "stop_method": lv.get("stop_method"), "target_method": lv.get("target_method"),
            "reward_risk": lv.get("reward_risk"), "cost_basis": lv.get("cost_basis"),
            "gap_note": "손절은 체결을 보장하지 않습니다. 갭이 생기면 더 불리한 가격에 나갈 수 있습니다.",
            "invalidation": _swing_invalidation(t, lv), "exit_triggers": ["종가 손절선 이탈", "종가 50일선 이탈 + 50일선 하락", "목표 도달",
                                                                       "손익비 1 미만으로 악화", "실적·중대 공시 전 재평가", "시장 국면 급악화", "거래대금 기준 미달"],
            "why": reasons, "status": "HYPOTHESIS"}


def _swing_invalidation(t: Dict, lv: Dict) -> List[str]:
    out = []
    if lv.get("stop"):
        out.append(f"종가가 {lv['stop']:,.2f} 아래로 마감")
    if t.get("ma50"):
        out.append(f"종가가 50일선 {t['ma50']:,.2f} 아래로 마감하고 50일선이 하락 전환")
    return out or ["기준 가격을 계산할 수 없습니다"]


# ---------------------------------------------------------------------- long-term horizon
def long_plan(res: Dict, ctx: Dict, entry_date: date) -> Dict[str, Any]:
    p = config.LONG_TERM
    step = stepper(res["market"])
    reasons, low, high = [], p["min_months"], p["max_months"]
    q, g, v = _factor(res, "business_quality"), _factor(res, "growth_quality"), _factor(res, "valuation")
    if q is not None and g is not None and q >= 0.7 and g >= 0.6:
        low = 24
        reasons.append(f"사업 품질 {q * 100:.0f}/100, 성장 품질 {g * 100:.0f}/100으로 복리 기간을 길게 봅니다")
    elif q is not None and q < 0.4:
        high = 24
        reasons.append(f"사업 품질 {q * 100:.0f}/100으로 낮아 상단을 24개월로 줄입니다")
    else:
        reasons.append("초기 정책 범위 12~36개월을 그대로 씁니다")
    if v is not None and v < 0.25:
        reasons.append(f"밸류에이션 {v * 100:.0f}/100: 진입 전 관찰 기간이 더 필요할 수 있습니다")
    first = on_or_after_session(add_months(entry_date, p["review_months"]), step)
    second = on_or_after_session(add_months(entry_date, 2 * p["review_months"]), step)
    return {"strategy": "LONG_TERM", "entry_date": entry_date.isoformat(), "range_months": [low, high], "first_review": first.isoformat(), "next_review": second.isoformat(),
            "review_note": "12개월이 지났다는 이유만으로 매도하지 않습니다. 강제 종료일은 없습니다.", "milestones": _milestones(ctx),
            "invalidation": ["수익성 지속 악화 (ROE·영업이익률 하락)", "정당한 이유 없는 FCF 적자 지속", "재무 건전성 악화", "중대한 지배구조 문제", "심각한 주식 희석"],
            "reduce_conditions": ["밸류에이션 점수 25/100 미만 지속", "종목·섹터 한도 초과"], "scenarios": _scenarios(res, ctx), "why": reasons, "status": "HYPOTHESIS"}


def _milestones(ctx: Dict) -> List[str]:
    f = ctx.get("fund") or {}
    out = []
    if f.get("rev_growth") is not None:
        out.append(f"다음 실적의 매출 성장률이 최근 {f['rev_growth'] * 100:.1f}%를 유지하는지" if f["rev_growth"] >= 0 else
                   f"다음 실적에서 매출 감소(최근 {f['rev_growth'] * 100:.1f}%)가 멈추는지")
    if f.get("op_margin") is not None:
        out.append(f"영업이익률 {f['op_margin'] * 100:.1f}% 유지 여부")
    if f.get("fcf_margin") is not None:
        out.append(f"FCF 마진 {f['fcf_margin'] * 100:.1f}% 유지 여부")
    if not out and f.get("roe") is not None:                 # a bank or an insurer: no sales or margin line, but its return on equity is there
        out.append(f"다음 실적에서 자기자본이익률(ROE) {f['roe'] * 100:.1f}%가 유지되는지")
    return out or ["매출·이익률·현금흐름 수치가 없어 점검 항목을 정할 수 없습니다"]


def _scenarios(res: Dict, ctx: Dict) -> Dict[str, Any]:
    """One-year EPS x multiple.  Only when EPS and PER exist; otherwise explicitly unavailable, never a guess."""
    f = ctx.get("fund") or {}
    eps, pe, g = f.get("eps"), f.get("pe"), f.get("rev_growth")
    if not eps or eps <= 0 or not pe or pe <= 0 or g is None:
        return {"status": "UNAVAILABLE", "reason": "EPS, PER 또는 성장률이 없거나 적자라 시나리오를 만들지 않습니다."}
    def case(name, gm, mult, why):
        return {"case": name, "price": eps * (1 + gm) * mult, "eps_growth": gm, "multiple": mult, "assumption": why}
    g = max(-0.2, min(0.3, g))
    return {"status": "REAL", "method": "1년 뒤 EPS × 배수. 가정에 크게 의존하는 참고 범위입니다.",
            "cases": [case("약세", g - 0.10, pe * 0.75, "성장 10%p 둔화, 배수 25% 축소"), case("기준", g, pe, "최근 매출 성장 유지, 현재 배수"),
                      case("강세", g + 0.05, pe * 1.15, "성장 5%p 개선, 배수 15% 확대")]}


# ---------------------------------------------------------------------- exits
def evaluate_exit(res: Dict, ctx: Dict, position: Dict[str, Any], today: date) -> Dict[str, Any]:
    """``position``: avg_cost, opened (ISO), stop, target.  Returns one action plus every condition checked."""
    kr = ctx.get("market") == "KR"
    px, ga = (lambda v: f"{v:,.0f}원"), "이"
    if not kr:
        px, ga = (lambda v: f"{v:,.2f}"), "가"
    t, strategy = res["tech"], res["strategy"]
    hits: List[Dict[str, str]] = []
    step = stepper(res["market"])

    def hit(code, action, text):
        hits.append({"code": code, "action": action, "text": text})
    close, stop, target = t["close"], position.get("stop"), position.get("target")
    if strategy == "SWING":
        if stop and close <= stop:
            hit("STOP_BREACH", "EXIT", f"종가 {px(close)}{ga} 손절 기준 {px(stop)} 이하입니다. 다음 시가 체결을 가정하면 손절가보다 불리할 수 있습니다.")
        if t.get("ma50") and close < t["ma50"] and (t.get("ma50_slope") or 0) < 0:
            hit("TREND_BREAKDOWN", "THESIS_INVALIDATED", f"종가가 하락 중인 50일선 {px(t['ma50'])} 아래입니다.")
        m = _factor(res, "momentum")
        if m is not None and m < 0.25:
            hit("MOMENTUM_DETERIORATION", "REDUCE", f"모멘텀 점수가 {m * 100:.0f}/100으로 낮습니다.")
        if target and close >= target:
            hit("TARGET_REACHED", "PARTIAL_TAKE_PROFIT", f"종가가 목표 {px(target)}에 도달했습니다.")
        if stop and target and close > stop and (target - close) / (close - stop) < 1:
            hit("REWARD_RISK_DETERIORATED", "HOLD_AND_REVIEW", f"남은 손익비가 {(target - close) / (close - stop):.2f}로 1 미만입니다.")
        e = ctx.get("earnings") or {}
        if e.get("sessions") is not None and e["sessions"] <= config.EARNINGS_BLOCK_SESSIONS:
            hit("EVENT_RISK", "HOLD_AND_REVIEW", f"실적 발표 {e['date']}가 임박했습니다.")
        if position.get("opened"):
            opened = datetime.strptime(position["opened"], "%Y-%m-%d").date()
            ts = add_sessions(opened, config.SWING["time_stop"], step)
            hr = position.get("hold_rules")                # the turnover rules when they are in force (turnover_book.active_rules)
            if today >= ts and hr and today < add_sessions(opened, hr["hold_cap"], step) and (res["score"] or 0) >= hr["hold_score"] and res["actionability"] == "ACTIONABLE":
                hit("TIME_STOP_EXTENDED", "HOLD", f"보유 {config.SWING['time_stop']}거래일이 지났지만 스윙 점수 {res['score']:.1f}점이 {hr['hold_score']:g}점 이상이고 차단이 없어 "
                                                  f"계속 보유로 읽습니다(최대 {hr['hold_cap']}거래일, 회전율 규칙).")
            elif today >= ts:
                hit("TIME_STOP", "TIME_STOP_REVIEW", f"보유 {config.SWING['time_stop']}거래일이 지나 재평가 대상입니다 ({ts}). 자동 매도는 아닙니다.")
        regime = res["domains"]["REGIME"].get("score_100")           # 0.0 is the worst reading there is, not a missing one (audit 2026-11-22, RED-04)
        if regime is not None and regime < 25:
            if config.ADVERSE_SIZE_FACTOR.get(res["market"], 1.0) < 1.0:
                hit("REGIME_SEVERE", "REDUCE", f"시장 국면 점수가 {regime:.0f}/100으로 급악화했습니다.")
            else:
                # A market whose state value the test found nothing in (MKT-1: Korea) and whose order size does not read it
                # (user decision 2026-11-16) does not tell a holder to reduce on it either: a reference line (user decision
                # 2026-11-25).  The Korean value is mostly the won and the credit spread; it sat at 25-27 for eight sessions.
                hit("REGIME_NOTE", "HOLD", f"참고: 시장 상태 값이 {regime:.0f}/100으로 낮습니다. 이 시장에서는 이 값의 뜻이 검증에서 확인되지 않아 "
                                           "줄이라는 판단은 내리지 않습니다. 청산 조건에는 해당하지 않습니다.")
    else:
        # Price alone is not a long-term exit rule.  This one exists because the user requires a stop and chose this reading of it.
        if stop and close <= stop:
            hit("STOP_BREACH", "EXIT", f"종가 {px(close)}{ga} 직접 정한 손절가 {px(stop)} 이하입니다.")
        rr, share = position.get("rank_rules"), position.get("ahead_share")      # the rank rules when they are in force (rank_book.active_rules)
        if rr and share is not None and share >= rr["long_exit_top"]:
            hit("RANK_OUT", "REDUCE", f"장기 점수 순위가 그날 평가한 종목의 상위 {share * 100:.0f}% 지점으로, 보유 기준(상위 {rr['long_exit_top'] * 100:.0f}%) 밖입니다(순위 규칙).")
        f = ctx.get("fund") or {}
        if f.get("roe") is not None and f.get("roe_prev") is not None and f["roe"] < f["roe_prev"] - 0.05 and f["roe"] < 0.08:
            hit("PROFITABILITY_DOWN", "THESIS_INVALIDATED", f"ROE가 {f['roe_prev'] * 100:.1f}%에서 {f['roe'] * 100:.1f}%로 하락했습니다.")
        if f.get("fcf_years_positive") is not None and f["fcf_years_positive"] < 0.34 and not f.get("is_financial"):
            hit("NEGATIVE_FCF", "HOLD_AND_REVIEW", "최근 연도 대부분 FCF가 적자입니다. 이유가 있는지 확인이 필요합니다.")
        r = _factor(res, "financial_resilience")
        if r is not None and r < 0.2:
            hit("BALANCE_DETERIORATION", "REDUCE", f"재무 복원력 점수가 {r * 100:.0f}/100입니다.")
        for g in ((ctx.get("events") or {}).get("governance") or [])[:2]:
            hit("GOVERNANCE", "HOLD_AND_REVIEW", f"지배구조 공시: {g['label']}")
        if f.get("share_change") is not None and f["share_change"] > 0.10:
            hit("SEVERE_DILUTION", "THESIS_INVALIDATED", f"주식 수가 1년간 {f['share_change'] * 100:.1f}% 늘었습니다.")
        v = _factor(res, "valuation")
        if v is not None and v < 0.1:
            hit("VALUATION_EXTREME", "PARTIAL_TAKE_PROFIT", f"밸류에이션 점수가 {v * 100:.0f}/100으로 매우 낮습니다.")
        if (position.get("weight_pct") or 0) > (position.get("max_weight_pct") or math.inf):
            hit("CONCENTRATION", "REDUCE", f"비중 {position['weight_pct']:.1f}%가 한도 {position['max_weight_pct']:.0f}%를 넘습니다.")
    for s in ((ctx.get("events") or {}).get("severe") or []):
        hit("SEVERE_EVENT", "EXIT", f"중대한 공시: {s['label']}")
    if (t.get("adv_value") or 0) < config.GATES[res["market"]]["min_adv_value"]:
        hit("LIQUIDITY", "REDUCE", "거래대금이 기준 아래로 떨어졌습니다.")
    order = ["EXIT", "THESIS_INVALIDATED", "REDUCE", "PARTIAL_TAKE_PROFIT", "TIME_STOP_REVIEW", "HOLD_AND_REVIEW", "HOLD"]
    action = next((a for a in order if any(h["action"] == a for h in hits)), "HOLD")
    must = "손절선과 추세가 유지되어야 합니다." if strategy == "SWING" else "수익성, 현금흐름, 재무 건전성이 유지되어야 합니다."
    kept = next((h["text"] for h in hits if h["action"] == "HOLD"), None)
    return {"action": action, "conditions": hits, "reason": next(h["text"] for h in hits if h["action"] == action) if action != "HOLD" else kept or f"청산 조건에 해당하지 않습니다. {must}"}


def what_would_change(res: Dict) -> List[str]:
    out, s = [], res["score"]
    if s is None or res["actionability"] == "INSUFFICIENT_DATA":
        return ["부족한 데이터가 채워지면 점수를 판단할 수 있습니다: " + ", ".join(res["missing"][:4])]
    above = [(lo, label) for lo, _, label in config.BANDS if lo > s]
    pin = res.get("deal_pin")
    if pin:
        # a pinned stock gets no buy band whatever its score: "3.2 points more is a strong buy" was false for it (2026-11-25)
        out.append("합병 절차로 가격이 묶여 있는 동안은 점수가 올라도 상위 구간을 주지 않습니다. 거래가 끝나거나 깨져 가격이 다시 움직이면"
                   f"(최근 20거래일 변동성 연 {deal_pin.PIN_VOL:g}% 이상) 점수 구간대로 읽습니다.")
    elif res.get("band_held_back"):
        out.append("빠진 자료가 채워져 그 요인을 넣고도 상위 구간 기준(" + f"{config.BANDS[1][0]:g}점) 이상이면 상위 구간과 진입 판단이 돌아옵니다.")
    elif above:
        lo, label = min(above)
        out.append(f"{lo - s:.1f}점 오르면 '{label}' 구간입니다.")
    floor = max((lo for lo, _, _ in config.BANDS if lo <= s), default=0.0)
    if res.get("band") == "BUY_CANDIDATE" and s >= config.BUY_BAND_EXIT:
        # in at 70, out under 67: the next record keeps the band down to the buffer's floor
        out.append(f"{s - config.BUY_BAND_EXIT:.1f}점 넘게 내려가 {config.BUY_BAND_EXIT:g}점 아래가 되면 상위 구간을 벗어납니다({config.BANDS[1][0]:g}점에 들어가고 {config.BUY_BAND_EXIT:g}점 아래에서 나가는 완충).")
    elif floor > 0:
        out.append(f"{s - floor:.1f}점 내려가면 현재 구간을 벗어납니다.")
    for g in res["gates"]:
        out.append(f"게이트 해제 필요: {g['text']}")
    if res["top_negative"]:
        out.append(f"가장 큰 감점 요인: {res['top_negative'][0]['text']}")
    return out
