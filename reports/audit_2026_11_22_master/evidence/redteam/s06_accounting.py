from common import *
from terminal.qsf import fundamentals as F
up = bars(drift=0.0010, vol=0.012, seed=5, volume=5e7)
close = up[-1]["close"]

def series(**cols):
    """cols: name -> list of 4 yearly values (FY2022..FY2025); None skips a year."""
    ends = ["2022-12-31", "2023-12-31", "2024-12-31", "2025-12-31"]
    filed = ["2023-02-20", "2024-02-20", "2025-02-20", "2026-02-20"]
    return {k: [{"end": e, "val": float(v), "filed": f} for e, f, v in zip(ends, filed, vals) if v is not None] for k, vals in cols.items()}

def show(name, annual, as_of="2026-11-20", shares=None, strategies=("LONG_TERM", "SWING"), **kw):
    m = F.metrics(annual, close, as_of, shares=shares, **kw)
    keys = ("status", "roe", "op_margin", "rev_growth", "eps_growth", "rev_cagr3", "eps_cagr3", "ocf_to_ni", "fcf_margin", "debt_equity", "debt_basis", "interest_cover", "pe", "pb", "fcf_yield", "equity_assets", "roe_years_positive")
    print(f"\n--- {name}")
    print("   metrics:", {k: (round(m[k], 3) if isinstance(m.get(k), float) else m.get(k)) for k in keys})
    for s in strategies:
        c = ctx("US", up, fund=m, rs_rank=0.8); r = engine.score(c, s)
        fs = {x["factor"]: (x["status"][:4] if x["normalized"] is None else round(float(x["normalized"]), 2)) for x in r["factors"] if x["domain"] == "FUNDAMENTAL" or x["factor"] in ("financial_resilience", "leverage", "capital_allocation")}
        print(f"   {s}: score {r['score']:.1f} {r['band']} action {r['action']} cov {r['coverage']:.2f} conf {r['confidence']} entry {holding.entry_status(r, c)['status']}\n      {fs}")
    return m

sh = [100e6] * 4
# A. revenue grows 30% a year, losses deepen every year, cash burn, funded by share issues
A = series(revenue=[1000e6, 1300e6, 1690e6, 2197e6], gross_profit=[550e6, 715e6, 930e6, 1210e6], op_income=[-100e6, -250e6, -500e6, -900e6], net_income=[-120e6, -280e6, -560e6, -1000e6],
           ocf=[-80e6, -200e6, -450e6, -800e6], capex=[50e6, 60e6, 80e6, 100e6], eps=[-1.2, -2.5, -4.5, -7.0], shares_avg=[100e6, 112e6, 124e6, 143e6],
           equity=[2000e6, 2200e6, 2100e6, 1900e6], assets=[2600e6, 3000e6, 3100e6, 3200e6], liabilities=[600e6, 800e6, 1000e6, 1300e6], current_assets=[1800e6, 2000e6, 1900e6, 1700e6],
           current_liabilities=[300e6, 400e6, 500e6, 600e6], cash=[1500e6, 1600e6, 1500e6, 1200e6], debt_long=[0, 0, 0, 0])
show("A. sales +30%/yr, losses deepening every year (-120M -> -1,000M), cash burn, 15% dilution/yr", A, shares=143e6)

# B. profitable company with NEGATIVE equity (buybacks), real debt
B = series(revenue=[10e9, 10.5e9, 11e9, 11.5e9], gross_profit=[5e9, 5.2e9, 5.5e9, 5.8e9], op_income=[3e9, 3.1e9, 3.3e9, 3.5e9], net_income=[2e9, 2.1e9, 2.2e9, 2.4e9], ocf=[2.6e9, 2.7e9, 2.9e9, 3.1e9],
           capex=[0.5e9] * 4, interest=[0.4e9] * 4, eps=[20, 21.5, 23, 25.5], shares_avg=[100e6, 98e6, 96e6, 94e6], buyback=[2e9] * 4, dividends=[1e9] * 4,
           equity=[-2e9, -3e9, -4e9, -5e9], assets=[20e9] * 4, liabilities=[22e9, 23e9, 24e9, 25e9], current_assets=[4e9] * 4, current_liabilities=[4e9] * 4, cash=[1e9] * 4, debt_long=[12e9, 13e9, 14e9, 15e9])
mB = show("B. profitable, negative equity (-5bn), debt 15bn", B, shares=94e6)

# C. NEGATIVE equity and a debt figure of exactly zero
C = dict(B); C.update(series(debt_long=[0, 0, 0, 0]))
mC = show("C. negative equity (-5bn), tagged debt = 0", C, shares=94e6)
print("   debt_equity repr:", repr(mC["debt_equity"]), "| leverage factor:", factors.leverage({"fund": mC}).get("normalized"), "| balance_dilution:", round(factors.balance_dilution({"fund": mC})["normalized"], 2))

# D. tiny positive equity: ROE in the thousands of per cent
D = dict(B); D.update(series(equity=[60e6, 60e6, 60e6, 61.5e6]))
mD = show("D. tiny equity (61.5M on 20bn assets): ROE and D/E", D, shares=94e6)
print("   roe =", f"{mD['roe'] * 100:.0f}%", "| profitability factor:", factors.profitability({"fund": mD, "tech": {}})["normalized"], "| business_quality:", round(factors.business_quality({"fund": mD})["normalized"], 2),
      "| D/E =", round(mD["debt_equity"], 1), "(> the 99.0 'no equity' mark)" if mD["debt_equity"] > 99 else "")

# E. bank: financial rule
E = series(revenue=[10e9, 10.5e9, 11e9, 11.5e9], net_income=[1e9, 1.05e9, 1.1e9, 0.6e9], eps=[10, 10.5, 11, 6.0], shares_avg=[100e6] * 4, equity=[10e9, 10.5e9, 11e9, 11.2e9], assets=[150e9, 160e9, 170e9, 180e9],
           liabilities=[140e9, 149.5e9, 159e9, 168.8e9], dividends=[0.3e9] * 4, ocf=[2e9, -3e9, 5e9, -8e9])
show("E. bank (is_financial=True): EPS -45%, equity/assets 6.2%", E, shares=100e6, is_financial=True)

# F. loss-maker: is a NEGATIVE PER ever cheap?
G = series(revenue=[5e9] * 4, op_income=[0.3e9, 0.1e9, -0.2e9, -0.5e9], net_income=[0.2e9, 0.05e9, -0.3e9, -0.6e9], eps=[2, 0.5, -3, -6], shares_avg=[100e6] * 4, equity=[4e9, 4e9, 3.7e9, 3.1e9], assets=[8e9] * 4,
           liabilities=[4e9, 4e9, 4.3e9, 4.9e9], ocf=[0.5e9, 0.3e9, 0.1e9, -0.2e9], capex=[0.2e9] * 4, current_assets=[2e9] * 4, current_liabilities=[1.5e9] * 4, cash=[0.5e9] * 4, debt_long=[2e9, 2e9, 2.3e9, 2.8e9], interest=[0.1e9] * 4)
mG = show("G. loss-maker: negative PER", G, shares=100e6, strategies=("LONG_TERM",))
print("   pe =", round(mG["pe"], 2), "| valuation factor:", round(factors.valuation({"fund": mG})["normalized"], 3), "(PER part is 0.0 when PER <= 0)")

# H. stale fundamentals: the newest fiscal year is 2 years old
H = {k: v[:3] for k, v in B.items()}       # newest year 2024-12-31
mH = show("H. newest fiscal year 2024-12-31 read on 2026-11-20 (691 days old)", {k: v for k, v in H.items()}, shares=96e6)
H2 = {k: v[:2] for k, v in B.items()}
mH2 = F.metrics(H2, close, "2026-11-20", shares=98e6)
print("   two years old (FY2023):", mH2["status"])
