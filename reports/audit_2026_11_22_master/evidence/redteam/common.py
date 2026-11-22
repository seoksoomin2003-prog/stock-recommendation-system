"""Scratch helpers for the red-team audit.  Imports repo modules read-only; builds synthetic inputs only."""
import sys, math, random
from datetime import date, timedelta
REPO = "~/Developer/quant-stock-engine"
if REPO not in sys.path:
    sys.path.insert(0, REPO)
sys.dont_write_bytecode = True
from terminal.qsf import config, engine, factors, technicals, holding  # noqa


def weekdays(n, end=date(2026, 11, 20)):
    out, d = [], end
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d -= timedelta(days=1)
    return out[::-1]


def bars(n=520, start=100.0, drift=0.0008, vol=0.012, seed=1, volume=5e6, end=date(2026, 11, 20)):
    rnd = random.Random(seed)
    px, out = start, []
    for d in weekdays(n, end):
        r = drift + vol * rnd.gauss(0, 1)
        o = px * (1 + 0.002 * rnd.gauss(0, 1))
        c = px * (1 + r)
        h, lo = max(o, c) * (1 + abs(0.004 * rnd.gauss(0, 1))), min(o, c) * (1 - abs(0.004 * rnd.gauss(0, 1)))
        out.append({"date": d, "open": o, "high": h, "low": lo, "close": c, "adj_close": c, "volume": volume})
        px = c
    return out


GOOD_FUND = dict(status="REAL", source="synthetic", filed="2026-02-15", is_financial=False, roe=0.22, roe_prev=0.21, op_margin=0.22, gross_margin=0.50, net_margin=0.15,
                 rev_growth=0.12, eps_growth=0.15, rev_cagr3=0.10, eps_cagr3=0.12, ocf_to_ni=1.15, fcf=1.0, fcf_margin=0.14, fcf_years_positive=1.0,
                 roe_years_positive=1.0, debt_equity=0.4, current_ratio=2.0, interest_cover=12.0, cash_debt=0.7, equity_assets=0.5, share_change=-0.01,
                 returns_capital=True, market_cap=5e10, eps=5.0, pe=18.0, pb=3.5, fcf_yield=0.05, insider_pct=0.03)
EVENTS_OK = {"status": "REAL", "severe": [], "negative": [], "positive": [], "governance": [], "window_days": 90, "window_long_days": 365, "as_of": "2026-11-20", "source": "synthetic",
             "insider": {"status": "REAL", "open_market_buy": 0.0, "open_market_sell": 0.0, "window_days": 90}}


def ctx(market="US", b=None, bench=None, fund=None, events=None, earnings=None, rs_rank=0.6, regime=None, **kw):
    b = b or bars()
    bench = bench or bars(seed=99, drift=0.0004, vol=0.008)
    c = {"market": market, "ticker": "SYN", "bars": b, "bench": bench, "bench_name": "SPY", "fund": dict(GOOD_FUND) if fund is None else fund,
         "events": dict(EVENTS_OK) if events is None else events, "earnings": {"sessions": 30, "date": "2027-01-05"} if earnings is None else earnings,
         "rs_rank": rs_rank, "regime": regime or {}, "price_fresh": True, "expected_session": b[-1]["date"], "identity_ok": True}
    c.update(kw)
    return c


def brief(res):
    return {k: (round(res[k], 2) if isinstance(res[k], float) else res[k]) for k in ("profile", "score", "band", "action", "raw_action", "actionability", "coverage", "confidence")} | {
        "gates": [g["code"] for g in res["gates"]], "missing": res["missing"], "stale": res["stale"]}


def stub_calc(values, status=None):
    """Replace every factor calculator IN THIS PROCESS ONLY by a stub returning the given normalized value (default 0.5).
    values: {factor: float | 'MISSING' | 'NA'}"""
    orig = dict(factors.CALC)
    def mk(fid):
        def f(c):
            v = values.get(fid, values.get("*", 0.5))
            if v == "MISSING":
                return factors.missing("stub")
            if v == "NA":
                return factors.not_applicable("stub")
            return {"status": (status or {}).get(fid, "REAL"), "normalized": float(v), "raw": {}, "explanation": fid, "source": "stub", "as_of": None}
        return f
    for fid in list(factors.CALC):
        factors.CALC[fid] = mk(fid)
    return orig


def restore_calc(orig):
    factors.CALC.clear(); factors.CALC.update(orig)
