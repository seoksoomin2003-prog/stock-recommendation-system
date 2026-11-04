"""KR factor research study (P6-23 §5.2).  Diagnostic, NOT a backtest of the strategy.

PRE-REGISTERED RULE (fixed in code before results were observed, 2026-11-04):
  candidates, in priority order: MOM_6_1, REV_1M, LOWVOL_60, TREND_50
  * rebalance every 21 sessions; forward return = adjusted close t -> t+20 sessions (non-overlapping)
  * statistic: cross-sectional Spearman rank IC of the direction-adjusted factor vs forward return
  * DROP a factor if its mean IC t-statistic < -2.0 (significantly opposite to its hypothesis)
  * DROP a factor if its mean cross-sectional rank correlation with an already-kept factor > 0.70
  * weights: equal over kept factors (never fitted)
KNOWN BIASES: the universe is TODAY's liquid-300 looked back in time (survivorship and look-ahead in
membership); Yahoo supplementary prices; no transaction costs.  The result may only inform inclusion,
never claim predictive power.
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from markets.kr import KR_DATA_SPEC_VERSION, acquisition, security_master, universe  # noqa: E402
from markets.kr import calendar as krcal  # noqa: E402
from markets.kr.market_data import YahooKRProvider  # noqa: E402
from markets.kr.model import FACTOR_CANDIDATES, raw_factors  # noqa: E402
from markets.storage import data_dir  # noqa: E402

PRIORITY = ["MOM_6_1", "REV_1M", "LOWVOL_60", "TREND_50"]
T_DROP, CORR_DROP, STEP, HORIZON = -2.0, 0.70, 21, 20


def main(out_path="reports/KR_FACTOR_STUDY_RESULTS.json", years=3.2):
    now = datetime.now(timezone.utc)
    ddir = data_dir("KR")
    m = security_master.load_master(ddir)
    master = m["master"]
    prov = YahooKRProvider()
    s, e = acquisition.window(now, 70)
    idx = acquisition.index_bars(prov, *acquisition.window(now, int(365 * years) + 10), now)
    sessions = pd.DatetimeIndex(idx["KOSPI"].index)
    latest = krcal.latest_completed_session(idx["KOSPI"], now)
    elig = master[master["eligible"].astype(bool)]
    ub = acquisition.bars(prov, elig, s, e, now, ddir / "cache", "universe")
    uni = universe.build(master, ub["bars"], sessions[sessions >= pd.Timestamp(s)], latest)
    members = master.set_index("canonical_ticker").loc[uni["members"]["ticker"]].reset_index()
    hs, he = acquisition.window(now, int(365 * years))
    hb = acquisition.bars(YahooKRProvider(), members, hs, he, now, ddir / "cache", "history")
    adj = acquisition.wide_adjusted(hb["bars"]).reindex(sessions[sessions >= pd.Timestamp(hs)])
    dates = adj.index
    ics = {f: [] for f in PRIORITY}
    corr = {(a, b): [] for a in PRIORITY for b in PRIORITY if a < b}
    used = []
    for i in range(126, len(dates) - HORIZON, STEP):
        hist = adj.iloc[: i + 1]
        fwd = adj.iloc[i + HORIZON] / adj.iloc[i] - 1
        rf = raw_factors(hist, PRIORITY)
        ok = rf.dropna().index.intersection(fwd.dropna().index)
        if len(ok) < 100:
            continue
        used.append(str(dates[i].date()))
        rk = rf.loc[ok].rank()
        fr = fwd.loc[ok].rank()
        for f in PRIORITY:
            ics[f].append(float((rk[f] * FACTOR_CANDIDATES[f]["direction"]).corr(fr)))
        for (a, b) in corr:
            corr[(a, b)].append(float(rk[a].corr(rk[b])))
    stats = {}
    for f, v in ics.items():
        v = np.array(v)
        n = len(v)
        sd = v.std(ddof=1) if n > 1 else np.nan
        stats[f] = {"periods": n, "mean_ic": float(v.mean()) if n else None, "std_ic": float(sd) if n > 1 else None,
                    "t_stat": float(v.mean() / (sd / np.sqrt(n))) if n > 1 and sd > 0 else None,
                    "hit_rate": float((v > 0).mean()) if n else None}
    mean_corr = {f"{a}|{b}": float(np.mean(v)) if v else None for (a, b), v in corr.items()}
    kept, decisions = [], {}
    for f in PRIORITY:
        t = stats[f]["t_stat"]
        if t is not None and t < T_DROP:
            decisions[f] = f"DROPPED: t={t:.2f} < {T_DROP}"
            continue
        red = [k for k in kept if abs(mean_corr.get(f"{min(f, k)}|{max(f, k)}") or 0) > CORR_DROP]
        if red:
            decisions[f] = f"DROPPED: redundant with {red} (|rank corr| > {CORR_DROP})"
            continue
        kept.append(f)
        decisions[f] = "KEPT"
    res = {"generated_at": now.isoformat(), "data_spec": KR_DATA_SPEC_VERSION, "rule": __doc__.split("KNOWN")[0].strip(),
           "known_biases": ["survivorship / membership look-ahead (current liquid-300)", "Yahoo supplementary prices",
                            "no costs", "short sample"],
           "universe_summary": uni["summary"], "master_meta": {k: v for k, v in m["meta"].items() if k != "master"},
           "history_window": [hs, he], "rebalance_dates": used, "factor_stats": stats,
           "mean_factor_rank_correlation": mean_corr, "decisions": decisions, "kept_factors": kept,
           "weights": {f: 1 / len(kept) for f in kept} if kept else {}}
    Path(out_path).write_text(json.dumps(res, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    print(json.dumps({"kept": kept, "decisions": decisions, "stats": stats, "corr": mean_corr,
                      "universe": uni["summary"]}, indent=1, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
