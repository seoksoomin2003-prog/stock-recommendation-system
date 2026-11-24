"""Agent 03 cross review of agent 02: which factors make up agent 02's 'bad factor left unsaid' counts (same approximation as
agent_02/unsaid.py: a None among the factor's raw figures), and how many cards are actionable.  Factor values only, no returns."""
import sys, collections
from pathlib import Path
REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
from terminal.qsf.ledger import Ledger
from terminal import plain
led = Ledger(REPO)
for m in ("US", "KR"):
    row = [r for r in led._live_rows() if r["market"] == m][-1]
    snaps = [s for s in led._load(row) if s["strategy"] == "LONG_TERM"]
    by_factor, cards, nonblocked = collections.Counter(), 0, 0
    missing_key = collections.Counter()
    for s in snaps:
        if s.get("actionability") == "BLOCKED":
            continue
        nonblocked += 1
        loss = any(f["factor"] == "valuation" and isinstance(f.get("raw"), dict) and (f["raw"].get("pe") or 1) <= 0 for f in s["factors"])
        hid = []
        for f in s["factors"]:
            v = f.get("normalized")
            if f.get("scored") is False or v is None or f["factor"] not in plain.FACTOR or v > 0.35:
                continue
            raw = f.get("raw") if isinstance(f.get("raw"), dict) else {}
            none = [k for k, x in raw.items() if x is None and not (loss and k in ("eps_cagr3", "eps_growth"))]
            if none:
                hid.append(f["factor"]); missing_key.update(f"{f['factor']}:{k}" for k in none)
        if hid:
            cards += 1
            by_factor.update(set(hid))
    print(m, "non-blocked long cards", nonblocked, "cards with a hidden bad factor", cards)
    print("   by factor", dict(by_factor.most_common()))
    print("   missing raw keys behind them", dict(missing_key.most_common(10)))


# Second pass: would the hidden bad factor have been spoken at all?  plain._sides keeps only the three heaviest bad factors
# (weight x |v - 0.5|), so a hidden factor outside that three changes nothing the reader sees.
print("--- with the three-sentence cap of plain._sides")
for m in ("US", "KR"):
    row = [r for r in led._live_rows() if r["market"] == m][-1]
    snaps = [s for s in led._load(row) if s["strategy"] == "LONG_TERM"]
    changed, buy = 0, 0
    for s in snaps:
        if s.get("actionability") == "BLOCKED":
            continue
        loss = any(f["factor"] == "valuation" and isinstance(f.get("raw"), dict) and (f["raw"].get("pe") or 1) <= 0 for f in s["factors"])
        bad = []
        for f in s["factors"]:
            v = f.get("normalized")
            if f.get("scored") is False or v is None or f["factor"] not in plain.FACTOR or v > 0.35:
                continue
            raw = f.get("raw") if isinstance(f.get("raw"), dict) else {}
            hidden = any(x is None and not (loss and k in ("eps_cagr3", "eps_growth")) for k, x in raw.items())
            bad.append((float(f.get("weight") or 0) * abs(v - 0.5), hidden))
        top = sorted(bad, key=lambda b: -b[0])[:3]
        if any(h for _, h in top):
            changed += 1
            buy += s["band"] in ("BUY_CANDIDATE", "STRONG_BUY_CANDIDATE")
    print(m, "cards where a hidden bad factor would be among the three spoken:", changed, "| in the buy band:", buy)
