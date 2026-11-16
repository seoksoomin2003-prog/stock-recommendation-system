"""The former live Korean universe, scored every session next to the live one.  Rules: reports/QSF_KR_TRADED_UNIVERSE_PROTOCOL.md.

On 2026-11-11 the live Korean scan moved from the 300 most traded stocks to the 300 largest by market value (QSF-1.3.0).  The former
universe is still chosen by its own rule and scored with the live code, by a scan that writes no live file.  A record is written
once and chained by hash.  No return is computed while the record grows, and the single evaluation is refused until 240 sessions
have matured.  The record has the shape of the market-value record, so the same day measure reads it.
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List

import numpy as np

from terminal.qsf import kr_cap_universe as cu, kr_forward as kf, live_forward as lf, validate
from terminal.qsf.ledger import Ledger
from utils import durable

PROTOCOL = "reports/QSF_KR_TRADED_UNIVERSE_PROTOCOL.md"
FOLDER = Path("research_data") / "kr_traded_universe"
REPORT = Path("reports") / "qsf" / "QSF_KR_TRADED_UNIVERSE.json"
FIRST = "2026-11-11"       # the first session the live scan records on the market-value universe
MIN_SCORED = cu.MIN_SCORED
HORIZON = cu.HORIZON
NEED = cu.NEED
MIN_T = cu.MIN_T


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def build_doc(session: str, codes: List[str], scan: Dict[str, Any], live: List[str], entry: str) -> Dict[str, Any]:
    """The market-value record's shape: ``rows`` are the former universe, ``in_live`` and ``live_only`` describe the live one."""
    mem = [{"code": c, "rank": n, "cap": None} for n, c in enumerate(codes, 1)]
    doc = cu.build_doc(session, mem, scan, live, entry)
    for r in doc["rows"]:
        r["traded_rank"] = r.pop("cap_rank")
        r.pop("cap", None)
    return {**doc, "protocol": PROTOCOL, "universe": "TRADED_VALUE"}


def record(base: Path, service: Any, now: Callable[[], datetime] = _utcnow) -> Dict[str, Any]:
    """OK: the session is written or was already.  WAITING: the live record is not there yet, the former universe could not be
    built, or too few stocks were scored on the session's price.  A session the market has moved past is never written afterwards."""
    base = Path(base)
    session = service.regime("KR").get("session")
    if not session or session < FIRST:
        return {"status": "OK", "written": [], "reason": "BEFORE_FIRST"}
    if session in {r["session"] for r in kf.read_index(base, FOLDER)}:
        return {"status": "OK", "written": [], "last": session}
    live = cu.live_tickers(Ledger(base), session)
    if len(live) < MIN_SCORED:
        return {"status": "WAITING", "reason": "LIVE_NOT_RECORDED", "session": session}
    try:
        codes = service.kr_former_universe_codes()
    except Exception as exc:
        return {"status": "WAITING", "reason": "UNIVERSE_NOT_BUILT", "kind": type(exc).__name__, "session": session}
    if len(codes) < MIN_SCORED:
        return {"status": "WAITING", "reason": "TOO_FEW_MEMBERS", "session": session}
    scan = service.scan("KR", tickers=codes, record=False, side_files=False)
    if scan.get("session") != session:
        return {"status": "WAITING", "reason": "SESSION_MOVED", "session": session}
    try:
        doc = build_doc(session, codes, scan, live, service._entry_date("KR", session).isoformat())
    except ValueError as exc:
        if str(exc) != "TOO_FEW_STOCKS":
            raise
        return {"status": "WAITING", "reason": "TOO_FEW_STOCKS", "session": session}
    wrote = kf.write_record(base, session, now(), False, store=FOLDER, scorer=lambda b, d: doc)
    return {"status": "OK", "written": [session] if wrote else [], "stocks": len(doc["rows"]), "overlap": sum(1 for r in doc["rows"] if r["in_live"])}


def status(base: Path) -> Dict[str, Any]:
    rows = kf.read_index(base, FOLDER)
    return {"records": len(rows), "first": rows[0]["session"] if rows else None, "last": rows[-1]["session"] if rows else None, "needed": NEED, "horizon": HORIZON,
            "evaluated": (Path(base) / REPORT).exists()}


# ---------------------------------------------------------------------- the one evaluation
def universe_reading(days: List[Dict[str, Any]], h: int = HORIZON) -> Dict[str, Any]:
    """The live (market-value) universe less the former (traded-value) universe, both at equal weight, day by day."""
    diff = [d["live_net"] - d["universe_net"] for d in days]
    mid = len(days) // 2
    early, late = float(np.mean(diff[:mid])), float(np.mean(diff[mid:]))
    t = validate.newey_west_t(diff, h)
    up, down = early > 0 and late > 0, early < 0 and late < 0
    word = "SWITCH_SUPPORTED" if up and t is not None and t >= MIN_T else "FORMER_BETTER" if down and t is not None and t <= -MIN_T else "SAME_DIRECTION_NOT_SIGNIFICANT" if up else "NOT_DISTINGUISHED"
    return {"mean": float(np.mean(diff)), "t": t, "early": early, "late": late, "reading": word}


def evaluate_once(base: Path, log=print, panel: Any = None) -> Dict[str, Any]:
    base = Path(base)
    out = base / REPORT
    if out.exists():
        raise RuntimeError("평가는 한 번만 실행합니다. 이미 결과가 있습니다.")
    if kf.verify(base, FOLDER)["status"] != "OK":
        raise RuntimeError("기록 파일 검증에 실패했습니다.")
    if panel is None:
        from terminal.qsf import research_kr_live
        panel = research_kr_live.ensure_panel(base, log)
    docs = [kf._read_day(base / FOLDER, r["session"]) for r in kf.read_index(base, FOLDER)]
    place = {d: n for n, d in enumerate(panel.dates)}
    ready = [d for d in docs if d.get("entry_session") in place and place[d["entry_session"]] - 1 + HORIZON < len(panel.dates)]
    if len(ready) < NEED:
        raise RuntimeError(f"만기 기록일이 {len(ready)}개입니다. {NEED}개가 되기 전에는 평가하지 않습니다.")
    used = ready[:NEED]
    swing = [d for d in (cu.measure_day(doc, panel) for doc in used) if d]
    long_ = [d for d in (cu.measure_day(doc, panel, key="long") for doc in used) if d]
    if len(swing) < NEED // 2:
        raise RuntimeError(f"수익을 계산할 수 있는 날이 {len(swing)}일뿐입니다.")
    s = lf.summarize(swing, HORIZON)
    res = {"status": "REAL", "protocol": PROTOCOL, "horizon": HORIZON, "records": len(docs), "sessions_used": len(used), "first": used[0]["session"], "last": used[-1]["session"],
           "universe": universe_reading(swing), "former_swing_reference": {**lf.reading(s), "summary": s},
           "former_long_reference": lf.summarize(long_, HORIZON) if len(long_) > 2 * HORIZON else None,
           "mean_overlap": float(np.mean([d["overlap"] for d in swing])), "note": "NOT_DISTINGUISHED는 '차이 없음'이 아니라 '아직 모름'입니다. " + lf.NOTE}
    out.parent.mkdir(parents=True, exist_ok=True)
    durable.write_text(out, json.dumps(res, ensure_ascii=False, indent=1))
    return res
