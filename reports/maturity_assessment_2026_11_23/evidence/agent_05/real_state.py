"""AGENT 5 (2026-11-23) scratch: read-only look at the stored state.  No provider, no return or performance figure, no money
amount, nothing of .env printed.  Reads one ledger shard per market (the newest).  Writes only its own output beside it."""
import gzip
import json
import os
import sys
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))

import numpy as np                                            # noqa: E402

from terminal.qsf import technicals                           # noqa: E402
from terminal.qsf.ledger import Ledger                        # noqa: E402

OUT = {}
led = Ledger(REPO)
OUT["ledger_verify"] = led.verify()
idx = led.read_index()["rows"]
live = led._live_rows()
OUT["ledger_sessions"] = {m: {"n": sum(1 for r in live if r["market"] == m), "first": min((r["session"] for r in live if r["market"] == m), default=None),
                              "last": max((r["session"] for r in live if r["market"] == m), default=None)} for m in ("US", "KR")}
OUT["ledger_index_keys"] = sorted(live[-1].keys())
vers = Counter()
for m in ("US", "KR"):
    rows = [r for r in live if r["market"] == m]
    snaps = led._load(rows[-1])
    vers[m] = Counter(s.get("model_version") for s in snaps)
    act = Counter((s.get("strategy"), s.get("actionability")) for s in snaps)
    gates = Counter(g if isinstance(g, str) else g.get("code") for s in snaps for g in (s.get("gates") or []))
    prov = Counter(((s.get("provenance") or {}).get("price")) for s in snaps)
    stale = sum(1 for s in snaps if (s.get("provenance") or {}).get("stale"))
    late = sum(1 for s in snaps if s.get("data_date") != rows[-1]["session"])
    buy_with_missing = Counter()
    for s in snaps:
        if s.get("actionability") == "ACTIONABLE" and s.get("band") in ("BUY_CANDIDATE", "STRONG_BUY_CANDIDATE"):
            miss = [f["factor"] for f in s.get("factors") or [] if f.get("status") == "MISSING" and f.get("scored") is not False and f.get("weight")]
            buy_with_missing[(s.get("strategy"), "with_missing_factor" if miss else "complete")] += 1
    conf = Counter((s.get("strategy"), s.get("confidence")) for s in snaps)
    OUT[f"ledger_newest_{m}"] = {"session": rows[-1]["session"], "snapshots": len(snaps), "model_versions": dict(vers[m]), "actionability": {f"{a}|{b}": n for (a, b), n in sorted(act.items())},
                                 "gates": dict(gates), "provenance_price": dict(prov), "cards_scored_from_stored_copies": stale, "cards_whose_price_date_is_not_the_session": late,
                                 "buy_band_cards": {f"{a}|{b}": n for (a, b), n in sorted(buy_with_missing.items())}, "confidence": {f"{a}|{b}": n for (a, b), n in sorted(conf.items())},
                                 "snapshot_has_conservative_score": "conservative_score" in snaps[0], "snapshot_keys": sorted(snaps[0].keys())}
    del snaps

# the newest scan summaries
for m in ("US", "KR"):
    try:
        d = json.loads((REPO / "data" / "qsf" / f"latest_{m}.json").read_text(encoding="utf-8"))
        OUT[f"latest_{m}"] = {k: d.get(k) for k in ("status", "session", "model_version", "tickers", "scored", "fundamentals", "stale_inputs", "price_source", "universe", "generated_at")} | {"errors": len(d.get("errors") or {})}
    except Exception as exc:
        OUT[f"latest_{m}"] = {"error": type(exc).__name__}

# the look-ahead audit as stored
for name in ("lookahead_audit.json",):
    for p in (REPO / "data").rglob(name):
        d = json.loads(p.read_text(encoding="utf-8"))
        OUT["lookahead_stored"] = {"file": str(p.relative_to(REPO)), "status": d.get("status"), "checked_at": d.get("checked_at"), "prices_to": d.get("prices_to"), "sampled_days": d.get("sampled_days"),
                                   "functions": [{k: f.get(k) for k in ("id", "days", "filled", "moved", "ok")} for f in d.get("functions") or []],
                                   "control": {k: (d.get("control") or {}).get(k) for k in ("id", "days", "moved", "ok")},
                                   "records": [{k: r.get(k) for k in ("store", "sessions", "first", "last", "chain", "before_next_open", "late")} for r in d.get("records") or []], "problems": d.get("problems")}

# KRX daily files: are the days on file a whole calendar? (file names only)
root = REPO / "research_data" / "krx"
days = {b: sorted(p.name[:10] for p in (root / b).glob("*.json.gz")) for b in ("KOSPI", "KOSDAQ")}
both = sorted(set(days["KOSPI"]) & set(days["KOSDAQ"]))
first = (date.today() - timedelta(days=800)).isoformat()
win = [d for d in both if d >= first]
gaps = []
for a, b in zip(win, win[1:]):
    g = int(np.busday_count(np.datetime64(a) + 1, np.datetime64(b)))
    if g >= 1:
        gaps.append((a, b, g))
OUT["krx_day_files"] = {"kospi": len(days["KOSPI"]), "kosdaq": len(days["KOSDAQ"]), "only_one_board": len(set(days["KOSPI"]) ^ set(days["KOSDAQ"])), "first": both[0] if both else None, "last": both[-1] if both else None,
                        "in_800_day_window": len(win), "weekday_gaps_in_window": len(gaps), "longest_gaps": sorted(gaps, key=lambda x: -x[2])[:8],
                        "one_weekday_gaps": [g[:2] for g in gaps if g[2] == 1][:40]}

# the Korean bar store of the newest scan: holes, impossible rows, runs of days without trade (counts only)
try:
    with gzip.open(REPO / "data" / "qsf" / "bars_KR.json.gz", "rt", encoding="utf-8") as fh:
        kb = json.load(fh)
    gap_hist, zero_run, n_rows, last_dates, bad, dup = Counter(), Counter(), [], Counter(), 0, 0
    for code, rows in kb.items():
        year = rows[-253:]
        gap_hist[technicals._max_gap([r["date"] for r in year])] += 1
        run = best = 0
        for r in year:
            run = run + 1 if (r.get("volume") or 0) == 0 else 0
            best = max(best, run)
        zero_run["0" if best == 0 else "1-5" if best <= 5 else "6-10" if best <= 10 else "11+"] += 1
        n_rows.append(len(rows))
        last_dates[rows[-1]["date"]] += 1
        bad += sum(1 for r in year if (r.get("high") is not None and r.get("low") is not None and r["high"] < r["low"]) or (r.get("volume") is not None and r["volume"] < 0))
        dup += sum(1 for i in range(1, len(rows)) if rows[i]["date"] <= rows[i - 1]["date"])
    OUT["bars_KR_store"] = {"stocks": len(kb), "rows_min_median_max": [int(min(n_rows)), int(np.median(n_rows)), int(max(n_rows))], "last_dates": dict(last_dates), "longest_weekday_gap_per_stock": dict(sorted(gap_hist.items())),
                            "longest_run_of_days_without_trade_in_the_last_year": dict(zero_run), "impossible_rows": bad, "doubled_or_unordered_rows": dup,
                            "stocks_under_200_rows": sum(1 for x in n_rows if x < 200)}
    del kb
except Exception as exc:
    OUT["bars_KR_store"] = {"error": type(exc).__name__, "text": str(exc)[:100]}

# coin reply on file: contracts whose name starts with a digit (unit prefixes)
try:
    doc = json.loads((REPO / "data" / "terminal" / "cache" / "coin_public.json").read_text(encoding="utf-8"))
    syms = list(doc.get("symbols") or doc.get("bars") or [])
    OUT["coin_reply_on_file"] = {"symbols": len(syms), "starting_with_a_digit": [s for s in syms if s[:1].isdigit()], "close_ms": doc.get("close_ms"), "fetched_ms": doc.get("fetched_ms")}
    del doc
except Exception as exc:
    OUT["coin_reply_on_file"] = {"error": type(exc).__name__}

# price archive and backups (names, sizes and devices only)
arch = REPO / "data" / "qsf" / "price_archive"
OUT["price_archive"] = {p.name: p.stat().st_size for p in sorted(arch.glob("*"))} if arch.exists() else None
bdir = Path(os.environ.get("QPP_BACKUP_DIR") or Path.home() / "QuantEngineBackups")
if bdir.exists():
    names = sorted(p.name for p in bdir.iterdir())
    OUT["backups"] = {"folder_is_default": not os.environ.get("QPP_BACKUP_DIR"), "entries": len(names), "newest": names[-3:], "same_device_as_repository": os.stat(bdir).st_dev == os.stat(REPO).st_dev}
else:
    OUT["backups"] = {"folder_exists": False}

# forward stores: sessions on file (index lines only)
fw = {}
for p in sorted((REPO / "research_data").glob("*/index.jsonl")):
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
        fw[p.parent.name] = len(lines)
    except OSError:
        pass
OUT["forward_store_index_lines"] = fw

Path(__file__).with_name("real_state_output.json").write_text(json.dumps(OUT, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
for k, v in OUT.items():
    print(k, json.dumps(v, ensure_ascii=False, default=str)[:1800])
