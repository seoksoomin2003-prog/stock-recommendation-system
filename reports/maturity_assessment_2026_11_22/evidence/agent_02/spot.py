"""Scratch (agent 02): spot-check stored fundamental figures against the cached annual statement rows (read-only, no network)."""
import sys, json
from pathlib import Path
repo = Path("~/Developer/quant-stock-engine")
sys.path.insert(0, str(repo / "reports/maturity_assessment_2026_11_22/evidence/agent_02"))
from load import load, sectors, raw
from terminal.cache import FileCache
from terminal import sources
from terminal.qsf import factors as F
cache = FileCache(repo / "data/qsf/cache")
PICK = {"US": ["JPM", "O", "NVDA", "CRWD", "NEE", "XOM", "MCD", "V", "GOOGL", "PHM", "PGR"], "KR": ["005930", "105560", "034730", "000660", "015760", "011200", "293490", "032830"]}
KEYS = ["revenue", "gross_profit", "op_income", "net_income", "net_income_all", "equity", "equity_all", "assets", "liabilities", "current_assets", "current_liabilities", "cash", "ocf", "capex", "interest",
        "debt_total", "debt_long", "debt_short", "debt_borrow", "shares_avg", "eps", "buyback", "dividends"]
def last2(rows, as_of):
    per = {}
    for r in rows or []:
        if r["filed"] <= as_of and (r["end"] not in per or r["filed"] >= per[r["end"]]["filed"]):
            per[r["end"]] = r
    ks = sorted(per)[-4:]
    return [(k, per[k]["val"], per[k].get("alias", per[k].get("basis", ""))) for k in ks]
for m in ("US", "KR"):
    row, snaps = load(m); sec = sectors(m)
    L = {s["ticker"]: s for s in snaps if s["strategy"] == "LONG_TERM"}; S = {s["ticker"]: s for s in snaps if s["strategy"] == "SWING"}
    for t in PICK[m]:
        l, s = L.get(t), S.get(t)
        if not l:
            print(f"\n##### {m} {t}: not in the session"); continue
        print(f"\n##### {m} {t} {sec.get(t)} price {l['price']:.2f} LONG {l['score'] and round(l['score'],1)} {l['band']} entry {l.get('entry_status')} FUND {round(l['domains']['FUNDAMENTAL'].get('score_100') or 0,1)} | SWING {s and s['score'] and round(s['score'],1)}")
        for snap in (l, s):
            for f in snap["factors"]:
                if f["domain"] in ("FUNDAMENTAL",) or f["factor"] in ("financial_resilience", "leverage", "capital_allocation"):
                    r = f.get("raw")
                    rr = {k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items()} if isinstance(r, dict) else f.get("reason")
                    print(f"  {snap['strategy'][:4]} {f['factor']:26s} {f['status']:14s} norm {None if f['normalized'] is None else round(f['normalized'],3)}  {rr}  filed {f.get('as_of')}")
        key = f"annual4:{sources.facts_key(t, l.get('cik'))}" if m == "US" else f"krfund3:{t}"
        rec = cache.read(key)
        if not rec or not rec.get("data"):
            print("  (no cached annual under", key, ")"); continue
        a = rec["data"]
        for k in KEYS:
            if a.get(k):
                print(f"    {k:20s}", [(e, f"{v:,.2f}" if abs(v) < 1e6 else f"{v/1e6:,.0f}M", al) for e, v, al in last2(a[k], row["session"])])
        if a.get("_bases"): print("    bases", a["_bases"])
