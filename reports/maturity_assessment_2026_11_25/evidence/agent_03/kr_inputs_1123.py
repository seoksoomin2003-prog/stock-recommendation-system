"""Agent 03: how many KR and US long-term cards of the 2026-11-23 record carry each raw input inside the multi-input factors.
Reads the stored factor raw dicts only.  Also counts US swing/long cards whose stored annualised volatility (atr_risk raw) is under 10% / 15%."""
import sys, gc, collections
from pathlib import Path
REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
from terminal.qsf.ledger import Ledger
led = Ledger(REPO)
rows = led._live_rows()
CHECK = {"business_quality": ("roe", "op_margin", "gross_margin", "roe_years_positive"), "financial_resilience": None,
         "balance_dilution": ("debt_equity", "share_change", "equity_assets"), "capital_allocation": ("share_change", "returns_capital"),
         "valuation": ("pe", "pb", "fcf_yield"), "growth_quality": ("rev_cagr3", "eps_cagr3", "rev_growth")}
for m in ("US", "KR"):
    r = [x for x in rows if x["market"] == m and x["session"] == "2026-11-23"][-1]
    cnt = collections.defaultdict(collections.Counter); n = 0; vol = collections.Counter(); keys_fr = collections.Counter()
    for s in led._load(r):
        fs = {f["factor"]: f for f in s.get("factors") or []}
        if s["strategy"] == "SWING" and "atr_risk" in fs:
            raw = fs["atr_risk"].get("raw") or {}
            hv = raw.get("hist_vol") or raw.get("vol") or raw.get("annual_vol")
            if hv is not None:
                vol["n"] += 1; vol["lt10"] += hv < 0.10; vol["lt15"] += hv < 0.15
            else:
                vol["keys:" + ",".join(sorted(raw))] += 1
        if s["strategy"] != "LONG_TERM":
            continue
        n += 1
        for fac, ks in CHECK.items():
            f = fs.get(fac) or {}
            raw = f.get("raw") or {}
            if f.get("status") not in ("REAL", "STALE"):
                cnt[fac]["factor_not_real"] += 1; continue
            if ks is None:
                for k, v in raw.items():
                    keys_fr[k] += v is not None
                continue
            for k in ks:
                if k in raw:
                    cnt[fac][k + "_present"] += raw[k] is not None
    print(m, "long cards", n)
    for fac, c in cnt.items():
        print("  ", fac, dict(c))
    print("   financial_resilience raw present:", dict(keys_fr))
    print("   swing stored vol:", dict(vol))
    gc.collect()
