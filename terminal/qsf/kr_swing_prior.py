"""The former Korean swing formula, written down every session next to the live score.  Rules: reports/QSF_KR_SWING_PRIOR_PROTOCOL.md.

On 2026-11-11 the technical domain left the live Korean swing score (QSF-1.2.0).  Its factors are still computed and stored in the
ledger as reference rows, so the former composite can be worked out from the ledger alone.  The ledger is only read.  A record is
written once and chained by hash.  No return is computed while the record grows, and the single evaluation is refused until twelve
separate 20-session samples have ended.
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List

from terminal.qsf import calibrate
import numpy as np

from terminal.qsf import config, engine, kr_forward as kf, validate
from terminal.qsf.kr_swing_challenger import _fifths, _ic, _t
from terminal.qsf.ledger import Ledger
from utils import durable

PROTOCOL = "reports/QSF_KR_SWING_PRIOR_PROTOCOL.md"
FOLDER = Path("research_data") / "kr_swing_prior"
REPORT = Path("reports") / "qsf" / "QSF_KR_SWING_PRIOR.json"
FIRST = "2026-11-11"       # the earliest Korean session QSF-1.2.0 can have recorded
STRATEGY = "SWING"
MIN_ROWS = 200             # fewer than this is a partial day, not a day
HORIZON = 20
MIN_T = 2.0
MIN_SAMPLES = config.MIN_INDEPENDENT
WATCH_SCORE = 55.0         # the entry reading looks at stocks the screen would at least watch
MIN_GROUP = 10
READY = "ENTRY_NOW"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def has_reference(snap: Dict[str, Any]) -> bool:
    return any(f.get("scored") is False for f in snap.get("factors") or [])


def score_session(snaps: List[Dict[str, Any]], session: str) -> Dict[str, Any]:
    """FORMER_COMPOSITION: the session was recorded while the technical domain still counted, and is never written here."""
    fresh = sorted((s for s in snaps if s.get("strategy") == STRATEGY and s.get("data_date") == session and s.get("score") is not None), key=lambda s: s["ticker"])
    if fresh and not any(has_reference(s) for s in fresh):
        raise ValueError("FORMER_COMPOSITION")
    fresh = [s for s in fresh if has_reference(s)]
    if len(fresh) < MIN_ROWS:
        raise ValueError("TOO_FEW_STOCKS")
    rows = []
    for s in fresh:
        p = engine.prior_formula_score(s.get("factors") or [])
        rows.append({"ticker": s["ticker"], "prior": None if p is None else round(p, 3), "live": round(float(s["score"]), 3), "entry_session": s.get("entry_session"),
                     "entry_status": s.get("entry_status"), "actionability": s.get("actionability")})
    return {"session": session, "protocol": PROTOCOL, "model_versions": sorted({str(s.get("model_version")) for s in fresh}), "rows": rows}


def _session_snaps(led: Ledger, session: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for r in led._live_rows():
        if r["market"] == "KR" and r["session"] == session:
            out += led._load(r)
    return out


def record(base: Path, now: Callable[[], datetime] = _utcnow, first: str = FIRST) -> Dict[str, Any]:
    """OK: every Korean ledger session of the new composition is written.  WAITING: a session in the ledger is still partial."""
    at = now()
    led = Ledger(Path(base))
    if led.verify()["status"] != "OK":
        return {"status": "FAILED", "reason": "LEDGER_BROKEN"}
    sessions = sorted({r["session"] for r in led._live_rows() if r["market"] == "KR" and r["session"] >= first})
    done = {r["session"] for r in kf.read_index(base, FOLDER)}
    wrote: List[str] = []
    partial: List[str] = []
    former: List[str] = []
    for day in sessions:
        if day in done:
            continue
        try:
            late = day != sessions[-1]
            if kf.write_record(base, day, at, late, store=FOLDER, scorer=lambda b, d: score_session(_session_snaps(led, d), d)):
                wrote.append(day)
        except ValueError as exc:
            if str(exc) == "FORMER_COMPOSITION":
                former.append(day)
            elif str(exc) == "TOO_FEW_STOCKS":
                partial.append(day)
            else:
                raise
    return {"status": "WAITING" if partial else "OK", "written": wrote, "partial": partial, "former_composition": former, "last": max(done | set(wrote), default=None)}


def status(base: Path) -> Dict[str, Any]:
    rows = kf.read_index(base, FOLDER)
    return {"records": len(rows), "first": rows[0]["session"] if rows else None, "last": rows[-1]["session"] if rows else None, "late": sum(1 for r in rows if r.get("late")),
            "samples_needed": MIN_SAMPLES, "horizon": HORIZON, "evaluated": (Path(base) / REPORT).exists()}


# ---------------------------------------------------------------------- the one evaluation
def _entry_gap(rows: List[Dict[str, Any]], ret: np.ndarray):
    """Mean excess return of the stocks the entry assessment called ready, minus the other watched stocks; None when a side is thin."""
    ok = np.isfinite(ret)
    if ok.sum() < 30:
        return None
    ex = ret - ret[ok].mean()
    watched = np.array([r["live"] is not None and r["live"] >= WATCH_SCORE for r in rows]) & ok
    ready = np.array([r.get("entry_status") == READY for r in rows]) & watched
    rest = watched & ~ready
    return float(ex[ready].mean() - ex[rest].mean()) if ready.sum() >= MIN_GROUP and rest.sum() >= MIN_GROUP else None


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
        lv = np.array([np.nan if r["live"] is None else r["live"] for r in doc["rows"]], dtype=float)
        pr = np.array([np.nan if r["prior"] is None else r["prior"] for r in doc["rows"]], dtype=float)
        a, b = _ic(lv, ret), _ic(pr, ret)
        if a is None or b is None:
            continue
        out.append({"session": doc["session"], "entry": px.dates[i + 1], "ic_live": a, "ic_prior": b, "fifths_live": _fifths(lv, ret), "fifths_prior": _fifths(pr, ret),
                    "entry_gap": _entry_gap(doc["rows"], ret), "late": bool(doc.get("late"))})
    return out


def verdict(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """``rows``: separate samples.  The protocol's rule: whether the live score and the former formula can be told apart."""
    lv, pr = [r["ic_live"] for r in rows], [r["ic_prior"] for r in rows]
    diff = [a - b for a, b in zip(lv, pr)]
    gap = {"mean": float(np.mean(diff)), "t": _t(diff)}
    t = gap["t"]
    bar = calibrate.plain_bar(MIN_T, len(rows))          # a dozen samples: the table's value is passed too often (2026-11-22)
    word = "DECISION_SUPPORTED" if t is not None and gap["mean"] > 0 and t >= bar else "PRIOR_BETTER" if t is not None and gap["mean"] < 0 and t <= -bar else "NOT_DISTINGUISHED"
    return {"samples": len(rows), "t_bar": bar, "live": {"mean": float(np.mean(lv)), "t": _t(lv)}, "prior": {"mean": float(np.mean(pr)), "t": _t(pr)}, "difference": gap, "verdict": word}


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
    gaps = [d["entry_gap"] for d in separate if d["entry_gap"] is not None]
    res = {"status": "REAL", "protocol": PROTOCOL, "horizon": HORIZON, "records": len(docs), "matured": len(days), **verdict(separate),
           "all_days": {"days": len(days), "ic_live": float(np.mean([d["ic_live"] for d in days])), "t_live": validate.newey_west_t([d["ic_live"] for d in days], HORIZON),
                        "ic_prior": float(np.mean([d["ic_prior"] for d in days])), "t_prior": validate.newey_west_t([d["ic_prior"] for d in days], HORIZON)},
           "fifths": {k: {x: float(np.mean([d[k][x] for d in separate if d[k]])) for x in ("top", "bottom")} for k in ("fifths_live", "fifths_prior")},
           "entry_reading": {"samples": len(gaps), "mean_gap": float(np.mean(gaps)) if gaps else None, "t": _t(gaps), "note": "서술일 뿐 판정이 아닙니다. 진입 판단은 검증된 적이 없습니다."},
           "late_share": float(np.mean([d["late"] for d in days])), "note": "NOT_DISTINGUISHED는 '차이 없음'이 아니라 '아직 모름'입니다. 12개 표본의 검정력은 낮습니다."}
    out.parent.mkdir(parents=True, exist_ok=True)
    durable.write_text(out, json.dumps(res, ensure_ascii=False, indent=1))
    return res
