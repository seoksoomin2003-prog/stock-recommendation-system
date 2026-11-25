"""AGENT 3, experiment 3: what some factors actually read, from recorded raw inputs (no return).
- business_quality / growth_quality / financial_resilience / valuation: which inputs are there (pattern counts)
- insider_activity (US): buy/sell patterns behind the normalized value
- risk_reward: ATR projection vs resistance target, relation to distance from the 52-week high and to trend
- saturation (share at 0 or 1) of the volatility factors over every recorded session
"""
import json, sys
from pathlib import Path
from collections import Counter, defaultdict
import numpy as np, pandas as pd
from terminal.qsf.ledger import Ledger
from terminal.qsf.order_plan import session_snaps
led = Ledger(Path("."))
S = "2026-11-24"


def sp(a, b):
    a, b = pd.Series(a, dtype=float), pd.Series(b, dtype=float)
    ok = a.notna() & b.notna()
    return round(float(a[ok].rank().corr(b[ok].rank())), 3), int(ok.sum())


for market in ("US", "KR"):
    sn = session_snaps(led, market, S)
    by = defaultdict(dict)
    for s in sn:
        for f in s["factors"]:
            by[(s["strategy"], f["factor"])][s["ticker"]] = f
    print("=" * 90, market, S)
    for strat, fid in (("LONG_TERM", "business_quality"), ("LONG_TERM", "growth_quality"), ("LONG_TERM", "financial_resilience"), ("LONG_TERM", "valuation"), ("LONG_TERM", "balance_dilution"),
                       ("LONG_TERM", "capital_allocation"), ("LONG_TERM", "insider_ownership"), ("LONG_TERM", "free_cash_flow"), ("SWING", "earnings_revenue_quality"), ("SWING", "balance_sheet"), ("SWING", "cash_flow_quality"), ("SWING", "profitability")):
        c = Counter()
        for t, f in by[(strat, fid)].items():
            raw = f.get("raw")
            if f.get("status") not in ("REAL", "STALE") or not isinstance(raw, dict):
                c[f"[{f.get('status')}]"] += 1; continue
            if fid == "insider_ownership":
                c["+".join((["insider_pct"] if raw.get("insider_pct") is not None else []) + (["net_trades"] if (raw.get("insider") or {}).get("status") == "REAL" and ((raw["insider"].get("open_market_buy") or 0) + (raw["insider"].get("open_market_sell") or 0)) > 0 else [])) or "(none)"] += 1
            else:
                c["+".join(k for k, v in raw.items() if v is not None) or "(none)"] += 1
        n = sum(c.values())
        print(f"  {strat[:5]} {fid}: inputs present ->", [(k, v, f"{v/n:.0%}") for k, v in c.most_common(7)])
    if market == "US":
        c = Counter()
        for t, f in by[("SWING", "insider_activity")].items():
            r = f.get("raw") or {}
            b, s_ = r.get("open_market_buy") or 0, r.get("open_market_sell") or 0
            c["no trades (0.5)" if b == 0 and s_ == 0 else "sells only (0)" if b == 0 else "buys only (1)" if s_ == 0 else "both"] += 1
        print("  SWING insider_activity patterns:", dict(c))
        c = Counter()
        for t, f in by[("LONG_TERM", "insider_ownership")].items():
            r = f.get("raw") or {}
            p = r.get("insider_pct")
            c["pct None" if p is None else "<1%" if p < 0.01 else "1-5%" if p < 0.05 else "5-10%" if p < 0.10 else ">=10%"] += 1
        print("  LONG insider_pct bands:", dict(c))
    else:
        c = Counter()
        for t, f in by[("LONG_TERM", "insider_ownership")].items():
            r = f.get("raw") or {}
            p = r.get("insider_pct")
            c["pct None" if p is None else "<1%" if p < 0.01 else "1-5%" if p < 0.05 else "5-10%" if p < 0.10 else ">=10%"] += 1
        print("  LONG insider_pct bands:", dict(c))
        c = Counter(str((f.get("raw") or {}).get("returns_capital")) + "|" + str(f.get("status")) for f in by[("LONG_TERM", "capital_allocation")].values())
        print("  LONG capital_allocation returns_capital|status:", dict(c))
    # risk_reward
    rr = by[("SWING", "risk_reward")]; bv = by[("SWING", "breakout_volume")]; tr = by[("SWING", "trend_structure")]; snap = {s["ticker"]: s for s in sn if s["strategy"] == "SWING"}
    proj = 0; tot = 0; vals = {}; dist = {}; trend = {}; rrraw = {}
    for t, f in rr.items():
        raw = f.get("raw") or {}
        if f.get("normalized") is None:
            continue
        tot += 1
        price = snap[t]["price"]; stop, target = raw.get("stop"), raw.get("target")
        ratio = (target - price) / (price - stop) if stop and target and price > stop else None
        is_proj = ratio is not None and abs(ratio - 1.5) < 1e-6
        proj += is_proj
        vals[t] = f["normalized"]; rrraw[t] = raw.get("reward_risk")
        dist[t] = (bv[t].get("raw") or {}).get("dist_high"); trend[t] = tr[t].get("normalized")
    v = np.array(list(vals.values()))
    pv = [vals[t] for t in vals if abs(((rr[t]["raw"]["target"] - snap[t]["price"]) / (snap[t]["price"] - rr[t]["raw"]["stop"])) - 1.5) < 1e-6]
    print(f"  risk_reward: n {tot}, target = 3 ATR projection (no resistance above) {proj} ({proj/tot:.0%}); their normalized max {max(pv) if pv else None:.3f}, mean {np.mean(pv) if pv else float('nan'):.3f}; share at 0 overall {np.mean(v<=1e-9):.0%}; reward_risk >= 1.5 share {np.mean([x >= 1.5 for x in rrraw.values() if x is not None]):.0%}")
    print("   spearman(risk_reward, dist_high)", sp(vals, dist), " spearman(risk_reward, trend_structure)", sp(vals, trend))
    hi = [t for t in snap if snap[t].get("score") is not None and snap[t]["score"] >= 70]
    print("   among score>=70:", len(hi), "entry_status", dict(Counter(snap[t].get("entry_status") for t in hi)), "mean risk_reward norm", round(float(np.mean([vals[t] for t in hi if t in vals])), 3) if hi else None)
    print("   entry_status all:", dict(Counter(s.get("entry_status") for s in snap.values())))

print("=" * 90, "saturation by session: share at 0 / share at 1")
for market in ("US", "KR"):
    for sess in sorted({x["session"] for x in led._live_rows() if x["market"] == market}):
        sn = session_snaps(led, market, sess)
        line = [market, sess]
        for strat, fid in (("SWING", "atr_risk"), ("SWING", "drawdown_gap"), ("LONG_TERM", "downside_drawdown"), ("SWING", "risk_reward"), ("SWING", "liquidity"), ("SWING", "earnings_calendar"), ("SWING", "trend_structure")):
            v = np.array([f["normalized"] for s in sn if s["strategy"] == strat for f in s["factors"] if f["factor"] == fid and f.get("normalized") is not None])
            line.append(f"{fid[:10]} {np.mean(v<=1e-9):.2f}/{np.mean(v>=1-1e-9):.2f}")
        print("  ", *line)
