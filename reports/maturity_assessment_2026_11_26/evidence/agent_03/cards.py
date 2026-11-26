import sys, json, pathlib
repo = pathlib.Path.cwd(); sys.path.insert(0, str(repo))
from terminal.qsf.ledger import Ledger
led = Ledger(repo)
mk = sys.argv[1]; want = sys.argv[2].split(",") if len(sys.argv) > 2 else []
rows = [r for r in led._live_rows() if r["market"] == mk]
snaps = led._load(rows[-1])
L = [s for s in snaps if s["strategy"] == "LONG_TERM"]
def r(x):
    return round(x, 3) if isinstance(x, float) else x
if not want:
    # summary: loss makers, top scorers
    out = []
    for s in L:
        fs = {f["factor"]: f for f in s["factors"]}
        v = fs.get("valuation", {}); g = fs.get("growth_quality", {})
        out.append((s["ticker"], s.get("name"), s.get("sector"), r(s.get("score")), s.get("band"), s.get("entry_status"), s.get("confidence"),
                    r((v.get("raw") or {}).get("pe")), r((g.get("raw") or {}).get("eps_cagr3")), g.get("explanation","")[-30:]))
    out.sort(key=lambda x: -(x[3] or 0))
    print("TOP 25"); [print(o) for o in out[:25]]
    print("LOSS"); [print(o) for o in out if o[7] is not None and o[7] <= 0][:40]
    print(len(L))
    import collections
    print(collections.Counter(o[4] for o in out)); print(collections.Counter(o[5] for o in out)); print(collections.Counter(o[2] for o in out))
else:
    for s in L:
        if s["ticker"] in want:
            print("=" * 100)
            print({k: r(s.get(k)) for k in ("ticker","name","sector","industry","score","conservative_score","band","band_held_back","action","entry_status","confidence","coverage","price","deal_pin")})
            print("domains", {d: (r(v["points"]), r(v["score_100"]), r(v["coverage"])) for d, v in s["domains"].items()})
            for f in s["factors"]:
                print(f"  {f['domain'][:4]} {f['factor']:22s} w{f['weight']:>2} n={r(f.get('normalized'))} {f['status']:8s} raw={ {k: r(v) for k, v in (f.get('raw') or {}).items() if not isinstance(v,(dict,list))} } | {f.get('explanation') or f.get('reason')}")
            for k in ("fund_checks","fund_period","gates","entry_reason","entry_note","reasons","notes","warnings","market_note","fuller_inputs","expectations"):
                if s.get(k): print(" ", k, json.dumps(s[k], ensure_ascii=False)[:900])
            print("  keys:", sorted(s.keys()))
            h = s.get("holding") or {}
            print("  holding:", json.dumps({k: h[k] for k in h if k not in ("cost_basis",)}, ensure_ascii=False)[:1200])
