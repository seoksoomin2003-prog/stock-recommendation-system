"""Reads the recorded BT-1 result files (no computation)."""
import json
def short(o):
    return {k: (round(x, 4) if isinstance(x, float) else x) for k, x in o.items() if not isinstance(x, (dict, list))}
for m in ("US", "KR"):
    d = json.load(open(f"reports/qsf/QSF_BACKTEST_CURRENT_{m}.json"))
    print("=====", m, d["evaluation_days"], d["first"], d["last"], d["benchmark"], d["cost_round_trip_pct"], d["mean_scored"])
    for s, v in d["strategies"].items():
        print(" --", s, v["reading"], "primary", v["primary_horizon"])
        for h, hv in v["horizons"].items():
            r = hv["rank"]
            print("   h", h, "ic", round(r["ic"], 4), "t", round(r["t"], 2), "lag", r["lag"], r["verdict"], "checks", r.get("checks"), "| top-idx", round(hv["fifths"]["top_minus_index"], 4), "band-idx", round(hv["fifths"]["band"]["minus_index"], 4) if hv["fifths"].get("band") else None, "mono", hv["fifths"]["monotone"])
        a = v["accounts"]
        print("   accounts keys:", list(a) if isinstance(a, dict) else type(a))
        for k, av in a.items():
            if isinstance(av, dict): print("    ", k, json.dumps(short(av), ensure_ascii=False)[:600])
            else: print("    ", k, av)
