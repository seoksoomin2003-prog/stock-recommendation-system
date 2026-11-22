"""'쉽게 설명해줘': a stock card or a portfolio told in everyday words (user request 2026-11-22).

Built by rules from fields the card already has: no model is called and nothing is fetched.  It adds no judgement of its
own: every sentence restates a field of the card.  Words a beginner would not know (the ones in ``AVOID``) are kept out of
every sentence this module writes; a test checks that.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

# Words this module's own sentences never use.  (Text quoted from elsewhere, such as a company name, is not checked.)
AVOID = ("밸류에이션", "모멘텀", "변동성", "손익비", "유동성", "저항선", "이동평균", "벤치마크", "커버리지", "펀더멘털", "ATR", "PER", "PBR", "FCF", "ROE",
         "스윙", "레버리지", "리스크", "드로다운", "게이트", "팩터", "요인", "프리미엄", "섹터", "익스포저", "포지션")

STYLE = {"SWING": ("짧게 사고파는 관점(몇 주 안팎)", "짧게"), "LONG_TERM": ("오래 들고 가는 관점(몇 달에서 몇 년)", "오래")}

BAND = {"STRONG_BUY_CANDIDATE": "이 프로그램의 기준에 아주 잘 맞는 편입니다.", "BUY_CANDIDATE": "이 프로그램의 기준에 잘 맞는 편입니다.",
        "HOLD_WATCH": "나쁘지는 않지만 사야 할 만큼 뚜렷하지도 않습니다. 지켜보는 구간입니다.", "WEAK_REDUCE": "기준에 잘 맞지 않습니다. 갖고 있다면 줄일지 살펴보는 구간입니다.",
        "SELL_AVOID": "기준에 맞지 않습니다. 새로 사지 않는 구간입니다."}

# factor -> (when it reads well, when it reads badly)
FACTOR = {
    "trend_structure": ("주가가 최근 몇 달 동안 오르는 흐름을 지키고 있습니다.", "주가 흐름이 내려가는 쪽이거나 방향이 뚜렷하지 않습니다."),
    "relative_strength": ("지난 여섯 달 동안 다른 종목들보다 더 많이 올랐습니다.", "지난 여섯 달 동안 다른 종목들보다 덜 올랐거나 더 많이 내렸습니다."),
    "momentum": ("최근 들어 오르는 힘이 붙어 있습니다.", "최근 들어 오르는 힘이 약합니다."),
    "breakout_volume": ("지난 1년 가운데 가장 높았던 가격 가까이에 있고 거래도 늘었습니다.", "지난 1년 가운데 가장 높았던 가격에서 멀리 떨어져 있거나, 오를 때 거래가 따라붙지 않았습니다."),
    "volatility_structure": ("요즘 가격이 출렁이는 폭이 평소보다 좁습니다.", "요즘 가격이 출렁이는 폭이 평소보다 넓습니다."),
    "earnings_revenue_quality": ("회사의 매출과 이익이 늘고 있습니다.", "회사의 매출이나 이익이 줄고 있거나 늘지 않습니다."),
    "profitability": ("장사해서 남기는 비율이 좋습니다.", "장사해서 남기는 비율이 낮습니다."),
    "balance_sheet": ("빚이 많지 않고 살림이 튼튼한 편입니다.", "빚이 많거나, 곧 갚아야 할 돈에 비해 가진 돈이 빠듯합니다."),
    "cash_flow_quality": ("장부에 적힌 이익만큼 실제 현금도 들어오고, 쓰고 남는 현금도 있습니다.", "장부에 적힌 이익에 비해 실제로 들어오는 현금이 적거나, 쓰고 나면 남는 현금이 적습니다."),
    "risk_reward": ("지금 가격에서는 기대할 이익이 감수할 손실보다 넉넉히 큽니다.", "지금 가격에서는 기대할 이익에 비해 감수할 손실이 큰 편입니다."),
    "atr_risk": ("하루하루 가격이 움직이는 폭이 크지 않습니다.", "하루하루 가격이 크게 움직여서 짧은 기간에도 손실이 커질 수 있습니다."),
    "liquidity": ("거래가 활발해서 사고팔기 쉽습니다.", "거래가 많지 않아 원하는 값에 사고팔기 어려울 수 있습니다."),
    "drawdown_gap": ("지난 1년 동안 크게 떨어진 적이 없고, 최근 하루 사이에 값이 뚝 끊겨 움직인 날도 없습니다.", "지난 1년 사이에 크게 떨어졌거나, 최근 하루 사이에 값이 뚝 끊겨 움직인 날이 있습니다."),
    "earnings_calendar": ("실적 발표가 코앞은 아닙니다.", "곧 실적 발표가 있어 발표 직후 가격이 크게 움직일 수 있습니다."),
    "material_disclosures": ("최근 회사가 낸 공시에 걱정스러운 내용이 보이지 않습니다.", "최근 공시에 주주에게 불리할 수 있는 내용(예: 새 주식 발행)이 있습니다."),
    "insider_activity": ("회사 임원들이 자기 회사 주식을 사고 있습니다.", "회사 임원들이 자기 회사 주식을 팔고 있습니다."),
    "long_trend": ("긴 기간으로 보아 주가가 오르는 흐름입니다.", "긴 기간으로 보아 주가가 내려가는 흐름입니다."),
    "momentum_persistence": ("오르는 흐름이 여러 달 이어지고 있습니다.", "오르는 흐름이 이어지지 못하고 있습니다."),
    "valuation": ("회사가 버는 돈에 비해 주가가 비싸지 않은 편입니다.", "회사가 버는 돈에 비해 주가가 비싼 편입니다."),
    "business_quality": ("꾸준히 돈을 잘 버는 사업입니다.", "돈을 버는 힘이 약하거나 해마다 들쭉날쭉합니다."),
    "growth_quality": ("매출과 이익이 몇 해에 걸쳐 꾸준히 늘었습니다.", "매출과 이익이 몇 해 동안 잘 늘지 않았습니다."),
    "free_cash_flow": ("사업에 쓸 돈을 다 쓰고도 현금이 남습니다.", "사업에 쓸 돈을 쓰고 나면 남는 현금이 적거나 없습니다."),
    "balance_dilution": ("빚이 많지 않고, 주식 수를 늘리지 않아 기존 주주의 몫이 줄지 않았습니다.", "빚이 많거나, 주식 수가 늘어 기존 주주의 몫이 줄었습니다."),
    "financial_resilience": ("어려운 시기가 와도 버틸 여력이 있습니다.", "어려운 시기에 버틸 여력이 넉넉하지 않습니다."),
    "downside_drawdown": ("지난 1년 동안 떨어질 때도 떨어진 폭이 크지 않았습니다.", "지난 1년 사이에 크게 떨어진 적이 있습니다."),
    "leverage": ("빚이 적습니다.", "빚이 많습니다."),
    "governance": ("회사 운영에서 걱정스러운 신호가 보이지 않습니다.", "회사 운영과 관련해 걱정스러운 공시가 있습니다."),
    "material_events": ("최근 큰 사건을 알리는 공시가 없습니다.", "최근 주가를 크게 움직일 수 있는 사건 공시가 있습니다."),
    "insider_ownership": ("경영진이 자기 회사 주식을 많이 갖고 있어 주주와 같은 배를 탔습니다.", "경영진이 가진 자기 회사 주식이 적습니다."),
    "capital_allocation": ("번 돈을 배당이나 자기 주식 사들이기로 주주에게 돌려주고, 주식 수를 늘리지 않습니다.", "번 돈을 주주에게 돌려주는 모습이 뚜렷하지 않거나 주식 수가 늘고 있습니다."),
}

ENTRY = {
    "WAIT_FOR_PULLBACK": "지금 가격에 사면 기대할 이익에 비해 감수할 손실이 큽니다. 가격이 조금 내려올 때까지 기다리라는 것이 이 프로그램의 규칙입니다.",
    "WAIT_FOR_BREAKOUT_CONFIRMATION": "전에 못 넘던 가격대를 확실히 넘어서는지 본 다음에 사라는 것이 이 프로그램의 규칙입니다.",
    "WAIT_FOR_EARNINGS": "곧 실적 발표가 있습니다. 발표로 가격이 크게 움직일 수 있어 발표 뒤에 다시 보라는 규칙입니다.",
    "OVERVALUED_AT_CURRENT_PRICE": "회사가 버는 돈에 비해 지금 주가가 비쌉니다. 이 가격에서는 사지 않는다는 규칙입니다.",
    "NO_VALID_ENTRY_SETUP": "지금은 살 만한 조건이 갖춰지지 않았습니다.",
}
ENTRY_NOW = {"SWING": "이 프로그램의 규칙으로는 지금 사는 것을 막는 조건이 없습니다. '지금 사면 오른다'는 뜻은 아닙니다.",
             "LONG_TERM": "오래 들고 갈 관점에서 지금 사는 것을 막는 조건이 없습니다. '좋은 때'라는 뜻이 아니라 '막는 이유가 없다'는 뜻입니다."}

GATE = {"DATA_ANOMALY": "가격 자료에 이상한 값이 있어 믿을 수 없습니다.", "EARNINGS_IMMINENT": "실적 발표가 코앞입니다.",
        "INVALID_ACCOUNTING": "회사의 살림 숫자에 문제가 있습니다(예: 가진 것보다 빚이 더 많음).", "INVALID_IDENTITY": "이 종목이 맞는지 확인되지 않았습니다.",
        "LOW_LIQUIDITY": "거래가 너무 적어 사고팔기 어렵습니다.", "LOW_PRICE": "주가가 너무 낮아 작은 움직임에도 크게 흔들립니다.", "NO_TRADING": "거래가 멈춰 있습니다.",
        "SEVERE_EVENT": "거래 정지나 상장 폐지 위험 같은 심각한 공시가 있습니다.", "SHORT_HISTORY": "상장한 지 얼마 안 돼 살펴볼 기록이 짧습니다.", "STALE_PRICE": "최신 가격을 받지 못했습니다."}

CAVEAT = ("점수가 높다고 주가가 오른다는 뜻이 아닙니다. 이 점수가 실제로 맞는지는 아직 확인되지 않았고, 확인에는 1년 넘게 걸립니다. "
          "이 프로그램은 사라고 권하지 않고 주문도 내지 않습니다. 잃어도 되는 돈인지, 스스로 판단하세요.")

WORDS = {"손절 가격": "샀는데 값이 내려갈 때 '여기까지 내려가면 판다'고 미리 정해 두는 가격입니다. 손해를 더 키우지 않으려는 선입니다.",
         "목표 가격": "이 프로그램의 규칙이 '여기까지 오르면 팔 것을 생각한다'고 잡은 가격입니다. 거기까지 오른다는 약속이 아닙니다.",
         "실적 발표": "회사가 석 달마다 얼마를 팔고 얼마를 남겼는지 알리는 날입니다. 이날 앞뒤로 주가가 크게 움직이는 일이 많습니다.",
         "공시": "회사가 법에 따라 투자자에게 알려야 하는 소식을 공개한 문서입니다.",
         "현금 비중": "돈 가운데 주식을 사지 않고 그대로 두는 몫입니다."}


def money(v: Optional[float], market: str) -> str:
    if v is None:
        return "없음"
    return f"{v:,.0f}원" if market == "KR" else f"{v:,.2f}달러"


def _pct(v: float) -> str:
    """A whole per cent, or one decimal when it is under one: "약 0%" told nothing about a stock that barely moves."""
    return f"{abs(v):.1f}" if abs(v) < 1 else f"{abs(v):.0f}"


DEBT = ("balance_sheet", "balance_dilution", "leverage")      # sentences about debt: not said of a bank, whose deposits are its debt
LOSS_VALUE = "회사가 가진 재산에 비하면 주가가 낮은 편이지만, 지금은 적자라 '버는 돈에 비해 싸다'고 말할 수는 없습니다."
LOSS_WORRY = "지금 적자입니다. 버는 돈이 없어 주가가 싼지 따질 수 없고, 이 프로그램은 이런 경우를 비싼 것으로 봅니다."
NO_VALUE = "회사가 버는 돈에 비해 주가가 싼지 비싼지 따질 자료가 없어서, 지금 사도 되는지를 판단하지 않았습니다. 자료가 없다는 것은 값이 적당하다는 뜻이 아닙니다."
MARKET = {"ADVERSE": "지금 시장 전체의 상태가 좋지 않은 쪽으로 읽힙니다.", "UNKNOWN": "시장 전체의 상태를 읽을 자료가 모자라, 좋은지 나쁜지 알지 못합니다."}


def _sides(card: Dict[str, Any], n: int = 3, facts: Optional[Dict[str, Any]] = None) -> Tuple[List[str], List[str], int]:
    """The scored factors that read clearly well or clearly badly, the heaviest first, and how many were left unsaid.
    A factor computed from part of its figures is not spoken for: a sentence here names every figure the factor reads, and a
    Korean stock's "debt and share count" factor is computed from the debt alone (2026-11-22: it read "has not issued shares"
    for a company whose share count this program does not know)."""
    rows, unsaid = [], 0
    facts = facts or {}
    for f in card.get("factors") or []:
        v = f.get("normalized")
        if f.get("scored") is False or f.get("status") == "MISSING" or v is None or f.get("factor") not in FACTOR:
            continue
        if facts.get("financial") and f["factor"] in DEBT:      # a bank's "debt" is mostly its customers' deposits
            unsaid += v >= 0.65 or v <= 0.35
            continue
        got = f.get("inputs") or {}
        if got.get("total") and (got.get("have") or 0) < got["total"]:
            unsaid += v >= 0.65 or v <= 0.35
            continue
        rows.append((float(f.get("weight") or 0) * abs(v - 0.5), v, f["factor"]))
    rows.sort(key=lambda r: (-r[0], r[2]))
    loss = bool(facts.get("loss"))
    good = [LOSS_VALUE if loss and k == "valuation" else FACTOR[k][0] for _, v, k in rows if v >= 0.65][:n]
    bad = [LOSS_WORRY if loss and k == "valuation" else FACTOR[k][1] for _, v, k in rows if v <= 0.35][:n]
    return good, bad, int(unsaid)


def card_plain(card: Dict[str, Any], facts: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """One strategy's card in everyday words: ``{"title", "parts": [{"h", "lines"}], "words": [{"word", "means"}]}``.
    ``facts``: what the card's own fields do not say but its sentences depend on: ``loss`` (the company loses money now),
    ``financial`` (a bank or insurer), ``deals`` (merger or tender-offer filings).  Until 2026-11-23 a merger target read
    "fits the criteria well" and nothing else, and a loss-maker could read "not expensive for what it earns"."""
    facts = facts or {}
    market, strategy = card.get("market") or "US", card.get("strategy") or "SWING"
    view, short = STYLE.get(strategy, STYLE["SWING"])
    parts: List[Dict[str, Any]] = []
    used: List[str] = []
    state = card.get("actionability")
    if state == "INSUFFICIENT_DATA" or card.get("score") is None:
        parts.append({"h": "한 줄로", "lines": ["자료가 모자라서 프로그램이 이 종목을 판단하지 않았습니다. 점수가 있더라도 믿을 만하지 않습니다."]})
        parts.append({"h": "꼭 알아 둘 것", "lines": [CAVEAT]})
        return {"title": f"{view}에서 본 설명", "parts": parts, "words": []}
    score = float(card["score"])
    # one decimal: 69.83 read "70점" beside a band that starts at 70
    head = [f"{view}에서 100점 만점에 {score:.1f}점입니다. {BAND.get(card.get('band'), '')}".strip(),
            "점수는 주가 흐름, 회사의 살림과 벌이, 위험, 최근 공시를 정해진 규칙으로 따져 더한 값입니다."]
    if state == "BLOCKED":
        why = [GATE.get(g.get("code"), "") for g in card.get("gates") or []]
        head = [f"프로그램이 '지금은 다루지 않는다'고 막아 둔 종목입니다. 이유: {' '.join(w for w in why if w) or '확인이 필요한 문제가 있습니다.'}",
                f"참고로 점수는 100점 만점에 {score:.1f}점이지만, 막힌 종목의 점수는 사거나 팔 근거로 쓰지 않습니다."]
    if card.get("band_held_back") and card.get("conservative_score") is not None:
        head.append(f"일부 자료가 없어서, 없는 부분을 '보통'으로 치면 {float(card['conservative_score']):.1f}점쯤입니다. 그래서 더 낮은 구간으로 보여 줍니다.")
    if card.get("stale_fund_days"):
        head.append(f"회사 살림 자료를 새로 받지 못해 {float(card['stale_fund_days']):.0f}일 전에 받아 둔 자료로 계산했습니다. 그래서 이 점수를 믿는 정도를 낮게 봅니다.")
    deals = facts.get("deals") or []
    if deals:
        head.append("다만 이 회사는 다른 회사와 합치거나 팔리는 절차에 관한 서류를 냈습니다. 아래 '먼저 알아 둘 사건'을 보세요.")
    parts.append({"h": "한 줄로", "lines": head})
    if deals:
        used.append("공시")
        parts.append({"h": "먼저 알아 둘 사건", "lines": [
            f"{deals[0].get('date')}에 합병이나 공개 매수(회사를 통째로 사겠다는 제안)에 관한 공시가 있었습니다({deals[0].get('label') or deals[0].get('form')}).",
            "이런 회사의 주가는 사겠다고 한 값 가까이에 묶여 잘 움직이지 않는 일이 많습니다. 그러면 점수가 높아도 더 오를 자리가 거의 없고, 거래가 깨지면 크게 떨어질 수 있습니다. "
            "점수는 이 사정을 따지지 않습니다."]})
    good, bad, unsaid = _sides(card, facts=facts)
    if card.get("entry_status") == "OVERVALUED_AT_CURRENT_PRICE" and not any(s in bad for s in (FACTOR["valuation"][1], LOSS_WORRY)):
        bad = [LOSS_WORRY if facts.get("loss") else FACTOR["valuation"][1]] + bad[:2]      # the entry rule says so: the worries must too
    parts.append({"h": "좋게 본 점", "lines": good or ["뚜렷하게 좋게 본 점이 없습니다."]})
    parts.append({"h": "걱정되는 점", "lines": bad or ["뚜렷하게 걱정되는 점이 없습니다."]})
    if unsaid:
        parts.append({"h": "말하지 않은 것", "lines": [
            f"{'자료가 일부만 있거나, 금융 회사라 빚의 뜻이 다른' if facts.get('financial') else '자료가 일부만 있는'} 항목 {unsaid}개는 좋다 나쁘다를 여기서 말하지 않았습니다. 점수에는 있는 자료만으로 들어가 있습니다."]})
    if any("실적 발표" in s for s in good + bad):
        used.append("실적 발표")
    if any("공시" in s for s in good + bad):
        used.append("공시")
    if state != "BLOCKED":
        status = card.get("entry_status")
        now = ENTRY_NOW.get(strategy) if status == "ENTRY_NOW" else ENTRY.get(status) or "지금 살 조건인지는 이 프로그램의 규칙으로 정해지지 않았습니다."
        if status == "NO_VALID_ENTRY_SETUP" and "자료가 없어" in str((card.get("entry") or {}).get("reason") or ""):
            now = NO_VALUE
        if status == "WAIT_FOR_EARNINGS":
            used.append("실적 발표")
        lines = [now]
        if card.get("earnings_unknown"):
            lines.append("실적 발표 날짜를 받지 못했습니다. 발표가 코앞인지를 이 프로그램이 오늘은 확인하지 못했습니다.")
            used.append("실적 발표")
        ms = card.get("market_state") or {}
        if ms.get("state") in MARKET:
            cut = ms.get("size_factor")
            lines.append(MARKET[ms["state"]] + (f" 이런 날에는 새로 사는 크기를 {cut * 100:.0f}%로 줄이는 것이 이 프로그램의 규칙입니다." if cut is not None and cut < 1
                                                else " 이 시장에는 그런 날 크기를 줄이는 규칙이 없습니다. 참고로만 보세요."))
        parts.append({"h": "지금 사도 되나", "lines": lines})
    lv, price = card.get("levels") or {}, card.get("price")
    if strategy == "SWING" and price and lv.get("stop") and lv.get("target") and state != "BLOCKED":
        down, up = (1 - lv["stop"] / price) * 100, (lv["target"] / price - 1) * 100
        parts.append({"h": f"{short} 산다면 미리 정해 둘 가격", "lines": [
            f"계산에 쓴 가격은 {card.get('data_date') or '기준일'} 장을 마칠 때의 값 {money(price, market)}입니다. 지금 가격은 이와 다를 수 있습니다.",
            f"손절 가격은 {money(lv['stop'], market)}입니다(그 값보다 약 {_pct(down)}% 아래). 여기까지 내려가면 손해를 더 키우지 않으려고 파는 선입니다.",
            f"목표 가격은 {money(lv['target'], market)}입니다(그 값보다 약 {_pct(up)}% {'위' if up >= 0 else '아래'}). 거기까지 오른다는 약속이 아니라, 규칙이 잡은 기준입니다."]})
        used += ["손절 가격", "목표 가격"]
    parts.append({"h": "꼭 알아 둘 것", "lines": [CAVEAT]})
    return {"title": f"{view}에서 본 설명", "parts": parts, "words": [{"word": w, "means": WORDS[w]} for w in dict.fromkeys(used)]}


PORTFOLIO = {"BUFFETT": "좋은 회사를 골라 오래 들고 가는 방식입니다.", "MUNGER": "아주 좋은 회사 몇 개에만 크게 담는 방식입니다.",
             "GRAHAM": "싸고 튼튼한 회사를 여러 개에 조금씩 나눠 담는 방식입니다.", "LYNCH": "잘 자라는데 값이 지나치지 않은 회사를 여러 종류로 담는 방식입니다.",
             "DRUCKENMILLER": "시장 분위기, 회사의 이익, 주가 흐름이 모두 좋을 때만 크게 담고, 아니면 현금으로 두는 방식입니다.",
             "COMMITTEE": "아래 다섯 가지 방식의 판단을 모아 하나로 만든 바구니입니다."}
PORTFOLIO_CAVEAT = ("이 바구니는 종이 위의 계산입니다. 이름에 붙은 투자자의 실제 의견이 아니라 그 사람의 방식을 본뜬 규칙으로 만들었습니다. "
                    "이대로 샀을 때 돈을 벌었는지는 확인된 적이 없고, 사라는 권유가 아닙니다.")


def _subject(word: str) -> str:
    """The word with the subject particle Korean grammar asks for ('금융이', '헬스케어가')."""
    last = word[-1:] if word else ""
    if not ("가" <= last <= "힣"):
        return f"{word}이(가)"
    return f"{word}{'이' if (ord(last) - 0xAC00) % 28 else '가'}"


def _won(share: float) -> str:
    """A share of an imagined one million won, so a percentage becomes an amount."""
    return f"{round(share * 100):,}만 원"


def portfolio_plain(p: Dict[str, Any]) -> Dict[str, Any]:
    """One of the six portfolios in everyday words.  Amounts are of an imagined one million won, never of the user's account."""
    rows = p.get("holdings") or []
    parts: List[Dict[str, Any]] = [{"h": "이 바구니는", "lines": [PORTFOLIO.get(p.get("key"), "정해진 규칙으로 종목을 골라 담은 바구니입니다."),
                                                         "'바구니'는 여러 종목을 정해진 몫대로 나눠 담은 묶음을 말합니다."]}]
    invested, cash = float(p.get("invested") or 0.0), float(p.get("cash") or 0.0)
    if not rows:
        parts.append({"h": "지금 담긴 것", "lines": ["지금은 이 방식의 조건에 맞는 종목이 없어서 전부 현금입니다. 억지로 채우지 않는 것이 이 바구니의 규칙입니다."]})
    else:
        top = ", ".join(f"{r.get('name') or r['ticker']} {r['weight'] * 100:.0f}%({_won(r['weight'])})" for r in rows[:3])
        parts.append({"h": "지금 담긴 것", "lines": [
            f"종목 {len(rows)}개에 돈의 {invested * 100:.0f}%를 넣고, {cash * 100:.0f}%는 현금으로 둡니다. 100만 원이라면 주식에 {_won(invested)}, 현금으로 {_won(cash)}입니다.",
            f"가장 많이 담은 종목: {top}. 괄호 안은 100만 원 가운데 그 종목에 들어가는 돈입니다."]})
        kinds = list((p.get("sectors") or {}).items())
        if kinds:
            name, share = kinds[0]
            line = f"업종으로 보면 {_subject(name)} {share * 100:.0f}%로 가장 많습니다."
            if share >= 0.3:
                line += " 한 업종이 많으면 그 업종이 나쁠 때 함께 떨어집니다."
            parts.append({"h": "한쪽으로 쏠렸나", "lines": [line]})
    if cash >= 0.3 and rows:
        parts.append({"h": "현금이 많은 이유", "lines": ["이 방식의 규칙에 따라 다 채우지 않았습니다. 조건에 맞는 종목이 적거나, 한 종목과 한 업종에 담을 수 있는 한도에 걸렸거나, 시장이 나쁠 때 현금을 늘리는 규칙 때문입니다. "
                                                         "정확한 이유는 이 화면의 '현금' 줄에 적혀 있습니다. 현금으로 두는 것도 이 바구니의 선택입니다."]})
    notes = [f"{n.get('name') or n['ticker']}의 값이 많이 올라 이 바구니의 {n['weight'] * 100:.0f}%를 차지합니다. 한 종목에 담기로 한 몫({n['cap'] * 100:.0f}%)보다 훨씬 큽니다. "
             f"이 바구니의 규칙은 {n['cap'] * 100:.0f}%로 줄이고 나머지를 현금으로 두는 것입니다. 여기서는 알리기만 하고 그대로 둡니다." for n in p.get("overweight") or []]
    notes += [f"{n.get('name') or n['ticker']}에 큰 문제가 드러나 이 바구니에서 전부 뺐습니다. 뺀 몫은 현금으로 둡니다. 이유: {n['why']}." for n in p.get("fatal") or []]
    if notes:
        parts.append({"h": "오늘의 알림", "lines": notes})
    if p.get("exits"):
        parts.append({"h": "빠진 종목", "lines": [f"어제까지 있다가 오늘 빠진 종목이 {len(p['exits'])}개 있습니다. 그 방식의 조건에서 벗어났기 때문입니다."]})
    parts.append({"h": "꼭 알아 둘 것", "lines": [PORTFOLIO_CAVEAT]})
    return {"title": f"{str(p.get('name') or '포트폴리오').replace(' 포트폴리오', '')} 바구니를 쉽게", "parts": parts, "words": [{"word": "현금 비중", "means": WORDS["현금 비중"]}]}


COMMITTEE_WORD = {"STRONG_BUY": "사는 쪽으로 뚜렷하게 기울었습니다", "BUY": "사는 쪽입니다", "CONDITIONAL_BUY": "조건이 맞으면 사는 쪽입니다", "HOLD": "갖고 있다면 그대로 두는 쪽입니다",
                  "WAIT": "아직 사지 않고 기다리는 쪽입니다", "REDUCE": "갖고 있다면 줄이는 쪽입니다", "SELL": "갖고 있다면 파는 쪽입니다", "AVOID": "사지 않고 피하는 쪽입니다",
                  "INSUFFICIENT_DATA": "자료가 모자라 정하지 않았습니다"}
COMMITTEE_CAVEAT = ("이 결론은 점수와 따로 계산한 참고 자료입니다. 이름에 붙은 투자자의 실제 의견이 아니라 그 사람의 방식을 본뜬 규칙의 결과입니다. "
                    "이대로 했을 때 돈을 벌었는지는 확인된 적이 없고, 사라는 권유가 아닙니다.")


def committee_plain(c: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """The five views' decision on one stock in everyday words (user choice 2026-11-23).  Restates counts and names the
    decision already has; names of risks are quoted as they stand."""
    if not c or not c.get("decision"):
        return None
    buyers, against, waiting = c.get("buyers") or [], c.get("against") or [], c.get("waiting") or []
    parts: List[Dict[str, Any]] = [{"h": "이게 뭔가요", "lines": ["이름난 투자자 다섯 명의 방식을 본뜬 규칙 다섯 개가 이 종목을 각자 따져 본 결과를 하나로 모은 것입니다."]}]
    rest = int(c.get("valid") or 0) - len(buyers) - len(against) - len(waiting)
    head = [f"다섯 가운데 {c.get('valid', 0)}개가 판단했습니다. 사는 쪽 {len(buyers)}개, 피하거나 파는 쪽 {len(against)}개, 조건을 기다리는 쪽 {len(waiting)}개"
            + (f", 그대로 두는 쪽 {rest}개" if rest > 0 else "") + "입니다.",
            f"모아서 낸 결론: {COMMITTEE_WORD.get(c['decision'], c.get('decision_ko') or '')}."]
    parts.append({"h": "결론", "lines": head})
    risks = c.get("material_risks") or []
    big = [r["name"] for r in risks if r.get("level") == "CRITICAL"]
    other = [r["name"] for r in risks if r.get("level") != "CRITICAL"]
    lines = []
    if big:
        lines.append(f"아주 큰 문제가 발견되었습니다: {', '.join(big)}. 이런 문제가 하나라도 있으면 찬성이 몇 개든 피하는 쪽으로 정합니다.")
    if other:
        lines.append(f"적어 둔 걱정: {', '.join(other[:4])}.")
    if lines:
        parts.append({"h": "걱정되는 점", "lines": lines})
    if buyers and against:
        parts.append({"h": "의견이 갈린 곳", "lines": [f"사는 쪽({', '.join(buyers)})과 피하는 쪽({', '.join(against)})이 갈렸습니다. 따지는 방식이 다르면 같은 회사를 다르게 봅니다. "
                                                 "어느 쪽이 맞는지는 이 프로그램이 알지 못합니다."]})
    unseen = c.get("unchecked_risks") or []
    if unseen:
        parts.append({"h": "살펴보지 못한 것", "lines": [f"자료가 없어 살펴보지 못한 위험 검사가 {len(unseen)}개 있습니다. 살펴보지 못한 것이지, 문제가 없다는 뜻이 아닙니다."]})
    parts.append({"h": "꼭 알아 둘 것", "lines": [COMMITTEE_CAVEAT]})
    return {"title": "다섯 관점의 판정을 쉽게", "parts": parts, "words": []}


def texts(doc: Dict[str, Any]) -> List[str]:
    """Every sentence of a plain explanation, for the test that keeps the avoided words out."""
    return [doc.get("title") or ""] + [s for part in doc.get("parts") or [] for s in [part.get("h") or ""] + list(part.get("lines") or [])] + [w["means"] for w in doc.get("words") or []]
