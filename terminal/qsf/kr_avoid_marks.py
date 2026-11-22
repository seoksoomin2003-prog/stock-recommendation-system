"""The one reading of the Korean avoid marks against the live score.  Rules: reports/QSF_KR_AVOID_MARKS_PROTOCOL.md.

No new record: the marks come from the three write-once forward records of the same session, the stocks and scores from the live
ledger.  The evaluation runs at the same 240 matured sessions as the Korean swing verdict, once.
"""
import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

import numpy as np

from terminal.qsf import calibrate, config, kr_events_forward as kef, kr_forward as kf, live_forward as lf, validate
from terminal.qsf.ledger import Ledger
from utils import durable

PROTOCOL = "reports/QSF_KR_AVOID_MARKS_PROTOCOL.md"
REPORT = Path("reports") / "qsf" / "QSF_KR_AVOID_MARKS.json"
H = lf.PRIMARY["SWING"]
NEED = lf.NEED["SWING"]
WATCH = 55.0                # the live WATCH floor: reading 2 looks inside the stocks the screen shows as worth watching or buying
MIN_SIDE = 3
MIN_DAYS_2 = 120
T1, T2 = -validate.MIN_T, -2.0
MARKS = ("high_risk", "weak_fund", "financing")


def _bottom_fifth(rows: List[Dict[str, Any]], key: str) -> Set[str]:
    values = [(r["code"], r[key]) for r in rows if r.get(key) is not None]
    if len(values) < 30:
        return set()
    q = validate.rank(np.array([v for _, v in values], dtype=float)) / (len(values) - 1)
    return {c for (c, _), x in zip(values, q) if x <= 0.2}


def marks_of(base: Path, session: str) -> Optional[Dict[str, Set[str]]]:
    """The session's marks, or None when any of the three records has no file for it."""
    docs = {}
    for name, folder in (("price", kf.FOLDER), ("fund", kf.FUND_FOLDER), ("events", kef.FOLDER)):
        try:
            docs[name] = kf._read_day(Path(base) / folder, session)["rows"]
        except (OSError, ValueError, KeyError):
            return None
    out = {"high_risk": _bottom_fifth(docs["price"], "low_risk"), "weak_fund": _bottom_fifth(docs["fund"], "score"),
           "financing": {r["code"] for r in docs["events"] if r.get("financing") == 1}}
    out["known"] = {r["code"] for d in docs.values() for r in d}
    out["any"] = out["high_risk"] | out["weak_fund"] | out["financing"]
    return out


def day_row(session: str, snaps: List[Dict[str, Any]], marks: Dict[str, Set[str]], px: lf.Prices, cost: float) -> Optional[Dict[str, Any]]:
    got = []
    for s in snaps:
        o = px.outcome(s, session, H, cost)
        if o:
            got.append((s["ticker"], float(s["score"]), o["net"]))
    if len(got) < lf.MIN_ROWS:
        return None
    mean = float(np.mean([n for _, _, n in got]))
    known = [(t, sc, n) for t, sc, n in got if t in marks["known"]]
    row: Dict[str, Any] = {"date": session, "n": len(got), "unknown_share": 1 - len(known) / len(got), "marked_share": sum(1 for t, _, _ in known if t in marks["any"]) / max(len(known), 1)}
    for name in ("any",) + MARKS:
        hit = [n for t, _, n in known if t in marks[name]]
        row[f"excess_{name}"] = float(np.mean(hit)) - mean if len(hit) >= MIN_SIDE else None
    watch_m = [n for t, sc, n in known if sc >= WATCH and t in marks["any"]]
    watch_u = [n for t, sc, n in known if sc >= WATCH and t not in marks["any"]]
    row["within_watch"] = float(np.mean(watch_m) - np.mean(watch_u)) if len(watch_m) >= MIN_SIDE and len(watch_u) >= MIN_SIDE else None
    band = [(t, n) for t, sc, n in got if sc >= lf.BUY]
    kept = [n for t, n in band if not (t in marks["known"] and t in marks["any"])]
    row["buy_n"], row["buy_removed"] = len(band), len(band) - len(kept)
    row["filter_gain"] = float(np.mean(kept) - np.mean([n for _, n in band])) if band and kept and len(kept) < len(band) else None
    return row


def series(rows: List[Dict[str, Any]], key: str) -> Dict[str, Any]:
    """Mean, Newey-West t (lag = horizon) and halves of one daily value; the halves split the days that have the value."""
    v = [r[key] for r in rows if r.get(key) is not None]
    if len(v) < 2 * H:
        return {"days": len(v), "status": "UNAVAILABLE"}
    mid = len(v) // 2
    return {"days": len(v), "mean": float(np.mean(v)), "t": validate.newey_west_t(v, H), "early": float(np.mean(v[:mid])), "late": float(np.mean(v[mid:]))}


def _negative(s: Dict[str, Any], limit: float) -> bool:
    return s.get("t") is not None and s["early"] < 0 and s["late"] < 0 and s["t"] <= limit


def reading(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    one, two = series(rows, "excess_any"), series(rows, "within_watch")
    # the bars for these samples' own design (daily values of H-session returns, lag H): terminal/qsf/calibrate.py, 2026-11-22
    b1, b2 = (calibrate.bar(-T1, one.get("days", 0), H, 1, H), calibrate.bar(-T2, two.get("days", 0), H, 1, H))
    p1 = _negative(one, -b1)
    p2 = _negative(two, -b2) and two["days"] >= MIN_DAYS_2
    return {"verdict": "AVOID_RULE_SUPPORTED" if p1 and p2 else "MARKS_FLAG_LOSERS_BUT_SCORE_KNOWS" if p1 else "NO_EVIDENCE",
            "reading_1": {**one, "passed": p1, "t_bar": -b1}, "reading_2": {**two, "passed": p2, "t_bar": -b2}}


def evaluate_once(base: Path, loader: Callable[[str], List[Dict]], bench: List[Dict], log=print, benches: Optional[Dict[str, List[Dict]]] = None) -> Dict[str, Any]:
    base = Path(base)
    out = base / REPORT
    if out.exists():
        raise RuntimeError("판정은 한 번만 합니다. 이미 결과가 있습니다.")
    led = Ledger(base)
    if led.verify()["status"] != "OK":
        raise RuntimeError("원장 검증에 실패해 판정하지 않습니다.")
    snaps = lf.session_rows(led, "KR", "SWING")
    px = lf.Prices(loader, bench, benches)
    ready = lf.matured_sessions(list(snaps), px.calendar, H)
    if len(ready) < NEED:
        raise RuntimeError(f"아직 판정할 수 없습니다. 만기 거래일 {len(ready)}개, 기준 {NEED}개입니다.")
    used = ready[:NEED]
    cost = config.round_trip_cost("KR")
    rows, skipped = [], 0
    for s in used:
        marks = marks_of(base, s)
        if marks is None:
            skipped += 1
            continue
        r = day_row(s, snaps[s], marks, px, cost)
        if r:
            rows.append(r)
    if len(rows) < NEED // 2:
        raise RuntimeError(f"세 기록이 모두 있는 날이 {len(rows)}일뿐입니다.")
    gains = [r["filter_gain"] for r in rows if r["filter_gain"] is not None]
    res = {"status": "REAL", "protocol": PROTOCOL, "horizon": H, "sessions_used": len(used), "days": len(rows), "days_without_all_three_records": skipped, **reading(rows),
           "by_mark": {m: series(rows, f"excess_{m}") for m in MARKS},
           "buy_band_filter": {"days_with_a_removal": len(gains), "mean_gain": float(np.mean(gains)) if gains else None, "mean_buy_names": float(np.mean([r["buy_n"] for r in rows])),
                               "mean_removed": float(np.mean([r["buy_removed"] for r in rows]))},
           "marked_share": float(np.mean([r["marked_share"] for r in rows])), "unknown_share": float(np.mean([r["unknown_share"] for r in rows])), "note": lf.NOTE}
    out.parent.mkdir(parents=True, exist_ok=True)
    durable.write_text(out, json.dumps(res, ensure_ascii=False, indent=1))
    log(f"avoid marks: {res['verdict']}")
    return res
