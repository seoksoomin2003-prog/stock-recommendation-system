"""The newest day of the Korean market-value universe record, for the screen.  Read only.

It reads the write-once record of terminal/qsf/kr_cap_universe.py (rules: reports/QSF_KR_CAP_UNIVERSE_PROTOCOL.md) and shows the
scores that day's run wrote down.  It computes no return, writes nothing and never touches the live ranking: this is a second list
next to the live one, not a replacement for it.
"""
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from terminal.qsf import kr_forward as kf

FOLDER = Path("research_data") / "kr_cap_universe"
PROTOCOL = "reports/QSF_KR_CAP_UNIVERSE_PROTOCOL.md"
KEYS = {"SWING": ("swing", "swing_actionability"), "LONG_TERM": ("long", "long_actionability")}
# What the one past test said, in the words of its report (reports/QSF_KR_UNIVERSE_TEST_RESULTS.md).  Not new evidence.
NOTES = ["과거 한 번의 탐색 시험(2019~2026)에서 같은 비중으로 들었을 때 시가총액 상위 300은 연 +7.1%, 거래대금 상위 300(지금의 라이브 대상)은 연 −10.9%, 시장은 +13.0%였습니다.",
         "그 시험에서 시가총액 상위 300 안에서는 점수의 순위 힘이 약했습니다(스윙·장기 모두 기준 미달). 이 목록에서 점수가 높다는 것은 근거가 더 약합니다.",
         "대형주가 그 기간에 좋았다는 것을 안 뒤에 고른 대안입니다. 매일 따로 기록 중이고 약 1년 뒤 한 번 판정합니다. 그 전에는 수익을 계산하지 않습니다.",
         "라이브 순위, 상위 3종목, 알림은 이 목록을 쓰지 않습니다."]


def view(base: Path, strategy: str = "SWING", name_of: Optional[Callable[[str], Optional[str]]] = None, top: int = 30) -> Dict[str, Any]:
    key, act = KEYS.get(strategy, KEYS["SWING"])
    idx = kf.read_index(base, FOLDER)
    if not idx:
        return {"status": "UNAVAILABLE", "reason": "시가총액 대상 기록이 아직 없습니다."}
    try:
        doc = kf._read_day(Path(base) / FOLDER, idx[-1]["session"])
    except (OSError, ValueError):
        return {"status": "UNAVAILABLE", "reason": "시가총액 대상 기록을 읽지 못했습니다."}
    scored = sorted((r for r in doc["rows"] if r.get(key) is not None), key=lambda r: (-r[key], r["cap_rank"]))
    rows = [{"rank": n + 1, "ticker": r["ticker"], "name": name_of(r["ticker"]) if name_of else None, "cap_rank": r["cap_rank"], "score": r[key], "in_live": bool(r.get("in_live")),
             "actionability": r.get(act)} for n, r in enumerate(scored[:top])]
    in_live = sum(1 for r in doc["rows"] if r.get("in_live"))
    return {"status": "REAL", "strategy": strategy if strategy in KEYS else "SWING", "session": doc["session"], "entry_session": doc.get("entry_session"), "model_version": doc.get("model_version"),
            "recorded_at": doc.get("recorded_at"), "records": len(idx), "size": doc.get("size"), "scored": len(scored), "in_both": in_live, "cap_only": len(doc["rows"]) - in_live,
            "live_only": len(doc.get("live_only") or []), "buy_band": sum(1 for r in scored if r[key] >= 70), "rows": rows, "notes": NOTES, "protocol": PROTOCOL}
