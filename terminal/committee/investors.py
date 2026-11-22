"""Five investor engines: five different ways of deciding about the same stock (rules IC-1).

User specification (2026-11-22): five independent decision makers in the manner of Buffett, Munger, Graham, Lynch and
Druckenmiller, whose differences are in the decision logic and not in the wording.  Each engine here has its own figures,
its own weights, its own gates and its own rule from score to recommendation:

  BUFFETT        the business first (returns on capital, cash, predictability), then the price against a conservative multiple
  MUNGER         an exceptional business or nothing; a separate permanent-loss score from asking how it could fail (inversion)
  GRAHAM         the price against conservative value first (margin of safety), then the balance sheet; sector-specific methods
  LYNCH          the company is classified into one of six kinds, and each kind is scored by its own rule
  DRUCKENMILLER  market regime, earnings direction and price trend; it changes its mind when the trend breaks

What this is not.  These are not the five men's opinions: they are this program's rules, written from principles known from
their books, letters and interviews.  Thresholds are this program's choice and are named constants.  Nothing here has been
tested on returns and no QSF score reads it.  Figures the free data does not carry (customer retention, market share, an
estimate history) are listed as missing, never guessed; without an engine's critical figures it says INSUFFICIENT_DATA.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple

from terminal.committee import figures as fg
from terminal.committee.figures import CONFIRMED, MISSING, NOT_APPLICABLE, band, blend, part, pct, times

RULES = "IC-1"
STRONG_BUY, BUY, HOLD, WAIT, REDUCE, SELL, AVOID, NO_DATA = "STRONG_BUY", "BUY", "HOLD", "WAIT", "REDUCE", "SELL", "AVOID", "INSUFFICIENT_DATA"
REC_KO = {STRONG_BUY: "적극 매수 조건 충족", BUY: "매수 조건 충족", HOLD: "보유(새로 사지 않음)", WAIT: "대기", REDUCE: "축소 조건", SELL: "매도 조건", AVOID: "회피", NO_DATA: "자료 부족"}
BUY_SIDE, SELL_SIDE = (STRONG_BUY, BUY), (REDUCE, SELL, AVOID)
MIN_COVERAGE = 0.5
NOTE = ("실존 투자자의 실제 의견이 아닙니다. 책과 주주서한 등으로 알려진 원칙을 이 프로그램이 규칙으로 옮긴 것이고, 기준값은 프로그램이 정했습니다. "
        "수익으로 검증하지 않았고 점수에 들어가지 않으며, 주문을 내지 않습니다.")
PCT = {"roe", "roic", "op_margin", "gross_margin", "eps_cagr3", "rev_cagr3", "rev_growth", "eps_growth", "fcf_margin", "fcf_yield", "share_change", "ma200_slope", "ma50_slope", "rs",
       "rel_126", "ret_12_1", "dist_high", "max_drawdown", "hist_vol", "atr_pct", "dividend_yield", "forward_growth", "profit_years", "fcf_years", "insider_pct", "breadth", "downside_vol"}


def shown(f: Dict[str, Any], name: str) -> str:
    v = f.get(name)
    if name == "insider_buy":
        return "내부자 순매수 " + ("자료 없음" if v is None or f.get("insider_sell") is None else "있음" if v > f["insider_sell"] else "없음")
    if name in ("events_positive", "events_negative", "governance_issues"):
        return f"{fg.label(name)} " + ("자료 없음" if v is None else f"{int(v)}건")
    if name == "debt_equity" and (f.get("no_equity") or f["_status"].get(name) == NOT_APPLICABLE):
        return "자본이 0 이하(부채/자본 계산 안 됨)" if f.get("no_equity") else "부채/자본은 금융업에 해당 없음"
    if name == "roic" and f.get("kind") == "FINANCIAL":
        return f"ROE {pct(v)}"                      # for a bank or an insurer the figure is return on equity itself
    if isinstance(v, bool):
        return f"{fg.label(name)} {'있음' if v else '없음'}"
    return f"{fg.label(name)} {pct(v) if name in PCT else times(v, 2 if name in ('pb', 'debt_equity', 'current_ratio', 'cash_debt', 'ocf_to_ni', 'reward_risk') else 1)}"


def flag(name: str, weight: float, value: Optional[bool]) -> Any:
    return (name, weight, None if value is None else 1.0 if value else 0.0, CONFIRMED if value is not None else MISSING)


def groups_score(f: Dict[str, Any], groups: Dict[str, Tuple[float, List[Any]]]) -> Dict[str, Any]:
    """Each group's 0-100 and the engine's: the weighted mean of the groups that have a figure.  ``evidence`` lists every part."""
    comp, cover, sure, evidence, missing = {}, 0.0, 0.0, [], []
    total = sum(w for w, _ in groups.values())
    for name, (w, parts) in groups.items():
        b = blend(parts)
        comp[name] = None if b["score"] is None else round(b["score"], 1)
        cover += w * b["coverage"]
        sure += w * b["sure"]
        missing += b["missing"]
        inside = sum(pw for _n, pw, v, _st in parts if v is not None) or 1.0
        evidence += [{"group": name, "figure": n, "value": v, "weight": w * pw / inside, "text": shown(f, n) if n in f else n} for n, pw, v, _st in parts if v is not None]
    live = [(w, comp[n]) for n, (w, _) in groups.items() if comp[n] is not None]
    score = sum(w * s for w, s in live) / sum(w for w, _ in live) if live else None
    return {"score": score, "components": comp, "coverage": cover / total if total else 0.0, "sure": sure / total if total else 0.0, "evidence": evidence, "missing": sorted(set(missing))}


def finish(key: str, f: Dict[str, Any], g: Dict[str, Any], rec: str, held: bool, horizon: str, valuation: str, expected: Dict[str, Any], downside: Dict[str, Any],
           opinion: str, thesis: str, conditions: Dict[str, str], weight: float, extra: Optional[Dict[str, Any]] = None, flags: Tuple[str, ...] = (),
           gaps: Tuple[str, ...] = ()) -> Dict[str, Any]:
    """``flags``: named dangers the engine found (they lead the negatives).  ``gaps``: what the engine would read and the data does not carry."""
    name, philosophy, question = PEOPLE[key]
    # what moved the score most, for and against: how far a figure is from the middle, times its weight in the score
    positives = [e["text"] for e in sorted(g["evidence"], key=lambda e: -e["value"] * e["weight"]) if e["value"] >= 0.7][:3]
    negatives = list(flags) + [e["text"] for e in sorted(g["evidence"], key=lambda e: -(1.0 - e["value"]) * e["weight"]) if e["value"] <= 0.3][:3]
    confidence = round(100 * g.get("sure", g["coverage"]) * (0.85 if f.get("marks") or f.get("deals") else 1.0))
    action = {STRONG_BUY: "추가 매수 조건" if held else "매수 조건 충족(비중 크게)", BUY: "보유 유지(추가 매수 가능)" if held else "매수 조건 충족", HOLD: "보유 유지" if held else "새로 사지 않음",
              WAIT: "보유 유지, 추가 매수 보류" if held else "조건이 될 때까지 기다림", REDUCE: "비중 축소", SELL: "전량 매도 조건", AVOID: "매도 조건" if held else "사지 않음", NO_DATA: "판단 보류"}[rec]
    return {"investor": key, "name": name, "philosophy": philosophy, "question": question, "ticker": f.get("ticker"), "as_of": f.get("as_of"), "rules": RULES,
            "score": None if g["score"] is None or rec == NO_DATA else round(g["score"], 1), "confidence": confidence, "coverage": round(g["coverage"], 3), "recommendation": rec,
            "recommendation_ko": REC_KO[rec], "held": held, "horizon": horizon, "valuation": valuation, "expected_return": expected, "downside_risk": downside,
            "positives": positives, "negatives": negatives[:4], "opinion": opinion, "thesis": thesis, "conditions": conditions, "suggested_weight": round(weight if rec in BUY_SIDE else 0.0, 4),
            "action": action, "components": g["components"], "missing": [fg.label(n) for n in g["missing"]] + list(gaps), "evidence": [{"group": e["group"], "text": e["text"], "level": round(e["value"], 2)} for e in g["evidence"]],
            **(extra or {})}


def no_data(key: str, f: Dict[str, Any], g: Dict[str, Any], why: str, held: bool) -> Dict[str, Any]:
    cond = {k: "자료가 채워지면 다시 판단합니다." for k in ("buy", "hold", "add", "reduce", "sell", "invalidation")}
    return finish(key, f, g, NO_DATA, held, "판단하지 않음", "판단하지 않음", {"value": None, "basis": "판단하지 않음"}, {"value": None, "basis": "판단하지 않음"},
                  f"{why} 그래서 판단하지 않습니다.", "핵심 자료가 없어 의견을 내지 않습니다.", cond, 0.0, {"insufficient": why})


def _growth_yield(f: Dict[str, Any]) -> Dict[str, Any]:
    y = f.get("fcf_yield") if f.get("fcf_yield") is not None else (1.0 / f["pe"] if f.get("pe") and f["pe"] > 0 else None)
    g3 = f.get("eps_cagr3")
    if y is None or g3 is None:
        return {"value": None, "basis": "수익률이나 성장률 자료가 없어 계산하지 않음"}
    return {"value": round(y + max(0.0, min(g3, 0.10)), 4), "basis": "현금(또는 이익) 수익률 + 3년 이익 성장률(상한 10%)의 단순 합. 예측이 아니며 검증되지 않았습니다"}


def _drawdown(f: Dict[str, Any]) -> Dict[str, Any]:
    return {"value": f.get("max_drawdown"), "basis": "지난 1년의 최대 낙폭(과거 값이며 앞으로의 하한이 아님)"}


def _de_text(f: Dict[str, Any]) -> str:
    return shown(f, "debt_equity")


# ------------------------------------------------------------------------------------------------- Buffett
B_QUALITY, B_PREDICT, B_STRENGTH = 65.0, 60.0, 40.0          # the business bar
B_SELL_QUALITY, B_SELL_PREDICT, B_STRONG_MOS, B_REDUCE_MOS = 45.0, 35.0, 0.20, -0.60


def fin_band(ctx: Optional[Dict[str, Any]], low: float, high: float) -> Tuple[float, float, Optional[Dict[str, float]]]:
    """Where a bank's or an insurer's return on equity is measured from.  User decision 2026-11-22: among the session's own
    financials, from their median (nothing) to their top tenth (everything), so that an ordinary financial is not read as an
    excellent business because it has few other figures.  Without the session's financials (a stock outside the scan, fewer
    than ``FIN_MIN`` of them) the fixed ``low``-``high`` band stands.  The band is never easier than the fixed one: where the
    session's best financials earn little (Korea's top tenth: 16.6% on 2026-11-20), being the best of them is not enough."""
    peers = (ctx or {}).get("financial_roe")
    if peers and peers.get("n", 0) >= FIN_MIN and peers["top"] > peers["median"]:
        return max(peers["median"], low), max(peers["top"], high), peers          # among peers, and never easier than the fixed band
    return low, high, None


FIN_MIN = 8


def buffett(f: Dict[str, Any], held: bool = False, ctx: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    fin = f["kind"] == "FINANCIAL"
    lo, hi, peers = fin_band(ctx, 0.08, 0.16) if fin else (0.06, 0.20, None)
    quality = [part(f, "roic", 3, lo, hi), part(f, "op_margin", 2, 0.08, 0.25), part(f, "fcf_margin", 2, 0.03, 0.15), part(f, "gross_margin", 1, 0.25, 0.50)]
    predict = [part(f, "profit_years", 3, 0.6, 1.0), part(f, "fcf_years", 2, 0.5, 1.0), part(f, "eps_cagr3", 2, -0.05, 0.10), part(f, "rev_cagr3", 1, 0.0, 0.08)]
    strength = [part(f, "debt_equity", 3, 2.0, 0.3), part(f, "cash_debt", 1, 0.1, 1.0), part(f, "interest_cover", 1, 2.0, 10.0)]
    if f.get("no_equity"):
        strength = [("debt_equity", 3, 0.0, CONFIRMED)] + strength[1:]
    capital = [part(f, "share_change", 2, 0.03, -0.02), flag("returns_capital", 1, f.get("returns_capital"))]
    pe = f.get("pe")
    earn_yield = None if not pe or pe <= 0 else 1.0 / pe
    price = [("fcf_yield", 2, band(f.get("fcf_yield"), 0.02, 0.07), f["_status"]["fcf_yield"]), ("pe", 2, band(earn_yield, 0.03, 0.08) if pe is not None else None, f["_status"]["pe"])]
    g = groups_score(f, {"사업의 질": (0.35, quality), "예측 가능성": (0.20, predict), "재무 건전성": (0.15, strength), "자본 배분": (0.10, capital), "가격": (0.20, price)})
    if pe is None or f.get("roic") is None or g["coverage"] < MIN_COVERAGE:
        return no_data("BUFFETT", f, g, "자본이 0 이하라 자본 수익률을 계산할 수 없습니다." if f.get("no_equity") else "PER이나 자본 수익률 자료가 없습니다.", held)
    q, p, s = g["components"]["사업의 질"], g["components"]["예측 가능성"], g["components"]["재무 건전성"]
    fair = 10.0 + 15.0 * q / 100.0 + 50.0 * max(0.0, min(f.get("eps_cagr3") or 0.0, 0.10))          # a conservative multiple this business may carry
    mos = None if pe <= 0 else 1.0 - pe / fair
    ok = q >= B_QUALITY and p is not None and p >= B_PREDICT and (s is None or s >= B_STRENGTH)
    if held and (q < B_SELL_QUALITY or (p is not None and p < B_SELL_PREDICT)):
        rec = SELL
    elif held and mos is not None and mos < B_REDUCE_MOS:
        rec = REDUCE
    elif not ok:
        rec = HOLD if held or (q >= 50 and (p is None or p >= 40)) else AVOID
    elif mos is None:
        rec = WAIT
    else:
        rec = STRONG_BUY if mos >= B_STRONG_MOS else BUY if mos >= 0 else WAIT
    among = f"(금융업 {peers['n']}종목의 중앙값 {pct(peers['median'])}, 상위 10% {pct(peers['top'])})" if peers else ""
    business = f"{'ROE' if fin else '투하자본 수익률'} {pct(f['roic'])}{among}, 흑자 연도 {pct(f.get('profit_years'), 0)}"
    if rec in BUY_SIDE:
        opinion = f"{business}로 오래 보유할 만한 사업이고, PER {pe:.1f}배가 보수적 적정 PER {fair:.1f}배 이하입니다. 사업의 질 점수가 {B_SELL_QUALITY:.0f} 아래로 떨어지면 생각을 바꿉니다."
    elif rec == WAIT:
        opinion = f"사업은 좋습니다({business}). 다만 " + (f"PER {pe:.1f}배가 보수적 적정 PER {fair:.1f}배보다 높아" if pe > 0 else "지금 적자라 값을 매길 수 없어") + f" 기다립니다. PER이 {fair:.1f}배 이하가 되면 매수 조건이 됩니다."
    elif rec in (SELL, REDUCE):
        opinion = (f"보유 근거가 약해졌습니다(사업의 질 {q:.0f}, 예측 가능성 {p:.0f}). 가격이 아니라 사업이 나빠진 것이 이유입니다." if rec == SELL
                   else f"사업은 여전히 좋지만 PER {pe:.1f}배가 적정 {fair:.1f}배의 1.6배를 넘어 일부를 줄일 조건입니다.")
    else:
        weak = "사업의 질" if q < B_QUALITY else "예측 가능성" if p is not None and p < B_PREDICT else "재무 건전성"
        opinion = f"{weak} 점수가 기준에 못 미쳐({g['components'][weak]:.0f}) 오래 보유할 사업으로 보지 않습니다. 근거: {business}, {_de_text(f)}. 사업의 질 {B_QUALITY:.0f}, 예측 가능성 {B_PREDICT:.0f} 이상이 되면 다시 봅니다."
    cond = {"buy": f"사업의 질 {B_QUALITY:.0f} 이상(지금 {q:.0f}), 예측 가능성 {B_PREDICT:.0f} 이상(지금 {'자료 없음' if p is None else f'{p:.0f}'})이고 PER이 보수적 적정 PER {fair:.1f}배 이하(지금 {pe:.1f}배)",
            "hold": f"사업의 질 {B_SELL_QUALITY:.0f} 이상이고 흑자가 이어지는 동안. 가격이 내렸다는 이유만으로는 팔지 않습니다",
            "add": f"사업 조건이 그대로이고 PER이 {fair * (1 - B_STRONG_MOS):.1f}배 이하(적정보다 20% 이상 쌀 때)",
            "reduce": f"PER이 적정 PER의 1.6배({fair * 1.6:.1f}배)를 넘을 때", "sell": f"사업의 질 {B_SELL_QUALITY:.0f} 미만 또는 예측 가능성 {B_SELL_PREDICT:.0f} 미만(적자 전환, 현금흐름 악화)",
            "invalidation": "경쟁 우위가 무너졌다는 신호: 자본 수익률과 이익률이 함께 떨어지고 적자 연도가 생길 때"}
    weight = 0.04 + 0.08 * max(0.0, min((g["score"] - 60.0) / 30.0, 1.0))
    return finish("BUFFETT", f, g, rec, held, "5년 이상", f"보수적 적정 PER {fair:.1f}배(사업의 질과 성장으로 정한 프로그램 규칙) 대비 지금 PER {pe:.1f}배" + ("" if mos is None else f", 안전마진 {mos * 100:+.0f}%"),
                  _growth_yield(f), _drawdown(f), opinion, f"좋은 사업을 적정한 값에: 사업의 질 {q:.0f}, 가격 {('적정 이하' if mos is not None and mos >= 0 else '적정 초과')}.", cond, weight,
                  {"fair_pe": round(fair, 1), "margin_of_safety": None if mos is None else round(mos, 3), "business_ok": ok}, (), ("경쟁 우위 자체(점유율, 가격 결정력의 직접 자료 없음)", "경영진의 질(직접 자료 없음)"))


# ------------------------------------------------------------------------------------------------- Munger
M_EXCELLENT, M_GOOD, M_RISK_OK, M_RISK_AVOID, M_PERSIST = 75.0, 60.0, 25.0, 50.0, 70.0


def loss_risk(f: Dict[str, Any]) -> Dict[str, Any]:
    """Inversion: how could this be a permanent loss?  Points for each way that is already visible; 0 is none, 100 the worst."""
    asks = [("부채가 사업을 무너뜨릴 수 있는가", 25 if f.get("no_equity") else None if f.get("debt_equity") is None else 20 if f["debt_equity"] > 2.0 else 10 if f["debt_equity"] > 1.0 else 0, _de_text(f)),
            ("이익이 끊긴 적이 있는가", None if f.get("profit_years") is None else 20 if f["profit_years"] <= 0.6 else 10 if f["profit_years"] < 1.0 else 0, shown(f, "profit_years")),
            ("현금이 새고 있는가", None if f.get("fcf_margin") is None else 15 if f["fcf_margin"] < 0 else 0, shown(f, "fcf_margin")),
            ("이익이 현금으로 들어오는가", None if f.get("ocf_to_ni") is None else 10 if f["ocf_to_ni"] < 0.6 else 0, shown(f, "ocf_to_ni")),
            ("주주가 희석되고 있는가", None if f.get("share_change") is None else 10 if f["share_change"] > 0.05 else 5 if f["share_change"] > 0.02 else 0, shown(f, "share_change")),
            ("경영진과 공시에 경고가 있는가", None if f.get("governance_issues") is None and f.get("events_negative") is None and not f.get("marks") else
             min(20, 10 * ((f.get("governance_issues") or 0) + (f.get("events_negative") or 0)) + 10 * len(f.get("marks") or [])), ", ".join(f.get("marks") or []) or f"지배구조 경고 {f.get('governance_issues') or 0}건, 부정 공시 {f.get('events_negative') or 0}건"),
            ("시장이 이미 큰 손실을 말하고 있는가", None if f.get("max_drawdown") is None else 10 if f["max_drawdown"] < -0.5 else 5 if f["max_drawdown"] < -0.35 else 0, shown(f, "max_drawdown"))]
    known = [(q, p, t) for q, p, t in asks if p is not None]
    score = min(100.0, sum(p for _q, p, _t in known) * (100.0 / 80.0)) if known else None
    return {"score": None if score is None else round(score, 1), "asked": len(asks), "answered": len(known), "ways": [{"ask": q, "points": p, "text": t} for q, p, t in known if p],
            "unanswered": [q for q, p, _t in asks if p is None] + ["경쟁 우위가 사라질 수 있는가(고객 유지율, 전환 비용, 점유율 자료 없음)"]}


def munger(f: Dict[str, Any], held: bool = False, ctx: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    fin = f["kind"] == "FINANCIAL"
    lo, hi, peers = fin_band(ctx, 0.10, 0.18) if fin else (0.10, 0.25, None)
    excellence = [part(f, "roic", 4, lo, hi), part(f, "gross_margin", 2, 0.30, 0.60), part(f, "op_margin", 3, 0.12, 0.30)]
    persist = [part(f, "profit_years", 3, 0.6, 1.0), part(f, "rev_cagr3", 2, 0.0, 0.10), part(f, "eps_cagr3", 2, 0.0, 0.12), part(f, "ocf_to_ni", 2, 0.7, 1.2)]
    buys = None if f.get("insider_buy") is None or f.get("insider_sell") is None else f["insider_buy"] >= f["insider_sell"]
    incentives = [part(f, "insider_pct", 2, 0.0, 0.05), flag("insider_buy", 1, buys), part(f, "share_change", 2, 0.03, -0.02)]
    risk = loss_risk(f)
    safety = [("permanent_loss", 1, None if risk["score"] is None else 1.0 - risk["score"] / 100.0, CONFIRMED if risk["score"] is not None else MISSING)]
    g = groups_score(f, {"사업의 탁월함": (0.45, excellence), "지속성과 재투자": (0.20, persist), "경영진의 이해관계": (0.10, incentives), "영구 손실 회피": (0.25, safety)})
    g["evidence"] = [e for e in g["evidence"] if e["figure"] != "permanent_loss"]
    pe = f.get("pe")
    if f.get("roic") is None or risk["score"] is None or g["coverage"] < MIN_COVERAGE:
        return no_data("MUNGER", f, g, "자본이 0 이하라 자본 수익률을 계산할 수 없습니다." if f.get("no_equity") else "자본 수익률이나 위험을 따질 자료가 없습니다.", held)
    ex, lr = g["components"]["사업의 탁월함"], risk["score"]
    fair = 15.0 + 20.0 * ex / 100.0                                   # an exceptional business may carry a premium, not any price
    ps = g["components"]["지속성과 재투자"]
    # exceptional means it has kept it up: no loss year on file, and the persistence figures say so too
    exceptional = ex >= M_EXCELLENT and lr <= M_RISK_OK and ps is not None and ps >= M_PERSIST and (f.get("profit_years") is None or f["profit_years"] >= 1.0)
    margin = ("ROE만으로 봄(금융업은 이익률이 해당 없음" + (f", 금융업 중앙값 {pct(peers['median'])}·상위 10% {pct(peers['top'])}와 비교)" if peers else ")")) if fin else f"영업이익률 {pct(f.get('op_margin'))}"
    if lr >= M_RISK_AVOID:
        rec = SELL if held else AVOID
    elif exceptional and pe is not None and pe > 0:
        rec = STRONG_BUY if pe <= 0.8 * fair else BUY if pe <= fair else WAIT
    elif exceptional:
        rec = WAIT
    elif ex >= M_GOOD and lr <= 40:
        rec = HOLD
    else:
        rec = REDUCE if held else AVOID
    worst = max(risk["ways"], key=lambda w: w["points"])["text"] if risk["ways"] else "눈에 띄는 것 없음"
    if rec in BUY_SIDE:
        opinion = f"탁월한 사업입니다({'ROE' if fin else '투하자본 수익률'} {pct(f['roic'])}, {margin}). 거꾸로 따져도 영구 손실 위험이 낮고({lr:.0f}/100) PER {pe:.1f}배는 이 사업에 줄 수 있는 {fair:.1f}배 이하입니다. 위험 점수가 {M_RISK_AVOID:.0f}을 넘으면 팝니다."
    elif rec == WAIT:
        opinion = f"탁월한 사업이고 영구 손실 위험도 낮습니다({lr:.0f}/100). 다만 " + ("값을 매길 이익이 없어" if not pe or pe <= 0 else f"PER {pe:.1f}배가 이 사업에 줄 수 있는 {fair:.1f}배를 넘어") + " 기다립니다. 기회비용을 생각하면 서두를 이유가 없습니다."
    elif lr >= M_RISK_AVOID:
        opinion = f"거꾸로 따져 보면 돈을 영영 잃을 길이 여럿 보입니다(위험 {lr:.0f}/100, 가장 큰 것: {worst}). 싸 보여도 피합니다. 위험 점수가 {M_RISK_OK:.0f} 아래로 내려와야 다시 봅니다."
    elif rec == HOLD:
        opinion = (f"좋은 사업이지만 탁월하다고 하기엔 모자랍니다(탁월함 {ex:.0f}/기준 {M_EXCELLENT:.0f}, 지속성 {'자료 없음' if ps is None else f'{ps:.0f}'}/기준 {M_PERSIST:.0f}, 흑자 연도 {pct(f.get('profit_years'), 0)}). "
                   f"가진 것은 두되 새로 살 이유는 없습니다. 적자 없이 높은 수익률이 이어지면 매수 후보가 됩니다.")
    else:
        opinion = f"평범한 사업은 싸도 사지 않습니다(탁월함 {ex:.0f}, {'ROE' if fin else '투하자본 수익률'} {pct(f['roic'])}{', ' + margin if fin else ''}). 탁월함 {M_GOOD:.0f} 이상이 되기 전에는 보지 않습니다."
    cond = {"buy": f"사업의 탁월함 {M_EXCELLENT:.0f} 이상(지금 {ex:.0f}), 지속성 {M_PERSIST:.0f} 이상이고 적자 연도 없음, 영구 손실 위험 {M_RISK_OK:.0f} 이하(지금 {lr:.0f}), PER {fair:.1f}배 이하(지금 {times(pe)})",
            "hold": f"탁월함 {M_GOOD:.0f} 이상, 위험 40 이하인 동안", "add": f"조건이 그대로이고 PER이 {0.8 * fair:.1f}배 이하일 때. 더 나은 기회가 없을 때만",
            "reduce": f"탁월함이 {M_GOOD:.0f} 아래로 내려가거나 훨씬 나은 사업이 같은 값에 나올 때", "sell": f"영구 손실 위험 {M_RISK_AVOID:.0f} 이상",
            "invalidation": "가격 결정력이 사라졌다는 신호(이익률 하락), 경영진의 신뢰를 깨는 공시, 재투자할 곳이 없어진 성장 정체"}
    weight = 0.08 + 0.10 * max(0.0, min((g["score"] - 70.0) / 25.0, 1.0))
    return finish("MUNGER", f, g, rec, held, "5년 이상", f"탁월한 사업에 줄 수 있는 PER {fair:.1f}배(프로그램 규칙) 대비 지금 {times(pe)}", _growth_yield(f),
                  {"value": lr, "basis": "영구 손실 위험 점수(0 없음 ~ 100 최악): 거꾸로 따져 본 일곱 질문의 합"}, opinion,
                  f"탁월한 사업만, 그리고 큰 실수를 피한다: 탁월함 {ex:.0f}, 영구 손실 위험 {lr:.0f}.", cond, weight, {"fair_pe": round(fair, 1), "loss_risk": risk, "exceptional": exceptional},
                  tuple(w["text"] for w in sorted(risk["ways"], key=lambda w: -w["points"])[:2]), ("고객 유지율, 전환 비용, 네트워크 효과(자료 없음)", "이익률의 여러 해 안정성(자료 없음)"))


# ------------------------------------------------------------------------------------------------- Graham
GRAHAM_PROFILES = {  # historical reference points, kept as settings: not a law of today's market
    "DEFENSIVE": {"label": "방어적 투자자", "pe": 15.0, "pb": 1.5, "pe_pb": 22.5, "current": 2.0, "debt": 1.0, "profit_years": 1.0, "mos_buy": 0.25, "mos_strong": 0.40, "strength": 55.0, "stability": 60.0},
    "ENTERPRISING": {"label": "적극적 투자자", "pe": 15.0, "pb": 1.5, "pe_pb": 22.5, "current": 1.5, "debt": 1.5, "profit_years": 0.75, "mos_buy": 0.33, "mos_strong": 0.50, "strength": 40.0, "stability": 40.0},
}
G_TRAP_DEBT, G_REDUCE_MOS, G_SELL_MOS = 2.0, 0.0, -0.25


def graham_value(f: Dict[str, Any], p: Dict[str, Any]) -> Dict[str, Any]:
    """Price against conservative value, by the method that fits the kind of company.  ``mos``: 1 - price / value."""
    pe, pb, kind = f.get("pe"), f.get("pb"), f["kind"]
    if pe is not None and pe <= 0:
        return {"mos": None, "method": "적자라 이익으로 값을 매길 수 없음", "loss": True}
    if kind == "REAL_ESTATE":                      # depreciation distorts a REIT's earnings: book value is the firmer ground
        return {"mos": None if pb is None or pb <= 0 else 1.0 - pb / p["pb"], "method": f"부동산: PER 대신 PBR {p['pb']}배 기준(감가상각이 이익을 왜곡)", "loss": False}
    if kind == "ASSET_LIGHT" or pb is None or pb <= 0:      # few tangible assets (or no equity): the earnings multiple alone
        return {"mos": None if pe is None else 1.0 - pe / p["pe"], "method": f"자산이 가벼운 업종: PBR 없이 PER {p['pe']:.0f}배 기준", "loss": False}
    if pe is None:
        return {"mos": None, "method": "PER 자료 없음", "loss": False}
    return {"mos": 1.0 - (pe * pb / p["pe_pb"]) ** 0.5, "method": f"PER×PBR {p['pe_pb']} 기준(그레이엄 수)", "loss": False}


def graham(f: Dict[str, Any], held: bool = False, ctx: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """The defensive profile decides (the portfolio and the record use it alone).  The enterprising profile's verdict is shown
    beside it for comparison and changes nothing (user decision 2026-11-22)."""
    asked = (ctx or {}).get("graham_profile") or "DEFENSIVE"
    out = _graham(f, held, GRAHAM_PROFILES[asked])
    if asked == "DEFENSIVE":
        other = _graham(f, held, GRAHAM_PROFILES["ENTERPRISING"])
        out["other_profile"] = {"profile": other.get("profile") or GRAHAM_PROFILES["ENTERPRISING"]["label"], "recommendation": other["recommendation"], "recommendation_ko": other["recommendation_ko"],
                                "score": other["score"], "opinion": other["opinion"], "buy": other["conditions"]["buy"], "same": other["recommendation"] == out["recommendation"]}
    return out


def _graham(f: Dict[str, Any], held: bool, p: Dict[str, Any]) -> Dict[str, Any]:
    val = graham_value(f, p)
    pe = f.get("pe")
    earn_yield = None if not pe or pe <= 0 else 1.0 / pe
    valuation = [("pe", 3, None if pe is None else 0.0 if pe <= 0 else band(pe, 25.0, 10.0), f["_status"]["pe"]), part(f, "pb", 2, 3.0, 1.0), part(f, "fcf_yield", 1, 0.03, 0.08),
                 ("margin_of_safety", 3, band(val["mos"], -0.3, 0.4), CONFIRMED if val["mos"] is not None else MISSING)]
    strength = [part(f, "current_ratio", 3, 1.0, p["current"]), part(f, "debt_equity", 3, 2.0 * p["debt"], 0.5 * p["debt"]), part(f, "cash_debt", 1, 0.1, 1.0)]
    if f.get("no_equity"):
        strength = [strength[0], ("debt_equity", 3, 0.0, CONFIRMED), strength[2]]
    stability = [part(f, "profit_years", 3, 0.5, 1.0), part(f, "eps_cagr3", 2, -0.03, 0.03), part(f, "fcf_years", 1, 0.5, 1.0)]
    income = [flag("returns_capital", 2, f.get("returns_capital")), part(f, "dividend_yield", 1, 0.0, 0.03)]
    g = groups_score(f, {"가격과 안전마진": (0.40, valuation), "재무의 튼튼함": (0.25, strength), "이익의 안정": (0.25, stability), "배당과 환원": (0.10, income)})
    g["evidence"] = [e for e in g["evidence"] if e["figure"] != "margin_of_safety"]
    if pe is None or (val["mos"] is None and not val["loss"]) or g["coverage"] < MIN_COVERAGE:
        return no_data("GRAHAM", f, g, "PER이나 PBR 자료가 없어 보수적 가치와 비교할 수 없습니다.", held)
    mos, st, sb = val["mos"], g["components"]["재무의 튼튼함"], g["components"]["이익의 안정"]
    sound = (st is None or st >= p["strength"]) and sb is not None and sb >= p["stability"]
    trap = mos is not None and mos > 0 and ((f.get("debt_equity") or 0) > G_TRAP_DEBT or f.get("no_equity") or (f.get("fcf_margin") is not None and f["fcf_margin"] < 0)
                                            or (f.get("ocf_to_ni") is not None and f["ocf_to_ni"] < 0.5) or ((f.get("eps_growth") or 0) < -0.2 and (f.get("rev_growth") or 0) < 0))
    if val["loss"] or trap:
        rec = SELL if held else AVOID
    elif held and (mos <= G_SELL_MOS or not sound):
        rec = SELL
    elif held and mos <= G_REDUCE_MOS:
        rec = REDUCE
    elif not sound:
        rec = AVOID
    else:
        rec = STRONG_BUY if mos >= p["mos_strong"] else BUY if mos >= p["mos_buy"] else HOLD if mos >= 0 else WAIT
    price = f"PER {times(pe)}, PBR {times(f.get('pb'), 2)}"
    if val["loss"]:
        opinion = "지금 적자입니다. 이익이 없는 회사를 보수적 가치로 평가할 수 없으므로 투자가 아니라 투기로 봅니다. 흑자가 여러 해 이어져야 다시 계산합니다."
    elif trap:
        opinion = f"값은 싸 보입니다(안전마진 {mos * 100:+.0f}%). 그러나 {_de_text(f)}, {shown(f, 'fcf_margin')}라 싼 데 이유가 있는 '가치 함정'일 수 있어 피합니다. 부채와 현금흐름이 나아져야 다시 봅니다."
    elif rec in BUY_SIDE:
        opinion = f"보수적 가치보다 {mos * 100:.0f}% 싸게 거래됩니다({price}). 재무({'해당 없음' if st is None else f'{st:.0f}'})와 이익의 안정({sb:.0f})도 기준을 넘어 분석이 틀려도 버틸 여유가 있습니다. 값이 보수적 가치에 닿으면 줄입니다."
    elif rec in (WAIT, HOLD) and not held:
        opinion = (f"회사는 튼튼합니다(재무 {'해당 없음' if st is None else f'{st:.0f}'}, 이익의 안정 {sb:.0f}). 그러나 {price}는 보수적 가치 대비 안전마진이 {mos * 100:+.0f}%뿐이라 "
                   f"{'새로 사지는 않습니다' if rec == HOLD else '기다립니다'}. 안전마진이 {p['mos_buy'] * 100:.0f}% 이상이 되면 매수 조건입니다.")
    elif rec in (SELL, REDUCE, HOLD):
        opinion = (f"값이 보수적 가치에 닿았습니다(안전마진 {mos * 100:+.0f}%). 싸서 산 것이므로 {'일부를 줄일' if rec == REDUCE else '팔'} 조건입니다." if mos <= G_REDUCE_MOS and sound
                   else f"안전마진 {mos * 100:+.0f}%가 남아 있어 보유합니다." if rec == HOLD else "재무나 이익의 안정이 기준 아래로 내려가 싸다는 근거가 무너졌습니다.")
    else:
        cheap = "값이 싸 보여도 보호 장치가 없으면 사지 않습니다" if mos > 0 else "값도 보수적 가치보다 비쌉니다"
        opinion = (f"재무나 이익의 안정이 기준에 못 미칩니다(재무 {'해당 없음' if st is None else f'{st:.0f}'}/기준 {p['strength']:.0f}, 이익의 안정 {sb:.0f}/기준 {p['stability']:.0f}). "
                   f"{cheap}({price}, 안전마진 {mos * 100:+.0f}%). 재무와 이익이 기준을 넘고 안전마진이 {p['mos_buy'] * 100:.0f}% 이상이어야 합니다.")
    cond = {"buy": f"안전마진 {p['mos_buy'] * 100:.0f}% 이상(지금 {'계산 안 됨' if mos is None else f'{mos * 100:+.0f}%'}), 재무 {p['strength']:.0f} 이상, 이익의 안정 {p['stability']:.0f} 이상",
            "hold": "안전마진이 0%보다 크고 재무가 기준을 지키는 동안", "add": f"안전마진 {p['mos_strong'] * 100:.0f}% 이상. 한 종목에 몰지 않고 여러 종목에 나눕니다",
            "reduce": "값이 보수적 가치에 닿을 때(안전마진 0% 이하)", "sell": f"안전마진 {G_SELL_MOS * 100:.0f}% 이하이거나 재무가 기준 아래로 내려갈 때",
            "invalidation": "적자 전환, 부채 급증, 영업현금흐름이 순이익의 절반에 못 미칠 때"}
    return finish("GRAHAM", f, g, rec, held, "값이 가치에 닿을 때까지(대개 2~3년)", f"{val['method']}: 안전마진 {'계산 안 됨' if mos is None else f'{mos * 100:+.0f}%'}",
                  {"value": None if mos is None or mos >= 1 else round(mos / (1.0 - mos), 4), "basis": "값이 보수적 가치까지 오를 때의 차이. 예측이 아니며 언제 닿는지 말하지 않습니다"}, _drawdown(f), opinion,
                  f"안전마진: {val['method']}.", cond, 0.05, {"margin_of_safety": None if mos is None else round(mos, 3), "method": val["method"], "profile": p["label"], "value_trap": bool(trap), "sound": sound},
                  ("가치 함정 가능성",) if trap else (), ("순유동자산 가치와 유형 장부가(자료 없음)", "배당의 여러 해 이력(자료 없음)"))


# ------------------------------------------------------------------------------------------------- Lynch
SLOW, STALWART, FAST, CYCLICAL, TURNAROUND, ASSET = "SLOW_GROWER", "STALWART", "FAST_GROWER", "CYCLICAL", "TURNAROUND", "ASSET_PLAY"
KIND_KO = {SLOW: "저성장주", STALWART: "대형 우량주", FAST: "고성장주", CYCLICAL: "경기순환주", TURNAROUND: "회생주", ASSET: "자산주"}
L_FAST, L_STALWART, L_STRONG, L_BUY, L_HOLD, L_PEG_GROWTH, L_SLOW_PE = 0.18, 0.07, 75.0, 62.0, 50.0, 0.30, 20.0


def lynch_kind(f: Dict[str, Any]) -> Optional[str]:
    g3 = f.get("eps_cagr3") if f.get("eps_cagr3") is not None else f.get("rev_cagr3")
    if (f.get("pe") is not None and f["pe"] <= 0) or (f.get("profit_years") is not None and f["profit_years"] <= 0.6):
        return TURNAROUND
    if f.get("cyclical"):
        return CYCLICAL
    if f.get("pb") is not None and 0 < f["pb"] < 1.0:
        return ASSET
    if g3 is None:
        return None
    return FAST if g3 >= L_FAST else STALWART if g3 >= L_STALWART else SLOW


def lynch(f: Dict[str, Any], held: bool = False, ctx: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    kind = lynch_kind(f)
    pe, g3, dy = f.get("pe"), f.get("eps_cagr3"), f.get("dividend_yield") or 0.0
    # dividends count toward what the price buys; growth above L_PEG_GROWTH a year is not counted on to last
    peg = None if not pe or pe <= 0 or not g3 or g3 <= 0 else pe / ((min(g3, L_PEG_GROWTH) + dy) * 100.0)
    peg_part = ("peg", 3, band(peg, 2.0, 0.7), CONFIRMED if peg is not None else MISSING)
    debt = part(f, "debt_equity", 2, 1.5, 0.3)
    cashq = part(f, "ocf_to_ni", 2, 0.6, 1.1)
    small = ("market_cap", 1, None if f.get("market_cap") is None else band(f["market_cap"], 5e11 if f.get("market") == "US" else 5e13, 1e10 if f.get("market") == "US" else 1e12), f["_status"]["market_cap"])
    by_kind = {
        FAST: {"성장": (0.35, [part(f, "eps_cagr3", 3, 0.15, 0.30), part(f, "rev_growth", 2, 0.05, 0.20), part(f, "eps_growth", 2, 0.0, 0.25)]), "성장 대비 가격": (0.30, [peg_part]),
               "재무와 이익의 질": (0.25, [debt, cashq]), "더 클 여지": (0.10, [small])},
        STALWART: {"꾸준한 성장": (0.30, [part(f, "eps_cagr3", 3, 0.05, 0.15), part(f, "profit_years", 2, 0.75, 1.0), part(f, "rev_growth", 1, 0.0, 0.10)]),
                   "성장 대비 가격": (0.35, [peg_part, ("pe", 2, band(pe, 28.0, 14.0), f["_status"]["pe"])]), "재무와 이익의 질": (0.35, [debt, cashq])},
        SLOW: {"배당과 환원": (0.40, [part(f, "dividend_yield", 3, 0.01, 0.04), flag("returns_capital", 2, f.get("returns_capital"))]), "가격": (0.30, [("pe", 2, band(pe, 20.0, 10.0), f["_status"]["pe"])]),
               "안정": (0.30, [part(f, "profit_years", 2, 0.75, 1.0), debt])},
        CYCLICAL: {"회복 방향": (0.40, [part(f, "eps_growth", 3, -0.10, 0.30), part(f, "rev_growth", 2, -0.05, 0.15)]), "버틸 재무": (0.40, [debt, part(f, "cash_debt", 2, 0.1, 1.0), part(f, "current_ratio", 1, 1.0, 2.0)]),
                   "이익의 질": (0.20, [cashq])},
        TURNAROUND: {"돌아서는 증거": (0.50, [part(f, "eps_growth", 3, 0.0, 0.5), part(f, "rev_growth", 2, 0.0, 0.15), part(f, "fcf_margin", 2, 0.0, 0.08)]),
                     "살아남을 재무": (0.50, [debt, part(f, "cash_debt", 2, 0.2, 1.0), part(f, "current_ratio", 2, 1.0, 2.0)])},
        ASSET: {"자산 대비 가격": (0.45, [part(f, "pb", 3, 1.0, 0.5)]), "자산을 지키는 재무": (0.35, [debt, part(f, "profit_years", 2, 0.5, 1.0)]), "이익": (0.20, [part(f, "roe", 2, 0.0, 0.10)])},
    }
    if kind is None:
        return no_data("LYNCH", f, groups_score(f, {"성장": (1.0, [part(f, "eps_cagr3", 1, 0.0, 0.2)])}), "3년 이익·매출 성장률이 없어 어떤 종류의 회사인지 나눌 수 없습니다.", held)
    g = groups_score(f, by_kind[kind])
    for e in g["evidence"]:
        if e["figure"] == "peg":
            e["text"] = f"PEG {peg:.2f}"
        elif e["figure"] == "market_cap":
            e["text"] = "몸집이 작아 더 클 여지" if e["value"] >= 0.7 else "이미 큰 회사"
    if g["score"] is None or g["coverage"] < MIN_COVERAGE:
        return no_data("LYNCH", f, g, f"{KIND_KO[kind]}로 나눴지만 그 종류를 평가할 자료가 모자랍니다.", held)
    s = g["score"]
    story_broken = (kind == FAST and (f.get("eps_growth") or 0) < 0 and (f.get("rev_growth") or 0) < 0.05) or (kind == TURNAROUND and (f.get("eps_growth") or 0) <= 0 and (f.get("rev_growth") or 0) <= 0)
    # whatever the kind (a cyclical apart, whose earnings fall in every down-leg): earnings down by a fifth with sales falling is no story
    story_broken = story_broken or (kind != CYCLICAL and (f.get("eps_growth") or 0) < -0.2 and (f.get("rev_growth") or 0) < 0)
    dear = peg is not None and peg > 2.5
    leveraged = (f.get("debt_equity") or 0) > 2.0 or f.get("no_equity")
    quality_ok = not leveraged and (f.get("ocf_to_ni") is None or f["ocf_to_ni"] >= 0.6)
    # what each kind must show before any score counts: a growth stock a PEG, a slow grower a dividend and a modest multiple
    priced = {FAST: peg is not None, STALWART: peg is not None, SLOW: pe is not None and 0 < pe <= L_SLOW_PE and f.get("dividend_yield") is not None}.get(kind, True)
    if story_broken:
        rec = SELL if held else AVOID
    elif held and dear:
        rec = REDUCE
    elif s >= L_STRONG and quality_ok and priced and not dear:
        rec = STRONG_BUY
    elif s >= L_BUY and quality_ok and priced and not dear:
        rec = BUY
    elif s >= L_BUY and dear:
        rec = WAIT                                    # the growth is there; the price already has it
    elif s >= L_HOLD:
        rec = HOLD
    else:
        rec = REDUCE if held else AVOID
    growth = f"3년 주당이익 성장 연 {pct(g3)}, 최근 매출 성장 {pct(f.get('rev_growth'))}"
    peg_text = "PEG 계산 안 됨" if peg is None else f"PEG {peg:.2f}"
    turn = f"최근 주당이익 성장 {pct(f.get('eps_growth'))}, 최근 매출 성장 {pct(f.get('rev_growth'))}, {_de_text(f)}"
    basis, why = {FAST: (f"{growth}, {peg_text}", "성장에 비해 값이 지나치지 않습니다"), STALWART: (f"{growth}, {peg_text}", "성장에 비해 값이 지나치지 않습니다"),
                  SLOW: (f"배당수익률 {pct(f.get('dividend_yield'))}, PER {times(pe)}, 흑자 연도 {pct(f.get('profit_years'), 0)}", "배당과 안정으로 보는 종목이고 값이 무겁지 않습니다"),
                  CYCLICAL: (turn, "이익이 회복하는 방향이고 재무가 버팁니다. 낮은 PER은 정점일 수 있어 싸다고 읽지 않았습니다"), TURNAROUND: (turn, "돌아서는 증거가 숫자에 보이고 재무가 버팁니다"),
                  ASSET: (f"PBR {times(f.get('pb'), 2)}, ROE {pct(f.get('roe'))}, {_de_text(f)}", "자산보다 싸게 거래되고 재무가 그 자산을 지킵니다")}[kind]
    if rec in BUY_SIDE:
        opinion = f"{KIND_KO[kind]}로 봅니다({basis}). {why}. 이야기가 꺾이면(이익과 매출이 함께 줄면) 팝니다."
    elif s >= L_BUY and not quality_ok and not story_broken and not dear:
        bad = "부채가 과합니다" if leveraged else f"이익이 현금으로 들어오지 않습니다({shown(f, 'ocf_to_ni')})"
        opinion = f"{KIND_KO[kind]}로 점수({s:.0f})는 매수 기준 {L_BUY:.0f}을 넘지만 {bad}({_de_text(f)}). 숫자가 좋아 보여도 이 조건 없이는 사지 않습니다. 부채/자본 2배 이하, 영업현금흐름이 순이익의 60% 이상이 되면 매수 조건입니다."
    elif s >= L_BUY and not priced and not story_broken and not dear:
        need = f"PER {L_SLOW_PE:.0f}배 이하와 확인되는 배당이 있어야" if kind == SLOW else "PEG를 계산할 수 있어야(흑자이고 3년 이익이 늘었어야)"
        opinion = f"{KIND_KO[kind]}로 점수({s:.0f})는 기준을 넘지만 값을 따질 근거가 없습니다({basis}). 이 종류의 회사는 {need} 삽니다."
    elif rec == WAIT:
        opinion = f"{KIND_KO[kind]}로 성장은 확인됩니다({growth}). 다만 {peg_text}로 값이 성장을 이미 다 담고 있어 기다립니다. PEG가 2 아래로 내려오면 다시 봅니다."
    elif story_broken:
        opinion = f"{KIND_KO[kind]}의 이야기가 숫자로 확인되지 않습니다(최근 주당이익 성장 {pct(f.get('eps_growth'))}, 매출 성장 {pct(f.get('rev_growth'))}). 뒷받침 없는 기대에는 돈을 넣지 않습니다."
    elif kind == CYCLICAL:
        opinion = f"경기순환주입니다. 이런 회사는 PER이 낮을 때가 정점일 수 있어 낮은 PER을 싸다고 읽지 않습니다. 회복 방향과 버틸 재무({turn})로 보면 점수 {s:.0f}으로 기준 {L_BUY:.0f}에 못 미칩니다."
    else:
        opinion = f"{KIND_KO[kind]}로 봅니다. 점수 {s:.0f}으로 매수 기준 {L_BUY:.0f}에 못 미칩니다({basis}). 이 종류의 회사에서 보는 숫자가 좋아지면 다시 봅니다."
    cond = {"buy": f"{KIND_KO[kind]} 기준 점수 {L_BUY:.0f} 이상(지금 {s:.0f}), PEG 2.5 이하, 부채/자본 2배 이하, 이익이 현금으로 들어올 것. PEG가 1 아래여도 이 조건 없이는 사지 않습니다",
            "hold": "처음의 성장 이야기가 숫자로 이어지는 동안. 주가가 많이 올랐다는 이유만으로는 팔지 않습니다", "add": f"점수 {L_STRONG:.0f} 이상이고 이야기가 더 좋아질 때",
            "reduce": "PEG가 2.5를 넘을 때(값이 성장을 앞질렀을 때)", "sell": "성장 이야기가 꺾일 때: 이익과 매출이 함께 줄거나, 회생의 증거가 사라질 때",
            "invalidation": "재고가 매출보다 빨리 느는 것은 중요한 경고지만 재고 자료가 없어 확인하지 못합니다. 부채 급증과 이익 감소로 대신 봅니다"}
    weight = 0.05 + 0.05 * max(0.0, min((s - L_BUY) / 25.0, 1.0))
    return finish("LYNCH", f, g, rec, held, "성장 이야기가 이어지는 동안(대개 2~5년)", f"{peg_text}(PER ÷ (3년 이익 성장률[상한 {L_PEG_GROWTH * 100:.0f}%] + 배당수익률)), PER {times(pe)}", _growth_yield(f), _drawdown(f), opinion,
                  f"{KIND_KO[kind]}: {basis}.", cond, weight, {"category": kind, "category_ko": KIND_KO[kind], "peg": None if peg is None else round(peg, 2), "story_broken": story_broken},
                  ("부채 과다",) if leveraged else (), ("재고와 매출의 비율(자료 없음)", "시장 점유율과 고객 증가(자료 없음)"))


# ------------------------------------------------------------------------------------------------- Druckenmiller
D_STRONG, D_BUY, D_RISK_OFF, D_RISK_ON = 72.0, 60.0, 35.0, 60.0


def regimes(f: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The market's regimes that the stored figures can tell, more than one at a time, each with how sure (0-100).
    Inflation, growth and policy-rate regimes are not told: those series are not in the scan's record."""
    out = []
    state, vix, credit, breadth = f.get("market_state"), f.get("vix_pct"), f.get("credit_pct"), f.get("breadth")
    close, ma200, ma50 = f.get("index_close"), f.get("index_ma200"), f.get("index_ma50")
    if state is not None:
        if state < D_RISK_OFF:
            out.append({"regime": "RISK_OFF", "label": "위험 회피", "confidence": round(min(100.0, 50 + (D_RISK_OFF - state) * 2))})
        if state >= D_RISK_ON:
            out.append({"regime": "RISK_ON", "label": "위험 선호", "confidence": round(min(100.0, 50 + (state - D_RISK_ON) * 2))})
    if credit is not None and credit >= 0.7:
        out.append({"regime": "LIQUIDITY_CONTRACTION", "label": "유동성 축소", "confidence": round(credit * 100)})
    if credit is not None and credit <= 0.3:
        out.append({"regime": "LIQUIDITY_EXPANSION", "label": "유동성 확대", "confidence": round((1 - credit) * 100)})
    if close and ma200 and close < ma200 and breadth is not None and breadth < 0.3 and (credit is None or credit >= 0.6):
        out.append({"regime": "RECESSION_RISK", "label": "침체 위험", "confidence": round(min(100.0, 50 + (0.3 - breadth) * 150 + (10 if vix is not None and vix > 0.8 else 0)))})
    if close and ma200 and ma50 and close > ma50 and close < ma200:
        out.append({"regime": "ECONOMIC_RECOVERY", "label": "회복 시도", "confidence": 50})
    return out


def druckenmiller(f: Dict[str, Any], held: bool = False, ctx: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    price, ma200, ma50 = f.get("price"), f.get("ma200"), f.get("ma50")
    above200 = None if not price or not ma200 else price > ma200
    above50 = None if not price or not ma50 else price > ma50
    macro = [("market_state", 1, band(f.get("market_state"), 20.0, 70.0), f["_status"]["market_state"])]
    earnings = [part(f, "eps_growth", 3, -0.10, 0.25), part(f, "rev_growth", 2, 0.0, 0.15), part(f, "forward_growth", 3, 0.0, 0.20)]
    trend = [flag("ma200", 3, above200), part(f, "ma200_slope", 2, -0.02, 0.05), flag("ma50", 2, above50), part(f, "rs", 3, 0.5, 0.9), part(f, "ret_12_1", 2, 0.0, 0.4),
             part(f, "rel_126", 1, 0.0, 0.2), part(f, "dist_high", 2, -0.25, -0.03)]
    sector_rs = ((ctx or {}).get("sector_rs") or {}).get(f.get("sector"))
    industry = [("sector_rs", 1, band(sector_rs, 0.35, 0.65), CONFIRMED if sector_rs is not None else MISSING)]
    risk = [part(f, "reward_risk", 3, 1.0, 2.5), part(f, "atr_pct", 1, 0.06, 0.02), part(f, "max_drawdown", 2, -0.5, -0.15)]
    soon = f.get("earnings_sessions")
    catalyst = [("earnings_sessions", 2, None if soon is None else 1.0 if 0 <= soon <= 15 else 0.3, f["_status"]["earnings_sessions"]), ("events_positive", 1, band(f.get("events_positive"), 0, 2), f["_status"]["events_positive"])]
    g = groups_score(f, {"시장 환경": (0.15, macro), "이익의 방향": (0.25, earnings), "가격 추세": (0.30, trend), "업종의 힘": (0.10, industry), "위험 대비 보상": (0.15, risk), "계기": (0.05, catalyst)})
    for e in g["evidence"]:
        e["text"] = {"ma200": f"200일선 대비 {(price / ma200 - 1) * 100:+.1f}%" if above200 is not None else e["text"], "ma50": f"50일선 대비 {(price / ma50 - 1) * 100:+.1f}%" if above50 is not None else e["text"],
                     "market_state": f"시장 상태 {f['market_state']:.0f}/100" if f.get("market_state") is not None else e["text"], "sector_rs": f"업종 상대 강도 중앙값 {pct(sector_rs, 0)}",
                     "earnings_sessions": f"실적 발표까지 {soon}거래일" if soon is not None else e["text"]}.get(e["figure"], e["text"])
    if above200 is None or f.get("rs") is None or g["coverage"] < MIN_COVERAGE:
        return no_data("DRUCKENMILLER", f, g, "200일선이나 상대 강도 자료가 없어 추세를 읽을 수 없습니다.", held)
    s, state = g["score"], f.get("market_state")
    now = regimes(f)
    risk_off = any(r["regime"] == "RISK_OFF" for r in now)
    trend_ok = above200 and (above50 is None or above50 or (f.get("ma50_slope") or 0) > 0)
    if not above200:
        rec = SELL if held else AVOID
    elif held and not trend_ok and f["rs"] < 0.5:
        rec = REDUCE
    elif not trend_ok:
        rec = HOLD if held else WAIT
    else:
        rec = STRONG_BUY if s >= D_STRONG else BUY if s >= D_BUY else HOLD
        if risk_off:                              # in a risk-off market one notch lower and half the size: cash is a position
            rec = {STRONG_BUY: BUY, BUY: HOLD if held else WAIT}.get(rec, rec)
    where = f"200일선 대비 {(price / ma200 - 1) * 100:+.1f}%, 상대 강도 백분위 {pct(f['rs'], 0)}"
    names = ", ".join(r["label"] for r in now) or "뚜렷한 국면 없음"
    if rec in BUY_SIDE:
        opinion = f"추세와 이익이 같은 방향입니다({where}, 최근 주당이익 성장 {pct(f.get('eps_growth'))}). 시장은 '{names}'입니다. 가격이 200일선 아래로 내려가면 바로 생각을 바꿉니다."
    elif not above200:
        opinion = f"가격이 200일선 아래입니다({where}). 사업이 좋아도 추세가 꺾인 종목에는 서지 않습니다. 200일선을 되찾고 상대 강도가 올라오면 다시 봅니다."
    elif risk_off and trend_ok and s >= D_BUY:
        opinion = f"종목의 추세는 살아 있습니다({where}). 그러나 시장이 '{names}'(시장 상태 {state:.0f}/100)라 한 단계 낮춰 봅니다. 현금도 포지션입니다. 시장 상태가 {D_RISK_OFF:.0f}을 넘으면 올립니다."
    else:
        opinion = f"추세나 이익의 힘이 부족합니다(점수 {s:.0f}, 기준 {D_BUY:.0f}; {where}). 50일선과 200일선 위에서 이익 전망이 좋아지는 것을 확인하면 들어갑니다."
    cond = {"buy": f"가격이 200일선과 50일선 위, 점수 {D_BUY:.0f} 이상(지금 {s:.0f}), 시장 상태 {D_RISK_OFF:.0f} 이상(지금 {'자료 없음' if state is None else f'{state:.0f}'})",
            "hold": "가격이 200일선 위에 있는 동안", "add": f"점수 {D_STRONG:.0f} 이상이고 시장이 위험 회피가 아닐 때", "reduce": "50일선 아래로 내려가고 상대 강도가 절반 아래로 떨어질 때",
            "sell": "가격이 200일선 아래로 내려갈 때. 근거가 바뀌면 빨리 줄입니다", "invalidation": "이익 전망이 꺾이거나 시장이 위험 회피로 바뀔 때. 이익 추정치의 변화는 기록이 쌓이기 전이라 아직 읽지 못합니다"}
    weight = (0.08 + 0.10 * max(0.0, min((s - D_BUY) / 25.0, 1.0))) * (0.5 if risk_off else 1.0)
    upside = None if not f.get("target") or not price else f["target"] / price - 1.0
    down = None if not f.get("stop") or not price else f["stop"] / price - 1.0
    return finish("DRUCKENMILLER", f, g, rec, held, "추세가 이어지는 동안(몇 주~몇 달)", f"값보다 방향을 봅니다: {where}",
                  {"value": None if upside is None else round(upside, 4), "basis": "스캔이 저장한 목표가까지의 거리. 예측이 아닙니다"},
                  {"value": None if down is None else round(down, 4), "basis": "스캔이 저장한 손절가까지의 거리"}, opinion, f"시장 '{names}', 종목 추세 {'살아 있음' if trend_ok else '꺾임'}.", cond, weight,
                  {"regimes": now, "regimes_not_told": ["물가 상승·둔화 국면", "성장률과 정책 금리 국면"], "trend_ok": bool(trend_ok), "risk_off": risk_off},
                  (f"가격이 200일선 아래({(price / ma200 - 1) * 100:+.1f}%)",) if not above200 else (), ("이익 추정치의 변화(기록이 쌓이기 전)", "물가·성장률·정책 금리 국면(스캔 기록에 없음)"))


PEOPLE: Dict[str, Tuple[str, str, str]] = {
    "BUFFETT": ("버핏식", "장기 사업 소유자", "이 값에 이 사업 전체를 오래 갖고 싶은가"),
    "MUNGER": ("멍거식", "탁월한 사업에 집중", "오래 복리로 불어날 비범한 사업인가, 그리고 어떻게 망할 수 있는가"),
    "GRAHAM": ("그레이엄식", "방어적 가치 투자", "분석이 틀려도 버틸 만큼 보수적 가치보다 싸게 사는가"),
    "LYNCH": ("린치식", "성장 기회 발굴", "이 사업은 어떻게 크고, 지금 값은 그 성장에 비해 적당한가"),
    "DRUCKENMILLER": ("드러켄밀러식", "거시와 추세", "시장은 어디로 가고, 보상이 위험보다 훨씬 큰 곳은 어디인가"),
}
ENGINES: Dict[str, Callable[..., Dict[str, Any]]] = {"BUFFETT": buffett, "MUNGER": munger, "GRAHAM": graham, "LYNCH": lynch, "DRUCKENMILLER": druckenmiller}
ORDER = tuple(ENGINES)


def evaluate(f: Dict[str, Any], held: Optional[Dict[str, bool]] = None, ctx: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """The five engines on one stock, each on its own.  ``held``: {investor: is the stock in that investor's portfolio}."""
    return [ENGINES[key](f, bool((held or {}).get(key)), ctx) for key in ORDER]
