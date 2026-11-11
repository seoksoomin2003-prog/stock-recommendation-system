"""What the stored historical checks said about the live score, for the screen.  Read only: it reads report files already written
and computes no return.  Nothing here is new evidence; it puts the numbers of the one-run reports next to the score."""
import json
import math
from pathlib import Path
from typing import Any, Dict, Optional

# market -> report file, table key per strategy, and what kind of check it was
SOURCES = {
    "KR": {"file": "reports/qsf/QSF_KR_LIVE_REPLAY.json", "tables": {"SWING": "SWING|20", "LONG_TERM": "LONG_TERM|252"}, "results": "reports/QSF_KR_LIVE_REPLAY_RESULTS.md",
           "what": "라이브 점수 과거 재현 (거래대금 상위 300, 상장폐지 종목 포함, 구간마다 한 번 실행)",
           # a second window of the same score, checked once afterwards: its row stands next to the first, it does not replace it
           "more": [{"file": "reports/qsf/QSF_KR_LONG_EARLY.json", "strategy": "LONG_TERM", "results": "reports/QSF_KR_LONG_EARLY_RESULTS.md"}],
           # the replay scored the swing composition that still counted the technical domain; the live score dropped it on 2026-11-11
           "superseded": ("SWING",)},
    "US": {"file": "reports/qsf/QSF_CORRECTED_OPEN.json", "tables": {"SWING": "SWING|A|20", "LONG_TERM": "LONG_TERM|A|252"}, "results": "reports/QSF_CORRECTED_RECHECK_RESULTS.md",
           "what": "S&P 500 과거 검증 (라이브 방식 점수, 인수·파산 종목 일부 누락)"},
}
READINGS = {"WEAK_POSITIVE_EVIDENCE": "근거 있음(약함)", "RANK_ONLY": "순위만 설명", "NO_EVIDENCE": "근거 부족", "NOT_CONFIRMED": "확인 안 됨(같은 방향, 더 약함)"}
CAVEATS = {"KR": ["과거 구간의 결과입니다. 앞으로도 같다는 뜻이 아닙니다.", "시장 국면·공시 영역과 배당은 빠져 있습니다.",
                  "스캔 대상(거래대금 상위 300) 자체가 이 기간에 시장보다 부진했습니다.",
                  "스윙 줄은 차트 항목이 점수에 들어가던 이전 구성의 성적입니다. 2026-11-11부터의 스윙 점수(차트 항목 제외)는 과거 구간에서 시험한 적이 없고 앞으로의 기록으로만 확인합니다."],
           "US": ["과거 한 구간의 결과입니다. 앞으로도 같다는 뜻이 아닙니다.", "2017년 이후 지수에서 빠진 종목 일부가 없어 수익이 실제보다 좋게 보일 수 있습니다."]}


def pair_win(ic: Optional[float]) -> Optional[float]:
    """Chance that the higher-scored of two random stocks did better, from the rank correlation (0.5 + IC / pi)."""
    return None if ic is None else 0.5 + ic / math.pi


def _row(strategy: str, t: Dict[str, Any], primary: Dict[str, Any], money: Dict[str, Any]) -> Dict[str, Any]:
    reading = primary.get("reading") or (primary.get("condition_a") or {}).get("verdict") or ("NO_EVIDENCE" if t.get("t") is None or t["t"] < 2.24 else None)
    return {"strategy": strategy, "horizon": int(str(primary.get("horizon") or 0)) or None, "dates": t.get("dates"), "first": t.get("first"), "last": t.get("last"),
            "ic": t.get("ic"), "t": t.get("t"), "pair_win": pair_win(t.get("ic")), "top_fifth_excess": t.get("top_fifth_excess"), "bottom_fifth_excess": t.get("bottom_fifth_excess"),
            "buy_excess": t.get("buy_excess"), "buy_trades": t.get("buy_trades"), "universe_return": t.get("average_return"), "market_return": t.get("market_return"),
            "reading": reading, "reading_label": READINGS.get(reading, "근거 부족"), "beats_market": money.get("passed") if money else None}


def summary(base: Path, market: str) -> Dict[str, Any]:
    src = SOURCES.get(market)
    if not src:
        return {"status": "UNAVAILABLE", "market": market}
    try:
        doc = json.loads((Path(base) / src["file"]).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"status": "UNAVAILABLE", "market": market}
    rows = []
    for strategy, key in src["tables"].items():
        t = (doc.get("tables") or {}).get(key)
        if not t:
            continue
        primary = dict((doc.get("primary") or {}).get(strategy) or {}) if market == "KR" else {}
        primary.setdefault("horizon", key.rsplit("|", 1)[-1])
        row = _row(strategy, t, primary, (doc.get("money") or {}).get(strategy) or {})
        if strategy in src.get("superseded", ()):
            row["superseded"] = True
        rows.append(row)
    more = []
    for extra in src.get("more", ()):
        try:
            other = json.loads((Path(base) / extra["file"]).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        primary = other.get("primary") or {}
        if primary.get("strategy") != extra["strategy"] or primary.get("ic") is None:
            continue
        rows.append({**_row(extra["strategy"], primary, primary, (other.get("money") or {}).get(extra["strategy"]) or {}), "second_window": True})
        more.append(extra["results"])
    return {"status": "REAL" if rows else "UNAVAILABLE", "market": market, "what": src["what"], "source": src["results"], "more_sources": more, "rows": rows, "caveats": CAVEATS[market]}
