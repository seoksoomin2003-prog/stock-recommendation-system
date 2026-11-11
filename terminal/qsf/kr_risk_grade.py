"""The Korean risk grade and its one historical test.  Rules: reports/QSF_KR_RISK_GRADE_PROTOCOL.md.

The grade answers a different question from the score: not which stock gains more, but which one swings and loses more over the next
20 sessions.  Four price inputs known at the close are ranked inside the day's eligible stocks and averaged.  The test runs once and a
second run is refused.  Nothing here changes the live score, a limit or a stop.
"""
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

from terminal.qsf import research_kr as kr, validate

PROTOCOL = "reports/QSF_KR_RISK_GRADE_PROTOCOL.md"
REPORT = Path("reports") / "qsf" / "QSF_KR_RISK_GRADE.json"
START, STEP, H = "2011-01-03", 21, 20
SIZE = 300
INPUTS = ("vol60", "range14", "drop120", "thin20")
MIN_INPUTS = 3
GRADES = ((40.0, "LOW"), (70.0, "MEDIUM"), (90.0, "HIGH"), (math.inf, "VERY_HIGH"))
GRADE_NAMES = {"LOW": "낮음", "MEDIUM": "보통", "HIGH": "높음", "VERY_HIGH": "매우 높음"}
BIG_LOSS = -0.15
MIN_IC, MIN_T = 0.30, validate.MIN_T
FIFTH = 0.2


def _std(win: np.ndarray, least: int) -> np.ndarray:
    """Standard deviation of the daily changes down each column, where at least ``least`` changes exist."""
    with np.errstate(invalid="ignore", divide="ignore"):
        r = win[1:] / win[:-1] - 1
    have = np.isfinite(r).sum(axis=0)
    mean = np.nansum(np.where(np.isfinite(r), r, 0.0), axis=0) / np.where(have > 0, have, np.nan)
    var = np.nansum(np.where(np.isfinite(r), (r - mean) ** 2, 0.0), axis=0) / np.where(have > 1, have - 1, np.nan)
    return np.where(have >= least, np.sqrt(var), np.nan)


def inputs(d: Dict[str, np.ndarray], i: int) -> Dict[str, np.ndarray]:
    """The four raw values at the close of row ``i``, each turned so that a higher value means more risk.  Reads nothing after ``i``."""
    c = d["close"].astype(float)
    n = c.shape[1]
    out = {k: np.full(n, np.nan) for k in INPUTS}
    if i >= 60:
        out["vol60"] = _std(c[i - 60:i + 1], 40)
    if i >= 14:
        h, lo, pc = d["high"][i - 13:i + 1].astype(float), d["low"][i - 13:i + 1].astype(float), c[i - 14:i]
        with np.errstate(invalid="ignore"):
            tr = np.fmax(h - lo, np.fmax(np.abs(h - pc), np.abs(lo - pc)))
            tr = np.where(np.isfinite(h) & np.isfinite(lo) & np.isfinite(pc), tr, np.nan)
            have = np.isfinite(tr).sum(axis=0)
            mean = np.nansum(np.where(np.isfinite(tr), tr, 0.0), axis=0) / np.where(have > 0, have, np.nan)
            out["range14"] = np.where(have >= 10, mean / c[i], np.nan)
    if i >= 119:
        win = c[i - 119:i + 1]
        top = np.where(np.isfinite(win).any(axis=0), np.nanmax(np.where(np.isfinite(win), win, -np.inf), axis=0), np.nan)
        with np.errstate(invalid="ignore", divide="ignore"):
            out["drop120"] = 1 - c[i] / top
    v = d["value"][max(0, i - 19):i + 1].astype(float)
    have = np.isfinite(v).sum(axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        out["thin20"] = -(np.nansum(np.where(np.isfinite(v), v, 0.0), axis=0) / np.where(have > 0, have, np.nan))
    return out


def percentile(x: np.ndarray, ok: np.ndarray) -> np.ndarray:
    """0..1 inside the stocks marked ``ok`` that have a value; ties share a rank."""
    out = np.full(len(x), np.nan)
    m = ok & np.isfinite(x)
    if m.sum() >= 2:
        out[m] = validate.rank(x[m]) / (m.sum() - 1)
    return out


def score(d: Dict[str, np.ndarray], i: int, ok: np.ndarray) -> np.ndarray:
    """0..100, higher is riskier: the mean percentile of the inputs a stock has, when it has at least three."""
    ranks = np.vstack([percentile(v, ok) for v in inputs(d, i).values()])
    have = np.isfinite(ranks).sum(axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        mean = np.nansum(np.where(np.isfinite(ranks), ranks, 0.0), axis=0) / np.where(have > 0, have, np.nan)
    return np.where(have >= MIN_INPUTS, mean * 100, np.nan)


def grade(value: Optional[float]) -> Optional[str]:
    if value is None or not np.isfinite(value):
        return None
    return next(name for limit, name in GRADES if value < limit)


def targets(d: Dict[str, np.ndarray], i: int, h: int = H) -> Dict[str, np.ndarray]:
    """What happened over the next ``h`` sessions to a holder who bought at the next open.  A stock gone before the end closes at its last trade."""
    c, n = d["close"].astype(float), d["close"].shape[1]
    win = c[i + 1:i + h + 1]
    have = np.isfinite(win)
    last = win.shape[0] - 1 - np.argmax(have[::-1], axis=0)
    exit_ = win[last, np.arange(n)]
    exit_[~have.any(axis=0)] = np.nan
    entry = d["open"][i + 1].astype(float)
    lows = d["low"][i + 1:i + h + 1].astype(float)
    low = np.where(np.isfinite(lows).any(axis=0), np.nanmin(np.where(np.isfinite(lows), lows, np.inf), axis=0), np.nan)
    with np.errstate(invalid="ignore", divide="ignore"):
        return {"vol": _std(c[i:i + h + 1], 10), "drawdown": low / entry - 1, "ret": exit_ / entry - 1}


def members(d: Dict[str, np.ndarray], i: int, ok: np.ndarray, size: int = SIZE) -> np.ndarray:
    """The ``size`` largest eligible stocks by the day's market value."""
    cap = np.where(ok & np.isfinite(d["cap"][i]), d["cap"][i].astype(float), -np.inf)
    order = np.argsort(-cap, kind="mergesort")[:size]
    out = np.zeros(len(cap), dtype=bool)
    out[order[np.isfinite(cap[order])]] = True
    return out


def _corr(a: np.ndarray, b: np.ndarray) -> Optional[float]:
    m = np.isfinite(a) & np.isfinite(b)
    if m.sum() < 30:
        return None
    ra, rb = validate.rank(a[m]), validate.rank(b[m])
    if ra.std() == 0 or rb.std() == 0:
        return None
    return float(np.corrcoef(ra, rb)[0, 1])


def day_stats(sc: np.ndarray, t: Dict[str, np.ndarray], group: np.ndarray) -> Optional[Dict[str, Any]]:
    """The three readings of one day inside ``group``.  ``None`` when the day cannot be read."""
    m = group & np.isfinite(sc) & np.isfinite(t["ret"]) & np.isfinite(t["drawdown"])
    if m.sum() < 50:
        return None
    s = sc[m]
    q = validate.rank(s) / (m.sum() - 1)
    top, bottom = q >= 1 - FIFTH, q <= FIFTH
    loss = t["ret"][m] <= BIG_LOSS
    by_grade = {}
    for name in GRADE_NAMES:
        g = np.array([grade(v) == name for v in s])
        if g.any():
            vol = t["vol"][m][g]
            by_grade[name] = {"n": int(g.sum()), "vol": float(np.nanmean(vol)) if np.isfinite(vol).any() else None, "loss": float(loss[g].mean()),
                              "drawdown": float(t["drawdown"][m][g].mean()), "ret": float(t["ret"][m][g].mean())}
    return {"n": int(m.sum()), "ic_vol": _corr(sc[m], t["vol"][m]), "ic_ret": _corr(sc[m], t["ret"][m]),
            "loss_top": float(loss[top].mean()), "loss_all": float(loss.mean()), "loss_gap": float(loss[top].mean() - loss.mean()),
            "drawdown_top": float(t["drawdown"][m][top].mean()), "drawdown_bottom": float(t["drawdown"][m][bottom].mean()),
            "drawdown_gap": float(t["drawdown"][m][top].mean() - t["drawdown"][m][bottom].mean()), "grades": by_grade}


def _mean(x: Sequence[Optional[float]]) -> Optional[float]:
    v = [a for a in x if a is not None and np.isfinite(a)]
    return float(np.mean(v)) if v else None


def _series(days: List[Dict[str, Any]], key: str) -> Dict[str, Any]:
    x = [d[key] for d in days if d.get(key) is not None]
    half = len(x) // 2
    return {"days": len(x), "mean": _mean(x), "t": validate.newey_west_t(x, 1), "early": _mean(x[:half]), "late": _mean(x[half:])}


def summarize(days: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Means over days, the three readings with their pass marks, and the table by grade."""
    r1, r2, r3 = _series(days, "ic_vol"), _series(days, "loss_gap"), _series(days, "drawdown_gap")
    gt = lambda v, x: v is not None and v > x          # noqa: E731
    checks = {"volatility": gt(r1["mean"], MIN_IC - 1e-12) and gt(r1["t"], MIN_T - 1e-12) and gt(r1["early"], 0) and gt(r1["late"], 0),
              "big_loss": gt(r2["mean"], 0) and gt(r2["t"], MIN_T - 1e-12) and gt(r2["early"], 0) and gt(r2["late"], 0),
              "drawdown": r3["mean"] is not None and r3["mean"] < 0 and r3["t"] is not None and r3["t"] <= -MIN_T}
    grades = {}
    for name in GRADE_NAMES:
        rows = [d["grades"][name] for d in days if name in d["grades"]]
        n = sum(r["n"] for r in rows)
        if n:
            w = lambda k: float(sum(r[k] * r["n"] for r in rows if r[k] is not None) / sum(r["n"] for r in rows if r[k] is not None))      # noqa: E731
            grades[name] = {"n": n, "vol": w("vol"), "loss": w("loss"), "drawdown": w("drawdown"), "ret": w("ret")}
    ic = r1["mean"]
    return {"days": len(days), "first": days[0]["date"] if days else None, "last": days[-1]["date"] if days else None, "mean_n": _mean([d["n"] for d in days]),
            "volatility": r1, "big_loss": {**r2, "top": _mean([d["loss_top"] for d in days]), "all": _mean([d["loss_all"] for d in days])},
            "drawdown": {**r3, "top": _mean([d["drawdown_top"] for d in days]), "bottom": _mean([d["drawdown_bottom"] for d in days])},
            "return_ic": _series(days, "ic_ret"), "pair_win": None if ic is None else 0.5 + ic / math.pi,
            "checks": checks, "grades": grades}


def eval_rows(dates: Sequence[str], start: str = START, step: int = STEP, h: int = H) -> List[int]:
    first = next((n for n, day in enumerate(dates) if day >= start), len(dates))
    return [i for i in range(first, len(dates), step) if i + h < len(dates)]


def evaluate(d: Dict[str, np.ndarray], dates: Sequence[str], log=lambda m: None) -> Dict[str, Any]:
    """Both groups read on every evaluation day.  The verdict comes from the largest 300 alone."""
    out: Dict[str, List[Dict[str, Any]]] = {"top300": [], "all": []}
    rows = eval_rows(dates)
    for n, i in enumerate(rows):
        ok = kr.eligible(d, i)
        sc, t = score(d, i, ok), targets(d, i)
        for name, group in (("top300", members(d, i, ok)), ("all", ok)):
            s = day_stats(sc, t, group)
            if s:
                out[name].append({"date": dates[i], **s})
        if n % 40 == 0:
            log(f"{n}/{len(rows)} {dates[i]}")
    primary, reference = summarize(out["top300"]), summarize(out["all"])
    verdict = "RISK_GRADE_SUPPORTED" if primary["days"] and all(primary["checks"].values()) else "RISK_GRADE_NOT_SUPPORTED"
    return {"verdict": verdict, "primary": primary, "reference": reference}


def run_once(base: Path, log=print) -> Dict[str, Any]:
    """The one run.  A stored result is returned as it is and nothing is computed again."""
    path = Path(base) / REPORT
    if path.exists():
        return {**json.loads(path.read_text(encoding="utf-8")), "status": "ALREADY_RUN"}
    px = kr._load(Path(base))
    res = evaluate(px.data, px.dates, log)
    doc = {"status": "REAL", "protocol": PROTOCOL, "ran_at": datetime.now(timezone.utc).isoformat(), "data_first": px.dates[0], "data_last": px.dates[-1],
           "step": STEP, "horizon": H, "big_loss": BIG_LOSS, "grade_limits": [g[0] for g in GRADES[:-1]], "min_ic": MIN_IC, "min_t": MIN_T, **res}
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)
    return doc


def supported(base: Path) -> bool:
    """Whether the stored test allows the grade on screen."""
    try:
        return json.loads((Path(base) / REPORT).read_text(encoding="utf-8")).get("verdict") == "RISK_GRADE_SUPPORTED"
    except (OSError, ValueError):
        return False


def day_grades(d: Dict[str, np.ndarray], i: int) -> Dict[str, Dict[str, Any]]:
    """Score and grade of every eligible stock at row ``i``, for the daily record and the screen."""
    ok = kr.eligible(d, i)
    sc = score(d, i, ok)
    return {str(d["symbols"][j]): {"score": round(float(sc[j]), 1), "grade": grade(float(sc[j]))} for j in np.flatnonzero(np.isfinite(sc))}
