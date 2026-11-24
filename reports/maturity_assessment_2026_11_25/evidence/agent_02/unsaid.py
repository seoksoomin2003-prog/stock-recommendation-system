"""Agent 02: long-term cards whose clearly bad factors (normalized <= 0.35) are all computed from part of their figures, so
the plain explanation (plain._sides) leaves them unsaid.  The ledger rows do not keep the 'inputs' field, so 'partial' is
approximated here from a None among the factor's raw figures (a loss-maker's EPS growth read as 0 counts as present when
the PE is negative).  Approximate counts; no returns."""
import sys
from pathlib import Path
repo = Path.home() / "Developer" / "quant-stock-engine"
sys.path.insert(0, str(repo))
from terminal.qsf.ledger import Ledger
from terminal import plain
led = Ledger(repo)
for m in ("US", "KR"):
    row = [r for r in led._live_rows() if r["market"] == m][-1]
    snaps = [s for s in led._load(row) if s["strategy"] == "LONG_TERM"]
    silent, silent_buy, any_hidden = [], [], 0
    for s in snaps:
        if s.get("actionability") == "BLOCKED":
            continue
        loss = any(f["factor"] == "valuation" and isinstance(f.get("raw"), dict) and (f["raw"].get("pe") or 1) <= 0 for f in s["factors"])
        bad_said, bad_hidden = [], []
        for f in s["factors"]:
            v = f.get("normalized")
            if f.get("scored") is False or v is None or f["factor"] not in plain.FACTOR or v > 0.35:
                continue
            raw = f.get("raw") if isinstance(f.get("raw"), dict) else {}
            none = [k for k, x in raw.items() if x is None and not (loss and k in ("eps_cagr3", "eps_growth"))]
            (bad_hidden if none else bad_said).append((f["factor"], round(v, 2), f.get("weight")))
        if bad_hidden:
            any_hidden += 1
        if bad_hidden and not bad_said:
            silent.append((s["ticker"], round(s["score"], 1), s["band"], s.get("entry_status"), bad_hidden))
            if s["band"] in ("BUY_CANDIDATE", "STRONG_BUY_CANDIDATE"):
                silent_buy.append(silent[-1])
    print(m, row["session"], "long cards with a bad factor left unsaid:", any_hidden, "| cards whose 'worries' would read 'none' though a factor is bad:", len(silent), "| of them in the buy band:", len(silent_buy))
    for x in silent_buy[:12]:
        print("   ", x)
