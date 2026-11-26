import json, sys, time, urllib.request
E = sys.argv[1]
led = json.load(open(E + "/ledger_cards.json"))
for m, t in (("US", "MSFT"), ("US", "JPM"), ("KR", "005930")):
    t0 = time.time()
    r = json.load(urllib.request.urlopen(f"http://127.0.0.1:8765/api/qsf/evaluate?t={t}&market={m}", timeout=120))
    el = time.time() - t0
    print(m, t, "status", r.get("status"), "rank_basis", r.get("rank_basis"), f"{el:.1f}s")
    for s, c in (r.get("cards") or {}).items():
        L = led.get(f"{m}:{t}:{s}")
        if not L: print("  no ledger row", s); continue
        live = {f["factor"]: f.get("normalized") for f in c["factors"]}
        diffs = {k: (L["factors"].get(k), v) for k, v in live.items() if (L["factors"].get(k) is None) != (v is None) or (v is not None and abs(v - L["factors"][k]) > 1e-9)}
        print(f"  {s}: live score {c['score']:.4f} data_date {c['data_date']} | ledger score {L['score']:.4f} data_date {L['data_date']} | band {c['band']} vs {L['band']} | factor diffs {len(diffs)}/{len(live)}")
        for k, (a, b) in diffs.items(): print(f"      {k}: ledger {a} live {b}")
