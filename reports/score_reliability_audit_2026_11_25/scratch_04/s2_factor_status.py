"""Agent 4: factor status counts on the latest recorded session, by market x strategy.  No prices, no outcomes."""
import gzip, json, sys
from collections import Counter, defaultdict
from pathlib import Path
base = Path(".")
rows = [json.loads(l) for l in (base/"data/qsf/ledger/index.jsonl").read_text().splitlines()]
void = {r["file"] for r in rows if r.get("type") == "VOID"}
live = [r for r in rows if r.get("type") != "VOID" and r["file"] not in void]
session = sys.argv[1] if len(sys.argv) > 1 else max(r["session"] for r in live)
res = {}
for market in ("US", "KR"):
    snaps = []
    for r in live:
        if r["market"] == market and r["session"] == session:
            with gzip.open(base/"data/qsf/ledger"/r["file"], "rt") as fh:
                snaps += [json.loads(x) for x in fh]
    for strat in ("SWING", "LONG_TERM"):
        co = [s for s in snaps if s["strategy"] == strat]
        st = defaultdict(Counter)
        meta = {}
        for s in co:
            for f in s["factors"]:
                st[(f["domain"], f["factor"])][f["status"]] += 1
                meta[(f["domain"], f["factor"])] = (f.get("weight"), f.get("scored", True))
        print(f"\n== {market} {strat} session {session}: {len(co)} snapshots, versions {Counter(s['model_version'] for s in co)}")
        print("actionability", dict(Counter(s["actionability"] for s in co)), "confidence", dict(Counter(s.get("confidence") for s in co)))
        cov = sorted(s["coverage"] for s in co if s.get("coverage") is not None)
        if cov:
            print("coverage min/p10/median", cov[0], cov[len(cov)//10], cov[len(cov)//2], " <0.9:", sum(c < 0.9 for c in cov), " <0.8:", sum(c < 0.8 for c in cov))
        table = {}
        for (dom, fac), c in sorted(st.items()):
            w, scored = meta[(dom, fac)]
            print(f"{dom:12s} {fac:26s} w={w} scored={scored} {dict(c)}")
            table[f"{dom}.{fac}"] = {"weight": w, "scored": scored, **dict(c)}
        prov_stale = sum(1 for s in co if (s.get("provenance") or {}).get("stale"))
        price_src = Counter((s.get("provenance") or {}).get("price") for s in co)
        gates = Counter(g.get("code") for s in co for g in (s.get("gates") or []))
        hb = Counter(str(s.get("band_held_back")) for s in co)
        print("provenance.stale:", prov_stale, " price source:", dict(price_src))
        print("gates:", dict(gates)); print("band_held_back:", dict(hb))
        # statement age
        import datetime as dt
        ages = []
        nofund = 0
        for s in co:
            ff = (s.get("provenance") or {}).get("fund_filed")
            if ff:
                ages.append((dt.date.fromisoformat(session) - dt.date.fromisoformat(ff[:10])).days)
            else:
                nofund += 1
        ages.sort()
        if ages:
            print("fund_filed age days: min", ages[0], "median", ages[len(ages)//2], "p90", ages[int(len(ages)*.9)], "max", ages[-1], " >365:", sum(a > 365 for a in ages), " >469:", sum(a > 469 for a in ages), " none:", nofund)
        res[f"{market}_{strat}"] = {"n": len(co), "factors": table, "provenance_stale": prov_stale, "price_source": dict(price_src), "gates": dict(gates), "fund_none": nofund}
json.dump({"session": session, "cohorts": res}, open(Path(__file__).with_name(f"s2_factor_status_{session}.json"), "w"), ensure_ascii=False, indent=1)
