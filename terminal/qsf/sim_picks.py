"""Following the screen, simulated once.  Rules: reports/QSF_PICKS_SIMULATION_PROTOCOL.md (committed before the run).

Part 1: the three highest live-style scores (variant A of the stored historical replay) against screens that pick three names at
random from the same day's universe.  Part 2: how often the forward record's verdict rule (n independent samples, mean > 0 and
t >= 2) says "evidence" when the true rank correlation is 0 or small.

Research only: it reads stored scores and prices, never touches the ledger, the forward records or the live score, downloads
nothing, and refuses a second run.  The sample is the one earlier checks already judged, so nothing here is new evidence.
"""
import gzip
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from terminal.qsf import config, validate, validate_open

PROTOCOL = "reports/QSF_PICKS_SIMULATION_PROTOCOL.md"
REPORT = Path("reports") / "qsf" / "QSF_PICKS_SIMULATION.json"
SCORES = "scores_corrected_open.json.gz"
PRICES = "prices15y_open.npz"
VARIANT = "A"
HORIZONS = {"SWING": (1, 5, 10, 20), "LONG_TERM": (5, 21, 63)}       # the horizons of the top-3 forward record
PRIMARY = {"SWING": 5, "LONG_TERM": 21}
TOP = 3
MIN_NAMES = 30
SEED = 20261110
RANDOM_SCREENS = 20_000
POWER_TRIALS = 100_000
POWER_HORIZONS = {"SWING": (5, 20), "LONG_TERM": (21, 63)}
TRUE_ICS = (0.0, 0.01, 0.02, 0.03, 0.05)
SAMPLES = (12, 24, 36, 60, 120)
T_RULE = 2.0
HIGH, LOW = 97.5, 2.5


def pick_top(score: np.ndarray, names: List[str], k: int) -> np.ndarray:
    """Indices of the ``k`` highest scores; ties go to the earlier ticker code."""
    order = sorted(range(len(names)), key=lambda j: (-score[j], names[j]))
    return np.array(order[:k], dtype=int)


def day_rows(by_i: Dict[int, List[Dict[str, Any]]], px, key: str, h: int, step: int) -> List[Dict[str, Any]]:
    """One row per usable evaluation day: the day's names, scores and forward returns.  Days are thinned so holds do not overlap."""
    days = sorted(by_i)
    gap = max(1, math.ceil(h / step))
    rows = []
    for n, i in enumerate(days):
        if n % gap:
            continue
        fwd = px.forward(i, h)
        g = by_i[i]
        score = np.array([r[key] if r.get(key) is not None else np.nan for r in g], dtype=float)
        ret = np.array([fwd[px.col[r["t"]]] for r in g], dtype=float)
        ok = np.isfinite(score) & np.isfinite(ret)
        if ok.sum() < MIN_NAMES:
            continue
        rows.append({"date": px.dates[i], "i": i, "names": [g[j]["t"] for j in np.flatnonzero(ok)], "score": score[ok], "ret": ret[ok], "spy": float(fwd[px.col["SPY"]])})
    return rows


def _t(x: np.ndarray) -> Optional[float]:
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 and x.std(ddof=1) > 0 else None


def random_screens(rows: List[Dict[str, Any]], k: int, cost: float, rng: np.random.Generator, screens: int) -> np.ndarray:
    """Mean excess return over the days of ``screens`` screens that each pick ``k`` names at random every day."""
    total = np.zeros(screens)
    for r in rows:
        n = len(r["ret"])
        idx = np.argpartition(rng.random((screens, n), dtype=np.float32), k - 1, axis=1)[:, :k]           # k distinct names per screen
        total += r["ret"][idx].mean(axis=1) - cost - r["ret"].mean()
    return total / len(rows)


def measure(rows: List[Dict[str, Any]], chosen: List[np.ndarray], cost: float) -> Dict[str, Any]:
    """Net excess of the chosen names over the day's universe average; days with nothing chosen are skipped."""
    ex, vs_spy, n_picks = [], [], 0
    dates = []
    for r, idx in zip(rows, chosen):
        if len(idx) == 0:
            continue
        net = float(r["ret"][idx].mean() - cost)
        ex.append(net - float(r["ret"].mean()))
        vs_spy.append(net - r["spy"] if r["spy"] == r["spy"] else np.nan)
        dates.append(r["date"])
        n_picks += len(idx)
    if not ex:
        return {"days": 0}
    e, s = np.array(ex), np.array(vs_spy)
    mid = len(e) // 2
    return {"days": len(e), "first": dates[0], "last": dates[-1], "picks": n_picks, "mean_excess": float(e.mean()), "median_excess": float(np.median(e)), "t": _t(e),
            "days_above_average": float((e > 0).mean()), "mean_vs_spy": float(np.nanmean(s)) if np.isfinite(s).any() else None,
            "days_above_spy": float((s[np.isfinite(s)] > 0).mean()) if np.isfinite(s).any() else None,
            "early_excess": float(e[:mid].mean()) if mid else None, "late_excess": float(e[mid:].mean())}


def growth(rows: List[Dict[str, Any]], chosen: List[np.ndarray], cost: float) -> Dict[str, Any]:
    """1 rolled through every day's picks in turn, next to the universe average and SPY over the same holds."""
    def path(vals: List[float]) -> Dict[str, Any]:
        nav = np.cumprod(1 + np.array(vals))
        peak = np.maximum.accumulate(nav)
        return {"end": float(nav[-1]), "max_drawdown": float((nav / peak - 1).min())}
    picks = [float(r["ret"][idx].mean() - cost) for r, idx in zip(rows, chosen) if len(idx)]
    avg = [float(r["ret"].mean()) for r, idx in zip(rows, chosen) if len(idx)]
    spy = [r["spy"] if r["spy"] == r["spy"] else 0.0 for r, idx in zip(rows, chosen) if len(idx)]
    return {"holds": len(picks), "top": path(picks), "universe_average": path(avg), "spy": path(spy)} if picks else {"holds": 0}


def reading(percentile: float, early: Optional[float], late: Optional[float]) -> str:
    if percentile >= HIGH and early is not None and late is not None and early > 0 and late > 0:
        return "DISTINCT_FROM_RANDOM"
    if percentile <= LOW:
        return "WORSE_THAN_RANDOM"
    return "NOT_DISTINCT_FROM_RANDOM"


def picks_part(by_i: Dict[int, List[Dict[str, Any]]], px, step: int, screens: int = RANDOM_SCREENS, seed: int = SEED) -> Dict[str, Any]:
    cost = config.round_trip_cost("US")
    rng = np.random.default_rng(seed)
    out: Dict[str, Any] = {"cost_round_trip": cost, "tables": {}, "primary": {}}
    for strategy, hs in HORIZONS.items():
        key = f"{strategy}|{VARIANT}"
        for h in hs:
            rows = day_rows(by_i, px, key, h, step)
            if not rows:
                out["tables"][f"{strategy}|{h}"] = {"days": 0}
                continue
            top3 = [pick_top(r["score"], r["names"], TOP) for r in rows]
            m = measure(rows, top3, cost)
            sims = random_screens(rows, TOP, cost, rng, screens)
            m["random"] = {"screens": screens, "mean": float(sims.mean()), "p2_5": float(np.percentile(sims, 2.5)), "p50": float(np.percentile(sims, 50)), "p97_5": float(np.percentile(sims, 97.5))}
            m["percentile_vs_random"] = float((sims < m["mean_excess"]).mean() * 100)
            m["reading"] = reading(m["percentile_vs_random"], m.get("early_excess"), m.get("late_excess"))
            m["mean_names"] = float(np.mean([len(r["ret"]) for r in rows]))
            m["reference"] = {"top10": measure(rows, [pick_top(r["score"], r["names"], 10) for r in rows], cost),
                              "buy_band_70": measure(rows, [np.flatnonzero(r["score"] >= validate.BUY_SCORE) for r in rows], cost)}
            if h == PRIMARY[strategy]:
                m["growth"] = growth(rows, top3, cost)
                out["primary"][strategy] = {"horizon": h, **{k: m[k] for k in ("days", "mean_excess", "t", "days_above_average", "days_above_spy", "early_excess", "late_excess", "percentile_vs_random", "reading")}}
            out["tables"][f"{strategy}|{h}"] = m
    return out


def ic_series(by_i: Dict[int, List[Dict[str, Any]]], px, key: str, h: int, step: int) -> np.ndarray:
    vals = []
    for r in day_rows(by_i, px, key, h, step):
        ex = r["ret"] - r["ret"].mean()
        if r["score"].std() > 0 and ex.std() > 0:
            vals.append(float(np.corrcoef(validate.rank(r["score"]), validate.rank(ex))[0, 1]))
    return np.array(vals)


def rule_rate(true_ic: float, sd: float, n: int, rng: np.random.Generator, trials: int = POWER_TRIALS) -> float:
    """Share of simulated records of ``n`` independent days in which the rule (mean > 0 and t >= 2) says "evidence"."""
    x = rng.normal(true_ic, sd, size=(trials, n))
    mean = x.mean(axis=1)
    t = mean / (x.std(axis=1, ddof=1) / math.sqrt(n))
    return float(((mean > 0) & (t >= T_RULE)).mean())


def power_part(by_i: Dict[int, List[Dict[str, Any]]], px, step: int, trials: int = POWER_TRIALS, seed: int = SEED) -> Dict[str, Any]:
    rng = np.random.default_rng(seed)
    out: Dict[str, Any] = {"rule": f"평균 > 0 이고 t >= {T_RULE:g}", "trials": trials, "tables": {}}
    for strategy, hs in POWER_HORIZONS.items():
        for h in hs:
            ic = ic_series(by_i, px, f"{strategy}|{VARIANT}", h, step)
            if len(ic) < 3:
                continue
            sd = float(ic.std(ddof=1))
            out["tables"][f"{strategy}|{h}"] = {"days": len(ic), "observed_mean_ic": float(ic.mean()), "ic_sd": sd, "sessions_per_sample": h,
                                                "rate": {f"{mu:g}": {str(n): rule_rate(mu, sd, n, rng, trials) for n in SAMPLES} for mu in TRUE_ICS}}
    return out


def run_once(base: Path, log=print) -> Dict[str, Any]:
    base = Path(base)
    out = base / REPORT
    if out.exists():
        raise RuntimeError("시뮬레이션은 한 번만 실행합니다. 이미 결과가 있습니다.")
    root = base / "data" / "qsf" / "research"
    with gzip.open(root / SCORES, "rt", encoding="utf-8") as fh:
        recs = json.load(fh)["records"]
    px = validate_open.OpenPrices(root / PRICES, validate_open.load_universe(base))
    by_i: Dict[int, List[Dict[str, Any]]] = {}
    for r in recs:
        by_i.setdefault(r["i"], []).append(r)
    log(f"평가 {len(recs)}건, 평가일 {len(by_i)}개")
    result = {"status": "REAL", "protocol": PROTOCOL, "variant": VARIANT, "evaluations": len(recs), "evaluation_days": len(by_i), "seed": SEED,
              "note": "과거 검증과 같은 표본의 새 통계량이며 독립된 새 증거가 아닙니다. 국면·이벤트 영역은 과거 이력이 없어 빠져 있습니다.",
              "picks": picks_part(by_i, px, validate.STEP), "power": power_part(by_i, px, validate.STEP)}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    return result
