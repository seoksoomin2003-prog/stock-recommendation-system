"""The Korean filing-event score, written down every session and kept apart from the live score.  Rules: reports/QSF_KR_EVENTS_FORWARD_PROTOCOL.md.

The score, signals and window are the ones the one-shot test fixed.  Files, index and hash chain are its own, and its filing lists are its own, so
the test's data stays as it was run.  No return is computed while the record grows.  Nothing here reads or changes the live score, the QSF ledger or P6-11B.
"""
import json
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

import numpy as np

from terminal.qsf import config, kr_forward as kf, krx_history as kh, research_ensemble as en, research_kr as kr, research_kr_events as ke, research_swing as rs
from terminal.qsf.research_score import test_verdict
from utils import durable

PROTOCOL = "reports/QSF_KR_EVENTS_FORWARD_PROTOCOL.md"
FOLDER = Path("research_data") / "krx_forward_events"
REPORT = Path("reports") / "qsf" / "QSF_KR_FORWARD_EVENTS.json"
LISTS = Path("research_data") / "dart" / "forward_events"
FIRST = "2026-11-06"       # the test's prices end on 2026-11-05
YEARS_BACK = 2             # 252 sessions run to a little over a year, so a January record reaches two calendar years back
HORIZON, STEP = kf.HORIZON, kf.STEP
AVOID_LIMIT = -0.005       # the same bar the other records use for a lowest group


def recent_quarters(today: date) -> List[str]:
    """This quarter and the one before: new filings arrive there.  Older quarters are asked once."""
    q = (today.month - 1) // 3
    prev = (today.year, q - 1) if q else (today.year - 1, 3)
    return [f"{today.year}Q{q + 1}", f"{prev[0]}Q{prev[1] + 1}"]


def refresh_lists(base: Path, key: str, get: Callable[..., Any], today: date, log=print, sleep: Optional[Callable[[float], None]] = None) -> Dict[str, Any]:
    recent = recent_quarters(today)
    return ke.download(Path(base), log=log, get=get, sleep=sleep or time.sleep, today=today, key=key, root=Path(base) / LISTS, first_year=today.year - YEARS_BACK, refresh=lambda name: name in recent)


def score_day(base: Path, day: str) -> Dict[str, Any]:
    """Prices up to ``day``, and only filings received before it."""
    root = Path(base) / kr.DATA
    back = (date.fromisoformat(day) - timedelta(days=kf.WINDOW * 7 // 5 + 7)).isoformat()
    z = kr.build_prices(root, log=lambda m: None, days=list(kh.weekdays(back, day))[-kf.WINDOW:])
    i = len(z["dates"]) - 1
    if i < 0 or str(z["dates"][i]) != day:
        raise ValueError("NO_PRICES_FOR_DAY")
    px = kr.KrPrices(z)
    tensor = ke.build_features(px, [i], ke.load_events(Path(base) / LISTS), log=lambda m: None)
    final = ke.score_of(tensor)[0]
    names = {r[kr.F["ISU_CD"]]: r[kr.F["ISU_NM"]] for rows in kf._rows_of(root, day).values() for r in rows}

    def val(x: Any) -> Optional[float]:
        v = float(x)
        return round(v, 3) if np.isfinite(v) else None
    rows = []
    for j in np.flatnonzero(np.isfinite(final)):
        code = str(z["symbols"][j])
        rows.append({"code": code, "name": names.get(code), "board": "KOSPI" if z["kospi"][j] else "KOSDAQ", "score": val(final[j]), "financing": int(tensor[0, j, 0]), "buyback": int(tensor[0, j, 1]), "cap": val(z["cap"][i, j]), "traded": val(z["value"][i, j])})
    if len(rows) < kf.MIN_STOCKS:
        raise ValueError("TOO_FEW_SCORES")
    return {"session": day, "protocol": PROTOCOL, "rows": rows}


def record(base: Path, have: Sequence[str], at: datetime, key: Optional[str], get: Callable[..., Any], first: str = FIRST, log=print, sleep: Optional[Callable[[float], None]] = None) -> Dict[str, Any]:
    """The days not yet written.  A failure here leaves the price and financial records alone."""
    done = {r["session"] for r in kf.read_index(base, FOLDER)}
    days = [d for d in have if d >= first]
    pending = [d for d in days if d not in done]
    if not pending:
        return {"status": "OK", "written": []}
    if not key:
        return {"status": "FAILED", "reason": "NO_DART_KEY", "written": []}
    try:
        got = refresh_lists(base, key, get, at.astimezone(kf.KST).date(), log, sleep)
        if got.get("stopped"):
            return {"status": "FAILED", "reason": got["stopped"], "written": []}
        wrote = [d for d in pending if kf.write_record(base, d, at, d != days[-1], FOLDER, scorer=score_day)]
    except Exception as exc:                # the type only: a message could carry the key
        return {"status": "FAILED", "reason": type(exc).__name__, "written": []}
    return {"status": "OK", "written": wrote}


def status(base: Path, calendar: Optional[Sequence[str]]) -> Dict[str, Any]:
    return kf.status(base, calendar, FOLDER)


def marks(base: Path) -> Dict[str, Any]:
    """Who has a financing or buyback decision on the newest record.  For display: it feeds no score.  A code not on the record is unknown, not a no."""
    rows = kf.read_index(base, FOLDER)
    if not rows:
        return {"session": None, "financing": [], "buyback": [], "known": []}
    day = rows[-1]["session"]
    doc = kf._read_day(Path(base) / FOLDER, day)["rows"]
    return {"session": day, "financing": sorted(r["code"] for r in doc if r["financing"] == 1), "buyback": sorted(r["code"] for r in doc if r["buyback"] == 1), "known": sorted(r["code"] for r in doc)}


# ---------------------------------------------------------------------- the one evaluation
def _sets(fin: np.ndarray, buy: np.ndarray, px: kr.KrPrices, rows: List[int], picks: List[int], cost: float) -> Dict[str, Any]:
    """Fixed sets with no ranking inside, as in the test, each half held to the same rule."""
    ns = picks[::HORIZON // STEP]
    ret = np.stack([px.forward(rows[n], HORIZON) for n in ns])
    sets = {"all_equal": [np.isfinite(fin[n]) for n in ns], "no_financing": [fin[n] == 0 for n in ns], "financing": [fin[n] == 1 for n in ns], "buyback_clean": [(buy[n] == 1) & (fin[n] == 0) for n in ns]}
    path = {k: kr.rebalance_path(v, ret, cost) for k, v in sets.items()}
    path["market"] = [float(v) for v in ret[:, px.col[kr.MARKET]]]
    grow = lambda x: kr.annual_growth(x, HORIZON)      # noqa: E731
    parts = [{k: grow(kf._half(v)[part]) for k, v in path.items()} for part in (0, 1)]
    beat = lambda a, b: all(p[a] is not None and p[b] is not None and p[a] > p[b] for p in parts)      # noqa: E731
    return {"periods": len(ns), **{k: grow(v) for k, v in path.items()}, "early": parts[0], "late": parts[1],
            "mean_holdings": {k: float(np.mean([x.sum() for x in v])) for k, v in sets.items()}, "b1_buyback_beats_market": beat("buyback_clean", "market"), "b2_avoiding_financing_helps": beat("no_financing", "all_equal")}


def _low_tier(score: np.ndarray, px: kr.KrPrices, rows: List[int], picks: List[int]) -> Dict[str, Any]:
    """The 0-point stocks against the same day's average, before cost.  Average ranks would make this the bottom fifth anyway; the tier says it plainly."""
    out = []
    for n in picks:
        r = px.forward(rows[n], HORIZON)
        ok = np.isfinite(r) & np.isfinite(score[n])
        if ok.sum() >= kf.MIN_STOCKS and (ok & (score[n] == 0)).any():
            out.append(float(r[ok & (score[n] == 0)].mean() - r[ok].mean()))
    if not out:
        return {"excess": None, "early": None, "late": None, "supports_avoiding": False}
    a, b = kf._half(out)
    early, late, mean = float(np.mean(a)), float(np.mean(b)), float(np.mean(out))
    return {"excess": mean, "early": early, "late": late, "supports_avoiding": bool(early < 0 and late < 0 and mean <= AVOID_LIMIT)}


def reading(verdict: str, sets: Dict[str, Any]) -> str:
    if verdict != "WEAK_POSITIVE_EVIDENCE":
        return "NO_EVIDENCE"
    if sets["b1_buyback_beats_market"]:
        return "A_AND_B1"
    return "A_AND_B2" if sets["b2_avoiding_financing_helps"] else "A_ONLY"


def evaluate_once(base: Path, log=print) -> Dict[str, Any]:
    target = Path(base) / REPORT
    if target.exists():
        raise RuntimeError("이미 평가했습니다. 규칙상 다시 평가할 수 없습니다.")
    if kf.verify(base, FOLDER)["status"] != "OK":
        raise RuntimeError("기록 검증에 실패해 평가하지 않습니다.")
    index = kf.read_index(base, FOLDER)
    if not index:
        raise RuntimeError("기록이 없습니다.")
    folder = Path(base) / FOLDER
    days = list(kh.weekdays(index[0]["session"], kf.previous_weekday(date.today()).isoformat()))
    px = kr.KrPrices(kr.build_prices(Path(base) / kr.DATA, log=log, days=days))
    place = {d: n for n, d in enumerate(px.dates)}
    known = [r["session"] for r in index if r["session"] in place]
    matured = [d for d in known if place[d] + HORIZON < len(px.dates)]
    need = kf.MIN_INDEPENDENT * HORIZON
    if len(matured) < need:
        raise RuntimeError(f"아직 평가할 수 없습니다. 만기 거래일 {len(matured)}개, 기준 {need}개입니다.")
    chosen = matured[::STEP]
    rows = [place[d] for d in chosen]
    shape = (len(rows), len(px.symbols))
    score, fin, buy = np.full(shape, np.nan), np.full(shape, np.nan), np.full(shape, np.nan)
    for n, d in enumerate(chosen):
        for r in kf._read_day(folder, d)["rows"]:
            j = px.col.get(r["code"])
            if j is not None:
                score[n, j], fin[n, j], buy[n, j] = r["score"], r["financing"], r["buyback"]
    picks = list(range(len(rows)))
    cost = config.round_trip_cost("KR")
    test = en.evaluate(score, px, rows, picks, HORIZON, {}, cost)
    for regime in ("ic_spy_above_200d", "ic_spy_below_200d"):      # prices start at the first record, too short for a 200-day average
        test.pop(regime, None)
    judged = test_verdict(test)
    sets = _sets(fin, buy, px, rows, picks, cost)
    later_ic = [v for v in (rs._ic(score[n], px.forward(rows[n] + 1, HORIZON)) for n in picks) if v is not None]
    late = sum(1 for r in index if r["late"])
    out = {"status": "EVALUATED", "protocol": PROTOCOL, "horizon": HORIZON, "dates": len(rows), "first": chosen[0], "last": chosen[-1], "cost": cost, **test, **judged, "sets": sets, "low_tier": _low_tier(score, px, rows, picks), "reading": reading(judged["verdict"], sets),
           "one_day_later_entry_ic": float(np.mean(later_ic)) if later_ic else None, "late_share": late / len(index), "before_next_open_share": sum(1 for r in index if r["before_next_open"]) / len(index)}
    target.parent.mkdir(parents=True, exist_ok=True)
    durable.write_text(target, json.dumps(out, ensure_ascii=False, indent=1, default=str))
    return out
