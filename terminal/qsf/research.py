"""Historical check of the price-only part of US_SWING_V1 (REFERENCE ONLY).

Scores the technical and risk domains at fixed dates using only bars up to each date, with no parameter search, then measures
next-open to H-session-close returns net of the assumed cost, by score bucket, separately for each half of the period.

What this cannot show: fundamentals, events and regime have no point-in-time history here, so the full model is NOT backtested.
Members come from today's list filtered by join date, so removed stocks are missing (survivorship remains).  High and low are
approximated from open and close because the panel stores neither, which understates ATR.
"""
import statistics
from typing import Any, Dict, List, Optional

import numpy as np

from terminal.lab.backtest import members_at
from terminal.lab.panel import Panel
from terminal.qsf import config, engine, ledger

STEP = 20
HISTORY = 320
HORIZONS = (5, 10, 20, 30)
LIMITS = ["재무·이벤트·시장 국면은 시점 기준 이력이 없어 제외했습니다. 전체 모델의 백테스트가 아닙니다.",
          "지수에서 탈락한 종목이 빠져 있어 결과가 부풀려질 수 있습니다 (생존 편향).",
          "고가·저가가 없어 시가·종가로 근사했습니다. ATR이 실제보다 작게 계산됩니다.",
          "표본 기간이 약 5년으로 짧고, 겹치는 보유 기간은 독립 표본이 아닙니다."]


def _bars(p: Panel, j: int, i0: int, i1: int) -> List[Dict[str, Any]]:
    o, c, a, v = p.f("open"), p.f("close"), p.f("adj_close"), p.f("volume")
    out = []
    for i in range(i0, i1):
        if np.isfinite(c[i, j]):
            out.append({"date": p.dates[i], "open": float(o[i, j]) if np.isfinite(o[i, j]) else None, "high": None, "low": None, "close": float(c[i, j]),
                        "adj_close": float(a[i, j]) if np.isfinite(a[i, j]) else None, "volume": float(v[i, j]) if np.isfinite(v[i, j]) else None})
    return out


def run(p: Panel, universe: List[str], added: Optional[Dict[str, Optional[str]]], progress=None) -> Dict[str, Any]:
    cost = config.round_trip_cost("US")
    rows = list(range(HISTORY, len(p.dates) - max(HORIZONS) - 1, STEP))
    spy_j = p.col["SPY"]
    records: List[Dict[str, Any]] = []
    for n, i in enumerate(rows, 1):
        day = p.dates[i]
        bench = _bars(p, spy_j, i - HISTORY + 1, i + 1)
        for t in members_at(universe, added, day):
            if t not in p.col:
                continue
            b = _bars(p, p.col[t], i - HISTORY + 1, i + 1)
            if len(b) < config.MIN_BARS or b[-1]["date"] != day:
                continue
            ctx = {"market": "US", "bars": b, "bench": bench, "bench_name": "SPY", "fund": None, "events": None, "regime": None, "earnings": None, "expected_session": day}
            res = engine.score(ctx, "SWING")
            if res["gates"] or res["score"] is None:
                continue
            records.append({"date": day, "ticker": t, "score": res["score"]})
        if progress:
            progress(n, len(rows))
    paths: Dict[str, List[Dict]] = {}

    def path(t):
        if t not in paths:
            paths[t] = _bars(p, p.col[t], 0, len(p.dates))
        return paths[t]
    spy = path("SPY")
    dates = sorted({r["date"] for r in records})
    mid = dates[len(dates) // 2] if dates else None
    periods = {"전반": lambda d: d < mid, "후반": lambda d: d >= mid, "전체": lambda d: True}
    out: Dict[str, Any] = {"status": "REAL" if records else "UNAVAILABLE", "evaluated": len(records), "dates": len(dates), "first": dates[0] if dates else None, "last": dates[-1] if dates else None, "split": mid,
                           "step_sessions": STEP, "cost_round_trip_pct": cost * 100, "cost_basis": config.COSTS["US"]["basis"], "limitations": LIMITS, "model_version": config.MODEL_VERSION, "horizons": {}}
    for h in HORIZONS:
        by_period = {}
        outcomes = [(r, ledger.outcome(path(r["ticker"]), spy, r["date"], h, cost)) for r in records]
        for name, keep in periods.items():
            table = {}
            scores, rels = [], []
            for lo, hi in config.BUCKETS:
                key = f"{lo:g}-{min(hi, 100):.0f}"
                sel = [o for r, o in outcomes if o and lo <= r["score"] < hi and keep(r["date"]) and o["relative_net"] is not None]
                table[key] = {"n": len(sel), "mean_net": statistics.mean(o["net"] for o in sel) if sel else None, "mean_relative_net": statistics.mean(o["relative_net"] for o in sel) if sel else None,
                              "median_relative_net": statistics.median(o["relative_net"] for o in sel) if sel else None, "win_rate_vs_spy": sum(o["relative_net"] > 0 for o in sel) / len(sel) if sel else None,
                              "mean_worst": statistics.mean(o["worst"] for o in sel) if sel else None}
            for r, o in outcomes:
                if o and o["relative_net"] is not None and keep(r["date"]):
                    scores.append(r["score"])
                    rels.append(o["relative_net"])
            by_period[name] = {"buckets": table, "spearman_score_vs_relative": _spearman(scores, rels), "n": len(rels)}
        out["horizons"][str(h)] = {**by_period, "independent_samples_approx": len(dates) * STEP / h if h >= STEP else len(dates)}
    return out


def _spearman(a: List[float], b: List[float]) -> Optional[float]:
    if len(a) < 30:
        return None
    ra, rb = np.argsort(np.argsort(a)), np.argsort(np.argsort(b))
    return float(np.corrcoef(ra, rb)[0, 1])
