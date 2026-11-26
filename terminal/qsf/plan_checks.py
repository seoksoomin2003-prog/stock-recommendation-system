"""Why a card the entry rule reads "진입 규칙 충족" is left out of the REAL order plan (PC-1, user decisions 2026-11-26).

The institutional assessment of 2026-11-26 found two places where the program answered one question two ways:

* The swing entry rule reads the score and the reward-to-risk ratio, never the trend, while the swing exit rule reads "a close
  under a falling 50-day line" as a broken thesis.  On the session of 2026-11-25, 18 of 20 Korean and 2 of 6 US swing cards the
  entry rule read as enterable already met that exit condition on the day of entry.
* The buy check ("사도 돼?") waits on a card whose figures the program itself reads as worsening or whose confidence is LOW
  (user decision 2026-11-25); the order plan took the same card as a candidate.

The user chose to keep the entry rule and every record as they are, and to (1) say it on the card and in the buy check and
(2) leave such cards out of the real order plan.  So this module is read by the card, the buy check and ``services.order_plan``
only.  It must NOT be read by the engine, the entry or exit rules, the paper book, the comparison books or any forward record:
those keep the rules they were registered with.  None of the three conditions has been tested on returns.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Tuple

VERSION = "PC-1"
ENTRY_READY = "ENTRY_NOW"
LABELS = {"SAME_DAY_EXIT": "같은 날 정리 조건에도 해당", "FIGURES_WORSENING": "재무 점검이 '나빠지는 중'", "LOW_CONFIDENCE": "신뢰도 낮음"}
NOTE = ("진입 규칙과 기록(가상 매매, 비교 장부)은 그대로이고, 내 계좌의 주문 계획에서만 뺍니다(2026-11-26 결정). "
        "이 조건들이 수익에 도움이 되는지는 시험하지 않았습니다.")


def _raw(snap: Dict[str, Any], factor: str) -> Dict[str, Any]:
    raw = next((f.get("raw") for f in snap.get("factors") or [] if f.get("factor") == factor), None)
    return raw if isinstance(raw, dict) else {}


def trend_broken(snap: Dict[str, Any]) -> Optional[str]:
    """The swing exit rule's own trend condition (holding.evaluate_exit, TREND_BREAKDOWN) read on the card's recorded numbers:
    the close under a 50-day line that is falling.  None for a long-term card or when a number is missing (missing is not a yes)."""
    if snap.get("strategy") != "SWING":
        return None
    raw, close = _raw(snap, "trend_structure"), snap.get("price")
    ma50, slope = raw.get("ma50"), raw.get("ma50_slope")
    if not close or not ma50 or slope is None or not (float(close) < float(ma50) and float(slope) < 0):
        return None
    return (f"가격이 하락 중인 50일선보다 {(1 - float(close) / float(ma50)) * 100:.1f}% 아래입니다. 스윙 보유 규칙은 이 상태를 '보유 논리가 깨짐'으로 읽으므로, "
            "지금 사면 산 날부터 정리 조건에 해당합니다. 진입 규칙은 점수와 손익비만 읽고 추세는 읽지 않습니다.")


def reasons(snap: Dict[str, Any]) -> List[Dict[str, str]]:
    """[{"code", "label", "text"}] for a card the entry rule reads as enterable; [] for any other card."""
    if snap.get("entry_status") != ENTRY_READY:
        return []
    out: List[Dict[str, str]] = []

    def add(code: str, text: str) -> None:
        out.append({"code": code, "label": LABELS[code], "text": text})

    broken = trend_broken(snap)
    if broken:
        add("SAME_DAY_EXIT", broken)
    from terminal import assistant                      # the buy check's own reading of the figures' check: one rule, two readers
    worse = assistant._falling(snap.get("fund_checks"))
    if worse:
        add("FIGURES_WORSENING", f"이 프로그램의 재무 점검이 '나빠지는 중'으로 읽었습니다: {worse}")
    if snap.get("confidence") == "LOW":
        add("LOW_CONFIDENCE", "이 점수를 믿는 정도가 '낮음'입니다. 계산에 쓸 자료가 일부 없거나 오래됐습니다.")
    return out


def split(cands: Iterable[Dict[str, Any]], snaps: Iterable[Dict[str, Any]], strategy_of: Dict[str, str]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """(the candidates the real plan keeps, what to show of the rest).  A candidate without its snapshot is kept."""
    by = {(s.get("ticker"), s.get("strategy")): s for s in snaps}
    kept, left, counts = [], [], {}
    for c in cands:
        why = reasons(by.get((c["ticker"], strategy_of[c["style"]])) or {})
        if not why:
            kept.append(c)
            continue
        left.append({"ticker": c["ticker"], "name": c.get("name"), "style": c["style"], "score": c.get("score"), "codes": [w["code"] for w in why], "labels": [w["label"] for w in why]})
        for w in why:
            counts[w["label"]] = counts.get(w["label"], 0) + 1
    note = (f"'진입 규칙 충족'인 후보 가운데 {len(left)}종목을 이 계획에서 뺐습니다. '사도 돼?'가 기다림으로 답하는 종목입니다. " + NOTE) if left else None
    return kept, {"version": VERSION, "left_out": len(left), "left_out_by": counts, "rows": left, "note": note}
