"""Agent 1, experiment E5 (no return): an independent re-implementation of every factor's normalisation, fed with the RAW values
recorded in the ledger (sessions 2026-11-23 and 2026-11-24, QSF-1.5.2), compared with the recorded normalised value.
Formulas are typed from my reading of terminal/qsf/factors.py, not imported from it."""
import json, math, sys
from collections import defaultdict
from pathlib import Path
sys.path.insert(0, ".")
from terminal.qsf.ledger import Ledger

def ramp(x, lo, hi):
    if x is None or not isinstance(x, (int, float)) or not math.isfinite(x):
        return None
    return max(0.0, min(1.0, (x - lo) / (hi - lo)))
def mean(v):
    v = [x for x in v if x is not None]
    return sum(v) / len(v) if v else None

def alts(fid, raw, s):
    """Every value the documented formula can give for this raw record (several when a flag is not stored in raw)."""
    g = raw.get; px = s.get("price"); mk = s["market"]
    if fid == "trend_structure":
        ch = [px > g("ma200"), px > g("ma50"), g("ma50") > g("ma200"), g("ma20") > g("ma50"), (g("ma50_slope") or 0) > 0, (g("ma200_slope") or 0) > 0]
        return [sum(ch) / 6]
    if fid == "relative_strength":
        return [g("percentile")] if g("percentile") is not None else [ramp(mean([g("rel_63"), g("rel_126")]), -0.15, 0.20)]
    if fid == "momentum":
        r = g("rsi"); rs = None if r is None else (ramp(r, 30, 55) if r < 55 else 1.0 if r <= 65 else ramp(r, 85, 65))
        return [mean([rs, ramp(g("macd_hist_pct"), -0.01, 0.01)])]
    if fid == "breakout_volume":
        dist = ramp(g("dist_high"), -0.25, 0.0); vr = g("volume_ratio")
        conf = None if vr is None else (ramp(vr, 1.0, 2.0) if g("breakout") else ramp(vr, 1.5, 0.8) * 0.5)
        gap = None if g("gap_today") is None else (0.3 if g("gap_today") > 0.02 and not g("held_gap") else 0.7)
        return [mean([dist, dist, conf, gap])]
    if fid == "volatility_structure":
        return [None if g("bandwidth_pct") is None else 1 - g("bandwidth_pct")]
    if fid == "long_trend":
        return [mean([ramp(px / g("ma200") - 1, -0.15, 0.15), ramp(g("ma200_slope"), -0.05, 0.05)])]
    if fid == "momentum_persistence":
        return [mean([ramp(g("ret_12_1"), -0.10, 0.30), g("pos_month_share")])]
    z = lambda v: [v] if v is not None else [None, 0.0]        # a figure that may have been read as 0 (loss_now / cash_burn are not in raw)
    if fid == "earnings_revenue_quality":
        return [mean([ramp(g("rev_growth"), -0.05, 0.20), e, c]) for e in z(ramp(g("eps_growth"), -0.10, 0.25)) for c in z(ramp(g("ocf_to_ni"), 0.5, 1.2))]
    if fid == "profitability":
        return [mean([ramp(g("roe"), 0.0, 0.20), ramp(g("op_margin"), 0.0, 0.20)])]
    if fid == "balance_sheet":
        if "equity_assets" in raw: return [ramp(g("equity_assets"), 0.04, 0.15)]
        return [mean([ramp(g("debt_equity"), 2.0, 0.3), ramp(g("current_ratio"), 0.8, 2.0)])]
    if fid == "cash_flow_quality":
        return [mean([c, ramp(g("fcf_margin"), -0.02, 0.15)]) for c in z(ramp(g("ocf_to_ni"), 0.5, 1.2))]
    if fid == "valuation":
        pe = g("pe"); pes = 0.0 if pe is not None and pe <= 0 else ramp(pe, 40, 10)
        if "fcf_yield" not in raw: return [mean([pes, ramp(g("pb"), 2.5, 0.8)])]
        return [mean([pes, ramp(g("pb"), 8, 1.5), ramp(g("fcf_yield"), 0.0, 0.07)])]
    if fid == "business_quality":
        return [mean([ramp(g("roe"), 0.03, 0.25), ramp(g("op_margin"), 0.0, 0.25), ramp(g("gross_margin"), 0.15, 0.60), g("roe_years_positive")])]
    if fid == "growth_quality":
        return [mean([ramp(g("rev_cagr3"), -0.02, 0.15), e, ramp(g("rev_growth"), -0.05, 0.20)]) for e in z(ramp(g("eps_cagr3"), -0.05, 0.20))]
    if fid == "free_cash_flow":
        return [mean([ramp(g("fcf_margin"), -0.02, 0.18), g("fcf_years_positive")])]
    if fid == "balance_dilution":
        dil = ramp(g("share_change"), 0.05, -0.01)
        if "equity_assets" in raw: return [mean([ramp(g("equity_assets"), 0.04, 0.15), dil])]
        return [mean([ramp(g("debt_equity"), 2.0, 0.3), dil])]
    if fid in ("vix_regime", "vkospi_regime"):
        return [ramp(g("vix") if fid == "vix_regime" else g("vkospi"), 35, 12)]
    if fid == "vix_term": return [ramp(g("vix_vix3m"), 1.05, 0.85)]
    if fid in ("credit_spread", "credit_liquidity"):
        return [None if g("percentile") is None else 1 - g("percentile")]
    if fid in ("index_trend_breadth", "index_trend"):
        tr = sum([g("close") > g("ma200"), g("ma50") > g("ma200"), g("close") > g("ma50")]) / 3
        if fid == "index_trend": return [tr]
        return [mean([tr, ramp(g("breadth"), 0.30, 0.70)]), tr]
    if fid == "breadth": return [ramp(g("breadth"), 0.30, 0.70)]
    if fid == "usdkrw_regime": return [ramp(g("change_63"), 0.05, -0.03)]
    if fid == "risk_reward": return [ramp(g("reward_risk"), 1.0, 3.0)]
    if fid == "atr_risk": return [mean([ramp(g("atr_pct"), 0.06, 0.015), ramp(g("hist_vol"), 0.70, 0.20)])]
    if fid == "liquidity":
        lo, hi = (1e9, 5e10) if mk == "KR" else (2e7, 5e8)
        return [ramp(math.log10(g("adv_value")), math.log10(lo), math.log10(hi))]
    if fid == "drawdown_gap": return [mean([ramp(g("max_drawdown_252"), -0.45, -0.10), ramp(g("max_gap_60"), 0.12, 0.01)])]
    if fid == "financial_resilience":
        if "equity_assets" in raw: return [ramp(g("equity_assets"), 0.04, 0.15)]
        return [mean([ramp(g("current_ratio"), 0.8, 2.0), ramp(g("interest_cover"), 1.5, 10), ramp(g("cash_debt"), 0.05, 0.8)])]
    if fid == "downside_drawdown": return [mean([ramp(g("downside_vol"), 0.45, 0.12), ramp(g("max_drawdown_252"), -0.50, -0.12)])]
    if fid == "leverage": return [ramp(g("debt_equity"), 2.5, 0.2)]
    if fid == "earnings_calendar": return [ramp(float(g("sessions")), 2, 15)]
    if fid == "material_disclosures": return [max(0.0, min(1.0, 0.6 + 0.1 * g("positive") - 0.25 * g("negative")))]
    if fid == "material_events": return [max(0.0, min(1.0, 0.6 + 0.1 * g("positive") - 0.3 * g("negative")))]
    if fid == "insider_activity":
        b, se = g("open_market_buy"), g("open_market_sell")
        return [0.5 if b + se == 0 else ramp((b - se) / (b + se), -1.0, 1.0)]
    if fid == "governance": return [max(0.0, 0.8 - 0.3 * len(g("issues") or []))]
    if fid == "insider_ownership":
        i = g("insider") or {}; net = None
        if i.get("status") == "REAL" and i["open_market_buy"] + i["open_market_sell"] > 0:
            net = ramp((i["open_market_buy"] - i["open_market_sell"]) / (i["open_market_buy"] + i["open_market_sell"]), -1, 1)
        return [mean([ramp(g("insider_pct"), 0.0, 0.10), net])]
    if fid == "capital_allocation":
        rc = g("returns_capital")
        return [mean([ramp(g("share_change"), 0.05, -0.02), 1.0 if rc else 0.4 if rc is not None else None])]
    raise KeyError(fid)

led = Ledger(Path("."))
stat = defaultdict(lambda: {"n": 0, "match": 0, "match_zero_rule": 0, "mismatch": 0, "max_gap": 0.0, "error": 0, "examples": []})
for r in led._live_rows():
    if r["session"] not in ("2026-11-23", "2026-11-24"):
        continue
    for s in led._load(r):
        for f in s["factors"]:
            if f.get("normalized") is None or f.get("raw") is None:
                continue
            a = stat[f"{s['market']}|{f['factor']}"]
            a["n"] += 1
            try:
                cands = alts(f["factor"], f["raw"], s)
            except Exception as exc:
                a["error"] += 1
                if len(a["examples"]) < 2: a["examples"].append([s["ticker"], type(exc).__name__, str(exc)[:60]])
                continue
            gaps = [abs(c - f["normalized"]) if c is not None else 9.0 for c in cands]
            best = min(gaps); k = gaps.index(best)
            if best < 1e-9:
                a["match" if k == 0 else "match_zero_rule"] += 1
            else:
                a["mismatch"] += 1
                a["max_gap"] = max(a["max_gap"], best)
                if len(a["examples"]) < 3: a["examples"].append([s["ticker"], s["strategy"], f["normalized"], cands[0], f["raw"]])
out = dict(sorted(stat.items()))
Path("reports/score_reliability_audit_2026_11_25/scratch_1/e5_raw_to_norm.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str))
tot = defaultdict(int)
for k, a in out.items():
    for x in ("n", "match", "match_zero_rule", "mismatch", "error"): tot[x] += a[x]
    flag = "" if not a["mismatch"] and not a["error"] else "  <<<<"
    print(f"{k:35s} n={a['n']:5d} match={a['match']:5d} zero_rule={a['match_zero_rule']:4d} mismatch={a['mismatch']:4d} err={a['error']:3d} maxgap={a['max_gap']:.4f}{flag}")
    if flag:
        for e in a["examples"]: print("      ", str(e)[:400])
print(dict(tot))
