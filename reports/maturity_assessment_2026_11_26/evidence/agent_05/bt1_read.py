"""Reads the recorded BT-1 result files (no computation): structure and the recorded headline figures."""
import json
for m in ("US", "KR"):
    d = json.load(open(f"reports/qsf/QSF_BACKTEST_CURRENT_{m}.json"))
    print("=====", m, [k for k in d if k != "strategies"])
    for k in d:
        if k != "strategies" and not isinstance(d[k], (dict, list)): print("  ", k, d[k])
        elif k != "strategies": print("  ", k, json.dumps(d[k], ensure_ascii=False)[:400])
    for s, v in d["strategies"].items():
        print(" --", s, list(v))
        print("   reading", v.get("reading"), json.dumps({k: v[k] for k in v if k not in ("horizons", "accounts", "reading")}, ensure_ascii=False)[:500])
        for h, hv in (v.get("horizons") or {}).items():
            r = hv.get("rank") or hv
            print("   h", h, list(hv)[:12])
            print("     ", json.dumps({k: (round(x, 4) if isinstance(x, float) else x) for k, x in r.items() if not isinstance(x, (dict, list))}, ensure_ascii=False)[:420])
            for kk in ("checks", "fifths", "band_70", "buy"):
                if kk in hv: print("     ", kk, json.dumps(hv[kk], ensure_ascii=False)[:420])
        for a, av in (v.get("accounts") or {}).items():
            print("   acct", a, json.dumps({k: (round(x, 4) if isinstance(x, float) else x) for k, x in av.items() if not isinstance(x, (dict, list))}, ensure_ascii=False)[:520])
