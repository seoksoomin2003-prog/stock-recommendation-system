"""The Korean swing challenger, written down every session apart from the live score.  Rules: reports/QSF_KR_SWING_CHALLENGER_PROTOCOL.md.

The challenger is the live Korean swing score without its technical domain: the same factors, values and weights the QSF ledger
already holds, with the technical weights at zero.  The ledger is only read.  A record is written once and chained by hash.  No
return is computed while the record grows, and the single evaluation is refused until twelve separate 20-session samples have ended.
"""
import gzip
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import numpy as np

from terminal.qsf import config, kr_forward as kf, validate
from terminal.qsf.ledger import Ledger

PROTOCOL = "reports/QSF_KR_SWING_CHALLENGER_PROTOCOL.md"
FOLDER = Path("research_data") / "kr_swing_challenger"
REPORT = Path("reports") / "qsf" / "QSF_KR_SWING_CHALLENGER.json"
FIRST = "2026-11-09"       # the first Korean ledger session of QSF-1.1.8
DROPPED = "TECHNICAL"
STRATEGY = "SWING"
MIN_ROWS = 200             # fewer than this is a partial day, not a day
HORIZON = 20
MIN_T = 2.0
MIN_SAMPLES = config.MIN_INDEPENDENT
COUNTED = ("REAL", "STALE")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def challenger_score(factors: List[Dict[str, Any]]) -> Optional[float]:
    """The live composite over every factor outside the dropped domain that has a value; None when none has."""
    rows = [f for f in factors if f.get("domain") != DROPPED and f.get("status") in COUNTED and f.get("contribution") is not None]
    weight = sum(float(f["weight"]) for f in rows)
    return 100 * sum(float(f["contribution"]) for f in rows) / weight if weight > 0 else None


def score_session(snaps: List[Dict[str, Any]], session: str) -> Dict[str, Any]:
    """A stock whose ledger date is not this session is left out.  A partial day raises, and is asked again at the next run."""
    fresh = sorted((s for s in snaps if s.get("strategy") == STRATEGY and s.get("data_date") == session and s.get("score") is not None), key=lambda s: s["ticker"])
    if len(fresh) < MIN_ROWS:
        raise ValueError("TOO_FEW_STOCKS")
    rows = []
    for s in fresh:
        c = challenger_score(s.get("factors") or [])
        rows.append({"ticker": s["ticker"], "score": None if c is None else round(c, 3), "live": round(float(s["score"]), 3), "entry_session": s.get("entry_session"), "actionability": s.get("actionability")})
    return {"session": session, "protocol": PROTOCOL, "dropped_domain": DROPPED, "model_versions": sorted({str(s.get("model_version")) for s in fresh}), "rows": rows}


def _session_snaps(led: Ledger, session: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for r in led._live_rows():
        if r["market"] == "KR" and r["session"] == session:
            out += led._load(r)
    return out


def record(base: Path, now: Callable[[], datetime] = _utcnow, first: str = FIRST) -> Dict[str, Any]:
    """OK: every Korean ledger session from ``first`` is written.  WAITING: a session in the ledger is still partial."""
    at = now()
    led = Ledger(Path(base))
    if led.verify()["status"] != "OK":
        return {"status": "FAILED", "reason": "LEDGER_BROKEN"}
    sessions = sorted({r["session"] for r in led._live_rows() if r["market"] == "KR" and r["session"] >= first})
    done = {r["session"] for r in kf.read_index(base, FOLDER)}
    wrote: List[str] = []
    partial: List[str] = []
    for day in sessions:
        if day in done:
            continue
        try:
            late = day != sessions[-1]
            if kf.write_record(base, day, at, late, store=FOLDER, scorer=lambda b, d: score_session(_session_snaps(led, d), d)):
                wrote.append(day)
        except ValueError as exc:
            if str(exc) != "TOO_FEW_STOCKS":
                raise
            partial.append(day)
    return {"status": "WAITING" if partial else "OK", "written": wrote, "partial": partial, "last": max(done | set(wrote), default=None), "sessions_in_ledger": len(sessions)}


def status(base: Path) -> Dict[str, Any]:
    rows = kf.read_index(base, FOLDER)
    return {"records": len(rows), "first": rows[0]["session"] if rows else None, "last": rows[-1]["session"] if rows else None, "late": sum(1 for r in rows if r.get("late")),
            "samples_needed": MIN_SAMPLES, "horizon": HORIZON, "evaluated": (Path(base) / REPORT).exists()}


# ---------------------------------------------------------------------- the one evaluation
def _ic(score: np.ndarray, ret: np.ndarray) -> Optional[float]:
    ok = np.isfinite(score) & np.isfinite(ret)
    if ok.sum() < 30 or score[ok].std() == 0:
        return None
    ex = ret[ok] - ret[ok].mean()
    return float(np.corrcoef(validate.rank(score[ok]), validate.rank(ex))[0, 1]) if ex.std() > 0 else None


def _t(x: List[float]) -> Optional[float]:
    a = np.asarray(x, dtype=float)
    return float(a.mean() / (a.std(ddof=1) / math.sqrt(len(a)))) if len(a) > 2 and a.std(ddof=1) > 0 else None


def _fifths(score: np.ndarray, ret: np.ndarray) -> Optional[Dict[str, float]]:
    ok = np.isfinite(score) & np.isfinite(ret)
    if ok.sum() < 30:
        return None
    q = validate.rank(score[ok]) / (ok.sum() - 1)
    ex = ret[ok] - ret[ok].mean()
    return {"top": float(ex[q >= 0.8].mean()), "bottom": float(ex[q <= 0.2].mean())}


def measure_days(docs: List[Dict[str, Any]], px: Any, h: int = HORIZON) -> List[Dict[str, Any]]:
    """One row per record whose 20-session hold has ended: both scores' rank correlation with the excess return."""
    out = []
    for doc in docs:
        entries = {r["entry_session"] for r in doc["rows"] if r.get("entry_session")}
        if len(entries) != 1 or next(iter(entries)) not in px.dates:
            continue
        i = px.dates.index(next(iter(entries))) - 1          # forward() enters at the open of day i + 1
        if i < 0 or i + h >= len(px.dates):
            continue
        fwd = px.forward(i, h, config.round_trip_cost("KR"))
        ret = np.array([fwd[px.col[r["ticker"]]] if r["ticker"] in px.col else np.nan for r in doc["rows"]], dtype=float)
        ch = np.array([np.nan if r["score"] is None else r["score"] for r in doc["rows"]], dtype=float)
        lv = np.array([np.nan if r["live"] is None else r["live"] for r in doc["rows"]], dtype=float)
        a, b = _ic(ch, ret), _ic(lv, ret)
        if a is None or b is None:
            continue
        out.append({"session": doc["session"], "entry": px.dates[i + 1], "ic_challenger": a, "ic_live": b, "fifths_challenger": _fifths(ch, ret), "fifths_live": _fifths(lv, ret), "late": bool(doc.get("late"))})
    return out


def verdict(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """``rows``: separate samples.  The protocol's rule: the challenger's own evidence, and whether it beats the live score."""
    ch, lv = [r["ic_challenger"] for r in rows], [r["ic_live"] for r in rows]
    diff = [a - b for a, b in zip(ch, lv)]
    own = {"mean": float(np.mean(ch)), "t": _t(ch)}
    gap = {"mean": float(np.mean(diff)), "t": _t(diff)}
    has = own["mean"] > 0 and own["t"] is not None and own["t"] >= MIN_T
    better = has and gap["mean"] > 0 and gap["t"] is not None and gap["t"] >= MIN_T
    return {"samples": len(rows), "challenger": own, "live": {"mean": float(np.mean(lv)), "t": _t(lv)}, "difference": gap,
            "verdict": "CHALLENGER_BETTER" if better else "CHALLENGER_HAS_EVIDENCE" if has else "NO_EVIDENCE"}


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
    days = measure_days(docs, panel)
    separate = days[::HORIZON]
    if len(separate) < MIN_SAMPLES:
        raise RuntimeError(f"끝난 표본이 {len(separate)}개입니다. {MIN_SAMPLES}개가 되기 전에는 평가하지 않습니다.")
    res = {"status": "REAL", "protocol": PROTOCOL, "horizon": HORIZON, "records": len(docs), "matured": len(days), **verdict(separate),
           "all_days": {"days": len(days), "ic_challenger": float(np.mean([d["ic_challenger"] for d in days])), "t_challenger": validate.newey_west_t([d["ic_challenger"] for d in days], HORIZON),
                        "ic_live": float(np.mean([d["ic_live"] for d in days])), "t_live": validate.newey_west_t([d["ic_live"] for d in days], HORIZON)},
           "fifths": {k: {x: float(np.mean([d[k][x] for d in separate if d[k]])) for x in ("top", "bottom")} for k in ("fifths_challenger", "fifths_live")},
           "late_share": float(np.mean([d["late"] for d in days])), "note": "NO_EVIDENCE는 '효과 없음'이 아니라 '아직 모름'입니다. 12개 표본의 검정력은 낮습니다."}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    return res
