import sys, pathlib, datetime
repo = pathlib.Path.cwd(); sys.path.insert(0, str(repo))
from terminal.qsf.ledger import Ledger
from terminal.qsf import config
led = Ledger(repo)
for mk in ("US", "KR"):
    rows = [r for r in led._live_rows() if r["market"] == mk]
    L = [s for s in led._load(rows[-1]) if s["strategy"] == "LONG_TERM"]
    n = len(L); fin = nf = 0; finbuy = buy = 0; gm = om = ic = sc = 0; gap10 = 0; bandflip = 0; newer = 0; age = []
    bq_one = 0; finres1 = 0; res_fin = []
    def band(x):
        return next(b[1] for b in config.BANDS if x >= b[0])
    for s in L:
        fs = {f["factor"]: f for f in s["factors"]}
        isfin = fs.get("free_cash_flow", {}).get("status") == "NOT_APPLICABLE"
        isbuy = s["band"] in ("BUY_CANDIDATE", "STRONG_BUY_CANDIDATE")
        buy += isbuy
        if isfin:
            fin += 1; finbuy += isbuy
            r = fs.get("financial_resilience", {}).get("normalized")
            if r is not None: res_fin.append(r)
        else:
            nf += 1
            raw = (fs.get("business_quality", {}).get("raw") or {})
            gm += raw.get("gross_margin") is None; om += raw.get("op_margin") is None
            ic += ((fs.get("financial_resilience", {}).get("raw") or {}).get("interest_cover")) is None
        sc += ((fs.get("balance_dilution", {}).get("raw") or {}).get("share_change")) is None
        fp = s.get("fund_period") or {}
        a, t = (fp.get("annual") or {}), (fp.get("trailing") or {})
        if t.get("newer_quarter") and a.get("score") is not None and t.get("score") is not None:
            newer += 1
            d = abs(t["score"] - a["score"]); gap10 += d >= 10
            bandflip += band(t["score"]) != band(a["score"])
        if a.get("fiscal_end"):
            age.append((datetime.date(2026, 11, 25) - datetime.date.fromisoformat(a["fiscal_end"])).days)
    age.sort()
    print(mk, "n", n, "financial", fin, "buy-band", buy, "financial in buy band", finbuy, f"({finbuy/max(buy,1):.0%} vs {fin/n:.0%} of universe)")
    print("  non-fin without gross margin", gm, "/", nf, "| without op margin", om, "| without interest cover", ic, "| all: no share change", sc, "/", n)
    print("  newer quarter exists", newer, "| |trailing-annual|>=10:", gap10, "| band differs:", bandflip)
    print("  annual fiscal-end age days: median", age[len(age)//2], "p90", age[int(len(age)*.9)], "max", age[-1], "| over 300 days:", sum(a > 300 for a in age))
    print("  financial resilience (financials): ==1.0:", sum(r >= 0.999 for r in res_fin), "of", len(res_fin))
