"""Audit 6: does a direct evaluation of a ticker give the score the scan recorded?  Asks the running local server (GET only)."""
import sys, pathlib, json, random, urllib.request, time
real = pathlib.Path.home() / "Developer/quant-stock-engine"
sys.path.insert(0, str(real))
from utils import runtime_config
runtime_config.load_local_env(real / ".env")
from terminal.services import Terminal
from terminal.qsf import order_plan as op
t = Terminal(real); B = "http://127.0.0.1:8765"; rng = random.Random(6)
out = []
for m, k in (("US", 14), ("KR", 10)):
    last = t.qsf.latest(m)["session"]
    snaps = {(s["ticker"], s["strategy"]): s for s in op.session_snaps(t.qsf.ledger, m, last) if s.get("data_date") == last}
    tickers = rng.sample(sorted({k_[0] for k_ in snaps if k_[0] != "SPY"}), k)
    for tk in tickers:
        t0 = time.time()
        try:
            with urllib.request.urlopen(f"{B}/api/qsf/evaluate?t={tk}&market={m}", timeout=180) as r: d = json.loads(r.read())
        except Exception as e:
            out.append({"m": m, "t": tk, "error": type(e).__name__}); continue
        cards = d.get("cards") or {x: d.get(x) for x in ("SWING", "LONG_TERM")}
        row = {"m": m, "t": tk, "sec": round(time.time() - t0, 1)}
        for strat in ("SWING", "LONG_TERM"):
            c = (cards or {}).get(strat) or {}; s = snaps.get((tk, strat)) or {}
            fa = {f["factor"]: f.get("normalized") for f in c.get("factors") or []}; fb = {f["factor"]: f.get("normalized") for f in s.get("factors") or []}
            diff = sorted(((abs((fa.get(k_) or 0) - (fb.get(k_) or 0)), k_) for k_ in set(fa) | set(fb) if (fa.get(k_) is None) != (fb.get(k_) is None) or abs((fa.get(k_) or 0) - (fb.get(k_) or 0)) > 1e-6), reverse=True)
            row[strat] = {"scan": None if s.get("score") is None else round(s["score"], 3), "direct": None if c.get("score") is None else round(c["score"], 3), "date": (s.get("data_date"), c.get("data_date")),
                          "action": (s.get("action"), c.get("action")), "differing_factors": [(k_, round(fb.get(k_), 3) if fb.get(k_) is not None else None, round(fa.get(k_), 3) if fa.get(k_) is not None else None) for _d, k_ in diff[:4]]}
        out.append(row)
json.dump(out, open(pathlib.Path(__file__).parent / "exp_consistency.json", "w"), ensure_ascii=False, indent=1)
same = diffn = 0
for r in out:
    if "error" in r: print(r); continue
    for strat in ("SWING", "LONG_TERM"):
        x = r[strat]; eq = x["scan"] is not None and x["direct"] is not None and abs(x["scan"] - x["direct"]) < 0.005
        same += eq; diffn += not eq
        if not eq: print(r["m"], r["t"], strat, x)
print("identical:", same, "different:", diffn, "of", same + diffn)
