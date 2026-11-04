"""P6-20 tracking orchestration: update, status, report, replay.

Layout under ``tracking/`` (all append-only or write-once):
  ledger/observations.jsonl, ledger/events.jsonl   immutable records (prospective_ledger)
  prices/<snapshot_id>.csv.gz                       provider price snapshot used by an update
  outcomes/<update_id>.json                         outcomes computed from one snapshot
  updates.jsonl                                     hash-chained log of every update attempt
  reports/latest.md, reports/latest.html            human-readable report of the latest update

An update never edits the ledger. Files are written to a temporary name and atomically
renamed; the update log entry is appended last, so an interrupted update leaves no
partial state that a report could pick up.
"""
import gzip
import hashlib
import html
import io
import json
import os
import time as _time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import pandas as pd

from pipeline import prospective_diagnostics as diag
from pipeline import prospective_ledger as ledger
from pipeline import prospective_outcomes as po
from utils import nyse_calendar

UPDATES_FILE = "updates.jsonl"
PRICE_COLUMNS = ("open", "high", "low", "close", "adj_close", "volume", "dividends", "splits")
WARMUP_DAYS = 90
FETCH_CHUNK = 40


def _root(tracking_dir: Optional[str]) -> Path:
    return Path(tracking_dir or ledger.TRACKING_DIR)


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    with open(tmp, "wb") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


# ------------------------------------------------------------------ prices
def yfinance_fetcher(tickers: List[str], start: date, end: date) -> Dict[str, pd.DataFrame]:
    """Public Yahoo daily bars, raw (split-adjusted) OHLC + Adj Close + actions. Paced, retried."""
    import yfinance as yf
    out: Dict[str, pd.DataFrame] = {}
    for i in range(0, len(tickers), FETCH_CHUNK):
        chunk = tickers[i:i + FETCH_CHUNK]
        data, err = None, None
        for attempt in range(3):
            try:
                data = yf.download(chunk, start=start.isoformat(), end=(pd.Timestamp(end) + pd.Timedelta(days=1)).date().isoformat(),
                                   auto_adjust=False, actions=True, group_by="ticker", threads=False,
                                   progress=False)
                break
            except Exception as exc:  # transient provider failure
                err = exc
                _time.sleep(2 ** attempt)
        if data is None:
            raise RuntimeError(f"price download failed for {chunk}: {err}")
        for t in chunk:
            try:
                sub = data[t] if isinstance(data.columns, pd.MultiIndex) else data
            except KeyError:
                continue
            sub = sub.rename(columns={"Open": "open", "High": "high", "Low": "low", "Close": "close",
                                      "Adj Close": "adj_close", "Volume": "volume", "Dividends": "dividends",
                                      "Stock Splits": "splits"})
            sub = sub[[c for c in PRICE_COLUMNS if c in sub.columns]].dropna(how="all", subset=["close"])
            if not sub.empty:
                sub.index = [pd.Timestamp(x).date() for x in sub.index]
                out[t] = sub
        if i + FETCH_CHUNK < len(tickers):
            _time.sleep(1.0)
    return out


def _snapshot_bytes(prices: Dict[str, pd.DataFrame]) -> bytes:
    frames = []
    for t in sorted(prices):
        df = prices[t].copy()
        df.insert(0, "ticker", t)
        df.insert(0, "date", [d.isoformat() for d in df.index])
        frames.append(df.reset_index(drop=True))
    csv = (pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=["date", "ticker"])).to_csv(
        index=False, float_format="%.10g")
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        gz.write(csv.encode())
    return buf.getvalue()


def load_snapshot(path: Path) -> Dict[str, pd.DataFrame]:
    df = pd.read_csv(path, compression="gzip")
    out = {}
    for t, g in df.groupby("ticker"):
        g = g.drop(columns=["ticker"]).copy()
        g.index = [date.fromisoformat(x) for x in g.pop("date")]
        out[str(t)] = g.sort_index()
    return out


def _trim(prices: Dict[str, pd.DataFrame], as_of: date) -> Dict[str, pd.DataFrame]:
    """Only completed sessions (<= as_of); an in-progress daily bar is never used."""
    return {t: df[df.index <= as_of] for t, df in prices.items()}


# ------------------------------------------------------------------ helpers
def _cohorts(observations, tracking_dir) -> Dict[str, Dict[str, Any]]:
    excl = ledger.exclusions_index(tracking_dir)
    return {o["observation_id"]: ledger.eligibility_cohort(o, excl) for o in observations}


def _run_cohorts(runs, tracking_dir) -> Dict[str, str]:
    excl = ledger.exclusions_index(tracking_dir)
    return {r["run_id"]: ledger.eligibility_cohort({"run_id": r["run_id"], "observation_id": ""}, excl)["cohort"]
            for r in runs}


def alpha_lookup_from(runs: List[Dict[str, Any]], run_cohorts: Dict[str, str]):
    """Frozen 30D review needs alpha on the review session: taken from a VALID full scan whose
    recommendation became available after the previous session's close and by the review close."""
    def lookup(ticker: str, session: date):
        prev = nyse_calendar.previous_session(session)
        lo = pd.Timestamp(datetime.combine(prev, nyse_calendar.session_close_time(prev)), tz=nyse_calendar.ET)
        hi = pd.Timestamp(datetime.combine(session, nyse_calendar.session_close_time(session)), tz=nyse_calendar.ET)
        best = None
        for r in runs:
            if run_cohorts.get(r["run_id"]) != ledger.VALID_PROSPECTIVE:
                continue
            ts = pd.Timestamp(r["recommendation_timestamp_utc"]).tz_convert(nyse_calendar.ET)
            if lo < ts <= hi and ticker in (r.get("ranked_alpha") or {}):
                if best is None or ts > best[0]:
                    best = (ts, r["ranked_alpha"][ticker])
        return None if best is None else best[1]
    return lookup


def compute(tracking_dir: Optional[str], prices: Dict[str, pd.DataFrame], as_of: date,
            runs_dir="runs", observation_ids: Optional[List[str]] = None, with_diagnostics=True) -> Dict[str, Any]:
    recs = ledger.read_observations(tracking_dir)
    runs = [r for r in recs if r["record_type"] == "RUN"]
    obs = [r for r in recs if r["record_type"] == "OBSERVATION"]
    if observation_ids is not None:
        keep = set(observation_ids)
        obs = [o for o in obs if o["observation_id"] in keep]
        runs = [r for r in runs if any(o["run_id"] == r["run_id"] for o in obs)]
    prices = _trim(prices, as_of)
    cohorts = _cohorts(obs, tracking_dir)
    run_cohorts = _run_cohorts(runs, tracking_dir)
    lookup = alpha_lookup_from(runs, run_cohorts)
    outcomes = {o["observation_id"]: dict(po.observation_outcome(o, prices, as_of, lookup),
                                          cohort=cohorts[o["observation_id"]]["cohort"],
                                          exclusions=cohorts[o["observation_id"]]["exclusions"],
                                          corrections=ledger.corrections_for(o["observation_id"], tracking_dir))
                for o in obs}
    portfolios = []
    for r in runs:
        p = po.paper_portfolio(r, outcomes, prices, as_of)
        p["cohort"] = run_cohorts[r["run_id"]]
        portfolios.append(p)
    summary = po.summarize(obs, outcomes, cohorts, portfolios)
    result = {"as_of_session": as_of.isoformat(), "observation_ids": sorted(o["observation_id"] for o in obs),
              "outcomes": outcomes, "paper_portfolios": portfolios, "summary": summary,
              "cohort_counts": _cohort_counts(obs, cohorts, outcomes),
              "ranking_stability": diag.ranking_stability(runs, run_cohorts)}
    if with_diagnostics:
        result["diagnostics"] = {r["run_id"]: diag.run_diagnostics(r, runs_dir) for r in runs
                                 if run_cohorts[r["run_id"]] == ledger.VALID_PROSPECTIVE}
    return result


def _cohort_counts(obs, cohorts, outcomes) -> Dict[str, Any]:
    out = {"by_eligibility": {}, "by_outcome_state": {}, "by_class": {}}
    for o in obs:
        c = cohorts[o["observation_id"]]["cohort"]
        s = outcomes[o["observation_id"]].get("outcome_state")
        out["by_eligibility"][c] = out["by_eligibility"].get(c, 0) + 1
        out["by_class"][o["observation_class"]] = out["by_class"].get(o["observation_class"], 0) + 1
        if o["observation_class"] == "PORTFOLIO_TOP5":
            key = f"{c}/{s}"
            out["by_outcome_state"][key] = out["by_outcome_state"].get(key, 0) + 1
    return out


def outcome_hash(result: Dict[str, Any]) -> str:
    return hashlib.sha256(ledger.canonical_json({k: result[k] for k in ("as_of_session", "observation_ids",
                                                                        "outcomes", "paper_portfolios")}).encode()
                          ).hexdigest()


def read_updates(tracking_dir=None) -> List[Dict[str, Any]]:
    return ledger.read_jsonl(_root(tracking_dir) / UPDATES_FILE)


def latest_update(tracking_dir=None) -> Optional[Dict[str, Any]]:
    ok = [u for u in read_updates(tracking_dir) if u.get("status") in ("COMPLETE", "PARTIAL", "NO_CHANGE")]
    return ok[-1] if ok else None


# ------------------------------------------------------------------ update
def update(tracking_dir: Optional[str] = None, runs_dir="runs", fetcher: Optional[Callable] = None,
           now: Optional[datetime] = None, offline: bool = False) -> Dict[str, Any]:
    root = _root(tracking_dir)
    now = now or datetime.now(timezone.utc)
    sync = ledger.sync_runs(runs_dir, tracking_dir)
    recs = ledger.read_observations(tracking_dir)
    obs = [r for r in recs if r["record_type"] == "OBSERVATION"]
    as_of = nyse_calendar.latest_completed_session(now)
    started = now.isoformat()
    update_id = f"{now.strftime('%Y%m%dT%H%M%SZ')}_{hashlib.sha256(started.encode()).hexdigest()[:6]}"
    if not obs:
        return {"update_id": None, "status": "NOTHING_TO_TRACK", "sync": sync}
    needed = sorted({o["ticker"] for o in obs} | {po.BENCHMARK})
    start = min(pd.Timestamp(o["reference_session"] or o["signal"]["entry_session"]).date() for o in obs) \
        - pd.Timedelta(days=WARMUP_DAYS)
    prev = latest_update(tracking_dir)
    snapshot = None
    if prev and prev.get("as_of_session") == as_of.isoformat() and set(needed) <= set(prev.get("tickers", [])) \
            and (root / prev["snapshot"]).exists() and prev.get("start", "9999") <= start.isoformat():
        snapshot = {"path": prev["snapshot"], "sha256": prev["snapshot_sha256"], "reused": True}
    elif offline:
        return {"update_id": None, "status": "OFFLINE_NO_CURRENT_SNAPSHOT", "sync": sync}
    try:
        if snapshot is None:
            prices = (fetcher or yfinance_fetcher)(needed, start, as_of)
            data = _snapshot_bytes(_trim(prices, as_of))
            rel = f"prices/{update_id}.csv.gz"
            _atomic_write(root / rel, data)
            snapshot = {"path": rel, "sha256": hashlib.sha256(data).hexdigest(), "reused": False}
        prices = load_snapshot(root / snapshot["path"])
        missing = sorted(t for t in needed if t not in prices)
        result = compute(tracking_dir, prices, as_of, runs_dir)
        h = outcome_hash(result)
        status = "PARTIAL" if missing else "COMPLETE"
        if prev and prev.get("outcome_hash") == h:
            out_rel, status = prev["outcomes"], "NO_CHANGE"
        else:
            out_rel = f"outcomes/{update_id}.json"
            result.update({"update_id": update_id, "computed_at": started, "snapshot": snapshot,
                           "missing_tickers": missing})
            _atomic_write(root / out_rel, json.dumps(result, indent=1, default=str, allow_nan=True).encode())
        entry = {"update_id": update_id, "at": started, "status": status, "as_of_session": as_of.isoformat(),
                 "snapshot": snapshot["path"], "snapshot_sha256": snapshot["sha256"],
                 "snapshot_reused": snapshot["reused"], "tickers": needed, "start": start.isoformat(),
                 "missing_tickers": missing, "outcomes": out_rel, "outcome_hash": h,
                 "observations": len(result["observation_ids"]), "synced_runs": sync["recorded_runs"]}
    except Exception as exc:
        failed = {"update_id": update_id, "at": started, "status": "FAILED",
                  "error": f"{type(exc).__name__}: {exc}"[:500], "as_of_session": as_of.isoformat()}
        ledger.append_records(root / UPDATES_FILE, [failed], key="update_id")
        failed["sync"] = sync
        return failed
    ledger.append_records(root / UPDATES_FILE, [entry], key="update_id")
    write_report(tracking_dir, runs_dir)
    entry["sync"] = sync
    return entry


def load_latest_result(tracking_dir=None) -> Optional[Dict[str, Any]]:
    u = latest_update(tracking_dir)
    if not u:
        return None
    return json.loads((_root(tracking_dir) / u["outcomes"]).read_text())


def replay_update(update_id: Optional[str] = None, tracking_dir=None, runs_dir="runs") -> Dict[str, Any]:
    """Recompute an update from its stored snapshot and compare the outcome hash."""
    ups = [u for u in read_updates(tracking_dir) if u.get("outcome_hash")]
    if not ups:
        return {"match": None, "reason": "no updates"}
    u = next((x for x in ups if x["update_id"] == update_id), None) if update_id else ups[-1]
    if u is None:
        return {"match": None, "reason": f"unknown update {update_id}"}
    root = _root(tracking_dir)
    stored = json.loads((root / u["outcomes"]).read_text())
    snap = root / u["snapshot"]
    if hashlib.sha256(snap.read_bytes()).hexdigest() != u["snapshot_sha256"]:
        return {"update_id": u["update_id"], "match": False, "reason": "snapshot file altered"}
    result = compute(tracking_dir, load_snapshot(snap), date.fromisoformat(u["as_of_session"]), runs_dir,
                     observation_ids=stored["observation_ids"], with_diagnostics=False)
    return {"update_id": u["update_id"], "as_of_session": u["as_of_session"],
            "stored_hash": u["outcome_hash"], "replayed_hash": outcome_hash(result),
            "match": outcome_hash(result) == u["outcome_hash"]}


# ------------------------------------------------------------------ status / report
def status(tracking_dir=None) -> Dict[str, Any]:
    recs = ledger.read_observations(tracking_dir)
    runs = [r for r in recs if r["record_type"] == "RUN"]
    obs = [r for r in recs if r["record_type"] == "OBSERVATION"]
    cohorts = _cohorts(obs, tracking_dir)
    counts: Dict[str, int] = {}
    for o in obs:
        k = f"{o['observation_class']}/{cohorts[o['observation_id']]['cohort']}"
        counts[k] = counts.get(k, 0) + 1
    u = latest_update(tracking_dir)
    res = load_latest_result(tracking_dir)
    return {"runs": len(runs), "observations": len(obs), "by_class_and_cohort": counts,
            "run_cohorts": _run_cohorts(runs, tracking_dir),
            "latest_update": {k: u.get(k) for k in ("update_id", "at", "status", "as_of_session",
                                                    "missing_tickers")} if u else None,
            "outcome_states": (res or {}).get("cohort_counts", {}).get("by_outcome_state")}


def _pct(x, digits=2):
    return "n/a" if x is None or (isinstance(x, float) and x != x) else f"{x * 100:.{digits}f}%"


def _num(x, digits=2):
    return "n/a" if x is None or (isinstance(x, float) and x != x) else f"{x:,.{digits}f}"


def render_markdown(res: Dict[str, Any], st: Dict[str, Any], runs: List[Dict[str, Any]]) -> str:
    s = res["summary"]
    L = ["# Prospective Performance Report (P6-20)", "",
         f"As of completed session **{res['as_of_session']}** · update `{res.get('update_id')}` · "
         f"computed {res.get('computed_at')}", "",
         "> **Paper tracking only.** Figures are hypothetical paper results from the engine's original "
         "recommendations, not your actual investment returns. A REAL RECOMMENDATION is not evidence of "
         "profitability.", "",
         "## Statistical caution", "",
         f"- Sample status: **{s['sample_status']}** — {s['statistical_caution']}",
         f"- Measurement period: {s['measurement_period']['first_entry']} → {s['measurement_period']['last_exit']}",
         f"- Transaction costs: {s['transaction_costs_included']}", "",
         "## Overview", "",
         "| Item | Value |", "|---|---|",
         f"| Recorded runs | {st['runs']} |",
         f"| Observations (all classes) | {st['observations']} |",
         f"| Valid prospective TOP-5 observations | {s['valid_observations']} |",
         f"| Completed (official) | {s['completed_observations']} |",
         f"| Outcome states, TOP-5 | {res['cohort_counts']['by_outcome_state']} |",
         f"| By eligibility (all classes) | {res['cohort_counts']['by_eligibility']} |",
         f"| Paper portfolios valid / completed | {s['paper_portfolios']['valid']} / {s['paper_portfolios']['completed']} |",
         f"| Missing price data (tickers) | {res.get('missing_tickers') or 'none'} |", "",
         "## Performance (official scope: valid, TOP-5, completed)", ""]
    pr, ex = s["price_return"], s["excess_vs_spy"]
    L += ["| Metric | n | Mean | Median | Std | Win rate | Min | Max |", "|---|---|---|---|---|---|---|---|",
          f"| Price return | {pr['n']} | {_pct(pr['mean'])} | {_pct(pr['median'])} | {_pct(pr['std'])} | "
          f"{_pct(pr['win_rate'], 0)} | {_pct(pr['min'])} | {_pct(pr['max'])} |",
          f"| Excess vs SPY | {ex['n']} | {_pct(ex['mean'])} | {_pct(ex['median'])} | {_pct(ex['std'])} | "
          f"{_pct(ex['win_rate'], 0)} | {_pct(ex['min'])} | {_pct(ex['max'])} |", "",
          "Cost sensitivity (HYPOTHETICAL per-side costs, not observed): " + "; ".join(
              f"{c['cost_bps_per_side']:g} bps → mean {_pct(c['mean_net_return'])}, excess "
              f"{_pct(c['mean_net_excess_vs_spy'])}" for c in s["cost_sensitivity"]) +
          f". Conclusion changes with costs: {s['cost_sensitivity_conclusion_changes']}.", ""]
    if s["by_recommendation_rank"]:
        L += ["By recommendation rank: " + ", ".join(f"#{k}: n={v['n']} mean {_pct(v['mean'])}"
                                                      for k, v in s["by_recommendation_rank"].items()), ""]
    L += ["## Paper portfolios", "",
          "| Run | Cohort | Status | Capital | Window | Portfolio | SPY | Excess | Max DD | Open |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for p in res["paper_portfolios"]:
        w = p.get("window") or {}
        L.append(f"| `{p['run_id']}` | {p['cohort']} | {p.get('status')} | ${_num(p['capital'], 0)} | "
                 f"{w.get('start', '-')} → {w.get('end', '-')} | {_pct(p.get('portfolio_return_price'))} | "
                 f"{_pct(p.get('spy_return_same_window'))} | {_pct(p.get('excess_vs_spy'))} | "
                 f"{_pct(p.get('max_drawdown'))} | {', '.join(p.get('open_positions') or []) or '-'} |")
    L += ["", "## Recommendations and subsequent outcomes", "",
          "| Run | Ticker | Class | Rank | Cohort | State | Entry | Exit / mark | Return | SPY | Excess | Exit reason |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for oid, o in sorted(res["outcomes"].items()):
        e, x, r = o.get("entry") or {}, o.get("exit") or o.get("mark") or {}, o.get("returns") or {}
        L.append(f"| `{o['run_id'][:16]}` | {o['ticker']} | {o['observation_class'].split('_')[0]} | "
                 f"{o.get('rank_label', '')} | {o['cohort']} | {o.get('outcome_state')} | "
                 f"{e.get('session', e.get('reason', '-'))} {_num(e.get('price'))} | "
                 f"{x.get('session', '-')} {_num(x.get('price'))} | {_pct(r.get('price_return'))} | "
                 f"{_pct(r.get('benchmark_price_return'))} | {_pct(r.get('excess_vs_spy_price'))} | "
                 f"{(o.get('exit') or {}).get('reason', '-')} |")
    L += ["", "## Ranking stability (consecutive full scans)", "",
          "| From | To | Cohorts | TOP-5 Jaccard | Spearman (MODEL_RANK_E) |", "|---|---|---|---|---|"]
    for r in res["ranking_stability"]:
        L.append(f"| `{r['from']}` | `{r['to']}` | {r['from_cohort']} → {r['to_cohort']} | "
                 f"{r['top5_jaccard']:.2f} | {_num(r['spearman_model_rank_e'], 3)} |")
    for rid, d in (res.get("diagnostics") or {}).items():
        if not d.get("available"):
            continue
        L += ["", f"## Diagnostics for `{rid}` ({diag.HYPOTHETICAL.split(' - ')[0]} where marked)", "",
              "| Factor | n | Median z | Max | Min | abs(z)>3 | abs(z)>10 |", "|---|---|---|---|---|---|---|"]
        for f, v in d["factor_extremes"].items():
            L.append(f"| {f} | {v['n']} | {v['median']:.3f} | {v['max'][0]} {v['max'][1]:.2f} | "
                     f"{v['min'][0]} {v['min'][1]:.2f} | {v['count_abs_z_gt_3']} | {v['count_abs_z_gt_10']} |")
        L += ["", "| TOP-5 | Alpha | Dominant factor | Share of abs contribution | Dominates | Alpha rank w/o dominant (hyp.) |"
              " Hard-stop distance |", "|---|---|---|---|---|---|---|"]
        for t, c in d["top5_contributions"].items():
            if not c.get("available"):
                continue
            abl = c["factor_ablation"]["views"].get(c["dominant_factor"], {})
            sd = d["hard_stop_distance"].get(t, {})
            L.append(f"| {t} | {c['alpha']:.3f} | {c['dominant_factor']} ({c['contributions'][c['dominant_factor']]:.3f}) | "
                     f"{_pct(c['dominant_share_of_abs'], 0)} | {c['single_factor_dominates']} | "
                     f"{abl.get('alpha_rank_without_factor')} | {_pct(sd.get('distance_pct'))} |")
        L += ["", "Leave-one-out at the portfolio stage (hypothetical, scores fixed): " + "; ".join(
            f"without {t} → {', '.join(v['entered']) or 'no change'} enters"
            for t, v in d["leave_one_out"]["views"].items()), "",
            f"Sector exposure: {d['sector']['top5_exposure']}; over 40%: {d['sector']['top5_over_40pct'] or 'none'}; "
            f"frozen cap scope: {d['sector']['frozen_cap_scope']}."]
    L += ["", "## Exclusions", ""]
    ex_rows = {}
    for o in res["outcomes"].values():
        for e in o.get("exclusions") or []:
            ex_rows.setdefault(o["run_id"], e)
    for rid, e in sorted(ex_rows.items()):
        L.append(f"- `{rid}`: {e['category']} — {e['reason']} (source: {e.get('source')})")
    L += ["", "## Method (summary)", "",
          "- Entry: first regular-session open strictly after the recommendation timestamp "
          "(premarket → same-day open; regular session / after hours / non-session → next session open). "
          "Missing opens roll forward up to 5 sessions, otherwise INCOMPLETE.",
          "- Primary window: frozen P6-11B rules via the unmodified `DecisionEngine.evaluate_existing_position` "
          "on daily closes; signals filled at the next open; window ends at the first exit fill or at the frozen "
          "30-weekday review.",
          "- Benchmark: SPY over the identical window (same entry open, same exit price type and session). "
          "Excess return vs SPY is not alpha.",
          "- Full specification: `reports/P6-20_TRACKING_SPECIFICATION.md`."]
    return "\n".join(L) + "\n"


def write_report(tracking_dir=None, runs_dir="runs") -> Optional[Path]:
    res = load_latest_result(tracking_dir)
    if not res:
        return None
    recs = ledger.read_observations(tracking_dir)
    ranks = {r["observation_id"]: (f"#{r['recommendation_rank']}" if r.get("recommendation_rank")
                                   else f"W{r.get('watchlist_rank')}") for r in recs if r["record_type"] == "OBSERVATION"}
    for oid, o in res["outcomes"].items():
        o["rank_label"] = ranks.get(oid, "")
    md = render_markdown(res, status(tracking_dir), [r for r in recs if r["record_type"] == "RUN"])
    out = _root(tracking_dir) / "reports"
    _atomic_write(out / "latest.md", md.encode())
    _atomic_write(out / "latest.html", _md_to_html(md).encode())
    return out / "latest.md"


def _md_to_html(md: str) -> str:
    """Minimal, dependency-free Markdown (headings, tables, lists, paragraphs) -> standalone HTML."""
    body, in_table = [], False
    for line in md.splitlines():
        esc = html.escape(line)
        for mark, tag in (("**", "strong"), ("`", "code")):
            parts = esc.split(mark)
            esc = "".join(p if i % 2 == 0 else f"<{tag}>{p}</{tag}>" for i, p in enumerate(parts))
        if line.startswith("|"):
            cells = [c.strip() for c in esc.strip("|").split("|")]
            if set(line.replace("|", "").strip()) <= {"-"}:
                continue
            if not in_table:
                body.append("<table><thead><tr>" + "".join(f"<th>{c}</th>" for c in cells) + "</tr></thead><tbody>")
                in_table = True
            else:
                body.append("<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>")
            continue
        if in_table:
            body.append("</tbody></table>")
            in_table = False
        if line.startswith("# "):
            body.append(f"<h1>{esc[2:]}</h1>")
        elif line.startswith("## "):
            body.append(f"<h2>{esc[3:]}</h2>")
        elif line.startswith("> "):
            body.append(f"<blockquote>{esc[5:]}</blockquote>")
        elif line.startswith("- "):
            body.append(f"<li>{esc[2:]}</li>")
        elif line.strip():
            body.append(f"<p>{esc}</p>")
    if in_table:
        body.append("</tbody></table>")
    css = (":root{--bg:#fff;--fg:#1d1d1f;--mute:#6e6e73;--line:#d9d9de;--accent:#0b57d0}"
           "@media (prefers-color-scheme:dark){:root{--bg:#141416;--fg:#ececf0;--mute:#a1a1a8;--line:#34343a;"
           "--accent:#8ab4f8}}body{background:var(--bg);color:var(--fg);font:14px/1.5 -apple-system,system-ui,"
           "sans-serif;max-width:1180px;margin:0 auto;padding:24px 16px}h1{font-size:22px}h2{font-size:17px;"
           "margin-top:28px;border-bottom:1px solid var(--line);padding-bottom:4px}table{border-collapse:collapse;"
           "width:100%;display:block;overflow-x:auto;font-size:12.5px}td,th{border-bottom:1px solid var(--line);"
           "padding:4px 8px;text-align:left;white-space:nowrap}th{color:var(--mute);font-weight:600}"
           "blockquote{border-left:3px solid var(--accent);margin:12px 0;padding:6px 12px;color:var(--fg)}"
           "code{font-size:12px}")
    return ("<!doctype html><html lang=en><head><meta charset=utf-8><meta name=viewport "
            "content='width=device-width,initial-scale=1'><title>Prospective Performance</title>"
            f"<style>{css}</style></head><body>{''.join(body)}</body></html>")
