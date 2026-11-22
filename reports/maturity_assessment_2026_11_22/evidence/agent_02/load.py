"""Scratch (agent 02): read the newest ledger session of one market; scores and stored raw values only, no returns."""
import json, sys, statistics as st
from pathlib import Path
repo = Path("~/Developer/quant-stock-engine")
sys.path.insert(0, str(repo))
from terminal.qsf.ledger import Ledger
E = repo / "reports/maturity_assessment_2026_11_22/evidence/agent_02"

def load(market):
    led = Ledger(repo)
    rows = [r for r in led._live_rows() if r["market"] == market]
    snaps = led._load(rows[-1])
    return rows[-1], snaps

def sectors(market):
    d = json.load(open(E / f"screen_{market}.json"))
    return {r["ticker"]: (r.get("sector"), r.get("industry"), r.get("name")) for r in d.get("rows") or []}

def raw(snap, factor, key=None):
    for f in snap.get("factors") or []:
        if f.get("factor") == factor:
            if key is None:
                return f
            r = f.get("raw")
            return r.get(key) if isinstance(r, dict) else None
    return None
