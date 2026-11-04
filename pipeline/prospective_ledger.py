"""P6-20 immutable prospective recommendation ledger.

Append-only JSON-lines files with a sha256 hash chain (tamper-evident):

* ``tracking/ledger/observations.jsonl`` - one ``RUN`` record per eligible full market
  scan plus one ``OBSERVATION`` record per TOP-5 pick (``PORTFOLIO_TOP5``) and per
  watchlist name (``WATCHLIST_DIAGNOSTIC``, never part of portfolio statistics).
* ``tracking/ledger/events.jsonl`` - exclusions, corrections and notes that refer to
  original records. Original records are never edited, re-ranked or deleted.

Everything is built from the run's own artifacts (``runs/<id>/``), so a record never
depends on today's provider data.  Artifact sha256 hashes are stored so that the
original decision can be re-verified later (``verify``).
"""
import fcntl
import hashlib
import json
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from utils import nyse_calendar

SCHEMA = 2
GENESIS = "0" * 64
TRACKING_DIR = os.getenv("QPP_TRACKING_DIR", "tracking")
LEDGER_SUBDIR = "ledger"
OBSERVATIONS_FILE = "observations.jsonl"
EVENTS_FILE = "events.jsonl"
LEGACY_EXCLUSIONS_FILE = "excluded_runs.json"     # P6-19 file, preserved and read as events
ARTIFACT_FILES = ("run_manifest.json", "execution_status.json", "validation_result.json",
                  "candidate_flow.json", "provider_summary.json")
REAL = "REAL RECOMMENDATION"

# Eligibility cohorts (official statistics use VALID_PROSPECTIVE only)
VALID_PROSPECTIVE = "VALID_PROSPECTIVE"
PRE_FIX_EXCLUDED = "PRE_FIX_EXCLUDED"
DATA_INVALID = "DATA_INVALID"
EXCLUSION_CATEGORIES = {"PRE_FIX": PRE_FIX_EXCLUDED, "DATA_INVALID": DATA_INVALID}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str, allow_nan=True)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def ledger_dir(tracking_dir: Optional[str] = None) -> Path:
    return Path(tracking_dir or TRACKING_DIR) / LEDGER_SUBDIR


# --------------------------------------------------------------- append-only store
def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    """Parse a JSONL file. A torn *final* line (interrupted append) is ignored, never repaired."""
    if not path.exists():
        return []
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    rows = []
    for i, line in enumerate(lines):
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            if i == len(lines) - 1:
                break
            raise
    return rows


@contextmanager
def _locked(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = open(str(path) + ".lock", "a+")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(lock, fcntl.LOCK_UN)
        lock.close()


def _seal(record: Dict[str, Any], prev_hash: str) -> Dict[str, Any]:
    body = {k: v for k, v in record.items() if k not in ("prev_hash", "record_hash")}
    body["prev_hash"] = prev_hash
    body["record_hash"] = _sha256(canonical_json(body))
    return body


def append_records(path: Path, records: Iterable[Dict[str, Any]], key: str) -> int:
    """Append records whose ``key`` is not yet present. Returns the number written."""
    records = list(records)
    with _locked(path):
        existing = read_jsonl(path)
        seen = {r.get(key) for r in existing}
        prev = existing[-1]["record_hash"] if existing else GENESIS
        written = 0
        lines = []
        for rec in records:
            if rec.get(key) in seen:
                continue
            sealed = _seal(rec, prev)
            prev = sealed["record_hash"]
            seen.add(rec.get(key))
            lines.append(canonical_json(sealed))
            written += 1
        if lines:
            with open(path, "a", encoding="utf-8") as fh:
                fh.write("\n".join(lines) + "\n")
                fh.flush()
                os.fsync(fh.fileno())
    return written


def verify_chain(path: Path) -> Dict[str, Any]:
    rows, problems, prev = read_jsonl(path), [], GENESIS
    for i, r in enumerate(rows):
        body = {k: v for k, v in r.items() if k != "record_hash"}
        if r.get("prev_hash") != prev:
            problems.append(f"row {i + 1}: prev_hash mismatch")
        if _sha256(canonical_json(body)) != r.get("record_hash"):
            problems.append(f"row {i + 1}: record_hash mismatch (record altered)")
        prev = r.get("record_hash")
    return {"file": str(path), "rows": len(rows), "ok": not problems, "problems": problems}


# --------------------------------------------------------------- record building
def _load(run_dir: Path, name: str) -> Dict[str, Any]:
    p = run_dir / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def run_completed_at(status: Dict[str, Any]) -> Optional[str]:
    for cp in reversed(status.get("checkpoints") or []):
        if cp.get("stage") == "RUN_COMPLETED":
            return cp.get("at")
    return None


def eligibility_of_run(run_dir: Path) -> Dict[str, Any]:
    """Only completed, full-universe market scans with a REAL RECOMMENDATION are recorded."""
    v, st = _load(run_dir, "validation_result.json"), _load(run_dir, "execution_status.json")
    reasons = []
    # P6-21: the US ledger records US runs only.  Runs before P6-21 carry no "market" key; they were
    # produced exclusively by the US canonical pipeline, so their market is US by construction.
    if _load(run_dir, "run_manifest.json").get("market", "US") != "US":
        reasons.append("NOT_A_US_MARKET_RUN")
    if v.get("mode") != "market_scan":
        reasons.append("NOT_A_MARKET_SCAN")
    if v.get("validation_scope") != "full":
        reasons.append("NOT_FULL_UNIVERSE")
    if v.get("recommendation_status") != REAL:
        reasons.append("NO_VALID_PORTFOLIO_RECOMMENDATION")
    if st.get("state") != "COMPLETED" or not run_completed_at(st):
        reasons.append("RUN_NOT_COMPLETED")
    if len(v.get("recommendations") or []) != 5:
        reasons.append("TOP5_INCOMPLETE")
    return {"eligible": not reasons, "reasons": reasons}


def infer_data_input_spec(manifest: Dict[str, Any], flow: Dict[str, Any]) -> Dict[str, Any]:
    """Data-input specification in force for a run.

    Runs since P6-20 record it in the manifest. For older runs it is inferred from
    provenance markers that only the corresponding loader version writes.
    """
    if manifest.get("data_input_spec_version"):
        return {"version": manifest["data_input_spec_version"], "basis": "run_manifest"}
    has_pbr_check = has_margin_reject = False
    for c in flow.values():
        prov = c.get("fundamental_provenance") or {}
        has_pbr_check |= bool((prov.get("pbr") or {}).get("consistency_check")
                              or (prov.get("pbr") or {}).get("status") == "REJECTED_INCONSISTENT")
        has_margin_reject |= bool((prov.get("profitMargin") or {}).get("sec_rejected"))
    if has_pbr_check and has_margin_reject:
        return {"version": "P6-19-final", "basis": "inferred: provenance contains P/B consistency checks and "
                                                    "NET_INCOME_EXCEEDS_REVENUE_CONCEPT rejections (cache schema 4)"}
    if has_pbr_check:
        return {"version": "P6-19-intermediate", "basis": "inferred: P/B consistency checks present, no revenue-"
                                                           "slice rejections (cache schema 3)"}
    return {"version": "pre-P6-19-fix", "basis": "inferred: no P6-19 input-rule provenance markers"}


def _contributions(factors: Dict[str, Any], weights: Dict[str, float], alpha) -> Dict[str, Any]:
    """Exact frozen ScoringEngine decomposition: weights renormalised over available factors."""
    avail = {f: w for f, w in weights.items() if factors.get(f) is not None and factors.get(f) == factors.get(f)}
    total = sum(avail.values())
    if not avail or total <= 0:
        return {"available": False}
    contrib = {f: (w / total) * float(factors[f]) for f, w in avail.items()}
    recon = sum(contrib.values())
    abs_total = sum(abs(v) for v in contrib.values()) or 1.0
    top = max(contrib, key=lambda f: abs(contrib[f]))
    return {"available": True, "contributions": contrib, "effective_weights": {f: w / total for f, w in avail.items()},
            "reconstructed_alpha": recon,
            "reconstruction_error": (abs(recon - float(alpha)) if alpha is not None else None),
            "dominant_factor": top, "dominant_share_of_abs": abs(contrib[top]) / abs_total}


def build_records(run_dir: Path, source: str) -> List[Dict[str, Any]]:
    run_dir = Path(run_dir)
    manifest, status = _load(run_dir, "run_manifest.json"), _load(run_dir, "execution_status.json")
    v, provider = _load(run_dir, "validation_result.json"), _load(run_dir, "provider_summary.json")
    flow = _load(run_dir, "candidate_flow.json").get("candidates", {})
    run_id = v["run_id"]
    signal = nyse_calendar.classify_signal(run_completed_at(status))
    frozen = manifest.get("frozen_core") or {}
    weights = (frozen.get("values") or {}).get("DEFAULT_FACTOR_WEIGHTS") or {}
    tickers = sorted(flow)
    universe = provider.get("universe") or {}
    market = provider.get("market_data") or {}
    ranked = {t: c for t, c in flow.items() if c.get("model_rank_e_rank") is not None}
    run_rec = {
        "record_type": "RUN", "schema": SCHEMA, "key": f"RUN:{run_id}", "run_id": run_id,
        "recorded_at": _now(), "record_source": source,
        "run_started_utc": manifest.get("started_at") or v.get("executed_at"),
        "recommendation_timestamp_utc": signal["signal_utc"], "signal": signal,
        "model_version": v.get("model_version"), "strategy_version": v.get("strategy_version"),
        "frozen_config_sha256": frozen.get("sha256"),
        "frozen_source_sha256": manifest.get("frozen_source_sha256"),
        "data_input_spec": infer_data_input_spec(manifest, flow),
        "universe": {"source": universe.get("source"), "status": universe.get("status"),
                     "freshness": universe.get("freshness_status"), "retrieved_at": universe.get("retrieved_at"),
                     "constituent_count": universe.get("constituent_count"), "requested_count": len(tickers),
                     "tickers_sha256": _sha256(",".join(tickers)), "tickers": tickers},
        "market_data_retrieved_at": market.get("retrieved_at"),
        "last_bar_distribution": market.get("last_bar_distribution"),
        "market_regime": v.get("market_regime"),
        "capital": v.get("capital"), "capital_source": v.get("capital_source"), "currency": v.get("currency"),
        "recommendation_status": v.get("recommendation_status"), "validation_scope": v.get("validation_scope"),
        "funnel": v.get("funnel"),
        "top5": [{"ticker": r["ticker"], "rank": r.get("recommendation_rank"), "weight": r.get("target_weight")}
                 for r in v.get("recommendations") or []],
        "watchlist": [w.get("ticker") for w in v.get("watchlist") or []],
        "sector_exposure": v.get("sector_exposure"), "sector_cap_warnings": v.get("sector_cap_warnings"),
        "portfolio_cash": v.get("portfolio_cash"),
        "excluded_candidates": {t: c.get("reasons") for t, c in flow.items()
                                if c.get("final_status") in ("QUARANTINED", "NOT_EVALUATED", "BEAR_REJECTED")},
        "ranked_alpha": {t: c.get("alpha") for t, c in ranked.items()},
        "ranked_model_rank_e": {t: c.get("model_rank_e_rank") for t, c in ranked.items()},
        "artifact_sha256": {f: _file_sha256(run_dir / f) for f in ARTIFACT_FILES if (run_dir / f).exists()},
    }
    records = [run_rec]
    groups = [("PORTFOLIO_TOP5", v.get("recommendations") or [])]
    groups.append(("WATCHLIST_DIAGNOSTIC", [dict(flow.get(w.get("ticker"), {}), **{"watchlist_rank": i + 1})
                                            for i, w in enumerate(v.get("watchlist") or [])]))
    for cls, rows in groups:
        for r in rows:
            t = r.get("ticker")
            c = flow.get(t, r)
            prov = c.get("fundamental_provenance") or {}
            records.append({
                "record_type": "OBSERVATION", "schema": SCHEMA, "key": f"OBS:{run_id}:{t}",
                "observation_id": f"{run_id}:{t}", "observation_class": cls, "run_id": run_id,
                "recorded_at": run_rec["recorded_at"], "record_source": source,
                "recommendation_timestamp_utc": signal["signal_utc"], "signal": signal,
                "model_version": v.get("model_version"), "frozen_config_sha256": frozen.get("sha256"),
                "data_input_spec_version": run_rec["data_input_spec"]["version"],
                "universe_tickers_sha256": run_rec["universe"]["tickers_sha256"],
                "ticker": t, "name": c.get("name"), "sector": c.get("sector"), "sector_source": c.get("sector_source"),
                "recommendation_rank": c.get("recommendation_rank") if cls == "PORTFOLIO_TOP5" else None,
                "watchlist_rank": r.get("watchlist_rank"),
                "model_rank_e_rank": c.get("model_rank_e_rank"), "model_rank_e_score": c.get("model_rank_e_score"),
                "alpha": c.get("alpha"), "alpha_percentile": c.get("alpha_percentile"),
                "factors_z": c.get("factors"), "factor_contributions": _contributions(c.get("factors") or {}, weights,
                                                                                      c.get("alpha")),
                "fundamentals": c.get("fundamentals"), "fundamental_provenance": prov,
                "data_status": {"price": c.get("price_status"), "volume": c.get("volume_status"),
                                "fundamentals": c.get("fundamental_status")},
                "source_observation": {"last_bar": c.get("last_bar"), "adv20_window": c.get("adv20_window"),
                                       "sec_fiscal_period_end": prov.get("_sec_fiscal_period_end")},
                "source_retrieval": {"fundamentals_retrieved_at": prov.get("_retrieved_at"),
                                     "fundamentals_cache_hit": prov.get("_cache_hit"),
                                     "market_data_retrieved_at": market.get("retrieved_at")},
                "reference_session": c.get("last_bar"), "reference_close": c.get("close"),
                "reference_close_basis": "yfinance auto_adjust=True close of reference_session (as used by the scan)",
                "adv20": c.get("adv20"), "last_volume": c.get("last_volume"), "liquidity": c.get("liquidity"),
                "atr": c.get("atr"), "ema20": c.get("ema20"),
                "portfolio_eligible": cls == "PORTFOLIO_TOP5",
                "target_weight": c.get("target_weight") if cls == "PORTFOLIO_TOP5" else None,
                "target_notional": c.get("target_notional") if cls == "PORTFOLIO_TOP5" else None,
                "target_shares": c.get("target_shares") if cls == "PORTFOLIO_TOP5" else None,
                "entry_1_weight": c.get("entry_1_weight") if cls == "PORTFOLIO_TOP5" else None,
                "entry_2_weight": c.get("entry_2_weight") if cls == "PORTFOLIO_TOP5" else None,
                "hard_stop": c.get("hard_stop") if cls == "PORTFOLIO_TOP5" else None,
                "trailing_stop": c.get("trailing_stop") if cls == "PORTFOLIO_TOP5" else None,
                "horizon_days": c.get("horizon_days") or (frozen.get("values") or {}).get(
                    "DECISION_SETTINGS", {}).get("expected_horizon_days"),
                "final_status": c.get("final_status"), "reasons": c.get("reasons"),
                "recommendation_status": v.get("recommendation_status"),
            })
    return records


# --------------------------------------------------------------- public API
def record_run(run_dir, tracking_dir: Optional[str] = None, source: str = "live_run_hook") -> Dict[str, Any]:
    run_dir = Path(run_dir)
    elig = eligibility_of_run(run_dir)
    if not elig["eligible"]:
        return {"recorded_observations": 0, "eligible": False, "reasons": elig["reasons"]}
    records = build_records(run_dir, source)
    written = append_records(ledger_dir(tracking_dir) / OBSERVATIONS_FILE, records, key="key")
    top5 = sum(1 for r in records if r.get("observation_class") == "PORTFOLIO_TOP5")
    return {"recorded_observations": top5 if written else 0,
            "recorded_watchlist_diagnostics": (len(records) - 1 - top5) if written else 0, "eligible": True,
            "already_recorded": written == 0,
            "ledger": str(ledger_dir(tracking_dir) / OBSERVATIONS_FILE)}


def sync_runs(runs_dir="runs", tracking_dir: Optional[str] = None) -> Dict[str, Any]:
    """Record every eligible completed run not yet in the ledger (recovery after interruptions)."""
    out = {"recorded_runs": [], "skipped": {}}
    base = Path(runs_dir)
    if not base.exists():
        return out
    for d in sorted(p for p in base.iterdir() if p.is_dir()):
        if not (d / "validation_result.json").exists():
            continue
        res = record_run(d, tracking_dir, source="backfill_from_run_artifacts")
        if res.get("eligible") and not res.get("already_recorded"):
            out["recorded_runs"].append(d.name)
        elif not res.get("eligible"):
            out["skipped"][d.name] = res["reasons"]
    import_legacy_exclusions(tracking_dir)
    return out


def read_observations(tracking_dir: Optional[str] = None) -> List[Dict[str, Any]]:
    return read_jsonl(ledger_dir(tracking_dir) / OBSERVATIONS_FILE)


def read_events(tracking_dir: Optional[str] = None) -> List[Dict[str, Any]]:
    return read_jsonl(ledger_dir(tracking_dir) / EVENTS_FILE)


def append_event(kind: str, target: Dict[str, str], reason: str, category: Optional[str] = None,
                 tracking_dir: Optional[str] = None, source: str = "user", details: Optional[Dict] = None) -> bool:
    """Append an EXCLUSION / CORRECTION / NOTE event linked to an original record."""
    if kind not in ("EXCLUSION", "CORRECTION", "NOTE"):
        raise ValueError(f"unknown event kind {kind}")
    if kind == "EXCLUSION" and category not in EXCLUSION_CATEGORIES:
        raise ValueError(f"exclusion category must be one of {sorted(EXCLUSION_CATEGORIES)}")
    if not reason or not reason.strip():
        raise ValueError("an event needs a reason")
    key = _sha256(canonical_json({"kind": kind, "target": target, "category": category, "reason": reason}))
    rec = {"record_type": "EVENT", "schema": SCHEMA, "event_id": key, "kind": kind, "target": target,
           "category": category, "reason": reason.strip(), "source": source, "at": _now(), "details": details}
    return append_records(ledger_dir(tracking_dir) / EVENTS_FILE, [rec], key="event_id") == 1


def import_legacy_exclusions(tracking_dir: Optional[str] = None) -> int:
    """Mirror tracking/excluded_runs.json (kept unchanged) into the event log, idempotently."""
    path = Path(tracking_dir or TRACKING_DIR) / LEGACY_EXCLUSIONS_FILE
    if not path.exists():
        return 0
    n = 0
    for run_id, reason in json.loads(path.read_text(encoding="utf-8")).items():
        n += append_event("EXCLUSION", {"run_id": run_id}, reason, "PRE_FIX", tracking_dir,
                          source=f"tracking/{LEGACY_EXCLUSIONS_FILE}")
    return n


def exclusions_index(tracking_dir: Optional[str] = None) -> Dict[str, List[Dict[str, Any]]]:
    """{run_id or observation_id: [exclusion events]} - legacy JSON is always honoured too."""
    idx: Dict[str, List[Dict[str, Any]]] = {}
    for e in read_events(tracking_dir):
        if e.get("kind") != "EXCLUSION":
            continue
        tgt = e["target"].get("observation_id") or e["target"].get("run_id")
        idx.setdefault(tgt, []).append(e)
    legacy = Path(tracking_dir or TRACKING_DIR) / LEGACY_EXCLUSIONS_FILE
    if legacy.exists():
        for run_id, reason in json.loads(legacy.read_text(encoding="utf-8")).items():
            if not any(e.get("reason") == reason for e in idx.get(run_id, [])):
                idx.setdefault(run_id, []).append({"kind": "EXCLUSION", "category": "PRE_FIX", "reason": reason,
                                                   "source": f"tracking/{LEGACY_EXCLUSIONS_FILE}"})
    return idx


def eligibility_cohort(obs: Dict[str, Any], excl: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    events = excl.get(obs["run_id"], []) + excl.get(obs.get("observation_id", ""), [])
    if not events:
        return {"cohort": VALID_PROSPECTIVE, "exclusions": []}
    cohorts = [EXCLUSION_CATEGORIES.get(e.get("category"), DATA_INVALID) for e in events]
    cohort = PRE_FIX_EXCLUDED if PRE_FIX_EXCLUDED in cohorts else DATA_INVALID
    return {"cohort": cohort, "exclusions": [{"category": e.get("category"), "reason": e.get("reason"),
                                              "source": e.get("source")} for e in events]}


def corrections_for(obs_id: str, tracking_dir: Optional[str] = None) -> List[Dict[str, Any]]:
    return [e for e in read_events(tracking_dir)
            if e.get("kind") == "CORRECTION" and e["target"].get("observation_id") == obs_id]


def verify(tracking_dir: Optional[str] = None, runs_dir="runs") -> Dict[str, Any]:
    """Hash chains intact, and every RUN record still matches its run artifacts and rebuild."""
    out = {"chains": [verify_chain(ledger_dir(tracking_dir) / OBSERVATIONS_FILE),
                      verify_chain(ledger_dir(tracking_dir) / EVENTS_FILE)], "runs": {}}
    obs = read_observations(tracking_dir)
    for run in (r for r in obs if r["record_type"] == "RUN"):
        d = Path(runs_dir) / run["run_id"]
        if not d.exists():
            out["runs"][run["run_id"]] = {"artifacts": "MISSING", "reconstruction": "NOT_POSSIBLE"}
            continue
        changed = [f for f, h in run["artifact_sha256"].items()
                   if not (d / f).exists() or _file_sha256(d / f) != h]
        rebuilt = {r["key"]: r for r in build_records(d, "verify")}
        stored = {r["key"]: r for r in obs if r.get("run_id") == run["run_id"]}
        volatile = {"recorded_at", "record_source", "prev_hash", "record_hash"}
        def _stable(rec):
            return canonical_json({a: b for a, b in rec.items() if a not in volatile})
        diffs = sorted(k for k in stored if k not in rebuilt or _stable(stored[k]) != _stable(rebuilt[k]))
        out["runs"][run["run_id"]] = {"artifacts": "UNCHANGED" if not changed else f"CHANGED: {changed}",
                                      "reconstruction": "MATCH" if not diffs else f"MISMATCH: {diffs[:5]}"}
    out["ok"] = all(c["ok"] for c in out["chains"]) and all(
        r["artifacts"] == "UNCHANGED" and r["reconstruction"] == "MATCH" for r in out["runs"].values())
    return out
