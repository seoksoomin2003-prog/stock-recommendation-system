"""Agent 03: compact the 2026-11-23 live ledger session (QSF-1.5.2) per market into factor tables.
Reads factor VALUES only (normalized, status, weight); no price or return is read or computed.  One market at a time.
Sector and market value come from the 2026-11-20 offline cards of the earlier assessment (evidence of agent 3, 2026-11-23)."""
import json, sys, gc
from pathlib import Path
REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
from terminal.qsf.ledger import Ledger
OUT = Path(__file__).parent / "big"
OUT.mkdir(exist_ok=True)
old = json.loads((REPO / "reports/maturity_assessment_2026_11_23/evidence/agent_03/big/cards_151.json").read_text())
led = Ledger(REPO)
rows = led._live_rows()
for market in ("US", "KR"):
    meta = {}
    for k, c in old[market]["cards"].items():
        meta[c["ticker"]] = {"sector": c.get("sector"), "mcap": (c.get("fund") or {}).get("market_cap"), "is_fin": (c.get("fund") or {}).get("is_financial")}
    row = [r for r in rows if r["market"] == market and r["session"] == "2026-11-23"][-1]
    snaps = led._load(row)
    cards = []
    for s in snaps:
        cards.append({"ticker": s["ticker"], "strategy": s["strategy"], "score": s.get("score"), "cons": s.get("conservative_score"),
                      "band": s.get("band"), "held_back": s.get("band_held_back"), "entry": s.get("entry_status"), "act": s.get("actionability"),
                      "conf": s.get("confidence"), "cov": s.get("coverage"), "incov": s.get("input_coverage"), "version": s.get("model_version"),
                      "gates": [g.get("code") for g in (s.get("gates") or [])],
                      "f": {f["factor"] + ("@ref" if f.get("scored") is False else ""): [f.get("status"), f.get("normalized"), f.get("weight"), f.get("domain")] for f in s.get("factors") or []},
                      **meta.get(s["ticker"], {})})
    (OUT / f"s1123_{market}.json").write_text(json.dumps({"session": row["session"], "version": row["model_version"], "cards": cards}, ensure_ascii=False))
    print(market, row["session"], row["model_version"], len(cards), "with meta", sum(1 for c in cards if c.get("sector")))
    del snaps, cards; gc.collect()
