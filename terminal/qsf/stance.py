"""The user's stance per market: defensive, normal or aggressive (user decisions 2026-11-22).

It changes what the screen calls a candidate and how large the real account's planned orders are.  It never changes a
score, a band, a record, an entry rule, the paper book, the comparison books or the committee: the live score stays one
score, so the forward verdicts keep one sample.  NORMAL is exactly the program without this module.

The numbers of the presets are settings, not findings: none of them was chosen from returns and none is tested.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple

from terminal.qsf import config
from utils import durable

FILE = Path("data") / "qsf" / "stance.json"
LEVELS = ("DEFENSIVE", "NORMAL", "AGGRESSIVE")
LABELS = {"DEFENSIVE": "방어적", "NORMAL": "기본", "AGGRESSIVE": "공격적"}
VOLATILE_SHARE = 1 / 3          # defensive: the third of the day's stocks whose daily range is widest is left out
CONFIDENCE_ORDER = ("LOW", "MEDIUM", "HIGH")

# line: the score from which the screen calls an actionable stock this stance's candidate.
# size: multiplies the risk per trade and the weight limit of every new order of the real account's plan.
# exposure_cap: what all new orders of one plan may add up to, as a share of the account (None: no cap of this module's).
# plan_needs_line: the plan keeps only this stance's candidates (NORMAL and AGGRESSIVE keep the plan's own rule: entry status).
PRESETS: Dict[str, Dict[str, Any]] = {
    "DEFENSIVE": {"line": 75.0, "min_confidence": "MEDIUM", "drop_volatile": True, "size": 0.5, "exposure_cap": 0.5, "plan_needs_line": True},
    "NORMAL": {"line": config.BANDS[1][0], "min_confidence": None, "drop_volatile": False, "size": 1.0, "exposure_cap": None, "plan_needs_line": False},
    "AGGRESSIVE": {"line": config.BUY_BAND_EXIT, "min_confidence": None, "drop_volatile": False, "size": 1.5, "exposure_cap": None, "plan_needs_line": False},
}
REASONS = {"LINE": "점수가 이 성향의 선 아래", "CONFIDENCE": "자료가 적음(신뢰도 낮음)", "VOLATILE": "하루 움직임이 큰 쪽 3분의 1", "NOT_ACTIONABLE": "실행 가능 상태가 아님"}
NOTE = ("성향은 화면이 무엇을 후보로 부르는지와 실제 계좌 주문 계획의 크기만 바꿉니다. 점수, 구간, 기록, 진입 규칙, 모의 장부, 비교 장부, 투자위원회는 그대로입니다. "
        "아래 숫자는 설정값이고 수익으로 검증한 값이 아닙니다.")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def damaged(base: Path) -> bool:
    """The file is there and cannot be read: the stance in force is NORMAL, which is not what the user chose."""
    path = Path(base) / FILE
    if not path.exists():
        return False
    try:
        return not isinstance(json.loads(path.read_text(encoding="utf-8")), dict)
    except (OSError, ValueError):
        return True


def level(base: Path, market: str) -> str:
    """The stored stance of a market; NORMAL when nothing was chosen or the file cannot be read (``damaged`` says which)."""
    try:
        got = (json.loads((Path(base) / FILE).read_text(encoding="utf-8")).get(market) or {}).get("level")
    except (OSError, ValueError, AttributeError):
        got = None
    return got if got in LEVELS else "NORMAL"


def set_level(base: Path, market: str, new: str, now: Callable[[], datetime] = _utcnow) -> Dict[str, Any]:
    if market not in config.MARKETS:
        raise ValueError("INVALID_MARKET")
    if new not in LEVELS:
        raise ValueError("INVALID_STANCE")
    path = Path(base) / FILE
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        doc = doc if isinstance(doc, dict) else {}
    except (OSError, ValueError):
        doc = {}
    doc[market] = {"level": new, "at": now().isoformat()}
    path.parent.mkdir(parents=True, exist_ok=True)
    durable.write_text(path, json.dumps(doc, ensure_ascii=False, indent=1))
    return view(base, market)


def describe(name: str) -> List[str]:
    """What a preset does, in the order the screen lists it."""
    p = PRESETS[name]
    conf = "자료가 적은 종목(신뢰도 낮음)은 뺌" if p["min_confidence"] else "자료의 양으로 빼지 않음"
    wide = "하루 움직임이 큰 쪽 3분의 1은 뺌" if p["drop_volatile"] else "움직임의 크기로 빼지 않음"
    cap = f"새 주문 합계는 계좌의 {p['exposure_cap'] * 100:.0f}%까지" if p["exposure_cap"] else "새 주문 합계에 이 설정의 한도 없음"
    plan = "주문 계획은 이 성향의 후보만 담음" if p["plan_needs_line"] else "주문 계획은 지금과 같음: 진입 상태가 '지금'인 종목을 55점부터 담음(이 표의 점수 선과 무관)"
    return [f"후보로 부르는 점수: {p['line']:g}점 이상", conf, wide, f"주문 한 건의 위험 한도와 종목 비중 한도: {p['size']:g}배", cap, plan]


def view(base: Path, market: str) -> Dict[str, Any]:
    cur = level(base, market)
    return {"market": market, "level": cur, "label": LABELS[cur], "note": NOTE, "damaged": damaged(base),
            "damaged_note": "성향 파일(data/qsf/stance.json)을 읽을 수 없어 '기본'으로 계산하고 있습니다. 성향을 다시 골라 주세요." if damaged(base) else None,
            "adverse_note": "시장 상태가 나쁘거나 읽을 수 없는 날에는 공격적 성향의 1.5배를 쓰지 않습니다(그날의 0.5배 그대로). 방어적 성향의 0.5배는 그날에도 겹칩니다.",
            "levels": [{"level": k, "label": LABELS[k], "what": describe(k), **{f: PRESETS[k][f] for f in ("line", "size", "exposure_cap")}} for k in LEVELS]}


def _range_share(snap: Dict[str, Any]) -> Optional[float]:
    """A stock's usual daily range as a share of its price, from the record's own swing stop (price minus two ATR)."""
    price, stop = snap.get("price"), snap.get("stop")
    if not price or not stop or stop >= price:
        return None
    return (price - stop) / config.SWING["stop_atr"] / price


def volatile(snaps: Iterable[Dict[str, Any]]) -> Set[str]:
    """Tickers in the widest third of the session's stocks by daily range.  A stock without a reading is not in it."""
    width: Dict[str, float] = {}
    for s in snaps:
        if s.get("strategy") == "SWING":
            w = _range_share(s)
            if w is not None:
                width[s["ticker"]] = w
    if len(width) < 3:
        return set()
    ranked = sorted(width.items(), key=lambda kv: (-kv[1], kv[0]))
    return {t for t, _ in ranked[:int(len(ranked) * VOLATILE_SHARE)]}


def judge(snap: Dict[str, Any], name: str, wide: Set[str]) -> Optional[str]:
    """None when the snapshot is this stance's candidate, else the code of the first reason it is not.  The score read is the
    conservative one when the record has it: a line reached only because a factor has no data is not reached."""
    p = PRESETS[name]
    if snap.get("actionability") != "ACTIONABLE" or snap.get("score") is None:
        return "NOT_ACTIONABLE"
    seen = snap.get("conservative_score")
    if float(snap["score"] if seen is None else min(float(snap["score"]), float(seen))) < p["line"]:
        return "LINE"
    if p["min_confidence"] and CONFIDENCE_ORDER.index(snap.get("confidence") if snap.get("confidence") in CONFIDENCE_ORDER else "LOW") < CONFIDENCE_ORDER.index(p["min_confidence"]):
        return "CONFIDENCE"
    if p["drop_volatile"] and snap.get("ticker") in wide:
        return "VOLATILE"
    return None


def marks(snaps: List[Dict[str, Any]], name: str) -> Dict[Tuple[str, str], Optional[str]]:
    """{(ticker, strategy): None for a candidate of this stance, else the reason code}."""
    wide = volatile(snaps) if PRESETS[name]["drop_volatile"] else set()
    return {(s["ticker"], s["strategy"]): judge(s, name, wide) for s in snaps if s.get("ticker") and s.get("strategy")}


def for_plan(cands: List[Dict[str, Any]], state: Optional[Dict[str, Any]], got: Dict[Tuple[str, str], Optional[str]], name: str,
             strategy_of: Dict[str, str]) -> Tuple[List[Dict[str, Any]], Dict[str, Any], Dict[str, Any]]:
    """The plan's inputs under a stance: (candidates, the state the sizes are computed from, what to show).  NORMAL returns its
    inputs unchanged.  The market's own brake (adverse day) stays: the size factors multiply and the smaller cap holds."""
    p = PRESETS[name]
    kept = [c for c in cands if got.get((c["ticker"], strategy_of[c["style"]])) is None] if p["plan_needs_line"] else list(cands)
    out_reasons: Dict[str, int] = {}
    if p["plan_needs_line"]:
        for c in cands:
            why = got.get((c["ticker"], strategy_of[c["style"]]))
            if why:
                out_reasons[why] = out_reasons.get(why, 0) + 1
    base_factor = float((state or {}).get("size_factor") or 1.0)
    caps = [x for x in ((state or {}).get("new_exposure_cap"), p["exposure_cap"]) if x]
    # On a day the market's own brake is on, a stance never loosens it (user decision 2026-11-23): aggressive made 0.5 into 0.75.
    size = p["size"] if base_factor >= 1.0 or p["size"] <= 1.0 else 1.0
    used = {**(state or {}), "size_factor": base_factor * size, "new_exposure_cap": min(caps) if caps else None}
    shown = {"level": name, "label": LABELS[name], "size": p["size"], "exposure_cap": p["exposure_cap"], "line": p["line"] if p["plan_needs_line"] else None,
             "left_out": len(cands) - len(kept), "left_out_by": {REASONS[k]: v for k, v in out_reasons.items()}, "size_factor_total": base_factor * size,
             "size_used": size, "market_factor": base_factor,
             "note": None if name == "NORMAL" else f"{LABELS[name]} 성향: 주문 한 건의 위험 한도와 종목 비중 한도를 {size:g}배로 계산했습니다."
                     + (f" 시장 상태 때문에 이미 {base_factor:g}배인 날이라 합치면 {base_factor * size:g}배입니다." if base_factor < 1.0 else "")
                     + (" 시장 상태가 나쁘거나 읽을 수 없는 날에는 공격적 성향의 1.5배를 쓰지 않습니다." if size != p["size"] else "")
                     + (f" 새 주문 합계는 계좌의 {p['exposure_cap'] * 100:.0f}%까지입니다." if p["exposure_cap"] else "")
                     + (f" 이 성향의 후보가 아닌 {len(cands) - len(kept)}건은 계획에서 뺐습니다." if p["plan_needs_line"] else "") + " 설정값이고 검증된 값이 아닙니다."}
    return kept, used, shown
