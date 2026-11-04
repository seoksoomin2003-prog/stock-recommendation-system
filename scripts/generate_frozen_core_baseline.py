"""Capture the P6-11B frozen-core numerical baseline (P6-18).

Run ONCE against the unmodified frozen engines; the JSON it writes is the
golden reference used by ``tests/test_p6_18_frozen_core_parity.py``.
Re-running it after a change would silently re-baseline, so the script refuses
to overwrite an existing file unless ``--force`` is passed.

The fixture is fully deterministic (seeded RNG, fixed calendar) and touches no
network or production data.
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd

from core.decision_engine import DecisionEngine
from core.factor_engine import FactorEngine
from core.ranking_engine import RankingEngine
from core.scoring_engine import ScoringEngine
from utils.config import DEFAULT_FACTOR_WEIGHTS

OUT = PROJECT_ROOT / "tests" / "fixtures" / "frozen_core_baseline_p6_18.json"
AS_OF = datetime(2026, 1, 15, 12, tzinfo=timezone.utc)


def build_fixture():
    rng = np.random.default_rng(20261104)
    n = 24
    tickers = [f"F{i:02d}" for i in range(n)]
    dates = pd.bdate_range("2024-06-03", periods=430)
    drift = rng.normal(0.0004, 0.0006, n)
    vol = rng.uniform(0.008, 0.03, n)
    rets = rng.normal(drift, vol, size=(len(dates), n))
    prices = pd.DataFrame(100 * np.exp(np.cumsum(rets, axis=0)), index=dates, columns=tickers)
    financials = pd.DataFrame({
        "per": rng.uniform(5, 60, n),
        "pbr": rng.uniform(0.5, 20, n),
        "roe": rng.normal(0.15, 0.1, n),
        "profitMargin": rng.normal(0.12, 0.08, n),
    }, index=tickers)
    # Genuine missingness must be preserved (not median-filled in the matrix).
    financials.loc["F03", "per"] = np.nan
    financials.loc["F07", "roe"] = np.nan
    volumes = pd.Series(rng.uniform(200_000, 3_000_000, n), index=tickers)
    volumes["F05"] = 499_999.0
    volumes["F06"] = 500_000.0
    sectors = ["Technology" if i % 3 == 0 else ("Healthcare" if i % 3 == 1 else "Energy") for i in range(n)]
    return tickers, prices, financials, volumes, sectors


def candidates_from(tickers, prices, scores, volumes, sectors):
    pct = scores.rank(pct=True)
    out = []
    for i, t in enumerate(tickers):
        s = prices[t].dropna()
        close = float(s.iloc[-1])
        atr = float(s.pct_change().abs().rolling(14).mean().iloc[-1] * close)
        ema20 = float(s.ewm(span=20, adjust=False).mean().iloc[-1])
        out.append({
            "security_id": f"fx:{t}", "ticker": t, "close": close, "volume": float(volumes[t]),
            "alpha": float(scores[t]), "atr": atr, "ema20": ema20,
            "entry_readiness": float(close > ema20), "alpha_percentile": float(pct[t]),
            "sector": sectors[i], "data_status": "REAL", "price_status": "REAL",
            "volume_status": "REAL", "fundamental_status": "REAL",
        })
    return out


def _f(x):
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else float(x)


def compute():
    tickers, prices, financials, volumes, sectors = build_fixture()
    fm = FactorEngine().get_factor_matrix(prices, financials)
    std = RankingEngine().apply_cross_sectional_standardization(fm)
    scores = ScoringEngine(DEFAULT_FACTOR_WEIGHTS).calculate(std, weights=DEFAULT_FACTOR_WEIGHTS)
    cands = candidates_from(tickers, prices, scores, volumes, sectors)
    rank_e = RankingEngine().calculate_model_rank_e([dict(c) for c in cands], 10_000.0)
    decisions = {}
    for regime in ("BULL", "SIDEWAYS", "BEAR"):
        for capital in (10_000.0, 10_000_000.0):
            d = DecisionEngine().evaluate_portfolio(AS_OF, capital, regime, [dict(c) for c in cands])
            decisions[f"{regime}_{int(capital)}"] = {
                "data_quality": d.data_quality,
                "top5": [[s.ticker, s.target_weight, s.target_shares, s.hard_stop, s.sector] for s in d.top5],
                "watchlist5": [[s.ticker, s.reason_codes] for s in d.watchlist5],
                "sector_exposure": d.sector_exposure,
            }
    return {
        "factor_matrix": {c: {t: _f(v) for t, v in fm[c].items()} for c in fm.columns},
        "standardized": {c: {t: _f(v) for t, v in std[c].items()} for c in std.columns},
        "scores": {t: _f(v) for t, v in scores.items()},
        "model_rank_e_order": [c["ticker"] for c in rank_e],
        "model_rank_e_combined": {c["ticker"]: _f(c["combined_score"]) for c in rank_e},
        "decisions": decisions,
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    if OUT.exists() and not args.force:
        sys.exit(f"{OUT} exists; refusing to re-baseline without --force")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {"generated_at": datetime.now(timezone.utc).isoformat(),
               "note": "Captured from unmodified P6-11B engines before P6-18 changes.",
               "result": compute()}
    OUT.write_text(json.dumps(payload, indent=1, sort_keys=True))
    print(f"wrote {OUT}")
