"""Agent 01 cross review of Agent 03: the four claims, checked with the program's own functions.

Inputs: Agent 03's offline dry scan of today's code (evidence/agent_03/big/cards_151.json, QSF-1.5.1 cards of session 2026-11-20) and,
to check that dump, the two cards this agent got from the running server.  No provider, no record, no return or IC figure:
only scores, bands, factor values and what a hypothetical price would do to one factor.
"""
import json, sys
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
sys.path.insert(0, str(REPO))
from terminal.qsf import config, engine, factors, holding, order_plan as op, stance, technicals

dump = json.loads((HERE.parent / "agent_03" / "big" / "cards_151.json").read_text(encoding="utf-8"))

print("== 0. is the dump the live code's output?  (dump vs this agent's two server replies)")
for market, ticker, name in (("US", "AAPL", "eval_US_AAPL.json"), ("KR", "005930", "eval_KR_005930.json")):
    live = json.loads((HERE / "big" / name).read_text(encoding="utf-8"))["cards"]
    for strat in ("SWING", "LONG_TERM"):
        d = dump[market]["cards"][f"{ticker}|{strat}"]
        print(f"   {market} {ticker} {strat}: dump {d['score']:.4f} {d['band']} {d['entry_status']} | server {live[strat]['score']:.4f} {live[strat]['band']} {live[strat]['entry_status']}")

def snaps_of(market):
    session = dump[market]["session"]
    return session, [{**c, "data_date": session, "market": market} for c in dump[market]["cards"].values()]

print("\n== 1. the stance's line on the screen against the score floor of the order plan's candidates")
print("   presets:", {k: (v["line"], v["plan_needs_line"], v["size"]) for k, v in stance.PRESETS.items()})
for market in ("US", "KR"):
    session, snaps = snaps_of(market)
    cands = op.candidates(snaps, session)
    state = {"size_factor": 1.0, "new_exposure_cap": None}
    for level in stance.LEVELS:
        got = stance.marks(snaps, level)
        kept, used, shown = stance.for_plan(cands, state, got, level, op.STRATEGY_OF)
        for style in ("SWING", "LONG"):
            mine = [c["score"] for c in kept if c["style"] == style]
            screen = sum(1 for (t, s), why in got.items() if why is None and s == op.STRATEGY_OF[style])
            print(f"   {market} {style:5s} {level:10s} screen line {stance.PRESETS[level]['line']:g}: screen candidates {screen:3d} | plan candidates {len(mine):3d}"
                  f" lowest plan score {min(mine):.2f}" if mine else f"   {market} {style:5s} {level:10s} screen line {stance.PRESETS[level]['line']:g}: screen candidates {screen:3d} | plan candidates   0",
                  f"| under 70: {sum(1 for v in mine if v < 70)}", f"| size factor {used['size_factor']:g}")
    del snaps

print("\n== 2. stance.judge reads the score; the band shown reads the conservative score")
order = stance.CONFIDENCE_ORDER
for market in ("US", "KR"):
    session, snaps = snaps_of(market)
    held = [s for s in snaps if s.get("held_back")]
    marks = {lvl: stance.marks(snaps, lvl) for lvl in stance.LEVELS}
    print(f"   {market}: cards whose buy label was held back: {len(held)}")
    for s in sorted(held, key=lambda s: -s["score"]):
        print(f"      {s['ticker']:7s} {s['strategy']:9s} score {s['score']:.2f} conservative {s['conservative']:.2f} band {s['band']:10s} conf {s['confidence']:6s} coverage {s['coverage']:.3f}"
              f" entry {s['entry_status']:28s} | stance says: " + ", ".join(f"{lvl[:3]}={'CANDIDATE' if marks[lvl][(s['ticker'], s['strategy'])] is None else marks[lvl][(s['ticker'], s['strategy'])]}" for lvl in stance.LEVELS))
    hit = [s for s in snaps if s.get("held_back") and s["band"] not in engine.BUY_CODES and marks["DEFENSIVE"][(s["ticker"], s["strategy"])] is None]
    print(f"   {market}: held back out of the buy band AND a DEFENSIVE candidate: {len(hit)}")
    del snaps
print("   bound: score s, missing share m of the applicable weight -> conservative = s(1-m) + 50m.  For s >= 75 and conservative < 70: m > (s-70)/(s-50)")
for s in (75.0, 80.0, 85.0):
    m = (s - 70) / (s - 50)
    print(f"      s={s:g}: m > {m:.3f} -> coverage < {1 - m:.3f}; confidence there:", next((lab for lo, lab in config.CONFIDENCE_BANDS if 1 - m - 1e-9 >= lo), "under the 70% sufficiency rule: not judged"))

print("\n== 3. Korean swing: the factor that is absent for every stock, and the line the conservative score makes")
prof = config.profile_for("KR", "SWING")
scored = {f: w for d in config.DOMAINS for f, w in prof["domains"][d].items()}
print("   scored factors and weights:", scored, "| sum", sum(scored.values()))
session, snaps = snaps_of("KR")
sw = [s for s in snaps if s["strategy"] == "SWING"]
status = {}
for s in sw:
    st = next(f["status"] for f in s["factors"] if f["factor"] == "insider_activity")
    status[st] = status.get(st, 0) + 1
print("   insider_activity status over", len(sw), "cards:", status)
allmiss = {}
for s in sw:
    for f in s["factors"]:
        if f.get("scored") is not False and f["status"] == "MISSING":
            allmiss[f["factor"]] = allmiss.get(f["factor"], 0) + 1
print("   scored factors MISSING, by count:", allmiss)
top = max((s for s in sw if s["score"] is not None), key=lambda s: s["score"])
w_have = sum(f["weight"] for f in top["factors"] if f.get("scored") is not False and f["status"] in ("REAL", "STALE"))
w_miss = sum(f["weight"] for f in top["factors"] if f.get("scored") is not False and f["status"] == "MISSING")
print(f"   top card {top['ticker']}: score {top['score']:.2f} conservative {top['conservative']:.2f} | weight with data {w_have:g}, missing {w_miss:g}"
      f" | by the formula {(top['score'] / 100 * w_have + config.MISSING_NEUTRAL * w_miss) / (w_have + w_miss) * 100:.2f}")
W, M = 37.0, 3.0
line = (0.70 * (W + M) - config.MISSING_NEUTRAL * M) / W * 100
exit_ = (config.BUY_BAND_EXIT / 100 * (W + M) - config.MISSING_NEUTRAL * M) / W * 100
print(f"   score needed for the buy label when only insider_activity is absent: {line:.2f}; with the buffer: {exit_:.2f}")
def fake(score):          # a Korean swing card whose 37 points of factors all read score/100 and whose insider factor is absent, through the real engine
    ctx = {"market": "KR", "bars": [], "tech": {"n": 300, "date": "2026-11-20", "close": 10000.0, "adv_value": 1e12, "last_volume": 1, "atr": 100.0}, "levels": {"status": "UNAVAILABLE"}, "price_fresh": True}
    real = dict(factors.CALC)
    try:
        for f in scored:
            factors.CALC[f] = (lambda c, f=f: factors.missing("absent") if f == "insider_activity" else factors.obs(score / 100.0, {}, "", "test", "2026-11-20"))
        return engine.score(ctx, "SWING")
    finally:
        factors.CALC.clear(); factors.CALC.update(real)
for sc in (70.0, 71.0, 71.6, 71.7, 80.0, 81.0, 82.5):
    r = fake(sc)
    print(f"      engine.score at {sc:g}: score {r['score']:.2f} conservative {r['conservative_score']:.2f} band {r['band']} action {r['raw_action']} held_back {r['band_held_back']} confidence {r['confidence']}")
del snaps

print("\n== 4. risk_reward against the price")
print("   4a. the program's own functions on a made-up year of highs (two swing highs at 110 and 130; ATR 2.0; close moved in steps of 0.1)")
h = np.full(252, 100.0); h[100] = 110.0; h[180] = 130.0
atr, prev = 2.0, None
for close in np.arange(106.0, 110.01, 0.1):
    r = technicals._resistance(h, float(close), atr)
    lv = technicals.levels({"atr": atr, "close": float(close), "resistance": r}, "US")
    f = factors.ramp(lv["reward_risk"], 1.0, 3.0)
    if prev is not None and abs(f - prev[1]) > 0.2:
        print(f"      close {prev[0]:.1f} -> {close:.1f} ({(close / prev[0] - 1) * 100:.2f}%): target {prev[2]:.1f} -> {lv['target']:.1f}, reward/risk {prev[3]:.2f} -> {lv['reward_risk']:.2f}, factor {prev[1]:.2f} -> {f:.2f}")
    prev = (float(close), f, lv["target"], lv["reward_risk"])
h2 = np.full(252, 100.0); h2[100] = 110.0
for close in (107.9, 108.1):
    r = technicals._resistance(h2, close, atr); lv = technicals.levels({"atr": atr, "close": close, "resistance": r}, "US")
    print(f"      one high only, close {close}: target {lv['target']:.1f} ({lv['target_method'][:12]}), reward/risk {lv['reward_risk']:.2f}, factor {factors.ramp(lv['reward_risk'], 1.0, 3.0):.2f}")
print("   4b. Agent 03's price test repeated on the dump (stored close, ATR and resistance; x0.97 and x1.03), with what caused each large change")
for market in ("US", "KR"):
    session, snaps = snaps_of(market)
    rows = []
    for s in snaps:
        if s["strategy"] != "SWING" or s["score"] is None:
            continue
        t = s["tech"]
        fr = next((f for f in s["factors"] if f["factor"] == "risk_reward"), None)
        if not fr or fr["status"] not in ("REAL", "STALE") or not t.get("atr") or not t.get("close"):
            continue
        w_all = sum(f["weight"] for f in s["factors"] if f.get("scored") is not False and f["status"] in ("REAL", "STALE"))
        for mult in (0.97, 1.03):
            close = t["close"] * mult
            ok = t.get("resistance") if (t.get("resistance") and t["resistance"] >= close + t["atr"]) else None
            lv = technicals.levels({"atr": t["atr"], "close": close, "resistance": ok}, market)
            new = factors.ramp(lv["reward_risk"], 1.0, 3.0)
            switched = bool(t.get("resistance")) != bool(ok)
            rows.append((abs(new - fr["normalized"]) * fr["weight"] / w_all * 100, s["ticker"], mult, fr["normalized"], new, t["atr"] / t["close"] * 100, switched, 0.03 * t["close"] / t["atr"]))
    rows.sort(reverse=True)
    big = [r for r in rows if r[0] >= 3.0]
    print(f"   {market} swing: largest score change {rows[0][0]:.2f} points; changes of 3 points or more: {len(big)} of {len(rows)}; of those, target switched from the stored high to the 3-ATR projection: {sum(1 for r in big if r[6])}")
    for r in rows[:5]:
        print(f"      {r[1]:7s} x{r[2]}: factor {r[3]:.2f} -> {r[4]:.2f} = {r[0]:.2f} points | ATR {r[5]:.2f}% of price, so 3% is {r[7]:.1f} ATR | target switched: {r[6]}")
    sw_rows = [r for r in rows if r[6]]
    print(f"      among the {len(sw_rows)} cases where the target did switch: largest change {max((r[0] for r in sw_rows), default=0):.2f} points")
    del snaps
print("   the factor's whole weight on the 100 scale: US swing", 6 / 80 * 100, "| KR swing", round(6 / 37 * 100, 2), "(with insider_activity absent)")
