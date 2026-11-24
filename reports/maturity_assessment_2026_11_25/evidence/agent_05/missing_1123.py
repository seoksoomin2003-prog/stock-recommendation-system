"""Read-only, 2026-11-23 records: how many actionable cards in a buy band, or ranked by the raw score, miss a scored factor;
the stored raw vs conservative score gap.  Scores only; no prices, no returns."""
import json, sys
from collections import Counter
from pathlib import Path
repo = Path.home() / "Developer/quant-stock-engine"
sys.path.insert(0, str(repo))
from terminal.qsf.ledger import Ledger
from terminal.qsf import config, engine
led = Ledger(repo)
out = {}
for m in ("US", "KR"):
    row = [r for r in led._live_rows() if r["market"] == m and r["session"] == "2026-11-23"][0]
    snaps = led._load(row)
    for s in ("SWING", "LONG_TERM"):
        cs = [x for x in snaps if x["strategy"] == s and x.get("actionability") == "ACTIONABLE"]
        never = config.NEVER_AVAILABLE.get((m, s), ())
        def miss(x):
            return [f["factor"] for f in x["factors"] if f.get("status") == "MISSING" and f.get("scored") is not False and f["factor"] not in never]
        buy = [x for x in cs if x.get("band") in engine.BUY_CODES]
        top20 = sorted(cs, key=lambda x: -(x["score"] or 0))[:20]
        gaps = [round(x["score"] - x["conservative_score"], 2) for x in cs if x.get("conservative_score") is not None and miss(x)]
        out[f"{m}/{s}"] = {"actionable": len(cs), "in_buy_band": len(buy), "buy_band_with_missing": sum(1 for x in buy if miss(x)),
                           "held_back": sum(1 for x in cs if x.get("band_held_back")), "top20_raw_with_missing": sum(1 for x in top20 if miss(x)),
                           "missing_factor_counts": dict(Counter(f for x in cs for f in miss(x)).most_common(6)),
                           "raw_minus_conservative_max": max(gaps) if gaps else None,
                           "entry_now_with_missing_valuation": sum(1 for x in cs if x.get("entry_status") == "ENTRY_NOW" and "valuation" in miss(x))}
print(json.dumps(out, ensure_ascii=False, indent=1))
json.dump(out, open(repo / "reports/maturity_assessment_2026_11_25/evidence/agent_05/missing_1123.json", "w"), ensure_ascii=False, indent=1)
