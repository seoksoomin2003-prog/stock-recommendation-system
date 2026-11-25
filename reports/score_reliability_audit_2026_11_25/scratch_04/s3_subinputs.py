"""Agent 4: inside factors that read REAL/STALE, how many raw sub-inputs are None?  Latest recorded session.  No prices joined, no outcomes."""
import gzip, json, sys
from collections import Counter, defaultdict
from pathlib import Path
base = Path(".")
rows = [json.loads(l) for l in (base/"data/qsf/ledger/index.jsonl").read_text().splitlines()]
void = {r["file"] for r in rows if r.get("type") == "VOID"}
live = [r for r in rows if r.get("type") != "VOID" and r["file"] not in void]
session = sys.argv[1] if len(sys.argv) > 1 else max(r["session"] for r in live)
out = {}
for market in ("US", "KR"):
    snaps = []
    for r in live:
        if r["market"] == market and r["session"] == session:
            with gzip.open(base/"data/qsf/ledger"/r["file"], "rt") as fh:
                snaps += [json.loads(x) for x in fh]
    for strat in ("SWING", "LONG_TERM"):
        co = [s for s in snaps if s["strategy"] == strat]
        none = defaultdict(Counter); tot = Counter()
        for s in co:
            for f in s["factors"]:
                if f["status"] in ("REAL", "STALE") and isinstance(f.get("raw"), dict) and f["domain"] in ("FUNDAMENTAL", "RISK", "EVENTS"):
                    tot[f["factor"]] += 1
                    for k, v in f["raw"].items():
                        if v is None:
                            none[f["factor"]][k] += 1
        print(f"\n== {market} {strat} {session} (n={len(co)}): sub-inputs None inside usable factors")
        for fac in sorted(tot):
            if none[fac]:
                print(f"  {fac:26s} usable={tot[fac]:4d}  none: {dict(none[fac])}")
        out[f"{market}_{strat}"] = {fac: {"usable": tot[fac], "none": dict(none[fac])} for fac in tot}
        ic = [s.get("input_coverage") for s in co if s.get("input_coverage") is not None]
        if ic:
            vals = sorted(x if isinstance(x, (int, float)) else (x.get("share") if isinstance(x, dict) else None) for x in ic)
            vals = [v for v in vals if v is not None]
            if vals:
                print("  input_coverage min/p10/median:", vals[0], vals[len(vals)//10], vals[len(vals)//2], " <0.8:", sum(v < 0.8 for v in vals))
            else:
                print("  input_coverage sample:", ic[0])
        cs = [(s["score"], s.get("conservative_score")) for s in co if s.get("score") is not None and s.get("conservative_score") is not None]
        if cs:
            d = sorted(a - b for a, b in cs)
            print("  score - conservative_score: median", round(d[len(d)//2], 2), "p90", round(d[int(len(d)*.9)], 2), "max", round(d[-1], 2), " >=3pt:", sum(x >= 3 for x in d), " >=5pt:", sum(x >= 5 for x in d))
json.dump(out, open(Path(__file__).with_name(f"s3_subinputs_{session}.json"), "w"), ensure_ascii=False, indent=1)
