"""QSF scoring: weighted factors -> domain and composite scores, coverage, confidence, gates, classification.

composite = 100 * sum(weight * normalized) / sum(weight of factors with data).  A missing factor leaves both sums
(it is never zero) and lowers coverage instead.  Not-applicable factors also leave the coverage denominator.
Confidence is reported separately and never multiplies the score.  Gates override actionability, not the score.
A profile's reference domains are computed and kept on the card with ``scored: False`` and weight 0: they enter neither sum.
"""
from typing import Any, Dict, List, Optional, Sequence

from terminal.qsf import config, factors, technicals

_QUALITY = {"REAL": 1.0, "STALE": 0.5}


def classify(score: Optional[float]) -> Dict[str, str]:
    if score is None:
        return {"band": "NONE", "band_label": "점수 없음"}
    for lo, code, label in config.BANDS:
        if score >= lo:
            return {"band": code, "band_label": label}
    return {"band": "SELL_AVOID", "band_label": "매도·회피 후보"}


def action_for(score: Optional[float], held: bool) -> str:
    """Held and new candidates get different words: SELL only ever applies to a position actually held."""
    if score is None:
        return "INSUFFICIENT_DATA"
    if held:
        return "HOLD" if score >= 55 else "REDUCE" if score >= 40 else "SELL"
    return "BUY" if score >= 70 else "WATCH" if score >= 55 else "AVOID"


def _color(action: str, score: Optional[float]) -> str:
    """40-54.99 is the orange band even for a stock not held; red starts below 40 (spec 3.1)."""
    if action == "AVOID" and score is not None and score >= 40:
        return config.COLORS["REDUCE"]
    return config.COLORS[action]


def hard_gates(ctx: Dict[str, Any], strategy: str) -> List[Dict[str, str]]:
    t, market = ctx["tech"], ctx["market"]
    g = config.GATES[market]
    out = []

    def add(code, text):
        out.append({"code": code, "text": text})
    if not ctx.get("price_fresh", True):
        add("STALE_PRICE", f"마지막 시세 {t['date']}가 최근 완료 거래일 {ctx.get('expected_session')}이 아닙니다.")
    if t["n"] < config.MIN_BARS:
        add("SHORT_HISTORY", f"가격 이력이 {t['n']}일로 최소 {config.MIN_BARS}일에 못 미칩니다.")
    if t.get("max_move_5") is not None and t["max_move_5"] > config.EXTREME_MOVE:
        add("DATA_ANOMALY", f"최근 5일 안에 하루 {t['max_move_5'] * 100:.0f}% 변동이 있어 데이터 확인이 필요합니다.")
    if t.get("last_volume") == 0:
        add("NO_TRADING", "최근 거래일 거래량이 0입니다 (거래 정지 가능성).")
    if t.get("adv_value") is None or t["adv_value"] < g["min_adv_value"]:
        add("LOW_LIQUIDITY", f"20일 평균 거래대금이 기준 {g['min_adv_value']:,.0f} 미만이거나 없습니다.")
    if g["min_price"] and t["close"] < g["min_price"]:
        add("LOW_PRICE", f"주가가 기준 {g['min_price']:g} 미만입니다.")
    if ctx.get("identity_ok") is False:
        add("INVALID_IDENTITY", "종목 식별 정보를 확인할 수 없습니다.")
    for s in ((ctx.get("events") or {}).get("severe") or []):
        add("SEVERE_EVENT", f"중대한 공시: {s['label']} ({s.get('date')})")
    fund = ctx.get("fund") or {}
    if fund.get("basis_conflict"):
        add("INVALID_ACCOUNTING", "연결·별도 재무제표 기준이 섞여 있어 재무 값을 쓸 수 없습니다.")
    e = ctx.get("earnings") or {}
    if strategy == "SWING" and e.get("sessions") is not None and e.get("basis") == "ESTIMATE":
        if e.get("overdue"):
            add("EARNINGS_IMMINENT", f"실적 발표 추정일({e.get('date')})이 지났는데 아직 공시가 없어 스윙 신규 진입을 막습니다.")
        elif e["sessions"] <= config.EARNINGS_BLOCK_SESSIONS_ESTIMATE:
            add("EARNINGS_IMMINENT", f"실적 발표 추정일({e.get('date')}, 작년 같은 분기 기준)이 {e['sessions']}거래일 안이라 스윙 신규 진입을 막습니다.")
    elif strategy == "SWING" and e.get("sessions") is not None and e["sessions"] <= config.EARNINGS_BLOCK_SESSIONS:
        add("EARNINGS_IMMINENT", f"실적 발표가 {e['sessions']}거래일 안에 있어 스윙 신규 진입을 막습니다.")
    return out


def _reference_row(fid: str, domain: str, weight: float, ctx: Dict[str, Any]) -> Dict[str, Any]:
    """A factor the profile shows and stores but does not count: its value is kept, its weight in the score is zero."""
    try:
        o = factors.CALC[fid](ctx)
    except (KeyError, TypeError, ValueError, ZeroDivisionError) as exc:
        o = factors.missing(f"계산 오류 ({type(exc).__name__})")
    row = {"factor": fid, "domain": domain, "weight": 0, "reference_weight": weight, "scored": False, "direction": "HIGHER_IS_BETTER", **o, "contribution": None}
    if o["status"] not in _QUALITY:
        row["normalized"] = None
    return row


def _reference_domain(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """The domain's own 0-100 reading from its former weights, for display and for the record of the former formula."""
    have = [r for r in rows if r["normalized"] is not None]
    w = sum(r["reference_weight"] for r in have)
    app = sum(r["reference_weight"] for r in rows if r["status"] != "NOT_APPLICABLE")
    eff = sum(r["reference_weight"] * _QUALITY[r["status"]] for r in have)
    return {"score_100": 100 * sum(r["reference_weight"] * r["normalized"] for r in have) / w if w else None, "coverage": eff / app if app else None}


def formula_score(rows: List[Dict[str, Any]], counted: Optional[Sequence[str]] = None) -> Optional[float]:
    """The composite with the reference factors of the ``counted`` domains counting again (None: all of them), from a card's or a
    ledger snapshot's factor rows.  A reference row of another domain stays out."""
    w = c = 0.0
    for r in rows:
        if r.get("status") not in _QUALITY or r.get("normalized") is None:
            continue
        if r.get("scored") is False and counted is not None and r.get("domain") not in counted:
            continue
        weight = float(r["reference_weight"] if r.get("scored") is False else r["weight"])
        w, c = w + weight, c + weight * float(r["normalized"])
    return 100 * c / w if w else None


def prior_formula_score(rows: List[Dict[str, Any]]) -> Optional[float]:
    """The composite as it was when every reference factor still counted."""
    return formula_score(rows)


def market_state(rows: List[Dict[str, Any]], market: str) -> Dict[str, Any]:
    """The market state of a card or a ledger snapshot: its regime factors under the swing weights, so a swing card and a long card
    of one day read the same value.  It is in no score.  A missing factor leaves both sums, as in the score."""
    have = {r["factor"]: r for r in rows if r.get("domain") == "REGIME"}
    w = c = app = eff = 0.0
    parts = []
    for fid, weight in config.MARKET_STATE_WEIGHTS[market].items():
        r = have.get(fid)
        if r is None:
            continue
        if r.get("status") != "NOT_APPLICABLE":
            app += weight
        ok = r.get("status") in _QUALITY and r.get("normalized") is not None
        if ok:
            w, c, eff = w + weight, c + weight * float(r["normalized"]), eff + weight * _QUALITY[r["status"]]
        parts.append({"factor": fid, "weight": weight, "status": r.get("status"), "normalized": float(r["normalized"]) if ok else None, "raw": r.get("raw"),
                      "explanation": r.get("explanation"), "reason": r.get("reason"), "as_of": r.get("as_of")})
    value = 100 * c / w if w else None
    state = None if value is None else "ADVERSE" if value < config.MARKET_STATE_MID else "FAVOURABLE"
    factor = config.ADVERSE_SIZE_FACTOR.get(market, 1.0) if state == "ADVERSE" else 1.0
    return {"market": market, "score_100": value, "coverage": eff / app if app else None, "state": state, "label": config.MARKET_STATE_LABELS.get(state, "자료 없음"),
            "mid": config.MARKET_STATE_MID, "size_factor": factor, "note": config.MARKET_STATE_NOTES[market], "factors": parts}


def score(ctx: Dict[str, Any], strategy: str, held: bool = False) -> Dict[str, Any]:
    """``ctx``: market, bars, tech (optional), fund, regime, events, earnings, rs_rank, bench_name, price_fresh."""
    market = ctx["market"]
    profile = config.profile_for(market, strategy)
    ctx = dict(ctx)
    if "tech" not in ctx:
        ctx["tech"] = technicals.compute(ctx["bars"], ctx.get("bench"))
    if "levels" not in ctx:
        ctx["levels"] = technicals.levels(ctx["tech"], market)
    rows, domains = [], {}
    tot_w, tot_c, tot_app, tot_eff = 0.0, 0.0, 0.0, 0.0
    missing_names, stale_names = [], []
    for domain in config.DOMAINS:
        w_av, c_sum, app, eff = 0.0, 0.0, 0.0, 0.0
        for fid, weight in profile["domains"][domain].items():
            try:
                o = factors.CALC[fid](ctx)
            except (KeyError, TypeError, ValueError, ZeroDivisionError) as exc:
                o = factors.missing(f"계산 오류 ({type(exc).__name__})")
            row = {"factor": fid, "domain": domain, "weight": weight, "direction": "HIGHER_IS_BETTER", **o}
            if o["status"] != "NOT_APPLICABLE":
                app += weight
            if o["status"] in _QUALITY:
                row["contribution"] = weight * o["normalized"]
                w_av += weight
                c_sum += row["contribution"]
                eff += weight * _QUALITY[o["status"]]
                if o["status"] == "STALE":
                    stale_names.append(fid)
            else:
                row["contribution"] = None
                row["normalized"] = None
                if o["status"] == "MISSING":
                    missing_names.append(fid)
            rows.append(row)
        domains[domain] = {"label": config.DOMAIN_LABELS[domain], "max_points": sum(profile["domains"][domain].values()),
                           "points": c_sum, "available_weight": w_av,
                           "score_100": 100 * c_sum / w_av if w_av else None,
                           "coverage": eff / app if app else None}
        tot_w, tot_c, tot_app, tot_eff = tot_w + w_av, tot_c + c_sum, tot_app + app, tot_eff + eff
        ref = (profile.get("reference") or {}).get(domain)
        if ref:
            ref_rows = [_reference_row(fid, domain, weight, ctx) for fid, weight in ref.items()]
            rows += ref_rows
            domains[domain] = {**domains[domain], **_reference_domain(ref_rows), "reference": True}
    composite = 100 * tot_c / tot_w if tot_w else None
    coverage = tot_eff / tot_app if tot_app else 0.0

    short = [d for d, m in config.MIN_DOMAIN_COVERAGE[strategy].items() if profile["domains"][d] and (domains[d]["coverage"] or 0) < m]
    sufficient = coverage >= config.MIN_TOTAL_COVERAGE and not short
    confidence = "INSUFFICIENT"
    if sufficient:
        confidence = next((lab for lo, lab in config.CONFIDENCE_BANDS if coverage >= lo), "INSUFFICIENT")
        if stale_names and confidence == "HIGH":
            confidence = "MEDIUM"
    gates = hard_gates(ctx, strategy)
    action = action_for(composite if sufficient else None, held)
    actionability = "INSUFFICIENT_DATA" if not sufficient else "BLOCKED" if gates else "ACTIONABLE"
    display = action
    if actionability == "BLOCKED" and action == "BUY":
        display = "BLOCKED"           # a blocked stock is never shown as an actionable BUY; its score stays visible
    ranked = sorted((r for r in rows if r["contribution"] is not None), key=lambda r: r["normalized"] - 0.5, reverse=True)
    weighted = lambda r: (r["normalized"] - 0.5) * r["weight"]    # noqa: E731
    pos = sorted((r for r in ranked if r["normalized"] >= 0.6), key=weighted, reverse=True)[:3]
    neg = sorted((r for r in ranked if r["normalized"] <= 0.4), key=weighted)[:3]
    return {"model_version": config.MODEL_VERSION, "spec_version": config.SPEC_VERSION, "profile": profile["id"],
            "market": market, "strategy": strategy, "held": held, "score": composite,
            "diagnostic_only": not sufficient, **classify(composite), "action": display, "raw_action": action,
            "action_label": config.ACTION_LABELS[display], "color": _color(display, composite), "actionability": actionability,
            "coverage": coverage, "confidence": confidence, "domains": domains, "market_state": market_state(rows, market), "factors": rows, "gates": gates,
            "short_domains": short, "missing": missing_names, "stale": stale_names,
            "top_positive": [{"factor": r["factor"], "text": r["explanation"]} for r in pos],
            "top_negative": [{"factor": r["factor"], "text": r["explanation"]} for r in neg],
            "data_date": ctx["tech"]["date"], "price": ctx["tech"]["close"], "levels": ctx["levels"], "tech": ctx["tech"]}
