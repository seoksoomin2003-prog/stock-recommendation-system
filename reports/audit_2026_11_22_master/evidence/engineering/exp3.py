import sys, socket
def _no(*a, **k): raise RuntimeError("NETWORK BLOCKED")
socket.socket.connect = _no; socket.create_connection = _no
sys.path.insert(0, "~/Developer/quant-stock-engine")
from terminal.qsf import engine, technicals
from tests.test_qsf import ctx, bars
un = {"status": "UNAVAILABLE", "reason": "SEC CIK 없음", "no_cik": True}
for strat in ("SWING", "LONG_TERM"):
    full = engine.score(ctx(), strat)
    r = engine.score(ctx(fund=un, events={"status": "UNAVAILABLE", "reason": "SEC CIK 없음"}, earnings={"sessions": None}), strat)
    print(strat, "full score", round(full["score"], 1), full["actionability"], full["confidence"], "| no SEC data: score", round(r["score"], 1), "coverage", round(r["coverage"], 3), r["actionability"], r["confidence"], "action", r["action"], "missing", len(r["missing"]))
# 2-for-1 split left unadjusted on the last bar: does DATA_ANOMALY fire?
b = bars()
b2 = [dict(x) for x in b]
for k in ("open", "high", "low", "close", "adj_close"): b2[-1][k] = b2[-1][k] / 2
t = technicals.compute(b2)
r = engine.score(ctx(bars=b2), "SWING")
print("unadjusted 2:1 split on last bar: max_move_5 =", round(t["max_move_5"], 3), "gates =", [g["code"] for g in r["gates"]])
# duplicate last bar
b3 = b + [dict(b[-1])]
t3 = technicals.compute(b3); t0 = technicals.compute(b)
print("duplicated last bar: n", t0["n"], "->", t3["n"], "rsi", round(t0["rsi"], 2), "->", round(t3["rsi"], 2), "atr", round(t0["atr"], 4), "->", round(t3["atr"], 4), "ret_21", round(t0["ret_21"], 4), "->", round(t3["ret_21"], 4))
