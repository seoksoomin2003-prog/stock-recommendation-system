"""How much the live score moves from one session to the next.  Read only: the ledger's scores, no price and no return.

A score that reshuffles its buy candidates every day without news is hard to act on, whatever its long-run evidence.  Only
consecutive sessions of the same model version are compared, so a version change is never counted as instability.
"""
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from terminal.qsf import config, validate
from terminal.qsf.ledger import Ledger

BUY = validate.BUY_SCORE
MIN_COMMON = 30


def band_of(score: float) -> str:
    return next(name for floor, name, _ in config.BANDS if score >= floor)


def sessions(led: Ledger, market: str, strategy: str) -> List[Dict[str, Any]]:
    """One entry per ledger session: its model versions and the fresh scores by ticker."""
    out: Dict[str, Dict[str, Any]] = {}
    for r in led._live_rows():
        if r["market"] != market:
            continue
        day = out.setdefault(r["session"], {"session": r["session"], "versions": set(), "scores": {}})
        for s in led._load(r):
            if s.get("strategy") == strategy and s.get("score") is not None and s.get("data_date") == r["session"]:
                day["scores"][s["ticker"]] = float(s["score"])
                day["versions"].add(str(s.get("model_version")))
    return [out[d] for d in sorted(out)]


def compare(a: Dict[str, float], b: Dict[str, float]) -> Optional[Dict[str, Any]]:
    common = sorted(set(a) & set(b))
    if len(common) < MIN_COMMON:
        return None
    x, y = np.array([a[t] for t in common]), np.array([b[t] for t in common])
    buy_a, buy_b = {t for t in common if a[t] >= BUY}, {t for t in common if b[t] >= BUY}
    union = buy_a | buy_b
    return {"stocks": len(common), "rank_correlation": float(np.corrcoef(validate.rank(x), validate.rank(y))[0, 1]) if x.std() > 0 and y.std() > 0 else None,
            "mean_abs_change": float(np.abs(y - x).mean()), "moved_5_points_share": float((np.abs(y - x) >= 5).mean()),
            "band_changed_share": float(np.mean([band_of(p) != band_of(q) for p, q in zip(x, y)])),
            "buy_before": len(buy_a), "buy_after": len(buy_b), "buy_turnover": len(buy_a ^ buy_b) / len(union) if union else None}


def measure(days: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Consecutive sessions of one and the same model version."""
    rows = []
    for a, b in zip(days, days[1:]):
        if len(a["versions"]) == 1 and a["versions"] == b["versions"]:
            c = compare(a["scores"], b["scores"])
            if c:
                rows.append({"from": a["session"], "to": b["session"], "version": next(iter(a["versions"])), **c})

    def mean(key: str) -> Optional[float]:
        v = [r[key] for r in rows if r.get(key) is not None]
        return float(np.mean(v)) if v else None
    return {"pairs": len(rows), "sessions": len(days), "rank_correlation": mean("rank_correlation"), "mean_abs_change": mean("mean_abs_change"),
            "moved_5_points_share": mean("moved_5_points_share"), "band_changed_share": mean("band_changed_share"), "buy_turnover": mean("buy_turnover"), "last": rows[-1] if rows else None}


def report(base: Path) -> Dict[str, Any]:
    led = Ledger(Path(base))
    out: Dict[str, Any] = {"status": "REAL", "note": "같은 모델 버전의 이어진 두 거래일만 비교합니다. 수익은 읽지 않습니다.", "cohorts": {}}
    for market in config.MARKETS:
        for strategy in config.STRATEGIES:
            out["cohorts"][f"{market}_{strategy}"] = measure(sessions(led, market, strategy))
    return out
