"""Agent 02 scratch: do the plain sentences and the card sentence say more than the figures?
Stored factor raws of ONE ledger session -> today's factor code (terminal/qsf/factors.py) -> today's plain._sides.  Read only."""
import sys, collections
from pathlib import Path
repo = Path.home() / "Developer" / "quant-stock-engine"
sys.path.insert(0, str(repo))
from terminal.qsf.ledger import Ledger
from terminal.qsf import factors, config
from terminal import plain

market = sys.argv[1]
led = Ledger(repo)
row = [r for r in led._live_rows() if r["market"] == market][-1]
snaps = led._load(row)
by = collections.defaultdict(dict)
for s in snaps:
    by[s["ticker"]][s["strategy"]] = s
FUND = ("valuation", "business_quality", "growth_quality", "free_cash_flow", "balance_dilution", "financial_resilience", "leverage", "capital_allocation",
        "earnings_revenue_quality", "profitability", "balance_sheet", "cash_flow_quality", "insider_ownership")
said = collections.Counter()
wrong = collections.defaultdict(list)
unsaid_n = collections.Counter()
sentence_none = collections.Counter()
examples = collections.defaultdict(list)

for t, pair in by.items():
    raw, fin, note = {}, False, None
    for s in pair.values():
        for f in s["factors"]:
            if isinstance(f.get("raw"), dict):
                for k, v in f["raw"].items():
                    raw.setdefault(k, v)
            if f["factor"] in ("leverage", "free_cash_flow", "cash_flow_quality") and f["status"] == "NOT_APPLICABLE":
                fin = True
            if f["factor"] in ("free_cash_flow", "cash_flow_quality") and f["status"] == "MISSING" and "현금" in str(f.get("reason")):
                note = f.get("reason")
    insider = raw.get("insider")
    fund = {**raw, "status": "REAL", "is_financial": fin, "loss_now": (raw.get("roe") is not None and raw["roe"] <= 0) or (raw.get("pe") is not None and raw["pe"] <= 0), "cash_burn": False}
    if note:
        fund["cash_flow_note"] = note
    ctx = {"fund": fund, "events": {"status": "REAL", "insider": insider, "as_of": None, "source": "x"} if isinstance(insider, dict) else None}
    for strat, s in pair.items():
        prof = config.profile_for(market, strat)
        w = {fid: wt for d in prof["domains"].values() for fid, wt in d.items()}
        rows = []
        for f in s["factors"]:
            r = dict(f)
            if f["factor"] in FUND and f["status"] in ("REAL", "STALE") and f["factor"] in w:
                try:
                    o = factors.CALC[f["factor"]](ctx)
                except Exception as exc:  # noqa
                    o = {"status": "MISSING"}
                if o.get("status") in ("REAL", "STALE"):
                    r["normalized"] = o["normalized"]
                    if o.get("inputs"):
                        r["inputs"] = o["inputs"]
            r["weight"] = w.get(f["factor"], 0)
            if f["factor"] not in w:
                r["scored"] = False
            rows.append(r)
        card = {"factors": rows}
        good, bad, unsaid = plain._sides(card, n=99)
        unsaid_n[strat] += unsaid
        inv = {v[0]: k for k, v in plain.FACTOR.items()}
        inv_bad = {v[1]: k for k, v in plain.FACTOR.items()}
        for g in good:
            k = inv[g]
            if k not in FUND:
                continue
            said[(strat, k, "good")] += 1
            bad_case = None
            if k == "earnings_revenue_quality" and ((raw.get("rev_growth") is not None and raw["rev_growth"] < 0) or (raw.get("eps_growth") is not None and raw["eps_growth"] < 0)):
                bad_case = f"rev {raw.get('rev_growth')}, eps {raw.get('eps_growth')}"
            if k == "growth_quality" and any(raw.get(x) is not None and raw[x] < 0 for x in ("rev_cagr3", "eps_cagr3", "rev_growth")):
                bad_case = f"rev3 {raw.get('rev_cagr3')}, eps3 {raw.get('eps_cagr3')}, rev1 {raw.get('rev_growth')}"
            if k in ("balance_dilution", "capital_allocation") and (raw.get("share_change") is None or raw["share_change"] > 0.005):
                bad_case = f"share_change {raw.get('share_change')}"
            if k == "capital_allocation" and raw.get("returns_capital") is not True:
                bad_case = f"returns_capital {raw.get('returns_capital')}"
            if k == "valuation" and (raw.get("pe") is None or raw["pe"] <= 0 or raw["pe"] > 30):
                bad_case = f"pe {raw.get('pe')} pb {raw.get('pb')} fy {raw.get('fcf_yield')}"
            if k == "business_quality" and ((raw.get("roe_years_positive") or 1) < 1 or (raw.get("roe") is not None and raw["roe"] < 0.08)):
                bad_case = f"roe {raw.get('roe')} years {raw.get('roe_years_positive')}"
            if k == "free_cash_flow" and (raw.get("fcf_years_positive") or 1) < 1:
                bad_case = f"fcf years {raw.get('fcf_years_positive')}"
            if k == "cash_flow_quality" and ((raw.get("ocf_to_ni") or 0) > 3 or (raw.get("fcf_margin") is not None and raw["fcf_margin"] < 0)):
                bad_case = f"ocf/ni {raw.get('ocf_to_ni')} fcf_margin {raw.get('fcf_margin')}"
            if k == "insider_ownership" and (raw.get("insider_pct") or 0) > 0.3:
                bad_case = f"insider_pct {raw.get('insider_pct')}"
            if bad_case:
                wrong[(strat, k, "good")].append((t, bad_case))
        for b in bad:
            k = inv_bad[b]
            if k not in FUND:
                continue
            said[(strat, k, "bad")] += 1
            if k in ("balance_sheet", "balance_dilution", "leverage", "financial_resilience") and fin:
                wrong[(strat, k, "bad-financial")].append((t, f"equity/assets {raw.get('equity_assets')}"))
        # card sentence: the first strength / weakness quoted by _why_of (engine.score's ranking)
        ranked = [r for r in rows if r.get("normalized") is not None and r.get("scored") is not False and r["status"] in ("REAL", "STALE")]
        pos = sorted((r for r in ranked if r["normalized"] >= 0.6), key=lambda r: (r["normalized"] - 0.5) * r["weight"], reverse=True)[:1]
        neg = sorted((r for r in ranked if r["normalized"] <= 0.4), key=lambda r: (r["normalized"] - 0.5) * r["weight"])[:1]
        for side, rr in (("strength", pos), ("weakness", neg)):
            for r in rr:
                txt = r.get("explanation") or ""
                if " 없음" in txt and r["factor"] in FUND:
                    sentence_none[(strat, side, r["factor"])] += 1
                    if len(examples[(strat, side, r["factor"])]) < 3:
                        examples[(strat, side, r["factor"])].append((t, txt))

print("session", row["session"], market, "stocks", len(by))
print("plain sentences said per (strategy, factor, side) under today's code:")
for k in sorted(said):
    w = wrong.get(k, [])
    print(f"  {k}: said {said[k]}, figure does not support {len(w)}  e.g. {w[:4]}")
for k in sorted(wrong):
    if k[2] == "bad-financial":
        print(f"  {k}: {len(wrong[k])} e.g. {wrong[k][:4]}")
print("partial factors left unsaid (count of clear readings):", dict(unsaid_n))
print("card sentence: first strength/weakness whose text has a figure worded '없음':")
for k in sorted(sentence_none):
    print(f"  {k}: {sentence_none[k]}  e.g. {examples[k][:2]}")
