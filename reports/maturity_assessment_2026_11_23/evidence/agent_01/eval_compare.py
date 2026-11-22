"""Agent 01 scratch: the live server's card of one stock (workflow B, code of today) against the ledger record of the same session
(workflow A, recorded under QSF-1.4.1).  Scores and labels only; no prices of other days, no returns."""
import json, sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
from terminal.qsf.ledger import Ledger
led = Ledger(REPO)
for market, ticker, name in (("US", "AAPL", "eval_US_AAPL.json"), ("KR", "005930", "eval_KR_005930.json")):
    d = json.loads((Path(__file__).parent / "big" / name).read_text(encoding="utf-8"))
    print("==", market, ticker, "status", d.get("status"), "rank_basis", d.get("rank_basis"), "keys", sorted(k for k in d if k not in ("cards",))[:20])
    rows = [r for r in led._live_rows() if r["market"] == market]
    snaps = {s["strategy"]: s for s in led._load(rows[-1]) if s["ticker"] == ticker}
    for strat, c in (d.get("cards") or {}).items():
        s = snaps.get(strat) or {}
        print(strat, "| live:", c.get("model_version"), round(c["score"], 4) if c.get("score") is not None else None, c.get("band"), c.get("action"), c.get("actionability"), c.get("confidence"),
              "cov", round(c.get("coverage") or 0, 3), "in_cov", round(c.get("input_coverage") or 0, 3), "data_date", c.get("data_date"), "entry", c.get("entry_status"),
              "held_back", c.get("band_held_back"), "kept", c.get("band_kept"))
        print("      | record:", s.get("model_version"), round(s["score"], 4) if s.get("score") is not None else None, s.get("band"), s.get("action"), s.get("actionability"), s.get("confidence"),
              "cov", round(s.get("coverage") or 0, 3), "data_date", s.get("data_date"), "entry", s.get("entry_status"))
        print("      | price source live:", (c.get("provenance") or {}).get("price"), "| record:", (s.get("provenance") or {}).get("price"))
        lf = {f["factor"]: f.get("normalized") for f in c.get("factors") or []}
        rf = {f["factor"]: f.get("normalized") for f in s.get("factors") or []}
        diff = {k: (rf.get(k), lf.get(k)) for k in sorted(set(lf) | set(rf)) if (lf.get(k) is None) != (rf.get(k) is None) or (lf.get(k) is not None and abs(lf[k] - rf[k]) > 1e-6)}
        print("      | factors that differ (record, live):", {k: tuple(None if v is None else round(v, 4) for v in pair) for k, pair in diff.items()})
        print("      | plain parts:", [p["h"] for p in (c.get("plain") or {}).get("parts") or []])
