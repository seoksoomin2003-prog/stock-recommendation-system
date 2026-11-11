"""The newest day of the other Korean universe's record, for the screen.  Read only.

Since QSF-1.3.0 the live Korean scan covers the 300 largest companies by market value, and the 300 most traded stocks, the live
universe until then, are scored every day as a separate record (terminal/qsf/kr_traded_universe.py).  This shows that record's
newest day next to the live ranking.  It computes no return, writes nothing and never touches the live ranking.
"""
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from terminal.qsf import kr_forward as kf

FOLDER = Path("research_data") / "kr_traded_universe"
PROTOCOL = "reports/QSF_KR_TRADED_UNIVERSE_PROTOCOL.md"
KEYS = {"SWING": ("swing", "swing_actionability"), "LONG_TERM": ("long", "long_actionability")}
# What the past tests said, in the words of their reports.  Not new evidence.
NOTES = ["2026-11-10까지 라이브 순위가 쓰던 대상(20거래일 평균 거래대금 상위 300)입니다. 지금의 라이브 순위는 시가총액 상위 300을 씁니다.",
         "이 대상은 겹치지 않는 두 과거 구간(2016~2019, 2019~2026)에서 같은 비중으로 연 −11% 안팎이었고 시장보다 크게 부진했습니다. 거래가 몰린 중소형 테마주가 많습니다.",
         "이 대상 안에서는 장기 점수가 한 구간에서 순위를 설명했습니다. 점수가 낮은 종목을 피하는 데 참고할 수 있습니다.",
         "대상을 바꾼 결정이 옳았는지 보려고 매일 따로 기록 중이고 약 1년 뒤 한 번 판정합니다. 그 전에는 수익을 계산하지 않습니다. 라이브 순위, 상위 3종목, 알림은 이 목록을 쓰지 않습니다."]


def view(base: Path, strategy: str = "SWING", name_of: Optional[Callable[[str], Optional[str]]] = None, top: int = 30) -> Dict[str, Any]:
    key, act = KEYS.get(strategy, KEYS["SWING"])
    idx = kf.read_index(base, FOLDER)
    if not idx:
        return {"status": "UNAVAILABLE", "reason": "이전 대상 기록이 아직 없습니다."}
    try:
        doc = kf._read_day(Path(base) / FOLDER, idx[-1]["session"])
    except (OSError, ValueError):
        return {"status": "UNAVAILABLE", "reason": "이전 대상 기록을 읽지 못했습니다."}
    scored = sorted((r for r in doc["rows"] if r.get(key) is not None), key=lambda r: (-r[key], r["traded_rank"]))
    rows = [{"rank": n + 1, "ticker": r["ticker"], "name": name_of(r["ticker"]) if name_of else None, "traded_rank": r["traded_rank"], "score": r[key], "in_live": bool(r.get("in_live")),
             "actionability": r.get(act)} for n, r in enumerate(scored[:top])]
    in_live = sum(1 for r in doc["rows"] if r.get("in_live"))
    return {"status": "REAL", "strategy": strategy if strategy in KEYS else "SWING", "session": doc["session"], "entry_session": doc.get("entry_session"), "model_version": doc.get("model_version"),
            "recorded_at": doc.get("recorded_at"), "records": len(idx), "size": doc.get("size"), "scored": len(scored), "in_both": in_live, "former_only": len(doc["rows"]) - in_live,
            "live_only": len(doc.get("live_only") or []), "buy_band": sum(1 for r in scored if r[key] >= 70), "rows": rows, "notes": NOTES, "protocol": PROTOCOL}
