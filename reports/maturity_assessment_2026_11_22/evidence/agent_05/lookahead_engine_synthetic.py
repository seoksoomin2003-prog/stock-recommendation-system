"""AGENT 5 scratch: what the look-ahead audit of the score engine can and cannot show, on random prices (no repository data)."""
import json
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
from terminal.qsf import lookahead        # noqa: E402

rng = np.random.default_rng(5)
T, N = 420, 30
days, d0 = [], date(2025, 1, 1)
while len(days) < T:
    if d0.weekday() < 5:
        days.append(d0.isoformat())
    d0 += timedelta(days=1)
close = 100 * np.exp(np.cumsum(rng.normal(0.0003, 0.02, (T, N)), axis=0))
d = {"dates": np.array(days), "symbols": np.array([f"{k:06d}" for k in range(N)]), "close": close, "adj_close": close.copy(), "open": close * (1 + rng.normal(0, 0.003, (T, N))),
     "high": close * 1.01, "low": close * 0.99, "volume": rng.uniform(1e5, 1e6, (T, N)), "value": close * rng.uniform(1e5, 1e6, (T, N))}
rows = lookahead.sample_rows(T)
fn = next(f for f in lookahead.functions(d) if f["id"] == "engine.score")["fn"]
got = lookahead.check(fn, d, rows)
one = fn(d, rows[0])
ctx_keys = {"events": None, "regime": None, "earnings": None, "fund": None}
out = {"sampled_days": len(rows), "engine_check": {"days": got["days"], "filled": got["filled"], "moved": len(got["moved"])}, "stocks_scored_on_first_day": len(one),
       "inputs_the_audit_gives_the_engine": {"bars": "rows i0..i only (built before the engine is called)", **{k: "None" for k in ctx_keys}, "rs_rank": "absent"},
       "reading": "The engine receives only rows up to day i, so wiping or multiplying later rows cannot reach it: the check passes by construction. "
                  "It shows the engine keeps no hidden state between calls; it says nothing about statements (filing dates), events, the earnings calendar, the universe rank or the live service."}
Path(__file__).with_name("lookahead_engine_synthetic_output.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print(json.dumps(out, ensure_ascii=False, indent=1))
