import json, glob
def r(v):
    if isinstance(v, float): return round(v, 4)
    if isinstance(v, dict): return {k: r(x) for k, x in v.items()}
    if isinstance(v, list): return [r(x) for x in v][:12]
    return v
def show(name, d, keys):
    out = {k: r(d[k]) for k in keys if k in d}
    print("  ", name, json.dumps(out, ensure_ascii=False)[:900])
PK = ["hypothesis","strategy","horizon","dates","first","last","lag","mean_n","ic","t","ic_positive_share","spread_net","buy_excess","buy_dates","early","late","verdict","checks","reading","condition_a","condition_b","top_excess","top_fifth_excess","average_return","market_return","money"]
for f in ["QSF_1_2_VALIDATION","QSF_PIT_VALIDATION","QSF_OPEN_VALIDATION","QSF_OOS_TEST","QSF_CORRECTED_OPEN","QSF_CORRECTED_OOS","QSF_KR_LIVE_REPLAY","QSF_KR_UNIVERSE_TEST","QSF_KR_LONG_EARLY"]:
    d = json.load(open(f"reports/qsf/{f}.json", encoding="utf-8"))
    print("##", f, d.get("status"), d.get("note"))
    p = d.get("primary")
    if isinstance(p, dict) and "ic" in p: show("primary", p, PK)
    elif isinstance(p, dict):
        for k, v in p.items(): show(k, v, PK)
    if "money" in d: print("   money", json.dumps(r(d["money"]), ensure_ascii=False)[:1200])
