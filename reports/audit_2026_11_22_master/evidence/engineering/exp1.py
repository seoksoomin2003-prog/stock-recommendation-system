import sys, socket, json
from pathlib import Path
# hard network block for this experiment
def _no(*a, **k): raise RuntimeError("NETWORK BLOCKED")
socket.socket.connect = _no; socket.create_connection = _no
sys.path.insert(0, "~/Developer/quant-stock-engine")
from terminal.qsf import config, engine
from terminal.qsf.service import QSF
from tests.test_qsf import NOW, SESSION, FakeSrc, FakeTerm, bars, ctx, GOOD_FUND
from tests.test_qsf_stored_rank import Src, HeldTerm, TICKERS
tmp = Path(sys.argv[1])
q = QSF(tmp / "a", src=Src(), now=lambda: NOW, terminal=HeldTerm())
res = q.scan("US", tickers=TICKERS)
rows = {(r["ticker"], r["strategy"]): r for r in res["rows"]}
ev = q.evaluate("T20")
print("A. held T20 (style SWING):")
for s in config.STRATEGIES:
    c = ev["cards"][s]
    print(f"   {s:9s} scan: score={rows[('T20', s)]['score']:.3f} action={rows[('T20', s)]['action']:6s} | evaluate: score={c['score']:.3f} action={c['action']:6s} held={c['held']} exit={'exit' in c}")
snaps = [x for x in q.ledger.snapshots(market="US", ticker="T20")]
print("   ledger:", [(x["strategy"], x["action"], x["held"]) for x in snaps])
# B. partial sub-inputs inside a factor
full = engine.score(ctx(), "LONG_TERM")
thin_fund = {k: (v if k in ("status", "source", "filed", "roe", "pe") else None) for k, v in GOOD_FUND.items()}
thin = engine.score(ctx(fund=thin_fund), "LONG_TERM")
f = lambda r, fid: next(x for x in r["factors"] if x["factor"] == fid)
print("B. fund with only roe and pe present:")
for fid in ("valuation", "business_quality", "growth_quality", "free_cash_flow", "balance_dilution"):
    a, b = f(full, fid), f(thin, fid)
    print(f"   {fid:18s} full: {a['status']} {a['normalized']:.3f} | thin: {b['status']} {b['normalized'] if b['normalized'] is None else round(b['normalized'],3)}")
print(f"   coverage full={full['coverage']:.3f} thin={thin['coverage']:.3f} FUND coverage full={full['domains']['FUNDAMENTAL']['coverage']:.3f} thin={thin['domains']['FUNDAMENTAL']['coverage']:.3f} confidence {full['confidence']} -> {thin['confidence']} score {full['score']:.1f} -> {thin['score']:.1f} actionability={thin['actionability']}")
# C. annotation
import typing
from terminal import sources
try:
    typing.get_type_hints(sources.ecos_series); print("C. ecos_series hints OK")
except Exception as e:
    print("C. ecos_series get_type_hints ->", type(e).__name__, e)
# D. order plan candidate below BUY band
from terminal.qsf import order_plan as op
snap = {"data_date": SESSION, "actionability": "ACTIONABLE", "entry_status": "ENTRY_NOW", "score": 56.0, "price": 100.0, "stop": 96.0, "target": 110.0, "strategy": "SWING", "ticker": "X", "action": "WATCH",
        "factors": [{"factor": "liquidity", "raw": {"adv_value": 5e8}}]}
print("D. candidates from a WATCH-band (56) snapshot:", [(c["ticker"], c["score"]) for c in op.candidates([snap], SESSION)])
