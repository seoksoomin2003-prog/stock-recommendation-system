"""Dynamic liquid-300 universe (KR-DATA-0.1 §5).

1. eligible = security-master rows with ``eligible`` (common operating-company stock).
2. bars validated row by row (market_data.validate_rows); invalid rows are not observations.
3. ADTV20 = mean traded value over the last 20 *valid* session observations (missing sessions are
   skipped, never zero; a genuine zero-volume session is a valid observation of 0).
4. A security needs >= 20 valid observations, a last bar equal to the latest KRX session, and no
   halt signature (3 trailing zero-volume sessions); otherwise it is excluded with a reason.
5. rank by ADTV20 descending (ties: security key ascending) and keep the top N (default 300).
No absolute KRW floor is applied (KR-0.1): the 300th ADTV is recorded on every snapshot so that the need
for a floor can be assessed from evidence.
"""
from typing import Dict

import numpy as np
import pandas as pd

from markets.kr.market_data import series_checks

WINDOW = 20
DEFAULT_SIZE = 300


def build(master: pd.DataFrame, bars: pd.DataFrame, sessions: pd.DatetimeIndex, latest_session: pd.Timestamp,
          size: int = DEFAULT_SIZE, window: int = WINDOW) -> Dict:
    elig = master[master["eligible"].astype(bool)].copy()
    by = {t: g.sort_values("date") for t, g in bars.groupby("ticker")} if not bars.empty else {}
    rows = []
    for r in elig.itertuples():
        g = by.get(r.canonical_ticker)
        rec = {"security_key": r.security_key, "ticker": r.canonical_ticker, "company_name": r.company_name,
               "market": r.market, "industry": r.industry, "industry_class": r.industry_class}
        if g is None or g.empty:
            rows.append({**rec, "adtv20": np.nan, "valid_observations": 0, "status": "EXCLUDED",
                         "reason": "NO_MARKET_DATA"})
            continue
        chk = series_checks(g, sessions, latest_session)
        valid = g[g["quality_status"] == "REAL"].dropna(subset=["traded_value"])
        tail = valid.tail(window)
        adtv = float(tail["traded_value"].mean()) if len(valid) >= window else np.nan
        rec.update(adtv20=adtv, valid_observations=int(len(valid)), last_bar=chk.get("last_bar"),
                   window_first=str(tail["date"].min().date()) if len(tail) else None,
                   window_last=str(tail["date"].max().date()) if len(tail) else None,
                   traded_value_basis=(tail["traded_value_basis"].iloc[-1] if len(tail) else None),
                   flags=";".join(chk.get("flags", [])))
        if "STALE" in chk.get("flags", []):
            reason = "STALE_LAST_BAR"
        elif "ZERO_VOLUME_RUN_HALT_SUSPECTED" in chk.get("flags", []):
            reason = "HALT_SUSPECTED"
        elif len(valid) < window:
            reason = "INSUFFICIENT_VALID_OBSERVATIONS"
        else:
            reason = None
        rows.append({**rec, "status": "EXCLUDED" if reason else "CANDIDATE", "reason": reason})
    df = pd.DataFrame(rows)
    cand = df[df["status"] == "CANDIDATE"].sort_values(["adtv20", "security_key"], ascending=[False, True])
    cand = cand.reset_index(drop=True)
    cand["liquidity_rank"] = np.arange(1, len(cand) + 1)
    members = cand.head(size)
    df = df.merge(cand[["security_key", "liquidity_rank"]], on="security_key", how="left")
    df.loc[df["security_key"].isin(members["security_key"]), "status"] = "MEMBER"
    df.loc[(df["status"] == "CANDIDATE"), ["status", "reason"]] = ["NOT_SELECTED", "BELOW_LIQUID_300_RANK"]
    summary = {"size_target": size, "members": int(len(members)), "candidates": int(len(cand)),
               "eligible_master_rows": int(len(elig)),
               "by_market": {k: int(v) for k, v in members["market"].value_counts().items()},
               "adtv20_at_cutoff_krw": float(members["adtv20"].iloc[-1]) if len(members) else None,
               "adtv20_median_member_krw": float(members["adtv20"].median()) if len(members) else None,
               "exclusions": {k: int(v) for k, v in df.loc[df["status"] == "EXCLUDED", "reason"].value_counts().items()},
               "latest_session": str(pd.Timestamp(latest_session).date()), "window": window,
               "traded_value_basis": sorted(set(members.get("traded_value_basis", pd.Series(dtype=str)).dropna()))}
    return {"table": df, "members": members, "summary": summary}


def stability(prev_members, cur_members) -> Dict:
    a, b = set(prev_members), set(cur_members)
    if not a or not b:
        return {"overlap": None}
    return {"overlap": len(a & b), "entered": sorted(b - a)[:50], "left": sorted(a - b)[:50],
            "jaccard": round(len(a & b) / len(a | b), 4)}
