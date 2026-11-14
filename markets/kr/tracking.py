"""KR prospective paper tracking (P6-25), fully separate from the US P6-20 ledger.

Storage: tracking/kr/ledger/observations.jsonl (hash-chained, append-only; shared ledger primitives),
tracking/kr/prices/<update_id>.csv.gz (snapshots), tracking/kr/outcomes/<update_id>.json,
tracking/kr/updates.jsonl, tracking/kr/reports/latest.{md,html}.  Currency: KRW only.

Cohorts: every KR-EXP-* observation is EXPERIMENTAL_PROSPECTIVE (kept apart from any future approved
model).  Outcome states: PENDING_ENTRY, PENDING_OUTCOME (open; marked), COMPLETED_OUTCOME, INCOMPLETE.
"""
import hashlib
import json
import math
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional

import numpy as np
import pandas as pd

from markets import session_data
from markets.kr import calendar as krcal
from markets.kr.acquisition import BENCHMARKS
from markets.kr.market_data import YahooKRProvider
from markets.kr.model import HOLDING_SESSIONS
from markets.storage import runs_dir as _runs_dir, tracking_dir as _tracking_dir
from pipeline.prospective_ledger import append_records, canonical_json, read_jsonl, verify_chain

SCHEMA = "kr-1"
COST_BPS = (0.0, 10.0, 25.0, 50.0)       # per side, HYPOTHETICAL (KRX sell-side transaction tax not modelled)
MIN_SAMPLE = 30
TOP_N = 10


def _dir(tracking_dir=None) -> Path:
    return Path(tracking_dir) if tracking_dir else _tracking_dir("KR")


def _sha(path: Path) -> Optional[str]:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def _load(run_dir: Path, name: str) -> Dict:
    p = run_dir / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def eligibility(run_dir: Path) -> Dict:
    m, v, st = (_load(run_dir, n) for n in ("run_manifest.json", "validation_result.json", "execution_status.json"))
    r = []
    if m.get("market") != "KR":
        r.append("NOT_A_KR_RUN")
    if v.get("mode") != "kr_market_scan":
        r.append("NOT_A_MARKET_SCAN")
    if v.get("validation_scope") != "full":
        r.append("NOT_FULL_UNIVERSE")
    if v.get("recommendation_status") != "REAL RECOMMENDATION":
        r.append("NO_VALID_RECOMMENDATION")
    if st.get("state") != "COMPLETED":
        r.append("RUN_NOT_COMPLETED")
    if len(v.get("recommendations") or []) != TOP_N:
        r.append("TOP10_INCOMPLETE")
    return {"eligible": not r, "reasons": r}


def _completed_at(st: Dict) -> Optional[str]:
    for cp in reversed(st.get("checkpoints") or []):
        if cp.get("stage") == "RUN_COMPLETED":
            return cp.get("at")
    return None


def build_records(run_dir: Path) -> List[Dict]:
    v, st = _load(run_dir, "validation_result.json"), _load(run_dir, "execution_status.json")
    sig = krcal.classify_signal(_completed_at(st))
    run_id = v["run_id"]
    versions = {k: v.get(k) for k in ("market", "market_config_version", "data_spec_version",
                                      "account_mapping_version", "model_version", "model_status", "currency")}
    snap = run_dir / "universe_snapshot.csv.gz"
    run_rec = {"record_type": "RUN", "schema": SCHEMA, "key": f"RUN:KR:{run_id}", "run_id": run_id, **versions,
               "recorded_at": datetime.now(timezone.utc).isoformat(), "signal": sig,
               "recommendation_timestamp_utc": sig["signal_utc"], "capital_krw": v.get("capital_krw"),
               "universe": {**(v.get("universe") or {}), "snapshot_file": snap.name, "snapshot_sha256": _sha(snap)},
               "factors": v.get("factors"), "provider": v.get("provider"),
               "artifact_sha256": {n: _sha(run_dir / n) for n in ("validation_result.json", "candidate_flow.json")}}
    out = [run_rec]
    for p in v["recommendations"]:
        out.append({"record_type": "OBSERVATION", "schema": SCHEMA, "key": f"OBS:KR:{run_id}:{p['ticker']}",
                    "observation_id": f"KR:{run_id}:{p['ticker']}", "run_id": run_id, **versions,
                    "cohort": "EXPERIMENTAL_PROSPECTIVE" if v.get("model_status") == "EXPERIMENTAL" else "APPROVED_PROSPECTIVE",
                    "security_key": p["security_key"], "ticker": p["ticker"], "company_name": p.get("company_name"),
                    "exchange": p["market"], "industry": p.get("industry"), "industry_class": p.get("industry_class"),
                    "rank": p["rank"], "score": p["score"], "z": p.get("z"), "raw_factors": p.get("raw_factors"),
                    "target_weight": p["target_weight"], "shares": p["shares"],
                    "reference_close_krw": p["reference_close_krw"], "allocated_krw": p["allocated_krw"],
                    "recommendation_timestamp_utc": sig["signal_utc"], "entry_not_before": sig["entry_not_before"],
                    "entry_rule": sig["entry_rule"], "horizon_sessions": HOLDING_SESSIONS,
                    "exit_rule": f"close of session {HOLDING_SESSIONS} (entry session = 1); no stop (KR-EXP-0.1)",
                    "benchmark": BENCHMARKS[p["market"]], "currency": "KRW"})
    return out


def recorded_sessions(tracking_dir=None) -> Dict[str, str]:
    """The scored session of every recorded run -> the first run recorded for it."""
    out: Dict[str, str] = {}
    for r in read_jsonl(_dir(tracking_dir) / "ledger" / "observations.jsonl"):
        s = (r.get("universe") or {}).get("latest_session") if r.get("record_type") == "RUN" else None
        if s:
            out.setdefault(s, r["run_id"])
    return out


def record_run(run_dir, tracking_dir=None) -> Dict:
    """One set of observations per scored session.  A second scan of a session already recorded (a rerun the same day, a run on a
    holiday, a morning run whose index data still ends a day earlier) picks the same stocks from the same data, so recording it
    would count one signal twice; when it comes a day later it would also enter a session later on data that is by then two
    sessions old (2026-11-13).  The first run of a session stays; later ones are not recorded."""
    run_dir = Path(run_dir)
    e = eligibility(run_dir)
    if not e["eligible"]:
        return {"recorded_observations": 0, **e}
    v = _load(run_dir, "validation_result.json")
    first = recorded_sessions(tracking_dir).get(v.get("latest_session"))
    if first and first != v.get("run_id"):
        return {"recorded_observations": 0, "eligible": False, "reasons": ["SESSION_ALREADY_RECORDED"], "recorded_run": first}
    recs = build_records(run_dir)
    n = append_records(_dir(tracking_dir) / "ledger" / "observations.jsonl", recs, key="key")
    return {"recorded_observations": (len(recs) - 1) if n else 0, "eligible": True, "already_recorded": n == 0}


def sync_runs(runs_dir=None, tracking_dir=None) -> Dict:
    base = Path(runs_dir) if runs_dir else _runs_dir("KR")
    out = {"recorded": [], "skipped": {}}
    if base.exists():
        for d in sorted(p for p in base.iterdir() if p.is_dir()):
            r = record_run(d, tracking_dir)
            (out["recorded"].append(d.name) if r.get("eligible") and not r.get("already_recorded")
             else out["skipped"].__setitem__(d.name, r.get("reasons") or ["ALREADY_RECORDED"]))
    return out


def observations(tracking_dir=None) -> List[Dict]:
    return [r for r in read_jsonl(_dir(tracking_dir) / "ledger" / "observations.jsonl")
            if r.get("record_type") == "OBSERVATION"]


def runs(tracking_dir=None) -> List[Dict]:
    return [r for r in read_jsonl(_dir(tracking_dir) / "ledger" / "observations.jsonl")
            if r.get("record_type") == "RUN"]


# ----------------------------------------------------------------------------- outcomes
def outcome(obs: Dict, bars: pd.DataFrame, bench: pd.DataFrame, sessions: pd.DatetimeIndex) -> Dict:
    """bars: one ticker's validated rows (date, open, close, adj_close, quality_status); bench: index OHLC."""
    o = {"observation_id": obs["observation_id"], "ticker": obs["ticker"], "currency": "KRW"}
    b = bars[bars["quality_status"] == "REAL"].sort_values("date").set_index("date") if not bars.empty else bars
    nb = pd.Timestamp(obs["entry_not_before"])
    sess = sessions[sessions >= nb]
    if len(sess) == 0:
        return {**o, "outcome_state": "PENDING_ENTRY", "reason": "NO_SESSION_ON_OR_AFTER_ENTRY_DATE_YET"}
    entry_s = sess[0]
    if b.empty or entry_s not in b.index or not np.isfinite(b.loc[entry_s, "open"]):
        return {**o, "outcome_state": "INCOMPLETE", "reason": "ENTRY_BAR_MISSING", "entry_session": str(entry_s.date())}
    window = sess[:HOLDING_SESSIONS]
    have = [s for s in window if s in b.index]
    missing = [str(s.date()) for s in window if s not in b.index]
    if missing:
        return {**o, "outcome_state": "INCOMPLETE", "reason": "DATA_GAP", "missing_sessions": missing[:10],
                "entry_session": str(entry_s.date())}
    entry_px = float(b.loc[entry_s, "open"])
    done = len(window) == HOLDING_SESSIONS
    last = window[-1] if done else window[len(have) - 1]
    px = float(b.loc[last, "close"])
    pr = px / entry_px - 1
    f_in = b.loc[entry_s, "adj_close"] / b.loc[entry_s, "close"] if pd.notna(b.loc[entry_s, "adj_close"]) else np.nan
    f_out = b.loc[last, "adj_close"] / b.loc[last, "close"] if pd.notna(b.loc[last, "adj_close"]) else np.nan
    tr = (1 + pr) * (f_out / f_in) - 1 if np.isfinite(f_in) and np.isfinite(f_out) else None
    closes = b.loc[window[0]:last, "close"].astype(float)
    bret = None
    if entry_s in bench.index and last in bench.index:
        bret = float(bench.loc[last, "Close"] / bench.loc[entry_s, "Open"] - 1)
    res = {**o, "outcome_state": "COMPLETED_OUTCOME" if done else "PENDING_OUTCOME",
           "entry": {"session": str(entry_s.date()), "price": entry_px, "basis": "open"},
           ("exit" if done else "mark"): {"session": str(last.date()), "price": px, "basis": "close"},
           "sessions_held": len(have),
           "returns": {"price_return": pr, "total_return": tr, "benchmark": obs["benchmark"],
                       "benchmark_price_return": bret, "excess_vs_benchmark": (pr - bret) if bret is not None else None,
                       "mfe_close": float(closes.max() / entry_px - 1), "mae_close": float(closes.min() / entry_px - 1),
                       "cost_sensitivity": [{"cost_bps_per_side": c,
                                             "net_return": (1 + pr) * (1 - c / 1e4) / (1 + c / 1e4) - 1}
                                            for c in COST_BPS]}}
    return res


def _stats(vals) -> Dict:
    a = np.array([v for v in vals if v is not None and math.isfinite(v)], dtype=float)
    if not len(a):
        return {"n": 0, "mean": None, "median": None, "std": None, "win_rate": None, "min": None, "max": None}
    return {"n": int(len(a)), "mean": float(a.mean()), "median": float(np.median(a)),
            "std": float(a.std(ddof=1)) if len(a) > 1 else None, "win_rate": float((a > 0).mean()),
            "min": float(a.min()), "max": float(a.max())}


def paper_portfolios(obs: List[Dict], outs: Dict[str, Dict]) -> List[Dict]:
    by = {}
    for o in obs:
        by.setdefault(o["run_id"], []).append(o)
    res = []
    for rid, items in sorted(by.items()):
        alloc = {o["observation_id"]: o["shares"] * outs[o["observation_id"]]["entry"]["price"]
                 for o in items if outs[o["observation_id"]].get("entry")}
        states = {outs[o["observation_id"]]["outcome_state"] for o in items}
        p = {"run_id": rid, "currency": "KRW", "positions": len(items), "states": sorted(states),
             "status": "COMPLETED_OUTCOME" if states == {"COMPLETED_OUTCOME"} else "OPEN_OR_PENDING"}
        if alloc and len(alloc) == len(items) and sum(alloc.values()) > 0:
            tot = sum(alloc.values())
            val = sum(o["shares"] * (outs[o["observation_id"]].get("exit") or outs[o["observation_id"]].get("mark"))["price"]
                      for o in items)
            bw = [(alloc[o["observation_id"]] / tot, outs[o["observation_id"]]["returns"]["benchmark_price_return"])
                  for o in items]
            p.update(invested_krw=tot, value_krw=val, portfolio_price_return=val / tot - 1,
                     benchmark_return_weighted=(sum(w * r for w, r in bw) if all(r is not None for _, r in bw) else None))
            if p["benchmark_return_weighted"] is not None:
                p["excess_vs_benchmark"] = p["portfolio_price_return"] - p["benchmark_return_weighted"]
        res.append(p)
    return res


def summarize(obs: List[Dict], outs: Dict[str, Dict], run_recs: List[Dict]) -> Dict:
    done = [outs[o["observation_id"]] for o in obs if outs[o["observation_id"]]["outcome_state"] == "COMPLETED_OUTCOME"]
    states = {}
    for o in obs:
        s = outs[o["observation_id"]]["outcome_state"]
        states[s] = states.get(s, 0) + 1
    n = len(done)
    by_ver = {}
    for o in obs:
        k = f"{o['model_version']} / {o['data_spec_version']}"
        b = by_ver.setdefault(k, {"observations": 0, "completed": 0})
        b["observations"] += 1
        b["completed"] += outs[o["observation_id"]]["outcome_state"] == "COMPLETED_OUTCOME"
    picks = [sorted(o["ticker"] for o in obs if o["run_id"] == r["run_id"]) for r in run_recs]
    turnover = [1 - len(set(a) & set(b)) / TOP_N for a, b in zip(picks, picks[1:])]
    exposure = {}
    for o in obs:
        exposure[o.get("industry")] = exposure.get(o.get("industry"), 0) + 1
    return {"official_scope": "KR x EXPERIMENTAL_PROSPECTIVE x COMPLETED_OUTCOME (KRW)",
            "observations": len(obs), "outcome_states": states, "completed": n, "runs": len(run_recs),
            "sample_status": "NO_COMPLETED_OBSERVATIONS" if n == 0 else ("INSUFFICIENT_SAMPLE" if n < MIN_SAMPLE
                                                                           else "OBSERVATIONAL_ONLY"),
            "price_return": _stats([d["returns"]["price_return"] for d in done]),
            "excess_vs_benchmark": _stats([d["returns"]["excess_vs_benchmark"] for d in done]),
            "mfe_close": _stats([d["returns"]["mfe_close"] for d in done]),
            "mae_close": _stats([d["returns"]["mae_close"] for d in done]),
            "cost_sensitivity": [{"cost_bps_per_side": c, "mean_net_return": _stats(
                [d["returns"]["cost_sensitivity"][i]["net_return"] for d in done])["mean"]}
                for i, c in enumerate(COST_BPS)],
            "by_model_and_data_spec": by_ver, "turnover_between_consecutive_runs": turnover,
            "industry_exposure_counts": dict(sorted(exposure.items(), key=lambda kv: -kv[1])[:15])}


# The index bars the tracker may use, and the dates it holds back (rule in markets/session_data.py).  The index dates are the
# tracker's session calendar and the index values its yardstick: on 2026-11-14 09:01 KST the source's bar of session 2026-11-13
# had an open and no close, the day became a session, the stocks were marked on it and every comparison was stored as
# not-a-number.  The series ends before its first such bar, so a stock and its index are always measured over the same sessions.
whole_index = session_data.whole_index


def _fetch_bars(obs: List[Dict], start: str, end: str, now, provider) -> Dict:
    sec = pd.DataFrame([{"canonical_ticker": o["ticker"], "market": o["exchange"],
                         "yahoo_symbol": o["ticker"] + (".KS" if o["exchange"] == "KOSPI" else ".KQ")}
                        for o in {o["ticker"]: o for o in obs}.values()])
    b = provider.fetch(sec, start, end)
    b = krcal.drop_incomplete(b, now, date_col="date") if not b.empty else b
    idx, held = {}, {}
    for m, s in BENCHMARKS.items():
        idx[m], held[m] = whole_index(krcal.drop_incomplete(provider.fetch_index(s, start, end), now))
    return {"bars": b, "index": idx, "index_held_back": {m: d for m, d in held.items() if d}}


def update(tracking_dir=None, provider=None, now=None, offline_snapshot: Optional[str] = None) -> Dict:
    d = _dir(tracking_dir)
    now = now or datetime.now(timezone.utc)
    obs = observations(d)
    uid = f"{now:%Y%m%dT%H%M%SZ}_{uuid.uuid4().hex[:6]}"
    if not obs:
        return {"update_id": uid, "status": "NO_OBSERVATIONS"}
    start = (pd.Timestamp(min(o["entry_not_before"] for o in obs)) - pd.Timedelta(days=7)).strftime("%Y-%m-%d")
    end = (krcal.to_kst(now) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    (d / "prices").mkdir(parents=True, exist_ok=True)
    held: Dict[str, List[str]] = {}
    if offline_snapshot:
        snap = d / "prices" / offline_snapshot
        allb = pd.read_csv(snap, dtype={"ticker": str}, parse_dates=["date"])
    else:
        got = _fetch_bars(obs, start, end, now, provider or YahooKRProvider())
        held = got.get("index_held_back") or {}
        rows = [got["bars"]]
        for m, df in got["index"].items():
            if not df.empty:
                x = df.reset_index().rename(columns={"index": "date", "Date": "date", "Open": "open", "Close": "close",
                                                     "High": "high", "Low": "low"})
                x["ticker"], x["market"], x["quality_status"] = BENCHMARKS[m], m, "REAL"
                rows.append(x)
        allb = pd.concat(rows, ignore_index=True)
        snap = d / "prices" / f"{uid}.csv.gz"
        allb.to_csv(snap, index=False, compression="gzip")
    outs = compute(obs, allb)
    rr = runs(d)
    summary = summarize(obs, outs, rr)
    ports = paper_portfolios(obs, outs)
    (d / "outcomes").mkdir(parents=True, exist_ok=True)
    payload = {"update_id": uid, "computed_at": now.isoformat(), "snapshot": snap.name, "snapshot_sha256": _sha(snap),
               "index_bars_held_back": held, "outcomes": outs, "paper_portfolios": ports, "summary": summary}
    out_path = d / "outcomes" / f"{uid}.json"
    out_path.write_text(json.dumps(payload, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    append_records(d / "updates.jsonl", [{"key": uid, "update_id": uid, "computed_at": now.isoformat(),
                                          "snapshot": snap.name, "snapshot_sha256": payload["snapshot_sha256"],
                                          "outcomes_file": out_path.name, "outcomes_sha256": _sha(out_path),
                                          "states": summary["outcome_states"]}], key="key")
    return {"update_id": uid, "status": "COMPLETE", "states": summary["outcome_states"], "outcomes_file": str(out_path),
            **({"index_bars_held_back": held} if held else {})}


def compute(obs: List[Dict], allb: pd.DataFrame) -> Dict[str, Dict]:
    bench = {}
    for m, sym in BENCHMARKS.items():
        x = allb[allb["ticker"] == sym].copy()
        x["date"] = pd.to_datetime(x["date"]).dt.normalize()
        bench[m] = x.set_index("date").rename(columns={"open": "Open", "close": "Close"}).sort_index()
    sessions = pd.DatetimeIndex(bench["KOSPI"].index)
    outs = {}
    for o in obs:
        g = allb[allb["ticker"] == o["ticker"]].copy()
        g["date"] = pd.to_datetime(g["date"]).dt.normalize()
        outs[o["observation_id"]] = outcome(o, g, bench[o["exchange"]], sessions)
    return outs


def replay(update_id: str, tracking_dir=None) -> Dict:
    d = _dir(tracking_dir)
    log = {r["update_id"]: r for r in read_jsonl(d / "updates.jsonl")}
    if update_id not in log:
        return {"match": False, "reason": "UNKNOWN_UPDATE"}
    stored = json.loads((d / "outcomes" / log[update_id]["outcomes_file"]).read_text(encoding="utf-8"))
    allb = pd.read_csv(d / "prices" / log[update_id]["snapshot"], dtype={"ticker": str}, parse_dates=["date"])
    obs = [o for o in observations(d) if o["observation_id"] in stored["outcomes"]]
    re = json.loads(json.dumps(compute(obs, allb), default=str))
    return {"match": canonical_json(re) == canonical_json(stored["outcomes"]), "update_id": update_id}


def verify(tracking_dir=None, runs_dir=None) -> Dict:
    d = _dir(tracking_dir)
    res = {"chains": [verify_chain(d / "ledger" / "observations.jsonl"), verify_chain(d / "updates.jsonl")], "runs": []}
    base = Path(runs_dir) if runs_dir else _runs_dir("KR")
    for r in runs(d):
        rd = base / r["run_id"]
        if not rd.exists():
            res["runs"].append({"run_id": r["run_id"], "artifacts": "MISSING"})
            continue
        same = all(_sha(rd / n) == h for n, h in (r.get("artifact_sha256") or {}).items())
        rebuilt = {x["key"]: x for x in build_records(rd)}
        stored = {x["key"]: x for x in read_jsonl(d / "ledger" / "observations.jsonl") if x["run_id"] == r["run_id"]}
        strip = lambda x: {k: v for k, v in x.items() if k not in ("prev_hash", "record_hash", "recorded_at")}
        rec_ok = all(canonical_json(strip(rebuilt[k])) == canonical_json(strip(stored[k])) for k in stored if k in rebuilt)
        res["runs"].append({"run_id": r["run_id"], "artifacts": "UNCHANGED" if same else "CHANGED",
                            "reconstruction": "MATCH" if rec_ok else "MISMATCH"})
    log = read_jsonl(d / "updates.jsonl")
    if log:
        res["latest_replay"] = replay(log[-1]["update_id"], d)
    res["ok"] = all(c["ok"] for c in res["chains"]) and all(
        r.get("artifacts") == "UNCHANGED" and r.get("reconstruction") == "MATCH" for r in res["runs"]) and \
        res.get("latest_replay", {"match": True})["match"]
    return res


def _pct(x, nd=2):
    return "-" if x is None or not math.isfinite(x) else f"{x * 100:.{nd}f}%"


def write_report(tracking_dir=None) -> Path:
    from pipeline.prospective_tracking import _md_to_html
    d = _dir(tracking_dir)
    log = read_jsonl(d / "updates.jsonl")
    obs = observations(d)
    L = ["# KR Prospective Paper Tracking (EXPERIMENTAL model)", "",
         "**Market:** South Korea · **Currency:** KRW only (never combined with USD) · "
         "**Cohort:** EXPERIMENTAL_PROSPECTIVE · Paper results are not actual investor returns.", ""]
    if not log:
        L += [f"Observations recorded: {len(obs)}. No outcome update has been run yet "
              "(`python app.py --market KR tracking update`)."]
    else:
        p = json.loads((d / "outcomes" / log[-1]["outcomes_file"]).read_text(encoding="utf-8"))
        s = p["summary"]
        L += [f"Latest update `{p['update_id']}` (computed {p['computed_at']}). Sample status: **{s['sample_status']}** "
              f"({s['completed']} completed of {s['observations']} observations, {s['runs']} runs). No significance "
              f"test and no annualised figure are reported; results stay preliminary below {MIN_SAMPLE} completed "
              "observations from many independent scan dates.", "",
              f"Outcome states: {s['outcome_states']} · By model/data spec: {s['by_model_and_data_spec']}", ""]
        if p.get("index_bars_held_back"):
            L += [f"Index bars held back at this update (open without a close at the source): {p['index_bars_held_back']}. "
                  "Those days are not sessions yet; marks and comparisons end the session before and catch up at the next update.", ""]
        L += [
              "| Metric | n | Mean | Median | Win rate |", "|---|---|---|---|---|"]
        for k in ("price_return", "excess_vs_benchmark", "mfe_close", "mae_close"):
            st = s[k]
            L.append(f"| {k} | {st['n']} | {_pct(st['mean'])} | {_pct(st['median'])} | {_pct(st['win_rate'], 0)} |")
        L += ["", "Hypothetical cost sensitivity: " + "; ".join(
            f"{c['cost_bps_per_side']:g} bps/side → {_pct(c['mean_net_return'])}" for c in s["cost_sensitivity"]),
              f"Turnover between consecutive runs: {s['turnover_between_consecutive_runs']}", "",
              "## Paper portfolios (KRW)", "", "| Run | Status | Invested | Return | Benchmark | Excess |",
              "|---|---|---|---|---|---|"]
        for q in p["paper_portfolios"]:
            L.append(f"| `{q['run_id']}` | {q['status']} | {q.get('invested_krw', 0):,.0f} | "
                     f"{_pct(q.get('portfolio_price_return'))} | {_pct(q.get('benchmark_return_weighted'))} | "
                     f"{_pct(q.get('excess_vs_benchmark'))} |")
        L += ["", "## Observations", "", "| Run | Ticker | Company | Rank | State | Entry | Exit/mark | Return | Bench | Excess |",
              "|---|---|---|---|---|---|---|---|---|---|"]
        names = {o["observation_id"]: o for o in obs}
        for oid, x in sorted(p["outcomes"].items()):
            o, r = names.get(oid, {}), x.get("returns") or {}
            e, m = x.get("entry") or {}, x.get("exit") or x.get("mark") or {}
            L.append(f"| `{o.get('run_id', '')[:16]}` | {x['ticker']} | {o.get('company_name', '')} | {o.get('rank')} | "
                     f"{x['outcome_state']} | {e.get('session', x.get('reason', '-'))} | {m.get('session', '-')} | "
                     f"{_pct(r.get('price_return'))} | {_pct(r.get('benchmark_price_return'))} | "
                     f"{_pct(r.get('excess_vs_benchmark'))} |")
    L += ["", "Method: entry at the open of the first KRX session on/after the recommendation date rule; exit at "
          f"the close of session {HOLDING_SESSIONS}; benchmark = the security's own market index (KOSPI ^KS11 / "
          "KOSDAQ ^KQ11) over the identical window; Yahoo supplementary prices; costs hypothetical. Windows of runs "
          "less than 20 sessions apart overlap and are not independent observations."]
    md = "\n".join(L) + "\n"
    (d / "reports").mkdir(parents=True, exist_ok=True)
    (d / "reports" / "latest.md").write_text(md, encoding="utf-8")
    (d / "reports" / "latest.html").write_text(_md_to_html(md), encoding="utf-8")
    return d / "reports" / "latest.md"
