from common import *
import copy
from terminal.qsf import price_audit
base = bars(n=520, drift=0.0009, vol=0.011, seed=7, volume=5e7)
def sc(b, strat="SWING", market="US", **kw):
    c = ctx(market, b, **kw); r = engine.score(c, strat); return r, holding.entry_status(r, c)
def p(tag, r, e=None):
    t = r["tech"]
    print(f"{tag}: score {None if r['score'] is None else round(float(r['score']), 1)} action {r['action']} raw {r['raw_action']} act {r['actionability']} gates {[g['code'] for g in r['gates']]} cov {r['coverage']:.2f} conf {r['confidence']}"
          f" | n {t['n']} close {t['close']:.2f} ma200 {None if t['ma200'] is None else round(t['ma200'], 2)} maxDD {t['max_drawdown_252']:.2f} max_move_5 {None if t['max_move_5'] is None else round(t['max_move_5'], 2)}" + (f" | entry {e['status']}" if e else ""))
r0, e0 = sc(base); p("clean series (swing)", r0, e0)
r0l, e0l = sc(base, "LONG_TERM"); p("clean series (long) ", r0l, e0l)

print("\n== 7a. a 10-for-1 split left unadjusted (price / 10 from one bar on) ==")
def split(b, k, ratio):
    out = copy.deepcopy(b)
    for x in out[len(out) - k:]:
        for key in ("open", "high", "low", "close", "adj_close"):
            x[key] /= ratio
        x["volume"] *= ratio
    return out
for k in (1, 3, 5, 6, 30):
    r, e = sc(split(base, k, 10)); p(f"split 10:1 {k:2d} bars ago", r, e)
print("-- a 2-for-1 split left unadjusted")
for k in (1, 6):
    r, e = sc(split(base, k, 2)); p(f"split 2:1 {k:2d} bars ago ", r, e)
print("-- a 1-for-10 reverse split left unadjusted, 6 bars ago")
r, e = sc(split(base, 6, 0.1)); p("reverse split 6 bars ago", r, e)
rl, el = sc(split(base, 6, 0.1), "LONG_TERM"); p("  same, long card        ", rl, el)

print("\n== 7b. a stock pinned at a takeover price (jump +35% 80 bars ago, then +-0.1% a day) ==")
pin = copy.deepcopy(base)
level = pin[-81]["close"] * 1.35
rnd = random.Random(5)
for x in pin[-80:]:
    c = level * (1 + 0.001 * rnd.gauss(0, 1))
    x.update(open=c, high=c * 1.0008, low=c * 0.9992, close=c, adj_close=c)
for strat in ("SWING", "LONG_TERM"):
    r, e = sc(pin, strat, rs_rank=0.9); p(f"pinned ({strat})", r, e)
    print("     factors:", {x["factor"]: round(float(x["normalized"]), 2) for x in r["factors"] if x["domain"] in ("TECHNICAL", "RISK") and x["normalized"] is not None and x.get("scored", True) is not False})

print("\n== 7c. newly listed: 30, 60, 199, 200 bars ==")
for n in (30, 60, 199, 200):
    b = bars(n=n, drift=0.003, vol=0.02, seed=11, volume=5e7)
    for strat in ("SWING", "LONG_TERM"):
        r, e = sc(b, strat); p(f"{n:3d} bars {strat:9s}", r, e)

print("\n== 8a. last bar 5 sessions old (price_fresh False as service.context sets it) ==")
old = base[:-5]
r, e = sc(old, price_fresh=False, expected_session=base[-1]["date"]); p("stale by 5 sessions", r, e)
print("\n== 8b. one negative close 100 bars ago; one zero close; KR profile has no minimum price ==")
neg = copy.deepcopy(base); neg[-100]["close"] = -neg[-100]["close"]; neg[-100]["adj_close"] = neg[-100]["close"]
for m in ("US", "KR"):
    r, e = sc(neg, market=m); p(f"negative close mid-series ({m})", r, e)
negl = copy.deepcopy(base); negl[-1]["close"] = -5.0; negl[-1]["adj_close"] = -5.0
for m in ("US", "KR"):
    r, e = sc(negl, market=m); p(f"negative LAST close ({m})", r, e)
print("\n== 8c. zero-volume days ==")
zv = copy.deepcopy(base)
for x in zv[-12:-2]:
    x["volume"] = 0
r, e = sc(zv); p("10 zero-volume days ending 2 bars ago", r, e)
zl = copy.deepcopy(base); zl[-1]["volume"] = 0
r, e = sc(zl); p("zero volume on the last bar", r, e)
print("\n== 8d. duplicated dates ==")
short = bars(n=120, drift=0.003, vol=0.02, seed=11, volume=5e7)
dup = [x for b in short for x in (b, dict(b))]
r1, e1 = sc(short); p("120 real bars            ", r1, e1)
r2, e2 = sc(dup); p("the same, every bar twice", r2, e2)
d2 = base + [dict(base[-1])]
r3, e3 = sc(d2); p("520 bars + last bar twice", r3, e3)
print("   hist_vol clean", round(r0["tech"]["hist_vol"], 3), "| every bar twice (520 -> 1040):", round(engine.score(ctx("US", [x for b in base for x in (b, dict(b))]), "SWING")["tech"]["hist_vol"], 3))
print("\n== price_audit.audit_us_stock on the same series (the checker; it gates nothing) ==")
days = [b["date"] for b in base]
for tag, b in (("clean", base), ("zero-volume run", zv), ("duplicated last bar", d2), ("negative close", neg), ("10:1 split 30 bars ago", split(base, 30, 10))):
    a = price_audit.audit_us_stock(b, days[-253:])
    print(f"   {tag:24s} level {a['level']} counts {a['counts']}")
