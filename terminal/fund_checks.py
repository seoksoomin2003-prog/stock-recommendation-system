"""Which way a company's figures are moving, and what that does to a cheap or a good-looking score (FC-K, 2026-11-25).

The third maturity assessment's lowest research finding: the figures are computed correctly, but nothing tells an entrant what a
holder is told.  A held stock whose return on equity fell five points to under 8% reads "thesis invalidated" while the same
stock is an entry candidate (HMM: return on equity 13.6% to 7.1%, three-year sales down 16% a year, earnings per share down 61%,
buy band, "no worry" in the plain text).  The score is frozen (reports/QSF_FORMULA_FREEZE_2026_11_25.md) and the recorded tests
give no support for a new entry rule, so this is a reading aid: it says the facts, in the same words for an entrant and a
holder, and names the two patterns an investor checks first.  It changes no score, band, entry status or order.

Every line is a rule on the card's own figures with its numbers written out.  Thresholds are plain round values (a fall of five
points, a fifth, a half), the first one being the holding rule's own; none was fitted and none has been tested on returns.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

VERSION = "FC-K-1"
ROE_FALL, ROE_LOW = 0.05, 0.08                  # holding.evaluate_exit's PROFITABILITY_DOWN, said to an entrant too
EPS_FALL = -0.20
CASH_LOW = 0.5                                   # operating cash under half of profit
FCF_FEW = 0.34                                   # free cash flow positive in under about a third of the years (the holding rule's)
CHEAP, GOOD, POOR = 0.65, 0.65, 0.35             # the plain explanation's own lines for "good" and "worry"
NOTE = "재무 수치의 방향을 정해진 규칙으로 읽은 점검입니다. 점수와 판단을 바꾸지 않고, 이 규칙이 수익에 도움이 되는지는 시험하지 않았습니다."


def _pct(v: Optional[float], d: int = 1) -> str:
    return "자료 없음" if v is None else f"{v * 100:+.{d}f}%"


def _lvl(v: Optional[float]) -> str:
    return "자료 없음" if v is None else f"{v * 100:.1f}%"


def _factor(card: Dict[str, Any], fid: str) -> Optional[float]:
    return next((f.get("normalized") for f in card.get("factors") or [] if f.get("factor") == fid and f.get("status") != "MISSING"), None)


def read(fund: Optional[Dict[str, Any]], card: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """{"status", "direction", "direction_ko", "flags": [{"code", "side", "text"}], "pattern", "pattern_ko", "checked", "note"}.
    ``side``: "down" (worsening), "up" (improving), "risk" (a standing weakness).  ``checked``: how many of the direction checks had
    their figures; with fewer than two the direction is unknown, never "stable"."""
    f = fund or {}
    if f.get("status") not in ("REAL", "STALE"):
        return {"status": "UNAVAILABLE", "version": VERSION, "direction": "UNKNOWN", "direction_ko": "재무 자료가 없어 방향을 읽지 못했습니다", "flags": [], "pattern": None, "pattern_ko": None,
                "checked": 0, "note": NOTE}
    flags: List[Dict[str, str]] = []
    checked = 0

    def flag(code: str, side: str, text: str) -> None:
        flags.append({"code": code, "side": side, "text": text})

    roe, prev = f.get("roe"), f.get("roe_prev")
    if roe is not None and prev is not None:
        checked += 1
        if roe < prev - ROE_FALL and roe < ROE_LOW:
            flag("ROE_DOWN", "down", f"자기자본이익률(ROE)이 {_lvl(prev)}에서 {_lvl(roe)}로 내려갔습니다. 보유 종목이라면 이 프로그램이 '보유 논리가 깨짐'으로 읽는 조건입니다.")
        elif roe < prev - ROE_FALL:
            flag("ROE_LOWER", "down", f"자기자본이익률(ROE)이 {_lvl(prev)}에서 {_lvl(roe)}로 내려갔습니다.")
        elif roe > prev + ROE_FALL:
            flag("ROE_UP", "up", f"자기자본이익률(ROE)이 {_lvl(prev)}에서 {_lvl(roe)}로 올랐습니다.")
    rg, rc = f.get("rev_growth"), f.get("rev_cagr3")
    if rg is not None:
        checked += 1
        if rg < 0 and rc is not None and rc < 0:
            flag("SALES_DOWN", "down", f"매출이 줄고 있습니다: 최근 1년 {_pct(rg)}, 3년 연평균 {_pct(rc)}.")
        elif rg < 0:
            flag("SALES_DIP", "down", f"최근 1년 매출이 줄었습니다({_pct(rg)}). 3년 연평균은 {_pct(rc)}입니다.")
        elif rg > 0.10 and (rc is None or rc > 0):
            flag("SALES_UP", "up", f"매출이 늘고 있습니다: 최근 1년 {_pct(rg)}" + (f", 3년 연평균 {_pct(rc)}." if rc is not None else "."))
    eg = f.get("eps_growth")
    if eg is not None:
        checked += 1
        if eg <= EPS_FALL:
            flag("EPS_DOWN", "down", f"주당이익이 1년 사이 {_pct(eg, 0)} 줄었습니다.")
        elif eg >= -EPS_FALL:
            flag("EPS_UP", "up", f"주당이익이 1년 사이 {_pct(eg, 0)} 늘었습니다.")
    if not f.get("is_financial"):
        oc, fy, fm = f.get("ocf_to_ni"), f.get("fcf_years_positive"), f.get("fcf_margin")
        if oc is not None:
            checked += 1
            if oc < CASH_LOW:
                flag("CASH_BEHIND", "risk", f"영업으로 들어온 현금이 순이익의 {oc * 100:.0f}%뿐입니다. 장부의 이익만큼 현금이 들어오지 않았습니다.")
        if fm is not None and fm < 0:
            flag("FCF_NEGATIVE", "risk", f"설비투자를 빼면 남는 현금이 없습니다(잉여현금흐름이 매출의 {_pct(fm)}).")
        elif fy is not None and fy < FCF_FEW:
            flag("FCF_RARE", "risk", "최근 몇 해 가운데 잉여현금흐름이 남은 해가 3분의 1이 안 됩니다.")
    if f.get("loss_now"):
        flag("LOSS", "risk", "지금 적자입니다.")
    if f.get("cash_burn"):
        flag("CASH_BURN", "risk", "이익도 영업현금도 마이너스입니다(현금을 쓰고 있습니다).")
    down = [x for x in flags if x["side"] == "down"]
    up = [x for x in flags if x["side"] == "up"]
    if checked < 2:
        direction, ko = "UNKNOWN", "방향을 읽을 수치가 모자랍니다"
    elif len(down) >= 2 and not up:
        direction, ko = "DETERIORATING", "나빠지는 중"
    elif len(up) >= 2 and not down:
        direction, ko = "IMPROVING", "좋아지는 중"
    elif down and up:
        direction, ko = "MIXED", "엇갈림"
    elif down:
        direction, ko = "SOFTENING", "한 가지가 나빠짐"
    elif up:
        direction, ko = "FIRMING", "한 가지가 좋아짐"
    else:
        direction, ko = "STABLE", "큰 변화 없음"
    pattern, pko = _pattern(card or {}, direction, f)
    return {"status": "REAL", "version": VERSION, "direction": direction, "direction_ko": ko, "flags": flags, "pattern": pattern, "pattern_ko": pko, "checked": checked,
            "basis_note": _basis_note(card or {}), "note": NOTE}


def _pattern(card: Dict[str, Any], direction: str, f: Dict[str, Any]):
    """The two patterns read first, from the card's own valuation and quality factors and the direction above."""
    val, quality = _factor(card, "valuation"), _factor(card, "business_quality")
    if val is not None and val >= CHEAP and direction == "DETERIORATING" and not f.get("loss_now"):
        return "CHEAP_AND_WORSENING", "값은 싸게 읽히지만 재무가 나빠지는 중입니다. 싼 데 이유가 있는 경우(가치 함정)인지 먼저 확인할 자리입니다."
    if quality is not None and quality >= GOOD and val is not None and val <= POOR:
        return "GOOD_BUT_DEAR", "사업은 좋게 읽히지만 값이 비싸게 읽힙니다. 좋은 회사와 좋은 투자는 다를 수 있습니다."
    if val is not None and val >= CHEAP and direction in ("IMPROVING", "FIRMING"):
        return "CHEAP_AND_IMPROVING", "값이 싸게 읽히고 재무가 좋아지는 방향입니다."
    return None, None


def _basis_note(card: Dict[str, Any]) -> Optional[str]:
    """The direction above is read from annual statements.  When the same card's score on trailing four quarters differs by ten
    points or more, the newest quarters may point the other way, and the reader is told (re-check 2026-11-25: EOG read
    "worsening" beside a trailing score twelve points higher)."""
    fp = card.get("fund_period") or {}
    a, t = (fp.get("annual") or {}).get("score"), (fp.get("trailing") or {}).get("score")
    if a is None or t is None or not (fp.get("trailing") or {}).get("newer_quarter") or abs(t - a) < 10.0:
        return None
    way = "높아" if t > a else "낮아"
    return f"이 방향은 연간 재무제표로 읽은 것입니다. 최근 4분기 재무로 계산한 점수는 {abs(t - a):.1f}점 {way}, 최근 분기는 다른 쪽으로 움직였을 수 있습니다."


def lines(doc: Optional[Dict[str, Any]], limit: int = 3) -> List[str]:
    """The worsening and weakness lines, the pattern first: for the plain explanation and beside the buy-check conclusion."""
    if not doc or doc.get("status") != "REAL":
        return []
    out = [doc["pattern_ko"]] if doc.get("pattern") in ("CHEAP_AND_WORSENING", "GOOD_BUT_DEAR") else []
    out += [x["text"] for x in doc["flags"] if x["side"] in ("down", "risk")]
    return out[:limit]
