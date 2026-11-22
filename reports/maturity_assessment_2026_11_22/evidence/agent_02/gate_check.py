"""Scratch (agent 02): the long-term valuation gate of holding.entry_status on synthetic inputs.  No ledger, no provider, no return.

Run from the repository root:  .venv/bin/python reports/maturity_assessment_2026_11_22/evidence/agent_02/gate_check.py

Output on 2026-11-22 (commit b5ca247):
    valuation 0.03 quality 0.30 -> ENTRY_NOW                      (expensive and mediocre: passes, and the reason says the valuation does not block)
    valuation 0.03 quality 0.60 -> OVERVALUED_AT_CURRENT_PRICE
    valuation 0.24 quality 0.59 -> ENTRY_NOW
    valuation 0.26 quality 0.95 -> ENTRY_NOW                      (the line of 0.25 is a cliff)
"""
import sys

sys.path.insert(0, ".")
from terminal.qsf import holding  # noqa: E402


def res(v, q, score=60.0):
    return {"tech": {"close": 100.0, "atr": 2.0}, "levels": {}, "strategy": "LONG_TERM", "actionability": "ACTIONABLE", "score": score, "gates": [],
            "factors": [{"factor": "valuation", "normalized": v}, {"factor": "business_quality", "normalized": q}]}


for v, q in ((0.03, 0.30), (0.03, 0.60), (0.24, 0.59), (0.26, 0.95)):
    out = holding.entry_status(res(v, q), {})
    print(f"valuation {v:.2f} quality {q:.2f} -> {out['status']} | {out['reason']}")
