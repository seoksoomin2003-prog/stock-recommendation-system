"""P6-19 Phase I: prospective (forward) performance observation.

This module never changes, tunes or feeds back into the frozen P6-11B model.
It only

1. appends each *full-universe REAL RECOMMENDATION* TOP-5 to an append-only
   ledger at the moment it is produced (``record_run``), and
2. later measures what actually happened using public daily closes
   (``evaluate_ledger``).

Assumptions (stated in every summary):
* reference price = the adjusted close of the last completed session used by
  the run (``last_bar``); a real fill would happen at a later price;
* outcomes use daily adjusted closes only (no intraday highs/lows), so the
  MAE/MFE are close-to-close and the stop check is a close-based approximation;
* the transaction-cost figure is an assumed round-trip cost, not an observation;
* benchmark = SPY adjusted close over the same sessions.

Small samples are labelled INSUFFICIENT_SAMPLE.  Nothing here is evidence of
profitability until enough independent observations have matured, and even
then it is an observation, not a significance test.
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import numpy as np
import pandas as pd

TRACKING_DIR = os.getenv("QPP_TRACKING_DIR", "tracking")
LEDGER_FILE = "recommendation_ledger.jsonl"
HORIZONS = (5, 10, 20, 30)            # trading sessions; 30 = frozen expected horizon
MIN_SAMPLE = 30                       # below this a horizon is reported as INSUFFICIENT_SAMPLE
ASSUMED_ROUND_TRIP_COST = 0.001       # 10 bps, an assumption (not observed)
BENCHMARK = "SPY"


def _ledger_path(tracking_dir: Optional[str] = None) -> Path:
    return Path(tracking_dir or TRACKING_DIR) / LEDGER_FILE


def read_ledger(tracking_dir: Optional[str] = None) -> List[Dict[str, Any]]:
    path = _ledger_path(tracking_dir)
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


EXCLUSIONS_FILE = "excluded_runs.json"


def read_exclusions(tracking_dir: Optional[str] = None) -> Dict[str, str]:
    """{run_id: reason} for recorded runs later found to have been produced from defective inputs.

    Ledger rows are never edited or deleted; excluded runs keep their outcomes (flagged) but do not
    enter the summary statistics.
    """
    path = Path(tracking_dir or TRACKING_DIR) / EXCLUSIONS_FILE
    if not path.exists():
        return {}
    return {str(k): str(v) for k, v in json.loads(path.read_text(encoding="utf-8")).items()}


def record_run(validation: Dict[str, Any], tracking_dir: Optional[str] = None,
               frozen_fingerprint: Optional[str] = None) -> int:
    """Append the TOP-5 of a full-universe REAL RECOMMENDATION. Returns rows written (0 if not eligible)."""
    if validation.get("mode") != "market_scan" or validation.get("validation_scope") != "full":
        return 0
    if validation.get("recommendation_status") != "REAL RECOMMENDATION":
        return 0
    run_id = validation["run_id"]
    existing = {(r["run_id"], r["ticker"]) for r in read_ledger(tracking_dir)}
    rows = []
    for rec in validation.get("recommendations", []):
        if (run_id, rec.get("ticker")) in existing:
            continue
        rows.append({
            "schema": 1, "run_id": run_id, "recorded_at": datetime.now(timezone.utc).isoformat(),
            "generated_at": validation.get("executed_at"), "market_regime": validation.get("market_regime"),
            "model_version": validation.get("model_version"), "strategy_version": validation.get("strategy_version"),
            "frozen_fingerprint": frozen_fingerprint,
            "ticker": rec.get("ticker"), "name": rec.get("name"), "sector": rec.get("sector"),
            "recommendation_rank": rec.get("recommendation_rank"),
            "model_rank_e_rank": rec.get("model_rank_e_rank"), "model_rank_e_score": rec.get("model_rank_e_score"),
            "alpha": rec.get("alpha"), "alpha_percentile": rec.get("alpha_percentile"), "factors": rec.get("factors"),
            "reference_session": rec.get("last_bar"), "reference_close": rec.get("close"),
            "target_weight": rec.get("target_weight"), "hard_stop": rec.get("hard_stop"),
            "trailing_stop": rec.get("trailing_stop"), "horizon_days": rec.get("horizon_days"),
            "entry_1_weight": rec.get("entry_1_weight"), "entry_2_weight": rec.get("entry_2_weight"),
            "portfolio_eligible": True,
            "provenance": {k: rec.get(k) for k in ("price_status", "volume_status", "fundamental_status")},
        })
    if not rows:
        return 0
    path = _ledger_path(tracking_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, default=str) + "\n")
    return len(rows)


def _default_price_fetcher(tickers: List[str], start: str) -> pd.DataFrame:
    import yfinance as yf
    data = yf.download(sorted(set(tickers)), start=start, interval="1d", auto_adjust=True,
                       progress=False, threads=True, group_by="column")
    if data is None or data.empty:
        return pd.DataFrame()
    close = data["Close"] if isinstance(data.columns, pd.MultiIndex) else data[["Close"]]
    if isinstance(close, pd.Series):
        close = close.to_frame(tickers[0])
    close.index = pd.to_datetime(close.index).tz_localize(None).normalize()
    return close


def outcome_for(row: Dict[str, Any], closes: pd.DataFrame) -> Dict[str, Any]:
    """Observed close-to-close outcome of one ledger row (NaN where not yet matured)."""
    t, ref_day = row["ticker"], pd.Timestamp(row["reference_session"])
    out: Dict[str, Any] = {"run_id": row["run_id"], "ticker": t, "reference_session": row["reference_session"]}
    if t not in closes.columns or BENCHMARK not in closes.columns:
        out["status"] = "PRICE_DATA_UNAVAILABLE"
        return out
    s, b = closes[t].dropna(), closes[BENCHMARK].dropna()
    if ref_day not in s.index or ref_day not in b.index:
        out["status"] = "REFERENCE_SESSION_UNAVAILABLE"
        return out
    ref, bref = float(s.loc[ref_day]), float(b.loc[ref_day])
    fwd, bfwd = s[s.index > ref_day], b[b.index > ref_day]
    out["sessions_observed"] = int(len(fwd))
    for h in HORIZONS:
        if len(fwd) >= h and len(bfwd) >= h:
            r = float(fwd.iloc[h - 1] / ref - 1.0)
            br = float(bfwd.iloc[h - 1] / bref - 1.0)
            out[f"ret_{h}d"], out[f"bench_{h}d"], out[f"excess_{h}d"] = r, br, r - br
            out[f"ret_{h}d_after_cost"] = r - ASSUMED_ROUND_TRIP_COST
    horizon = int(row.get("horizon_days") or HORIZONS[-1])
    window = fwd.iloc[:horizon]
    if not window.empty:
        path = window / ref - 1.0
        out["mfe_close"] = float(path.max())
        out["mae_close"] = float(path.min())
        running_peak = np.maximum.accumulate(np.concatenate([[ref], window.values]))
        out["max_drawdown_close"] = float((np.concatenate([[ref], window.values]) / running_peak - 1.0).min())
        stop = row.get("hard_stop")
        out["hard_stop_breached_on_close"] = bool(stop is not None and (window <= float(stop)).any())
    out["status"] = "MATURED" if len(fwd) >= horizon else "OPEN"
    return out


def summarize(outcomes: List[Dict[str, Any]], ledger: List[Dict[str, Any]]) -> Dict[str, Any]:
    df = pd.DataFrame(outcomes)
    horizons = {}
    for h in HORIZONS:
        col = f"ret_{h}d"
        vals = df[col].dropna() if col in df else pd.Series(dtype=float)
        ex = df[f"excess_{h}d"].dropna() if f"excess_{h}d" in df else pd.Series(dtype=float)
        n = int(len(vals))
        horizons[f"{h}d"] = {
            "observations": n,
            "independent_runs": int(df.loc[vals.index, "run_id"].nunique()) if n else 0,
            "sample_status": "INSUFFICIENT_SAMPLE" if n < MIN_SAMPLE else "OBSERVATIONAL_ONLY",
            "mean_return": float(vals.mean()) if n else None,
            "median_return": float(vals.median()) if n else None,
            "win_rate": float((vals > 0).mean()) if n else None,
            "mean_excess_vs_spy": float(ex.mean()) if len(ex) else None,
            "mean_return_after_assumed_cost": float((vals - ASSUMED_ROUND_TRIP_COST).mean()) if n else None,
        }
    runs: Dict[str, set] = {}
    sectors: Dict[str, int] = {}
    for r in ledger:
        runs.setdefault(r["run_id"], set()).add(r["ticker"])
        sectors[r.get("sector") or "Unknown"] = sectors.get(r.get("sector") or "Unknown", 0) + 1
    ordered = [runs[k] for k in sorted(runs)]
    jaccard = [len(a & b) / len(a | b) for a, b in zip(ordered, ordered[1:]) if a | b]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "ledger_rows": len(ledger), "recorded_runs": len(runs),
        "horizons": horizons,
        "mfe_mae_close": {"mean_mfe": float(df["mfe_close"].mean()) if "mfe_close" in df and df["mfe_close"].notna().any() else None,
                          "mean_mae": float(df["mae_close"].mean()) if "mae_close" in df and df["mae_close"].notna().any() else None},
        "hard_stop_breach_rate_close": (float(df["hard_stop_breached_on_close"].dropna().astype(float).mean())
                                        if "hard_stop_breached_on_close" in df and df["hard_stop_breached_on_close"].notna().any() else None),
        "sector_concentration": sectors,
        "top5_stability_jaccard_consecutive_runs": {"mean": float(np.mean(jaccard)) if jaccard else None,
                                                    "pairs": len(jaccard)},
        "assumptions": {"reference_price": "adjusted close of the run's last completed session",
                        "outcome_prices": "daily adjusted closes (no intraday high/low)",
                        "assumed_round_trip_cost": ASSUMED_ROUND_TRIP_COST, "benchmark": BENCHMARK,
                        "min_sample_for_reporting": MIN_SAMPLE},
        "disclaimer": ("Observed forward outcomes of a frozen model. Not a significance test and not evidence of "
                       "profitability; the model must not be re-tuned on these observations."),
    }


def evaluate_ledger(tracking_dir: Optional[str] = None,
                    price_fetcher: Optional[Callable[[List[str], str], pd.DataFrame]] = None) -> Dict[str, Any]:
    ledger = read_ledger(tracking_dir)
    if not ledger:
        return {"ledger_rows": 0, "message": "No recommendations recorded yet. Run a full `scan` that ends in a "
                                             "REAL RECOMMENDATION; it is recorded automatically."}
    start = min(r["reference_session"] for r in ledger if r.get("reference_session"))
    closes = (price_fetcher or _default_price_fetcher)([r["ticker"] for r in ledger] + [BENCHMARK], start)
    exclusions = read_exclusions(tracking_dir)
    outcomes = [outcome_for(r, closes) for r in ledger]
    for o, r in zip(outcomes, ledger):
        if r["run_id"] in exclusions:
            o["excluded_from_statistics"] = exclusions[r["run_id"]]
    kept = [i for i, r in enumerate(ledger) if r["run_id"] not in exclusions]
    summary = summarize([outcomes[i] for i in kept], [ledger[i] for i in kept])
    summary["excluded_runs"] = exclusions
    summary["excluded_rows"] = len(ledger) - len(kept)
    out_dir = Path(tracking_dir or TRACKING_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "outcomes.json").write_text(json.dumps({"outcomes": outcomes, "summary": summary},
                                                      indent=2, default=str))
    return summary
