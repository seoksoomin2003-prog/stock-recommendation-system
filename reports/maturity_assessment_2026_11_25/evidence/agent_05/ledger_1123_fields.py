"""Read-only tallies of the 2026-11-23 records (QSF-1.5.2): gates, confidence, input coverage, held-back bands, halted names.
No prices compared, no returns."""
import json, sys
from collections import Counter
from pathlib import Path
repo = Path.home() / "Developer/quant-stock-engine"
sys.path.insert(0, str(repo))
from terminal.qsf.ledger import Ledger
led = Ledger(repo)
out = {}
for m in ("US", "KR"):
    row = [r for r in led._live_rows() if r["market"] == m and r["session"] == "2026-11-23"][0]
    snaps = led._load(row)
    keys = Counter(k for s in snaps for k in s.keys())
    gates = Counter(g.get("code") if isinstance(g, dict) else g for s in snaps for g in (s.get("gates") or []))
    conf = Counter((s["strategy"], s.get("confidence")) for s in snaps)
    held = Counter((s["strategy"], bool(s.get("band_held_back"))) for s in snaps)
    cov = [s.get("input_coverage") for s in snaps if isinstance(s.get("input_coverage"), (int, float))]
    halted = {s["ticker"]: [g.get("text")[:70] for g in s.get("gates") or [] if isinstance(g, dict) and "거래가 없던" in (g.get("text") or "")]
              for s in snaps if any(isinstance(g, dict) and "거래가 없던" in (g.get("text") or "") for g in s.get("gates") or [])}
    prov_keys = Counter(k for s in snaps for k in (s.get("provenance") or {}).keys())
    stale_prov = sum(1 for s in snaps if (s.get("provenance") or {}).get("stale"))
    sample_prov = next((s.get("provenance") for s in snaps if (s.get("provenance") or {}).get("stale")), None)
    four = {t: [(s["strategy"], s.get("actionability"), s.get("confidence"), [g.get("code") for g in s.get("gates") or []]) for s in snaps if s["ticker"] == t]
            for t in ("000880", "183300", "440110", "207940")} if m == "KR" else None
    out[m] = {"records": len(snaps), "fields": dict(keys), "gates": dict(gates), "confidence": {f"{a}/{b}": c for (a, b), c in conf.items()},
              "band_held_back": {f"{a}/{b}": c for (a, b), c in held.items()},
              "input_coverage_min_mean": [min(cov), sum(cov) / len(cov)] if cov else None, "halt_gated": halted,
              "provenance_keys": dict(prov_keys), "cards_with_provenance_stale": stale_prov, "sample_stale": sample_prov, "four_halted_2026_11_20": four}
print(json.dumps(out, ensure_ascii=False, indent=1, default=str)[:6000])
json.dump(out, open(repo / "reports/maturity_assessment_2026_11_25/evidence/agent_05/ledger_1123_fields.json", "w"), ensure_ascii=False, indent=1, default=str)
