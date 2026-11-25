"""AGENT 3, experiment 4: nominal weight against the share of score variance, by domain and by trait; and the number of bets the
weights alone would give if the factors were independent (arithmetic on recorded sd and weights from s01_out.json)."""
import json
from pathlib import Path
from collections import defaultdict
d = json.loads((Path(__file__).parent / "s01_out.json").read_text(encoding="utf-8"))
TRAIT = {"trend_structure": "가격 모멘텀", "relative_strength": "가격 모멘텀", "momentum": "가격 모멘텀", "breakout_volume": "가격 모멘텀", "long_trend": "가격 모멘텀", "momentum_persistence": "가격 모멘텀",
         "volatility_structure": "변동성", "atr_risk": "변동성", "drawdown_gap": "변동성", "downside_drawdown": "변동성",
         "earnings_revenue_quality": "성장", "growth_quality": "성장", "profitability": "수익성·질", "business_quality": "수익성·질", "cash_flow_quality": "수익성·질", "free_cash_flow": "수익성·질",
         "balance_sheet": "재무 건전성", "balance_dilution": "재무 건전성", "financial_resilience": "재무 건전성", "leverage": "재무 건전성", "valuation": "가치", "risk_reward": "진입 위치(손익비)", "liquidity": "유동성",
         "earnings_calendar": "사건·심리", "material_disclosures": "사건·심리", "insider_activity": "사건·심리", "governance": "사건·심리", "material_events": "사건·심리", "insider_ownership": "사건·심리", "capital_allocation": "자본 배분"}
for day in ("2026-11-24", "2026-11-16"):
    for prof in ("US_SWING", "US_LONG_TERM", "KR_SWING", "KR_LONG_TERM"):
        r = d[f"{prof}_{day}"]
        F = r["factors"]
        wsum = sum(x["weight"] for x in F.values())
        dom, trait = defaultdict(lambda: [0, 0.0]), defaultdict(lambda: [0, 0.0])
        for f, x in F.items():
            if not x["weight"]:
                continue
            vs = r["variance_share"].get(f, 0.0)
            dom[x["domain"]][0] += x["weight"]; dom[x["domain"]][1] += vs
            trait[TRAIT[f]][0] += x["weight"]; trait[TRAIT[f]][1] += vs
        ind = [(F[f]["weight"] * F[f]["sd"]) ** 2 for f in r["scored_varying"]]
        pr_ind = sum(ind) ** 2 / sum(v * v for v in ind)
        print(f"{prof} {day}: nominal weight {wsum}, varying factors {len(r['scored_varying'])}, bets if independent (weights x sd only) {pr_ind:.1f}, bets measured {r['participation_ratio_weighted']:.2f}, equal-weight correlation bets {r['participation_ratio_pearson']:.1f}")
        print("   domain  :", "  ".join(f"{k} {v[0]}({v[0]/wsum:.0%})->{v[1]:.0%}" for k, v in sorted(dom.items(), key=lambda kv: -kv[1][1])))
        print("   trait   :", "  ".join(f"{k} {v[0]}({v[0]/wsum:.0%})->{v[1]:.0%}" for k, v in sorted(trait.items(), key=lambda kv: -kv[1][1])))
