"""Agent 01 scratch (2026-11-25): the live server's card of 005930 (workflow B) beside the newest ledger record (workflow A,
session 2026-11-23).  Labels and structure only; the data dates differ, so scores are not expected to match.  No returns."""
import json, sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
from terminal.qsf.ledger import Ledger
d = json.loads((Path(__file__).parent / "big" / "eval_KR_005930.json").read_text(encoding="utf-8"))
print("status", d.get("status"), "rank_basis", d.get("rank_basis"), "top keys", sorted(k for k in d if k != "cards"))
led = Ledger(REPO)
rows = [r for r in led._live_rows() if r["market"] == "KR"]
snaps = {s["strategy"]: s for s in led._load(rows[-1]) if s["ticker"] == "005930"}
for strat, c in (d.get("cards") or {}).items():
    s = snaps.get(strat) or {}
    print(strat, "| live:", c.get("model_version"), c.get("data_date"), round(c["score"], 3) if c.get("score") is not None else None, c.get("band"), c.get("action"), c.get("confidence"),
          "deal_held", c.get("deal_held"), "earnings_unknown", bool(c.get("earnings_unknown")), "stale_fund_days", c.get("stale_fund_days"))
    print("      | record:", s.get("model_version"), s.get("data_date"), round(s["score"], 3) if s.get("score") is not None else None, s.get("band"), s.get("action"), s.get("confidence"))
    print("      | price source live:", c.get("price_source") or (c.get("provenance") or {}).get("price"))
    stale = [(f["factor"], f.get("status")) for f in c.get("factors") or [] if f.get("status") not in ("REAL",)]
    print("      | non-REAL factors live:", stale[:12])
print("-- factors that differ (record, live), normalized:")
for strat, c in (d.get("cards") or {}).items():
    s = snaps.get(strat) or {}
    lf = {f["factor"]: f.get("normalized") for f in c.get("factors") or []}
    rf = {f["factor"]: f.get("normalized") for f in s.get("factors") or []}
    diff = {k: (rf.get(k), lf.get(k)) for k in sorted(set(lf) | set(rf)) if (lf.get(k) is None) != (rf.get(k) is None) or (lf.get(k) is not None and abs(lf[k] - rf[k]) > 1e-9)}
    print(strat, "exact scores (live, record):", c.get("score"), s.get("score"), {k: tuple(None if v is None else round(v, 5) for v in p) for k, p in diff.items()})
