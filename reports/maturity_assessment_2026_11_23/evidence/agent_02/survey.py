"""Agent 02 scratch: read ONE ledger session per market (newest), survey the fundamental factors.  Read only, no provider, no returns."""
import json, sys, collections
from pathlib import Path
repo = Path.home() / "Developer" / "quant-stock-engine"
sys.path.insert(0, str(repo))
from terminal.qsf.ledger import Ledger

FUND = ("valuation", "business_quality", "growth_quality", "free_cash_flow", "balance_dilution", "financial_resilience", "leverage", "capital_allocation",
        "earnings_revenue_quality", "profitability", "balance_sheet", "cash_flow_quality", "insider_ownership")
market = sys.argv[1]
led = Ledger(repo)
rows = [r for r in led._live_rows() if r["market"] == market]
row = rows[-1]
snaps = led._load(row)
print("session", row["session"], "file", row["file"], "snaps", len(snaps), "version", snaps[0].get("model_version"))
long_ = {s["ticker"]: s for s in snaps if s["strategy"] == "LONG_TERM"}
swing = {s["ticker"]: s for s in snaps if s["strategy"] == "SWING"}
print("long", len(long_), "swing", len(swing))
print("snapshot keys:", sorted(snaps[0].keys()))


def fac(s, fid):
    return next((f for f in s["factors"] if f["factor"] == fid), None)


# 1. status counts and partial-input counts per fundamental factor
for name, book in (("LONG", long_), ("SWING", swing)):
    cnt = collections.defaultdict(collections.Counter)
    part = collections.Counter()
    rawmiss = collections.defaultdict(collections.Counter)
    for s in book.values():
        for f in s["factors"]:
            if f["factor"] in FUND:
                cnt[f["factor"]][f["status"]] += 1
                if f.get("inputs"):
                    part[f["factor"]] += 1
                for k, v in (f.get("raw") or {}).items():
                    if v is None:
                        rawmiss[f["factor"]][k] += 1
    print(f"--- {name}: status counts / partial inputs / raw None counts")
    for k in FUND:
        if k in cnt:
            print(f"  {k:26s} {dict(cnt[k])} partial={part[k]} rawNone={dict(rawmiss[k])}")

# 2. how many loss-makers, negative-equity, financials
fin = [t for t, s in long_.items() if (fac(s, "leverage") or {}).get("status") == "NOT_APPLICABLE"]
print("financial (leverage N/A):", len(fin))
loss = [t for t, s in long_.items() if ((fac(s, "valuation") or {}).get("raw") or {}).get("pe") is not None and fac(s, "valuation")["raw"]["pe"] <= 0]
print("pe<=0 (loss) :", len(loss), loss[:40])
noeq = [t for t, s in long_.items() if ((fac(s, "leverage") or {}).get("raw") or {}).get("debt_equity") == 99.0]
print("no equity (99):", len(noeq), noeq[:40])

# 3. distribution of normalized valuation & score bands among actionables
bands = collections.Counter((s.get("band"), s.get("actionability")) for s in long_.values())
print("long bands:", dict(bands))
ent = collections.Counter(s.get("entry_status") or (s.get("entry") or {}).get("status") for s in long_.values())
print("long entry:", dict(ent))
json.dump({"session": row["session"], "fin": fin, "loss": loss, "noeq": noeq}, open(Path(__file__).parent / f"survey_{market}.json", "w"))
