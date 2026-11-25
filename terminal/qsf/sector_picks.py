"""The highest-scored stocks of the sector behind a sector fund, as the newest scan recorded them.  Read only.

Ranking follows the tracked top-3 rule (``top_picks``): a score on the scan session, not INSUFFICIENT_DATA, highest first.  Nothing
is rescored here.  US funds are the SPDR sector funds and match the Yahoo sector of each stock one to one.  Korean funds are KODEX
sector funds plus TIGER 조선TOP10 and TIGER 200 커뮤니케이션서비스 where no KODEX fund covers the sector: with a stored holdings
snapshot (``terminal.kr_etf_holdings``, KODEX funds only) their members are the fund's own holdings; without one, stocks are
matched by KRX industry (and, for holding companies filed under "기타 금융업", by name), which is an
approximation.  The rule used is returned so the screen can show it.
"""
import re
from typing import Any, Dict, Optional

TOP = 3

US_FUNDS = {"XLK": "Technology", "XLF": "Financial Services", "XLV": "Healthcare", "XLY": "Consumer Cyclical", "XLP": "Consumer Defensive",
            "XLI": "Industrials", "XLB": "Basic Materials", "XLE": "Energy", "XLU": "Utilities", "XLRE": "Real Estate", "XLC": "Communication Services"}

# code: (industries, holding-company names under "기타 금융업" that belong here)
KR_FUNDS = {
    "091160": (("반도체 제조업", "전자부품 제조업", "특수 목적용 기계 제조업"), None),
    "091170": (("은행 및 저축기관",), r"((?<!^한국)금융지주|^KB금융|^신한지주)$"),
    "102970": (("금융 지원 서비스업",), r"^한국금융지주$"),
    "091180": (("자동차용 엔진 및 자동차 제조업", "자동차 신품 부품 제조업"), None),
    "117460": (("기초 화학물질 제조업", "석유 정제품 제조업", "화학섬유 제조업", "일차전지 및 이차전지 제조업"), None),
    "117680": (("1차 철강 제조업", "1차 비철금속 제조업"), None),
    "117700": (("건물 건설업", "토목 건설업", "건축기술, 엔지니어링 및 관련 기술 서비스업"), None),
    "102960": (("일반 목적용 기계 제조업", "특수 목적용 기계 제조업"), None),       # KODEX 기계장비 (not shipbuilding)
    "266420": (("의약품 제조업", "기초 의약물질 제조업", "의료용품 및 기타 의약 관련제품 제조업", "의료용 기기 제조업"), None),
    "266390": (("종합 소매업", "무점포 소매업", "오디오물 출판 및 원판 녹음업"), None),
    "266410": (("기타 식품 제조업", "담배 제조업"), None),
    "140710": (("해상 운송업", "항공 여객 운송업", "육상 여객 운송업", "기타 운송관련 서비스업", "운송장비 임대업"), None),
    "305720": (("일차전지 및 이차전지 제조업",), r"^에코프로$"),                          # KODEX 2차전지산업
    "140700": (("보험업", "재 보험업"), None),                                            # KODEX 보험
    "494670": (("선박 및 보트 건조업",), r"^HD한국조선해양$"),                          # TIGER 조선TOP10
    "315270": (("전기 통신업", "자료처리, 호스팅, 포털 및 기타 인터넷 정보매개 서비스업", "소프트웨어 개발 및 공급업",
                "오디오물 출판 및 원판 녹음업", "텔레비전 방송업", "영화, 비디오물, 방송프로그램 제작 및 배급업", "광고업"), None),  # TIGER 200 커뮤니케이션서비스
}
HOLDCO_INDUSTRY = "기타 금융업"


def fund_code(fund: str) -> str:
    return (fund or "").strip().upper().split(".")[0]


def member(market: str, fund: str, row: Dict[str, Any], holdings: Optional[Dict[str, Any]] = None) -> bool:
    code = fund_code(fund)
    if holdings:
        return row.get("ticker") in set(holdings["codes"])
    if market == "US":
        return code in US_FUNDS and row.get("sector") == US_FUNDS[code]
    industry = row.get("industry")                 # the detailed KRX industry; ``sector`` is the broad group
    if code not in KR_FUNDS or not industry:
        return False
    industries, holdco = KR_FUNDS[code]
    if industry in industries:
        return True
    return bool(holdco and industry == HOLDCO_INDUSTRY and re.search(holdco, row.get("name") or ""))


def rule_text(market: str, fund: str) -> Optional[str]:
    code = fund_code(fund)
    if market == "US":
        return f"Yahoo 업종 '{US_FUNDS[code]}'" if code in US_FUNDS else None
    if code not in KR_FUNDS:
        return None
    industries, holdco = KR_FUNDS[code]
    return "거래소 업종 " + ", ".join(industries) + (" · 이 업종의 지주회사(기타 금융업)" if holdco else "") + \
        ". ETF 보유 목록이 아니라 업종으로 맞춘 근사치입니다."


def holdings_rule(h: Dict[str, Any], stale: bool) -> str:
    shown = f"공개된 상위 {h['shown']}종목" + (f"(전체 {h['total']}종목)" if h.get("total") and h["total"] > h["shown"] else "")
    return f"{h['fund']} 실제 보유 종목 {shown}, 운용사 기준일 {h.get('as_of') or '?'} · {h['retrieved_at'][:10]} 받음" + \
        (" · 오래된 목록이라 지금 구성과 다를 수 있습니다" if stale else "")


def picks(latest: Dict[str, Any], market: str, fund: str, holdings: Optional[Dict[str, Any]] = None, stale: bool = False) -> Dict[str, Any]:
    """``holdings``: the fund's stored holdings (``kr_etf_holdings.members``), Korean funds only; None uses the industry match."""
    if rule_text(market, fund) is None:
        raise ValueError("UNKNOWN_FUND")
    holdings = holdings if market == "KR" else None
    if latest.get("status") != "REAL":
        return {"status": latest.get("status") or "UNAVAILABLE", "reason": latest.get("reason"), "strategies": {}}
    session = latest.get("session")
    out: Dict[str, Any] = {}
    for strategy in ("SWING", "LONG_TERM"):
        mine = [r for r in latest.get("rows") or [] if r.get("strategy") == strategy and member(market, fund, r, holdings)]
        ranked = [r for r in mine if r.get("score") is not None and r.get("actionability") != "INSUFFICIENT_DATA" and r.get("data_date") == session]
        ranked.sort(key=lambda r: (-r["score"], r["ticker"]))
        out[strategy] = {"n": len(mine), "ranked": len(ranked), "top": [_pick(i + 1, r) for i, r in enumerate(ranked[:TOP])],
                         "buy_candidates": sum(1 for r in ranked if r.get("band") in ("STRONG_BUY_CANDIDATE", "BUY_CANDIDATE"))}      # the band of 80 is inside the band of 70 (it was left out until 2026-11-25)
    return {"status": "REAL", "market": market, "fund": fund_code(fund), "session": session, "model_version": latest.get("model_version"),
            "rule": holdings_rule(holdings, stale) if holdings else rule_text(market, fund), "basis_kind": "HOLDINGS" if holdings else "MATCH",
            "fund_holdings": len(holdings["codes"]) if holdings else None, "strategies": out,
            "basis": "최근 스캔의 업종 안 점수 순위입니다(상위 3종목 추적과 같은 규칙). 점수 순위는 검증된 수익 예측이 아니며 주문을 실행하지 않습니다."}


def _pick(rank: int, r: Dict[str, Any]) -> Dict[str, Any]:
    keep = ("ticker", "name", "score", "action", "action_label", "band", "band_label", "confidence", "entry_status", "gates", "price", "data_date", "sector", "industry")
    return {"rank": rank, **{k: r.get(k) for k in keep}, "high_risk": bool(r.get("high_risk")), "filing_events": r.get("filing_events")}
