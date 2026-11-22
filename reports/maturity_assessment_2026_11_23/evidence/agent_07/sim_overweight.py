"""Agent 7: synthetic check of the overweight notice (made-up stocks and made-up price moves; no market data, no return computed)."""
import sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
from terminal.committee import portfolios as pf, service
from tests import committee_cases as cc
from tests.test_committee import CTX, book
b = book([dict(ticker="KEEP"), dict(cc.A_EXCELLENT_BUT_DEAR, ticker="WAITS")])
for t, e in b.items():
    b[t] = service.judge(e["figures"], {k: True for k in pf.ORDER}, CTX)
prev = {"KEEP": 0.12, "WAITS": 0.07}
for day in range(1, 9):
    p = pf.investor_portfolio("BUFFETT", b, prev, 60.0, None, {"KEEP": 0.35, "WAITS": 0.0}.get)   # KEEP +35% each step, made up
    rows = {r["ticker"]: r for r in p["holdings"]}
    n = p["overweight"]
    print(day, "KEEP weight", rows["KEEP"]["weight"], "cap", pf.SPEC["BUFFETT"]["cap"], "notice", bool(n), "new", n[0]["new"] if n else None, "largest", p["largest"], "concentration", p["concentration"], "sectors", p["sectors"])
    prev = {t: r["weight"] for t, r in rows.items()}
print(p["overweight"][0]["text"])
