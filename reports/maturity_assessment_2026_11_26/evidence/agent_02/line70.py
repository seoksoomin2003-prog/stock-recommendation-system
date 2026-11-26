"""Where the fixed line of 70 sits in each recorded session (scores only), and who is in the long buy band."""
from pathlib import Path
from collections import Counter
import json, gc
import numpy as np
from terminal.qsf.ledger import Ledger
led = Ledger(Path(".")); rows = led._live_rows()
for r in rows[-16:]:
    snaps = led._load(r); out = []
    for st in ("SWING", "LONG_TERM"):
        s = np.array([c["score"] for c in snaps if c["strategy"] == st and c["score"] is not None], float)
        out.append(f"{st[:5]} n={len(s)} >=70 {np.mean(s>=70)*100:4.1f}% >=80 {np.mean(s>=80)*100:4.1f}% med {np.median(s):.1f} p90 {np.percentile(s,90):.1f}")
    print(r["session"], r["market"], r["model_version"], " | ".join(out))
    last = snaps if r is rows[-1] or r is rows[-2] else None
    if last:
        for st in ("LONG_TERM",):
            cs = [c for c in last if c["strategy"] == st]
            fin = lambda c: any(f["factor"] == "leverage" and f.get("status") == "NOT_APPLICABLE" for f in c["factors"])
            buy = [c for c in cs if c["band"] in ("BUY_CANDIDATE", "STRONG_BUY_CANDIDATE")]
            print("   financial share all %.2f, in long buy band %.2f (n=%d of %d)" % (np.mean([fin(c) for c in cs]), np.mean([fin(c) for c in buy]) if buy else float('nan'), sum(fin(c) for c in buy), len(buy)))
            print("   missing factors in buy band:", dict(Counter(f["factor"] for c in buy for f in c["factors"] if f.get("status") == "MISSING" and f.get("weight"))))
            print("   partial-input factors (inputs have<total) all cards:", dict(Counter(f["factor"] for c in cs for f in c["factors"] if f.get("inputs"))))
    del snaps; gc.collect()
for m in ("US", "KR"):
    d = json.load(open(f"reports/qsf/QSF_BACKTEST_CURRENT_{m}.json"))
    print(m, d.get("status"), d.get("first"), d.get("last"), str(d.get("note"))[:300])
    for k, v in (d.get("strategies") or {}).items():
        print("  ", k, {kk: (vv if not isinstance(vv, (dict, list)) else "...") for kk, vv in v.items()})
