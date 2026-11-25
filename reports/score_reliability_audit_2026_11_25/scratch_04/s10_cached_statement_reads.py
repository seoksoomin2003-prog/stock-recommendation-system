"""Agent 4: what the live statement reader gives on the stored statement copies (US annual4 = the QSF-1.5.2 extraction, KR krfund3),
as of the latest recorded session.  A dummy price of 100 and no share count: only figures that need neither are counted.  No return."""
import json, sys
from collections import Counter
from pathlib import Path
from terminal.qsf import fundamentals
AS_OF = "2026-11-24"
folder = Path("data/qsf/cache")
def load(prefix):
    out = {}
    for f in sorted(folder.glob(f"{prefix}_*.json"), key=lambda f: f.stat().st_mtime, reverse=True):
        who = f.name[len(prefix) + 1:].rsplit("_", 1)[0]
        if who in out: continue
        try:
            d = json.loads(f.read_text(encoding="utf-8")).get("data")
        except (OSError, ValueError):
            continue
        if d: out[who] = d
    return out
sic = {k: (v or {}).get("sic") for k, v in load("submforms").items()}
res = {}
for market, prefix in (("US", "annual4"), ("KR", "krfund3")):
    docs = load(prefix)
    c = Counter(); basis = Counter(); cur = Counter(); vint = Counter()
    for who, annual in docs.items():
        fin = fundamentals.is_financial_sic(sic.get(who.split("+")[0])) if market == "US" else False
        try:
            m = fundamentals.metrics(annual, 100.0, AS_OF, is_financial=fin)
        except Exception as exc:
            c["error:" + type(exc).__name__] += 1; continue
        c["companies"] += 1; c["status:" + str(m.get("status"))] += 1
        if m.get("status") not in ("REAL", "STALE"): continue
        basis[str(m.get("debt_basis"))] += 1
        if m.get("currency"): cur[m["currency"]] += 1
        for k in ("gross_margin", "op_margin", "interest_cover", "share_change", "current_ratio", "rev_growth", "eps_growth", "eps_cagr3", "fcf", "ocf_to_ni", "roe", "debt_equity"):
            if m.get(k) is None: c["none:" + k] += 1
        c["financial"] += fin
        c["basis_changed"] += bool(m.get("basis_changed")); c["loss_now"] += bool(m.get("loss_now")); c["revenue_note"] += bool(m.get("revenue_note")); c["share_scale_error"] += bool(m.get("share_scale_error"))
        c["debt_equity_99"] += m.get("debt_equity") == 99.0
        # restated vintages: fiscal years the copy holds in more than one filing with a value that moved by more than 3%
        moved = False
        for k in ("revenue", "net_income"):
            per = {}
            for r in annual.get(k) or []:
                per.setdefault(r["end"], []).append(r["val"])
            moved = moved or any(len(v) > 1 and min(v) != 0 and abs(max(v) / min(v) - 1) > 0.03 for v in per.values() if all(x > 0 for x in v))
        c["has_restated_year_3pct"] += moved
        c["has_multi_vintage"] += any(len({r["filed"] for r in (annual.get(k) or []) if r["end"] == e}) > 1 for k in ("revenue", "net_income") for e in {r["end"] for r in (annual.get(k) or [])})
    print(market, prefix, dict(sorted(c.items()))); print("   debt_basis", dict(basis), "currency", dict(cur))
    res[market] = {"counts": dict(c), "debt_basis": dict(basis), "currency": dict(cur)}
json.dump(res, open(__file__.replace(".py", ".json"), "w"), ensure_ascii=False, indent=1)
