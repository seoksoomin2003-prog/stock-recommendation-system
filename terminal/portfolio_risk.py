"""Risk of the current holdings, measured on the past year of daily prices with today's weights held fixed.

Read only.  What it says is how the account would have moved over the last year if it had held today's weights all along: a
description of the mix, not a forecast or a loss limit.  Cash is a zero-return asset.  A holding with too little shared price history
is listed and left out of the calculation, never filled in.
"""
import math
from typing import Any, Dict, List, Optional

import numpy as np

DAYS = 252
MIN_DAYS = 120


def _series(rows: Optional[List[Dict[str, Any]]]) -> Dict[str, float]:
    out = {}
    for r in rows or []:
        v = r.get("adj_close") or r.get("close")
        if isinstance(v, (int, float)) and math.isfinite(v) and v > 0 and r.get("date"):
            out[r["date"]] = float(v)
    return out


def analyse(weights: Dict[str, float], history: Dict[str, List[Dict[str, Any]]], bench: List[Dict[str, Any]], equity: Optional[float]) -> Dict[str, Any]:
    """``weights``: each holding's share of the whole account (0-1, cash is the rest).  ``history``: daily bars per holding."""
    b = _series(bench)
    if len(b) < MIN_DAYS + 1:
        return {"status": "UNAVAILABLE", "reason": "NO_BENCHMARK"}
    dates = sorted(b)[-(DAYS + 1):]
    series = {t: _series(history.get(t)) for t in weights}
    short = sorted(t for t, s in series.items() if sum(d in s for d in dates) < MIN_DAYS + 1)
    used = [t for t in weights if t not in short and weights[t] > 0]
    if not used:
        return {"status": "UNAVAILABLE", "reason": "NO_HISTORY", "short_history": short}
    common = [d for d in dates if all(d in series[t] for t in used)]
    if len(common) < MIN_DAYS + 1:
        return {"status": "UNAVAILABLE", "reason": "NO_COMMON_DAYS", "short_history": short}
    px = np.array([[series[t][d] for t in used] for d in common])
    R = px[1:] / px[:-1] - 1
    bv = np.array([b[d] for d in common])
    br = bv[1:] / bv[:-1] - 1
    w = np.array([weights[t] for t in used])
    p = R @ w
    cov = np.cov(R, rowvar=False, ddof=1).reshape(len(used), len(used))
    var_p = float(w @ cov @ w)
    var_b = float(np.var(br, ddof=1))
    beta = lambda x: float(np.cov(x, br, ddof=1)[0, 1] / var_b) if var_b > 0 else None          # noqa: E731
    contrib = (w * (cov @ w)) / var_p if var_p > 0 else np.full(len(used), np.nan)
    sd = np.sqrt(np.diag(cov))
    corr = cov / np.outer(sd, sd) if np.all(sd > 0) else None
    cum = np.cumprod(1 + p)
    peak = np.maximum.accumulate(np.concatenate([[1.0], cum]))[1:]
    q5 = float(np.percentile(p, 5))
    tail = p[p <= q5]
    roll = [float(np.prod(1 + p[i:i + 20]) - 1) for i in range(len(p) - 19)]
    stock_w = float(w.sum())
    holdings = [{"ticker": t, "weight": float(weights[t]), "volatility": float(sd[i] * math.sqrt(DAYS)), "beta": beta(R[:, i]),
                 "risk_share": float(contrib[i]) if math.isfinite(contrib[i]) else None} for i, t in enumerate(used)]
    holdings.sort(key=lambda h: -(h["risk_share"] or 0))
    money = lambda x: x * equity if equity else None                                              # noqa: E731
    return {"status": "REAL", "days": len(p), "from": common[0], "to": common[-1], "holdings": holdings, "short_history": short,
            "invested": stock_w, "volatility": math.sqrt(var_p * DAYS), "benchmark_volatility": math.sqrt(var_b * DAYS), "beta": beta(p),
            "var95": -q5, "var95_amount": money(-q5), "es95": float(-tail.mean()), "es95_amount": money(float(-tail.mean())),
            "worst_day": float(p.min()), "worst_day_date": common[1 + int(p.argmin())], "worst_20d": min(roll) if roll else None,
            "max_drawdown": float((cum / peak - 1).min()), "return_1y": float(cum[-1] - 1),
            "effective_n": float(1 / np.sum((w / stock_w) ** 2)) if stock_w > 0 else None,
            "correlation": {"tickers": used, "matrix": corr.tolist()} if corr is not None and len(used) <= 15 else None,
            "avg_correlation": float((corr.sum() - len(used)) / (len(used) * (len(used) - 1))) if corr is not None and len(used) > 1 else None}
