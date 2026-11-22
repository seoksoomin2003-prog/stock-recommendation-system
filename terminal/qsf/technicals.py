"""Price-derived indicators and stop/target reference levels.  Pure functions of the bars passed in: a caller
scoring a past date passes bars up to that date, so nothing here can see the future."""
from typing import Any, Dict, List, Optional

import numpy as np

from terminal.qsf import config


def _ma(a: np.ndarray, n: int) -> np.ndarray:
    out = np.full(len(a), np.nan)
    if len(a) >= n:
        c = np.cumsum(np.insert(a, 0, 0.0))
        out[n - 1:] = (c[n:] - c[:-n]) / n
    return out


def _ema(a: np.ndarray, n: int) -> np.ndarray:
    k, out = 2 / (n + 1), np.empty(len(a))
    out[0] = a[0]
    for i in range(1, len(a)):
        out[i] = a[i] * k + out[i - 1] * (1 - k)
    return out


def _last(a: np.ndarray) -> Optional[float]:
    return float(a[-1]) if len(a) and np.isfinite(a[-1]) else None


def _ret(a: np.ndarray, n: int) -> Optional[float]:
    return float(a[-1] / a[-1 - n] - 1) if len(a) > n and a[-1 - n] > 0 else None


def compute(bars: List[Dict[str, Any]], bench: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Indicators at the last bar.  Missing high/low fall back to open/close (flagged by ``approx_range``)."""
    c = np.array([b["close"] for b in bars], dtype=float)
    o = np.array([b.get("open") if b.get("open") is not None else b["close"] for b in bars], dtype=float)
    approx = any(b.get("high") is None or b.get("low") is None for b in bars)
    h = np.array([b["high"] if b.get("high") is not None else max(b["close"], o[i]) for i, b in enumerate(bars)], dtype=float)
    lo = np.array([b["low"] if b.get("low") is not None else min(b["close"], o[i]) for i, b in enumerate(bars)], dtype=float)
    v = np.array([b.get("volume") if b.get("volume") is not None else np.nan for b in bars], dtype=float)
    adj = np.array([b.get("adj_close") if b.get("adj_close") is not None else b["close"] for b in bars], dtype=float)
    n = len(c)
    ma20, ma50, ma200 = _ma(c, 20), _ma(c, 50), _ma(c, 200)
    tr = np.maximum(h[1:] - lo[1:], np.maximum(np.abs(h[1:] - c[:-1]), np.abs(lo[1:] - c[:-1]))) if n > 1 else np.array([])
    atr = float(tr[-14:].mean()) if len(tr) >= 14 else None
    r = np.diff(adj) / adj[:-1] if n > 1 else np.array([])
    # RSI (simple 14-session average of gains and losses)
    rsi = None
    if n > 14:
        d = np.diff(c[-15:])
        up, dn = d[d > 0].sum() / 14, -d[d < 0].sum() / 14
        rsi = 100.0 if dn == 0 else 100 - 100 / (1 + up / dn)
    macd_hist = None
    if n >= 35:
        macd = _ema(c, 12) - _ema(c, 26)
        macd_hist = float((macd - _ema(macd, 9))[-1])
    bw_pct, bw = None, None
    if n >= 40:
        sd = np.array([c[i - 19:i + 1].std(ddof=0) if i >= 19 else np.nan for i in range(n)])
        with np.errstate(invalid="ignore", divide="ignore"):
            width = 4 * sd / ma20
        hist = width[np.isfinite(width)][-252:]
        if len(hist) >= 20 and np.isfinite(width[-1]):
            bw, bw_pct = float(width[-1]), float((hist <= width[-1]).mean())

    win = c[-252:]
    peak = np.maximum.accumulate(c[-252:]) if n else np.array([])
    max_dd = float((win / peak - 1).min()) if n else None
    prior20 = float(h[-21:-1].max()) if n > 21 else None
    avg20v = float(np.nanmean(v[-21:-1])) if n > 21 and np.isfinite(v[-21:-1]).any() else None
    adv_vals = (c[-20:] * v[-20:])
    adv_value = float(np.nanmean(adv_vals)) if np.isfinite(adv_vals).any() else None
    gaps = np.abs(o[1:] / c[:-1] - 1)[-60:] if n > 1 else np.array([])
    months = [adj[i] / adj[i - 21] - 1 for i in range(n - 1, 21, -21)][:12] if n > 22 else []
    neg = r[-252:][r[-252:] < 0]
    out = {
        "n": n, "date": bars[-1]["date"], "close": float(c[-1]), "approx_range": approx,
        "ma20": _last(ma20), "ma50": _last(ma50), "ma200": _last(ma200),
        "ma50_slope": float(ma50[-1] / ma50[-21] - 1) if n >= 70 else None,
        "ma200_slope": float(ma200[-1] / ma200[-64] - 1) if n >= 263 else None,
        "atr": atr, "atr_pct": atr / c[-1] if atr else None, "rsi": rsi,
        "macd_hist_pct": macd_hist / c[-1] if macd_hist is not None else None,
        "bandwidth": bw, "bandwidth_pct": bw_pct,
        "ret_21": _ret(adj, 21), "ret_63": _ret(adj, 63), "ret_126": _ret(adj, 126), "ret_252": _ret(adj, 252),
        "ret_12_1": float(adj[-22] / adj[-253] - 1) if n >= 253 else None,
        "high_252": float(h[-252:].max()), "low_252": float(lo[-252:].min()),
        "dist_high": float(c[-1] / h[-252:].max() - 1), "prior20_high": prior20,
        "breakout": bool(prior20 is not None and c[-1] > prior20),
        "volume_ratio": float(v[-1] / avg20v) if avg20v and np.isfinite(v[-1]) else None,
        "adv_value": adv_value, "last_volume": float(v[-1]) if np.isfinite(v[-1]) else None,
        "max_drawdown_252": max_dd, "max_gap_60": float(gaps.max()) if len(gaps) else None,
        "gap_today": float(o[-1] / c[-2] - 1) if n > 1 else None,
        "held_gap": bool(n > 1 and c[-1] >= o[-1]),
        "hist_vol": float(r[-252:].std(ddof=1) * np.sqrt(252)) if len(r) >= 60 else None,
        "downside_vol": float(np.sqrt((neg ** 2).sum() / max(len(r[-252:]), 1)) * np.sqrt(252)) if len(r) >= 60 else None,
        "pos_month_share": float(np.mean([m > 0 for m in months])) if len(months) >= 6 else None,
        "max_move_5": float(np.abs(c[-5:] / c[-6:-1] - 1).max()) if n > 5 else None,
        "max_move_252": float(np.abs(c[-252:] / c[-253:-1] - 1).max()) if n > 252 else float(np.abs(c[1:] / c[:-1] - 1).max()) if n > 1 else None,
        # rows whose date repeats the row before or goes back: a provider's doubled or late-corrected row (audit 2026-11-22, ENG-06:
        # a doubled last row moved RSI from 62.4 to 66.0 and nothing said so)
        "row_defects": sum(1 for i in range(1, n) if bars[i]["date"] <= bars[i - 1]["date"]),
        "support_60": float(lo[-60:].min()), "low_20": float(lo[-20:].min()),
        "resistance": _resistance(h, c[-1], atr),
    }
    if bench and len(bench) > 1:
        bmap = {b["date"]: (b.get("adj_close") or b["close"]) for b in bench}
        pairs = [(a, bmap[b["date"]]) for a, b in zip(adj, bars) if b["date"] in bmap]
        if len(pairs) > 126:
            s, m = np.array([p[0] for p in pairs]), np.array([p[1] for p in pairs])
            out["rel_63"] = float(s[-1] / s[-64] / (m[-1] / m[-64]) - 1)
            out["rel_126"] = float(s[-1] / s[-127] / (m[-1] / m[-127]) - 1)
    return out


def _resistance(h: np.ndarray, close: float, atr: Optional[float]) -> Optional[float]:
    """Nearest swing high at least one ATR above the close, from the last year's bars (None if none exists)."""
    if not atr:
        return None
    w = h[-252:]
    pivots = [w[i] for i in range(5, len(w) - 5) if w[i] == w[i - 5:i + 6].max() and w[i] >= close + atr]
    return float(min(pivots)) if pivots else None


def levels(t: Dict[str, Any], market: str) -> Dict[str, Any]:
    """Swing reference levels.  The stop is a scenario (2 ATR), not a guaranteed fill: gaps can fill worse."""
    if not t.get("atr"):
        return {"status": "UNAVAILABLE", "reason": "ATR을 계산할 이력이 부족합니다."}
    p = config.SWING
    entry, atr = t["close"], t["atr"]
    stop = entry - p["stop_atr"] * atr
    if t.get("resistance"):
        target, method = t["resistance"], "1년 내 저항선(스윙 고점)"
    else:
        target, method = entry + p["projection_atr"] * atr, f"위에 저항선이 없어 {p['projection_atr']:g} ATR 변동성 투영"
    cost = config.round_trip_cost(market) * entry
    risk, reward = entry - stop + cost, target - entry - cost
    return {"status": "REAL", "entry": entry, "stop": stop, "target": target, "target_method": method,
            "stop_method": f"{p['stop_atr']:g} ATR 시나리오", "reward_risk": reward / risk if risk > 0 else None,
            "cost_basis": config.COSTS[market]["basis"], "round_trip_cost_pct": config.round_trip_cost(market) * 100}
