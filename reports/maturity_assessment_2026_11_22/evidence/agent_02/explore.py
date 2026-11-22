import sys
sys.path.insert(0, "~/Developer/quant-stock-engine/reports/maturity_assessment_2026_11_22/evidence/agent_02")
from load import load, sectors, raw
import statistics as st
for m in ("US", "KR"):
    row, snaps = load(m); sec = sectors(m)
    L = {s["ticker"]: s for s in snaps if s["strategy"] == "LONG_TERM"}; S = {s["ticker"]: s for s in snaps if s["strategy"] == "SWING"}
    def n(s, f): return (raw(s, f) or {}).get("normalized")
    print(f"\n==== {m}")
    # loss makers (pe<=0)
    loss = [t for t, s in L.items() if (raw(s, "valuation", "pe") or 1) <= 0]
    print("loss-makers:", len(loss), "; with LONG score>=55:", sum(1 for t in loss if (L[t]["score"] or 0) >= 55), "; >=70:", [t for t in loss if (L[t]["score"] or 0) >= 70])
    print("  loss-makers growth_quality>=0.7:", [(t, round(n(L[t], "growth_quality"), 2)) for t in loss if (n(L[t], "growth_quality") or 0) >= 0.7][:15])
    print("  sample tech loss:", [(t, sec.get(t, ("", ""))[1], round(L[t]["score"] or 0, 1)) for t in loss if sec.get(t, ("",))[0] in ("Technology", "기술")][:12])
    # expensive and mediocre yet ENTRY_NOW
    em = [t for t, s in L.items() if (n(s, "valuation") is not None and n(s, "valuation") < 0.25 and (n(s, "business_quality") or 0) < 0.6 and s.get("entry_status") == "ENTRY_NOW")]
    print("valuation<0.25 & quality<0.6 & ENTRY_NOW:", len(em), [(t, round(L[t]["score"], 1), round(n(L[t], "valuation"), 2), round(n(L[t], "business_quality"), 2), raw(L[t], "valuation", "pe")) for t in em][:10])
    # buy band with valuation < 0.25
    bb = [t for t, s in L.items() if (s["score"] or 0) >= 70]
    print("buy band n:", len(bb), "; of them valuation<0.25:", sum(1 for t in bb if (n(L[t], "valuation") or 1) < 0.25), "; entry statuses:", {e: sum(1 for t in bb if L[t].get("entry_status") == e) for e in {L[t].get("entry_status") for t in bb}})
    print("  buy band actionability:", {e: sum(1 for t in bb if L[t].get("action") == e) for e in {L[t].get("action") for t in bb}})
    # cheap but deteriorating: valuation>=0.7 and (eps_growth<-0.2 and rev_growth<0)
    def eg(t): return raw(S.get(t) or {}, "earnings_revenue_quality", "eps_growth")
    def rg(t): return raw(S.get(t) or {}, "earnings_revenue_quality", "rev_growth")
    trap = [t for t, s in L.items() if (n(s, "valuation") or 0) >= 0.7 and eg(t) is not None and eg(t) < -0.2 and (rg(t) or 0) < 0]
    print("cheap(valuation>=0.7) with EPS -20% & sales down:", len(trap), "; of them score>=55:", sum(1 for t in trap if (L[t]["score"] or 0) >= 55), "; >=70:", [(t, round(L[t]["score"], 1), L[t].get("entry_status")) for t in trap if (L[t]["score"] or 0) >= 70])
    # EPS fell >20% (any) in buy band
    fall = [t for t in bb if eg(t) is not None and eg(t) < -0.2]
    print("buy band with eps_growth<-20%:", len(fall), [(t, round(eg(t), 2), round(L[t]["score"], 1)) for t in fall][:10])
    # rank correlation valuation vs business_quality (Spearman, scores only)
    pairs = [(n(s, "valuation"), n(s, "business_quality")) for s in L.values() if n(s, "valuation") is not None and n(s, "business_quality") is not None]
    def rk(v):
        o = sorted(range(len(v)), key=lambda i: v[i]); r = [0] * len(v)
        for i, j in enumerate(o): r[j] = i
        return r
    a, b = rk([p[0] for p in pairs]), rk([p[1] for p in pairs])
    print("Spearman valuation vs business_quality:", round(st.correlation(a, b), 3), "n", len(pairs))
    # unknown-sector tickers
    print("unknown sector:", [(t, round(L[t]["score"] or 0, 1), L[t].get("action")) for t in L if not sec.get(t, (None,))[0]])
    # stale fundamentals and as_of age
    ages = {}
    for t, s in L.items():
        f = raw(s, "valuation") or {}
        ages[f.get("status")] = ages.get(f.get("status"), 0) + 1
    print("valuation status:", ages)
    import datetime as dt
    d = []
    for t, s in L.items():
        f = raw(s, "valuation") or {}
        if f.get("as_of"):
            d.append((dt.date.fromisoformat(row["session"]) - dt.date.fromisoformat(f["as_of"])).days)
    print("days since the statements were filed: median", st.median(d), "p90", sorted(d)[int(len(d) * 0.9)], "max", max(d))
    # provenance sample
    any_s = next(iter(L.values())); print("provenance keys:", list((any_s.get("provenance") or {}).keys())); print("holding keys:", list((any_s.get("holding") or {}).keys()))
    fp = any_s.get("fund_period"); print("fund_period in snapshot:", bool(fp), (list(fp.keys()) if fp else None))
