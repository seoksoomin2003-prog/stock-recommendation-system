"""Agent 03: which raw inputs are empty inside the long-term factors of the 2026-11-20 record.  Ledger factor values only."""
import sys, pathlib, collections, json
real = pathlib.Path.home() / "Developer/quant-stock-engine"; sys.path.insert(0, str(real))
from terminal.qsf.ledger import Ledger
led = Ledger(real); out = {}
for m in ("US", "KR"):
    snaps = []
    for r in led._live_rows():
        if r["market"] == m and r["session"] == "2026-11-20": snaps += led._load(r)
    S = [s for s in snaps if s["strategy"] == "LONG_TERM" and s.get("data_date") == "2026-11-20" and s["ticker"] != "SPY"]
    reasons = collections.Counter(); none_in = collections.defaultdict(collections.Counter)
    for s in S:
        for f in s["factors"]:
            if f["factor"] == "free_cash_flow" and f.get("status") == "MISSING": reasons[(f.get("reason") or "")[:60]] += 1
            if f.get("normalized") is not None and isinstance(f.get("raw"), dict):
                for k, v in f["raw"].items():
                    if v is None: none_in[f["factor"]][k] += 1
    out[m] = {"n": len(S), "free_cash_flow_missing_reasons": dict(reasons), "empty_raw_inputs": {k: dict(v) for k, v in none_in.items()}}
json.dump(out, open(pathlib.Path(__file__).parent / "exp_raw_gaps.json", "w"), ensure_ascii=False, indent=1)
print(json.dumps(out, ensure_ascii=False, indent=1))
