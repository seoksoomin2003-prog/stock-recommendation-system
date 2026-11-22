"""Stocks for the committee tests: one sound, fairly priced company in an up-trend, and the ways the scenarios change it."""
from terminal.committee import figures as fg

BASE = dict(pe=18.0, pb=3.0, fcf_yield=0.05, roe=0.25, op_margin=0.25, gross_margin=0.50, profit_years=1.0, eps_cagr3=0.12, rev_cagr3=0.08, rev_growth=0.10, eps_growth=0.15, ocf_to_ni=1.1,
            fcf_margin=0.15, fcf_years=1.0, debt_equity=0.4, share_change=-0.01, returns_capital=True, current_ratio=2.2, cash_debt=0.8, interest_cover=12.0, ma20=105.0, ma50=100.0,
            ma50_slope=0.02, ma200=90.0, ma200_slope=0.05, rs=0.80, rel_126=0.15, ret_12_1=0.30, rsi=55.0, dist_high=-0.04, volume_ratio=1.2, breakout=False, max_drawdown=-0.15,
            downside_vol=0.15, hist_vol=0.25, atr_pct=0.02, adv_value=1e9, reward_risk=2.2, events_negative=0, events_positive=1, insider_pct=0.03, earnings_sessions=10,
            price=110.0, state=60.0, market_cap=5e10, dividend_yield=1.5, forward_pe=16.0, trailing_pe=18.0, insider_buy=5.0, insider_sell=1.0, issues=(), sector="산업재", industry="Machinery",
            ticker="GOOD", market="US", vix_pct=0.4, credit_pct=0.4, breadth=0.6, index_close=110.0, index_ma200=100.0, index_ma50=105.0)


def snaps(**over):
    v = {**BASE, **over}

    def f(name, **raw):
        return {"factor": name, "raw": {k: x for k, x in raw.items()}}
    long_ = {"ticker": v["ticker"], "market": v["market"], "data_date": "2026-11-20", "price": v["price"], "domains": {"REGIME": {"score_100": v["state"]}}, "stop": v["price"] * 0.92, "target": v["price"] * 1.2,
             "factors": [f("valuation", pe=v["pe"], pb=v["pb"], fcf_yield=v["fcf_yield"]), f("business_quality", roe=v["roe"], op_margin=v["op_margin"], gross_margin=v["gross_margin"], roe_years_positive=v["profit_years"]),
                         f("growth_quality", eps_cagr3=v["eps_cagr3"], rev_cagr3=v["rev_cagr3"], rev_growth=v["rev_growth"]), f("free_cash_flow", fcf_margin=v["fcf_margin"], fcf_years_positive=v["fcf_years"]),
                         f("balance_dilution", debt_equity=v["debt_equity"], share_change=v["share_change"]), f("financial_resilience", current_ratio=v["current_ratio"], cash_debt=v["cash_debt"], interest_cover=v["interest_cover"]),
                         f("capital_allocation", returns_capital=v["returns_capital"]), f("long_trend", ma200=v["ma200"], ma200_slope=v["ma200_slope"]), f("relative_strength", percentile=v["rs"], rel_126=v["rel_126"]),
                         f("momentum_persistence", ret_12_1=v["ret_12_1"]), f("downside_drawdown", max_drawdown_252=v["max_drawdown"], downside_vol=v["downside_vol"]), f("liquidity", adv_value=v["adv_value"]),
                         f("material_events", negative=v["events_negative"], positive=v["events_positive"]), f("governance", issues=list(v["issues"])),
                         f("insider_ownership", insider_pct=v["insider_pct"], insider={"status": "REAL", "open_market_buy": v["insider_buy"], "open_market_sell": v["insider_sell"]}),
                         f("vix_regime", percentile_5y=v["vix_pct"]), f("credit_spread", percentile=v["credit_pct"]), f("index_trend_breadth", breadth=v["breadth"], close=v["index_close"], ma200=v["index_ma200"], ma50=v["index_ma50"])]}
    swing = {"ticker": v["ticker"], "market": v["market"], "data_date": "2026-11-20", "price": v["price"], "domains": {"REGIME": {"score_100": v["state"]}}, "stop": v["price"] * 0.92, "target": v["price"] * 1.2,
             "factors": [f("trend_structure", ma20=v["ma20"], ma50=v["ma50"], ma50_slope=v["ma50_slope"], ma200=v["ma200"], ma200_slope=v["ma200_slope"]), f("momentum", rsi=v["rsi"]),
                         f("breakout_volume", dist_high=v["dist_high"], volume_ratio=v["volume_ratio"], breakout=v["breakout"]), f("earnings_revenue_quality", eps_growth=v["eps_growth"], ocf_to_ni=v["ocf_to_ni"], rev_growth=v["rev_growth"]),
                         f("atr_risk", atr_pct=v["atr_pct"], hist_vol=v["hist_vol"]), f("risk_reward", reward_risk=v["reward_risk"]), f("earnings_calendar", sessions=v["earnings_sessions"])]}
    for snap in (long_, swing):          # a figure given as None is not on file
        for fac in snap["factors"]:
            fac["raw"] = {k: x for k, x in fac["raw"].items() if x is not None}
    info = {k: x for k, x in {"marketCap": v["market_cap"], "dividendYield": v["dividend_yield"], "forwardPE": v["forward_pe"], "trailingPE": v["trailing_pe"], "industry": v["industry"]}.items() if x is not None}
    return long_, swing, info, v["sector"]


def figures(marks=(), deals=(), **over):
    long_, swing, info, sector = snaps(**over)
    f = fg.read(long_, swing, info, sector, marks, deals)
    f["name"] = f"{f['ticker']} Co"
    return f


# the six scenarios of the specification (2026-11-22)
A_EXCELLENT_BUT_DEAR = dict(ticker="AAA", pe=45.0, pb=14.0, fcf_yield=0.018, roe=0.40, op_margin=0.35, gross_margin=0.65, eps_cagr3=0.22, rev_growth=0.18, eps_growth=0.25, trailing_pe=45.0, forward_pe=36.0, sector="기술")
B_SOUND_AND_CHEAP = dict(ticker="BBB", pe=8.0, pb=0.9, fcf_yield=0.09, roe=0.12, op_margin=0.12, gross_margin=0.28, eps_cagr3=0.03, rev_cagr3=0.02, rev_growth=0.02, eps_growth=0.03, current_ratio=2.6, debt_equity=0.3,
                         trailing_pe=8.0, forward_pe=7.8, dividend_yield=3.5, rs=0.45, ret_12_1=0.02, ma200_slope=0.0, rel_126=-0.02, market_cap=8e9)
C_FAST_SMALL = dict(ticker="CCC", pe=28.0, pb=6.0, fcf_yield=0.02, roe=0.22, op_margin=0.16, gross_margin=0.45, eps_cagr3=0.32, rev_cagr3=0.28, rev_growth=0.30, eps_growth=0.35, market_cap=3e9, dividend_yield=0.0,
                    trailing_pe=28.0, forward_pe=21.0, current_ratio=1.6, debt_equity=0.5, sector="기술")
D_QUALITY_LOSING_MOMENTUM = dict(ticker="DDD", price=80.0, ma20=84.0, ma50=88.0, ma50_slope=-0.03, ma200=95.0, ma200_slope=-0.01, rs=0.25, rel_126=-0.12, ret_12_1=-0.10, dist_high=-0.28, eps_growth=-0.05,
                                 trailing_pe=18.0, forward_pe=19.5, reward_risk=0.8, max_drawdown=-0.30)
E_CHEAP_LEVERED = dict(ticker="EEE", pe=6.0, pb=0.7, fcf_yield=-0.03, roe=0.10, op_margin=0.05, gross_margin=0.18, eps_cagr3=-0.10, rev_cagr3=-0.03, rev_growth=-0.06, eps_growth=-0.30, ocf_to_ni=0.3, fcf_margin=-0.04,
                       fcf_years=0.4, debt_equity=3.5, current_ratio=0.8, cash_debt=0.05, interest_cover=1.2, profit_years=0.8, rs=0.2, ret_12_1=-0.25, price=70.0, ma50=85.0, ma200=95.0, ma200_slope=-0.04, max_drawdown=-0.45)
F_MOAT_FULL_PRICE = dict(ticker="FFF", pe=32.0, pb=9.0, fcf_yield=0.028, roe=0.45, op_margin=0.38, gross_margin=0.70, eps_cagr3=0.10, rev_cagr3=0.09, trailing_pe=32.0, forward_pe=29.0, sector="필수소비재")
