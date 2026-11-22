"""Scratch (agent 02): SYSTEM TEST D, industry fairness.  Scores and stored raw figures of the newest session only; no returns."""
import sys, statistics as st, json
sys.path.insert(0, "~/Developer/quant-stock-engine/reports/maturity_assessment_2026_11_22/evidence/agent_02")
from load import load, sectors, raw, E
FUND = ("valuation", "business_quality", "growth_quality", "free_cash_flow", "balance_dilution")
RISKF = ("financial_resilience", "leverage")
def med(v):
    v = [x for x in v if x is not None]
    return None if not v else st.median(v)
def f(x, d=1):
    return "  -  " if x is None else f"{x:.{d}f}"
out = {}
for m in ("US", "KR"):
    row, snaps = load(m)
    sec = sectors(m)
    longs = [s for s in snaps if s["strategy"] == "LONG_TERM"]
    print(f"\n=== {m} session {row['session']} model {row['model_version']} LONG_TERM n={len(longs)} sector known={sum(1 for s in longs if sec.get(s['ticker'],(None,))[0])}")
    by = {}
    for s in longs:
        by.setdefault(sec.get(s["ticker"], (None,))[0] or "?", []).append(s)
    allmed = med([s["score"] for s in longs]); allf = med([s["domains"]["FUNDAMENTAL"].get("score_100") for s in longs])
    print(f"ALL: n={len(longs)} score med {f(allmed)} FUND med {f(allf)} buy(>=70) {sum(1 for s in longs if (s['score'] or 0)>=70)}")
    hdr = f"{'sector':24s} {'n':>3s} {'score':>6s} {'FUND':>6s} {'buy70':>5s} | " + " ".join(f"{k[:8]:>8s}" for k in FUND + RISKF) + " | pe    pb   fcfy%  roe%  opm%   D/E  fin%"
    print(hdr)
    table = []
    for k, ss in sorted(by.items(), key=lambda kv: -(med([s["domains"]["FUNDAMENTAL"].get("score_100") for s in kv[1]]) or 0)):
        def fn(name):
            return med([(raw(s, name) or {}).get("normalized") for s in ss])
        def rv(fac, key, pos=False):
            v = [raw(s, fac, key) for s in ss]
            if pos: v = [x for x in v if x is not None and x > 0]
            return med(v)
        fin = sum(1 for s in ss if (raw(s, "leverage") or {}).get("status") == "NOT_APPLICABLE") / len(ss)
        de = med([x for x in (raw(s, "balance_dilution", "debt_equity") for s in ss) if x is not None and x != 99.0])
        line = {"sector": k, "n": len(ss), "score": med([s["score"] for s in ss]), "fund": med([s["domains"]["FUNDAMENTAL"].get("score_100") for s in ss]),
                "buy": sum(1 for s in ss if (s["score"] or 0) >= 70), **{n: fn(n) for n in FUND + RISKF},
                "pe": rv("valuation", "pe", True), "pb": rv("valuation", "pb", True), "fcfy": rv("valuation", "fcf_yield"), "roe": rv("business_quality", "roe"),
                "opm": rv("business_quality", "op_margin"), "de": de, "fin": fin}
        table.append(line)
        print(f"{k[:24]:24s} {line['n']:3d} {f(line['score']):>6s} {f(line['fund']):>6s} {line['buy']:5d} | " + " ".join(f"{f(line[n],2):>8s}" for n in FUND + RISKF)
              + f" | {f(line['pe']):>5s} {f(line['pb'],2):>5s} {f(None if line['fcfy'] is None else line['fcfy']*100):>5s} {f(None if line['roe'] is None else line['roe']*100):>5s} {f(None if line['opm'] is None else line['opm']*100):>5s} {f(line['de'],2):>5s} {fin*100:4.0f}")
    out[m] = table
    # sub-input gaps: for each fundamental factor, the share of stocks whose raw key is None (factor REAL)
    print(f"\n--- {m}: sub-input gaps (share of LONG_TERM stocks with the raw key empty, among stocks where the factor has a value)")
    for fac in FUND + RISKF + ("capital_allocation",):
        fs = [raw(s, fac) for s in longs]
        st_ = {}
        for x in fs:
            st_[(x or {}).get("status")] = st_.get((x or {}).get("status"), 0) + 1
        real = [x for x in fs if x and isinstance(x.get("raw"), dict)]
        keys = sorted({k for x in real for k in x["raw"]})
        print(f"  {fac:22s} status {st_}  " + ", ".join(f"{k} {sum(1 for x in real if x['raw'].get(k) is None)/max(1,len(real))*100:.0f}%" for k in keys))
    # entry statuses
    es = {}
    for s in longs:
        es[s.get("entry_status")] = es.get(s.get("entry_status"), 0) + 1
    print("  entry_status:", es)
    # PE<=0 or None
    pes = [raw(s, "valuation", "pe") for s in longs]
    print(f"  pe None {sum(1 for p in pes if p is None)}, pe<=0 {sum(1 for p in pes if p is not None and p<=0)}, pe>40 {sum(1 for p in pes if p is not None and p>40)}, pe<10 {sum(1 for p in pes if p is not None and 0<p<10)}")
    des = [raw(s, "balance_dilution", "debt_equity") for s in longs]
    print(f"  debt_equity==99 {sum(1 for d in des if d==99.0)}")
json.dump(out, open(E / "test_d_out.json", "w"), ensure_ascii=False, indent=1)
