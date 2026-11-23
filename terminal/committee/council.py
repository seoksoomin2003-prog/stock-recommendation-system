"""The unified investment committee: one decision from five independent opinions, with the disagreement kept in view (IC-1).

It is not a sixth investor.  It reads the five engines' results (terminal/committee/investors.py) and
  1. finds what they agree on and where they part,
  2. says what kind of disagreement each is: of philosophy (the price a view will pay), of fundamentals (the business
     itself), of the market (trend and regime against long-term merit), or of data (a view could not judge),
  3. reviews material risks from the figures themselves; one such risk outweighs a majority,
  4. decides by written rules, never by averaging the five scores, and
  5. says why, naming the views it did not follow.

Nine scores are reported side by side and are not folded into one number.  The rule from them to the decision is in
``decide``; its thresholds are named constants and were not fitted to returns.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from terminal.committee import investors as iv
from terminal.committee.figures import band, pct
from terminal.committee.investors import AVOID, BUY, BUY_SIDE, HOLD, NO_DATA, REDUCE, SELL, SELL_SIDE, STRONG_BUY, WAIT

CONDITIONAL_BUY = "CONDITIONAL_BUY"
DECISION_KO = {**iv.REC_KO, CONDITIONAL_BUY: "조건부 매수"}
CRITICAL, MAJOR = "CRITICAL", "MAJOR"
MIN_VALID = 3                     # fewer engines with a view than this: the committee does not decide
COMPELLING_SCORE, COMPELLING_CONFIDENCE, COMPELLING_DOWNSIDE = 75.0, 70, 55.0       # when one or two views are enough
MANY_AGAINST = 3                  # this many views saying avoid, reduce or sell: one or two buying views do not carry the decision
DATA_FLOOR, CONFIDENCE_CAP_DATA, CONFIDENCE_CAP_RISK = 60.0, 50.0, 60.0
KIND_KO = {"PHILOSOPHICAL": "철학의 차이", "FUNDAMENTAL": "사업에 대한 판단의 차이", "MARKET": "시장을 보는 차이", "DATA": "자료의 차이"}
LONG_TERM = ("BUFFETT", "MUNGER", "GRAHAM", "LYNCH")


def material_risks(f: Dict[str, Any], by: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Risks that stand whatever the vote: read from the figures, each with the view that speaks to it."""
    out: List[Dict[str, Any]] = []

    def add(level: str, name: str, text: str, who: str) -> None:
        out.append({"level": level, "name": name, "text": text, "raised_by": iv.PEOPLE[who][0]})

    de, cover, fcf = f.get("debt_equity"), f.get("interest_cover"), f.get("fcf_margin")
    if f.get("no_equity") or (de is not None and de > 3.0):
        worse = (cover is not None and cover < 1.5) or (fcf is not None and fcf < 0)
        add(CRITICAL if worse else MAJOR, "과도한 부채", ("자본이 0 이하" if f.get("no_equity") else f"부채/자본 {de:.2f}배") + (", 현금흐름이나 이자 지급 여력도 약함" if worse else ""), "GRAHAM")
    if f.get("ocf_to_ni") is not None and f["ocf_to_ni"] < 0.5 and (f.get("pe") or 0) > 0:
        add(MAJOR, "이익의 질", f"영업현금흐름이 순이익의 {f['ocf_to_ni'] * 100:.0f}%뿐: 이익이 현금으로 들어오지 않음", "BUFFETT")
    if (f.get("profit_years") is not None and f["profit_years"] <= 0.5) or ((f.get("eps_cagr3") or 0) < -0.15 and (f.get("rev_cagr3") or 0) < 0):
        add(MAJOR, "사업의 구조적 악화", f"흑자 연도 {pct(f.get('profit_years'), 0)}, 3년 주당이익 성장 {pct(f.get('eps_cagr3'))}, 3년 매출 성장 {pct(f.get('rev_cagr3'))}", "MUNGER")
    if (f.get("governance_issues") or 0) > 0 or (f.get("events_negative") or 0) >= 2:
        add(MAJOR, "공시·지배구조 경고", f"지배구조 경고 {f.get('governance_issues') or 0}건, 부정 공시 {f.get('events_negative') or 0}건", "MUNGER")
    if f.get("marks"):                # the program's own avoid marks: the one side of it that past data supported
        add(CRITICAL, "회피 표시", ", ".join(f["marks"]) + "(과거 자료에서 이후 수익이 부진했던 표시)", "MUNGER")
    if f.get("pe") is not None and f["pe"] > 60:
        add(MAJOR, "심한 고평가", f"PER {f['pe']:.0f}배", "GRAHAM")
    risk = (by.get("MUNGER") or {}).get("loss_risk") or {}
    if risk.get("score") is not None and risk["score"] >= 35:
        add(CRITICAL if risk["score"] >= 50 else MAJOR, "영구 손실 위험", f"거꾸로 따진 위험 점수 {risk['score']:.0f}/100", "MUNGER")
    if (by.get("GRAHAM") or {}).get("value_trap"):
        add(MAJOR, "가치 함정 가능성", "값은 싸지만 부채나 현금흐름이 나쁨", "GRAHAM")
    if f.get("deals"):
        add(MAJOR, "인수·합병 절차", "인수 가격이 정해진 종목은 가격이 그 값에 묶여 있을 수 있음", "DRUCKENMILLER")
    return out


def unchecked_risks(f: Dict[str, Any]) -> List[str]:
    """The risk reviews above that could not run because their figure is not there (not: does not apply)."""
    gone = lambda n: f.get(n) is None and (f.get("_status") or {}).get(n) == iv.MISSING          # noqa: E731
    out = []
    if gone("debt_equity") and not f.get("no_equity"):
        out.append("과도한 부채")
    if gone("ocf_to_ni"):
        out.append("이익의 질")
    if gone("profit_years"):
        out.append("사업의 구조적 악화")
    if f.get("governance_issues") is None and gone("events_negative"):
        out.append("공시·지배구조 경고")
    return out


def scores(f: Dict[str, Any], opinions: List[Dict[str, Any]], risks: List[Dict[str, Any]]) -> Dict[str, Optional[float]]:
    by = {o["investor"]: o for o in opinions}
    valid = [o for o in opinions if o["recommendation"] != NO_DATA]

    def comp(who: str, name: str) -> Optional[float]:
        return ((by.get(who) or {}).get("components") or {}).get(name) if (by.get(who) or {}).get("recommendation") != NO_DATA else None

    def mean(xs: List[Optional[float]]) -> Optional[float]:
        got = [x for x in xs if x is not None]
        return round(sum(got) / len(got), 1) if got else None
    stance = [1 if o["recommendation"] in BUY_SIDE else -1 if o["recommendation"] in SELL_SIDE else 0 for o in valid]
    agreement = round(100.0 * max(stance.count(s) for s in (1, 0, -1)) / len(valid), 1) if valid else None
    weight = sum(o["confidence"] for o in valid)
    attractive = round(sum(o["score"] * o["confidence"] for o in valid) / weight, 1) if weight else None
    growth = mean([None if v is None else 100.0 * v for v in (band(f.get("eps_cagr3"), 0.0, 0.20), band(f.get("rev_growth"), 0.0, 0.15), band(f.get("forward_growth"), 0.0, 0.20))])
    regime = None if comp("DRUCKENMILLER", "가격 추세") is None else round((comp("DRUCKENMILLER", "시장 환경") or 0.0) / 3.0 + comp("DRUCKENMILLER", "가격 추세") * 2.0 / 3.0, 1)
    loss = ((by.get("MUNGER") or {}).get("loss_risk") or {}).get("score")
    downside = mean([loss, None if f.get("max_drawdown") is None else 100.0 * band(f["max_drawdown"], -0.15, -0.60), None if f.get("hist_vol") is None else 100.0 * band(f["hist_vol"], 0.20, 0.80)])
    data = round(100.0 * sum(o["coverage"] for o in opinions) / len(opinions) * len(valid) / len(opinions), 1) if opinions else None
    confidence = None
    if valid and data is not None:
        confidence = 0.5 * data + 0.3 * sum(o["confidence"] for o in valid) / len(valid) + 0.2 * (agreement or 0.0)
        if data < DATA_FLOOR:
            confidence = min(confidence, CONFIDENCE_CAP_DATA)          # an attractive score on thin data is not to be trusted far
        if any(r["level"] == CRITICAL for r in risks):
            confidence = min(confidence, CONFIDENCE_CAP_RISK)
        confidence = round(confidence, 1)
    return {"attractiveness": attractive, "confidence": confidence, "agreement": agreement, "quality": mean([comp("BUFFETT", "사업의 질"), comp("BUFFETT", "예측 가능성"), comp("MUNGER", "사업의 탁월함"), comp("MUNGER", "지속성과 재투자")]),
            "valuation": mean([comp("GRAHAM", "가격과 안전마진"), comp("BUFFETT", "가격")]), "growth": growth, "regime": regime, "downside": downside, "data": data}


SCORE_KO = {"attractiveness": "투자 매력", "confidence": "자료·일치", "agreement": "의견 일치", "quality": "사업의 질", "valuation": "가격 매력", "growth": "성장 기회", "regime": "시장 국면 적합",
            "downside": "하방 위험(높을수록 위험)", "data": "자료 신뢰도"}


def disagreements(opinions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Each view that stands apart from the buying side (or, with no buyer, from the most favourable view), and what kind of parting it is."""
    out = []
    buyers = [o for o in opinions if o["recommendation"] in BUY_SIDE]
    for o in opinions:
        if o["recommendation"] == NO_DATA or o["confidence"] < 50:
            if buyers and o not in buyers:
                out.append({"kind": "DATA", "kind_ko": KIND_KO["DATA"], "investor": o["name"],
                            "text": f"{o['name']}은 자료가 모자라 {'판단하지 못했습니다' if o['recommendation'] == NO_DATA else '확신이 낮습니다'}({o.get('insufficient') or '확인된 자료 비율 ' + str(round(o['coverage'] * 100)) + '%'})."})
            continue
        if not buyers or o in buyers:
            continue
        names = ", ".join(b["name"] for b in buyers)
        if o["investor"] == "DRUCKENMILLER" or all(b["investor"] == "DRUCKENMILLER" for b in buyers):
            kind = "MARKET"
        elif o["recommendation"] == WAIT or o["investor"] == "GRAHAM":
            kind = "PHILOSOPHICAL"
        else:
            kind = "FUNDAMENTAL"
        why = o["negatives"][0] if o["negatives"] else o["thesis"]
        out.append({"kind": kind, "kind_ko": KIND_KO[kind], "investor": o["name"], "text": f"{names}은 매수 조건으로 보지만 {o['name']}은 '{o['recommendation_ko']}'입니다({why})."})
    return out


def decide(f: Dict[str, Any], opinions: List[Dict[str, Any]], held: bool = False) -> Dict[str, Any]:
    by = {o["investor"]: o for o in opinions}
    valid = [o for o in opinions if o["recommendation"] != NO_DATA]
    risks = material_risks(f, by)
    sc = scores(f, opinions, risks)
    buyers = [o for o in valid if o["recommendation"] in BUY_SIDE]
    strong = [o for o in buyers if o["recommendation"] == STRONG_BUY]
    against = [o for o in valid if o["recommendation"] in SELL_SIDE]
    waiting = [o for o in valid if o["recommendation"] == WAIT]
    critical = [r for r in risks if r["level"] == CRITICAL]
    major = [r for r in risks if r["level"] == MAJOR]
    parts = disagreements(opinions)
    why: List[str] = []
    names = lambda xs: ", ".join(o["name"] for o in xs) or "없음"      # noqa: E731
    if len(valid) < MIN_VALID:
        decision = NO_DATA
        why.append(f"다섯 관점 가운데 {len(valid)}개만 판단할 수 있어 위원회는 결정하지 않습니다(최소 {MIN_VALID}개).")
    elif critical:
        decision = SELL if held else AVOID
        why.append(f"중대한 위험({', '.join(r['name'] for r in critical)})이 있어 찬성 수({len(buyers)}개)와 무관하게 {'매도 조건' if held else '회피'}로 정했습니다. 위험 하나가 다수 의견보다 무겁습니다.")
    elif held and len(against) >= 3:
        decision = SELL if sum(1 for o in against if o["recommendation"] in (SELL, AVOID)) >= 2 else REDUCE
        why.append(f"보유 중인데 세 관점 이상({names(against)})이 매도·축소·회피입니다.")
    elif len(buyers) >= 4:
        decision = CONDITIONAL_BUY if major else STRONG_BUY if len(strong) >= 2 else BUY
        why.append(f"네 관점 이상({names(buyers)})이 매수 조건입니다." + (f" 다만 주요 위험({', '.join(r['name'] for r in major)})이 있어 조건을 붙였습니다." if major else ""))
    elif len(buyers) == 3:
        decision = CONDITIONAL_BUY if major or (sc["downside"] or 0) > 60 else BUY
        why.append(f"세 관점({names(buyers)})이 매수 조건입니다." + (" 주요 위험이나 큰 하방 위험이 있어 조건을 붙였습니다." if decision == CONDITIONAL_BUY else ""))
    elif buyers:
        leads = [o for o in buyers if o["recommendation"] == STRONG_BUY and o["score"] >= COMPELLING_SCORE and o["confidence"] >= COMPELLING_CONFIDENCE]
        # one or two views can carry the decision, but not against three or more that say avoid (user decision 2026-11-22, after
        # the audit found 17 of 66 US buy-side decisions were one view over three or four): the test for three against comes first
        compelling = bool(leads) and not major and (sc["downside"] or 0) <= COMPELLING_DOWNSIDE and len(against) < MANY_AGAINST
        lead = max(leads or buyers, key=lambda o: o["score"])
        if compelling:
            decision = CONDITIONAL_BUY
            why.append(f"찬성은 {len(buyers)}개 관점({names(buyers)})뿐이지만 {lead['name']}의 근거가 강하고(점수 {lead['score']:.0f}, 자료 확인 {lead['confidence']}) 주요 위험이 없어 조건부 매수로 정했습니다. 다수결이 아닙니다.")
        elif len(against) >= MANY_AGAINST:
            decision = REDUCE if held else AVOID
            why.append(f"찬성은 {names(buyers)}뿐이고 세 관점 이상({names(against)})이 회피입니다." + (f" {lead['name']}의 근거가 강해도(점수 {lead['score']:.0f}) 한두 관점이 세 관점 이상의 반대를 이기지는 못합니다." if leads else ""))
        else:
            decision = HOLD if held else WAIT
            why.append(f"찬성은 {len(buyers)}개 관점({names(buyers)})뿐이고 근거가 위원회의 기준(적극 매수 조건, 점수 {COMPELLING_SCORE:.0f} 이상, 신뢰 {COMPELLING_CONFIDENCE} 이상, 주요 위험 없음)에 못 미칩니다.")
    elif len(against) >= 3:
        decision = (SELL if sum(1 for o in against if o["recommendation"] in (SELL, AVOID)) >= 3 else REDUCE) if held else AVOID
        why.append(f"매수 조건으로 본 관점이 없고 세 관점 이상({names(against)})이 회피입니다.")
    elif waiting:
        decision = HOLD if held else WAIT
        why.append(f"매수 조건으로 본 관점은 없지만 {names(waiting)}은 조건이 되면 사겠다고 봅니다. 그 조건을 기다립니다.")
    else:
        decision = HOLD
        why.append("매수 조건으로 본 관점도, 뚜렷이 반대하는 다수도 없습니다.")
    if decision in BUY_SIDE + (CONDITIONAL_BUY,) and sc["data"] is not None and sc["data"] < DATA_FLOOR:
        # thin data lowers the decision, not only the confidence number (audit 2026-11-22, RED-07)
        decision = HOLD if held else WAIT
        why.append(f"자료 신뢰도가 {sc['data']:.0f}으로 기준 {DATA_FLOOR:.0f}에 못 미쳐 매수 쪽 판정을 내리지 않고 {'보유로' if held else '기다립니다'}. 자료가 적은 높은 점수는 근거로 삼지 않습니다.")
    unseen = unchecked_risks(f)
    if unseen:
        why.append(f"자료가 없어 확인하지 못한 위험 검사: {', '.join(unseen)}. 확인하지 못한 것이지 위험이 없다는 뜻이 아닙니다.")
    if major and decision not in (CONDITIONAL_BUY, NO_DATA) and not critical:
        why.append(f"주요 위험으로 적어 둔 것: {', '.join(r['name'] for r in major)}.")
    followed = BUY_SIDE + (CONDITIONAL_BUY,) if decision in BUY_SIDE + (CONDITIONAL_BUY,) else SELL_SIDE if decision in SELL_SIDE else (HOLD, WAIT)
    minority = [o for o in valid if o["recommendation"] not in followed]
    if minority and decision != NO_DATA:
        why.append("따르지 않은 의견: " + "; ".join(f"{o['name']} '{o['recommendation_ko']}'" for o in minority) + ". 아래에 그대로 적습니다.")
    best = max(buyers or waiting or valid, key=lambda o: o["score"]) if valid else None
    worst = min(against or waiting or valid, key=lambda o: o["score"]) if valid else None
    strongest_for = None if best is None else {"investor": best["name"], "text": (best["positives"][0] if best["positives"] else best["thesis"])}
    strongest_against = ({"investor": critical[0]["raised_by"], "text": f"{critical[0]['name']}: {critical[0]['text']}"} if critical
                         else None if worst is None else {"investor": worst["name"], "text": (worst["negatives"][0] if worst["negatives"] else worst["thesis"])})
    # entry: what the views that are not buying ask for; exit: what the buying views would sell on, and the risks
    others = sorted((o for o in valid if o["recommendation"] not in BUY_SIDE), key=lambda o: (o["recommendation"] != WAIT, o["recommendation"] != HOLD, -o["score"]))      # the nearest to buying first
    entry = [f"{o['name']}: {o['conditions']['buy']}" for o in (others[:3] if decision in (CONDITIONAL_BUY, WAIT, HOLD) else buyers[:3])]
    exit_ = [f"{o['name']}: {o['conditions']['sell']}" for o in (buyers or valid)][:3] + [f"위험: {r['name']}이 나타나거나 커질 때" for r in major[:2]]
    long_buyers = [o for o in buyers if o["investor"] in LONG_TERM]
    horizon = "판단하지 않음" if decision == NO_DATA else "장기(5년 이상)" if long_buyers and len(long_buyers) == len(buyers) else "전술적(몇 주~몇 달)" if buyers and not long_buyers else \
        "장기 관점과 추세 관점이 함께 봄" if buyers else "정해지지 않음(매수 조건인 관점 없음)"
    # what they share: a figure two or more views list on the same side
    def shared(key: str) -> List[str]:
        seen: Dict[str, int] = {}
        for o in valid:
            for t in o[key]:
                seen[t] = seen.get(t, 0) + 1
        return [t for t, n in sorted(seen.items(), key=lambda kv: -kv[1]) if n >= 2][:4]
    name = f.get("ticker") or ""
    thesis = _thesis(name, sc, decision, buyers, minority, risks, entry)
    return {"rules": iv.RULES, "decision": decision, "decision_ko": DECISION_KO[decision], "held": held, "scores": sc, "score_labels": SCORE_KO, "valid": len(valid),
            "buyers": [o["name"] for o in buyers], "against": [o["name"] for o in against], "waiting": [o["name"] for o in waiting],
            "agreement": {"positives": shared("positives"), "negatives": shared("negatives")}, "disagreements": parts, "material_risks": risks, "unchecked_risks": unseen,
            "strongest_for": strongest_for, "strongest_against": strongest_against, "reasons": why, "minority": [{"investor": o["name"], "recommendation_ko": o["recommendation_ko"], "opinion": o["opinion"]} for o in minority],
            "entry_conditions": entry, "exit_conditions": exit_, "horizon": horizon, "thesis": thesis, "note": iv.NOTE}


def _word(v: Optional[float], words: Any) -> str:
    return "판단할 자료가 없음" if v is None else f"{words[0] if v < 40 else words[1] if v < 65 else words[2]}({v:.0f})"


def _thesis(name: str, sc: Dict[str, Any], decision: str, buyers: List[Dict[str, Any]], minority: List[Dict[str, Any]], risks: List[Dict[str, Any]], entry: List[str]) -> str:
    if decision == NO_DATA:
        return "판단할 수 있는 관점이 모자라 위원회는 의견을 내지 않습니다."
    head = (f"사업의 질 {_word(sc['quality'], ('낮음', '보통', '높음'))}, 가격 매력 {_word(sc['valuation'], ('낮음', '보통', '높음'))}, 성장 기회 {_word(sc['growth'], ('작음', '보통', '큼'))}, "
            f"시장 국면 적합 {_word(sc['regime'], ('낮음', '보통', '높음'))}, 하방 위험 {_word(sc['downside'], ('낮음', '보통', '높음'))}.")
    risk = f" 위험: {', '.join(r['name'] for r in risks[:3])}." if risks else ""
    other = f" {minority[0]['name']}은 '{minority[0]['recommendation_ko']}'로 달리 봅니다." if minority else ""
    end = {STRONG_BUY: "위원회는 적극 매수 조건으로 봅니다.", BUY: "위원회는 매수 조건으로 봅니다.", CONDITIONAL_BUY: "위원회는 조건 없는 매수가 아니라 조건부 매수로 봅니다.",
           HOLD: "위원회는 새로 살 근거가 부족하다고 봅니다.", WAIT: "위원회는 조건이 될 때까지 기다립니다.", REDUCE: "위원회는 비중을 줄일 조건으로 봅니다.", SELL: "위원회는 매도 조건으로 봅니다.",
           AVOID: "위원회는 피합니다."}[decision]
    cond = f" 들어갈 조건: {entry[0]}." if entry and decision in (CONDITIONAL_BUY, WAIT) else ""
    return f"{head}{risk}{other} {end}{cond}"
