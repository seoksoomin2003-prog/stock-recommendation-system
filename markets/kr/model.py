"""Independent Korean model KR-EXP-0.1 (status EXPERIMENTAL).  See reports/KR_MODEL_SPECIFICATION.md.

Nothing here derives from P6-11B: own factors, own transformation (winsorised z-scores), own weights,
own portfolio rules.  Inputs are daily OHLCV only (OpenDART fundamentals are specified for a later
version and are inactive while OPENDART_API_KEY is unavailable / unvalidated).
"""
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from markets.kr import KR_MODEL_STATUS, KR_MODEL_VERSION

# Candidate factors (research).  value = function(adj_close wide frame up to t) -> Series per ticker.
# direction +1: higher raw value is better.  min_history: valid sessions required.
FACTOR_CANDIDATES = {
    "MOM_6_1": {"desc": "return from t-126 to t-21 sessions (adjusted close)", "direction": +1, "min_history": 127},
    "REV_1M": {"desc": "minus the return over the last 21 sessions (short-term reversal)", "direction": +1,
               "min_history": 22},
    "LOWVOL_60": {"desc": "minus the std of daily log returns over 60 sessions", "direction": +1,
                  "min_history": 61},
    "TREND_50": {"desc": "close / 50-session mean close - 1", "direction": +1, "min_history": 50},
}
# KR-EXP-0.1 active set and weights -- fixed by the pre-registered rule in KR_MODEL_RESEARCH_SPECIFICATION
# (equal weights over factors that survived the inclusion test; never fitted to returns).
# Confirmed by reports/KR_FACTOR_STUDY_RESULTS.json (2026-11-04): MOM_6_1, REV_1M, LOWVOL_60 KEPT;
# TREND_50 DROPPED as redundant with REV_1M (rank corr -0.85).  No factor had |t| > 1: no predictive evidence.
ACTIVE_FACTORS: List[str] = ["MOM_6_1", "REV_1M", "LOWVOL_60"]
WEIGHTS: Dict[str, float] = {f: 1.0 / len(ACTIVE_FACTORS) for f in ACTIVE_FACTORS}
WINSOR = (0.01, 0.99)
TOP_N = 10
MAX_PER_INDUSTRY = 3
HOLDING_SESSIONS = 20


def raw_factors(adj: pd.DataFrame, factors=None) -> pd.DataFrame:
    """adj: wide frame (index = sessions ascending, columns = tickers) of adjusted closes, valid only.
    Uses only rows up to the last index (no look-ahead).  Insufficient history -> NaN (never filled)."""
    factors = factors or list(FACTOR_CANDIDATES)
    out = {}
    n_valid = adj.notna().sum()
    for f in factors:
        need = FACTOR_CANDIDATES[f]["min_history"]
        if f == "MOM_6_1":
            v = adj.shift(21).iloc[-1] / adj.shift(126).iloc[-1] - 1
        elif f == "REV_1M":
            v = -(adj.iloc[-1] / adj.shift(21).iloc[-1] - 1)
        elif f == "LOWVOL_60":
            lr = np.log(adj / adj.shift(1)).iloc[-60:]
            v = -lr.std(ddof=1).where(lr.notna().sum() >= 55)
        elif f == "TREND_50":
            v = adj.iloc[-1] / adj.iloc[-50:].mean() - 1
        else:
            raise KeyError(f)
        out[f] = v.where(n_valid >= need)
    return pd.DataFrame(out)


def standardize(raw: pd.DataFrame) -> pd.DataFrame:
    """Cross-sectional winsorise (1%/99%) then z-score over the rows given (the gated cross-section)."""
    z = {}
    for c in raw.columns:
        s = raw[c].astype(float)
        lo, hi = s.quantile(WINSOR[0]), s.quantile(WINSOR[1])
        w = s.clip(lo, hi)
        sd = w.std(ddof=0)
        z[c] = (w - w.mean()) / sd if sd and np.isfinite(sd) and sd > 0 else w * np.nan
    return pd.DataFrame(z, index=raw.index)


def standardize_against(raw_point: pd.DataFrame, reference_raw: pd.DataFrame) -> pd.DataFrame:
    """Score rows NOT in the cross-section (direct evaluation) using the reference distribution only:
    the evaluated rows never influence the reference statistics."""
    z = {}
    for c in raw_point.columns:
        ref = reference_raw[c].astype(float)
        lo, hi = ref.quantile(WINSOR[0]), ref.quantile(WINSOR[1])
        w = ref.clip(lo, hi)
        mu, sd = w.mean(), w.std(ddof=0)
        z[c] = (raw_point[c].astype(float).clip(lo, hi) - mu) / sd
    return pd.DataFrame(z, index=raw_point.index)


def score(z: pd.DataFrame) -> pd.Series:
    cols = [f for f in ACTIVE_FACTORS]
    s = sum(z[f] * WEIGHTS[f] * FACTOR_CANDIDATES[f]["direction"] for f in cols)
    return s.where(z[cols].notna().all(axis=1))


def rank(scores: pd.Series, keys: pd.Series) -> pd.DataFrame:
    df = pd.DataFrame({"score": scores, "key": keys}).dropna(subset=["score"])
    df = df.sort_values(["score", "key"], ascending=[False, True])
    df["rank"] = np.arange(1, len(df) + 1)
    return df


def portfolio(ranked: pd.DataFrame, info: pd.DataFrame, capital_krw: float, closes: pd.Series) -> Dict:
    """TOP-10 equal weight, at most 3 names per KRX industry; whole shares (KRX has no fractional shares)."""
    picks, per_ind, skipped = [], {}, []
    for t, r in ranked.iterrows():
        ind = info.loc[t, "industry"] if t in info.index else None
        if per_ind.get(ind, 0) >= MAX_PER_INDUSTRY:
            skipped.append({"ticker": t, "rank": int(r["rank"]), "reason": "INDUSTRY_CAP"})
            continue
        picks.append(t)
        per_ind[ind] = per_ind.get(ind, 0) + 1
        if len(picks) == TOP_N:
            break
    w = 1.0 / TOP_N
    pos = []
    for t in picks:
        px = float(closes[t])
        shares = int(np.floor(capital_krw * w / px)) if capital_krw and px > 0 else 0
        pos.append({"ticker": t, "rank": int(ranked.loc[t, "rank"]), "score": float(ranked.loc[t, "score"]),
                    "target_weight": w, "reference_close_krw": px, "shares": shares,
                    "allocated_krw": shares * px, "funded": shares > 0})
    invested = sum(p["allocated_krw"] for p in pos)
    exposure = {}
    for t in picks:
        exposure[info.loc[t, "industry"]] = exposure.get(info.loc[t, "industry"], 0) + w
    return {"positions": pos, "industry_cap_skips": skipped[:20], "cash_krw": capital_krw - invested if capital_krw else None,
            "industry_exposure": exposure, "complete": len(pos) == TOP_N,
            # selection is unchanged by capital; a slice smaller than one share is reported, never re-sized
            "unfunded_positions": [p["ticker"] for p in pos if not p["funded"]],
            "model_version": KR_MODEL_VERSION, "model_status": KR_MODEL_STATUS}
