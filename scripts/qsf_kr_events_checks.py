"""After the one Korean filing-event run: is the result real?  Rules, scores and the report are untouched; these only read them.

1. the tier figures recomputed without the shared evaluation code;
2. a shuffle of the signal across stocks, which should find nothing;
3. the result with one-day moves beyond the price limit removed, since a rights date read as a loss would flatter this signal;
4. what is left after size and the other Korean themes;
5. non-overlapping 252-session windows, the real number of independent samples;
6. how many stocks the current Korean scan's buy band has with a recent financing decision.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from terminal.qsf import config, research_ensemble as en, research_kr as kr, research_kr_events as ke, research_kr_fund as kf, validate  # noqa: E402

LIMIT = 0.31


def ranks(x):
    return validate.rank(x.astype(float)) / (len(x) - 1)


def tiers_by_hand(score, px, rows, picks, h, cost):
    excess, ic = {0: [], 50: [], 100: []}, []
    for n in picks:
        i = rows[n]
        win = px.data["adj_close"][i + 1:i + h + 1].astype(float)
        last = np.full(win.shape[1], np.nan)
        for row in win:                                   # the last traded close in the window
            last = np.where(np.isfinite(row), row, last)
        r = last / px.data["open"][i + 1].astype(float) - 1
        s = score[n].astype(float)
        ok = np.isfinite(r) & np.isfinite(s)
        if ok.sum() < 30:
            continue
        ic.append(np.corrcoef(validate.rank(s[ok]), validate.rank(r[ok]))[0, 1])
        for t in excess:
            excess[t].append(r[ok & (s == t)].mean() - r[ok].mean())
    return {"ic": float(np.mean(ic)), **{str(t): float(np.mean(v)) for t, v in excess.items()}, "net_spread": float(np.mean(excess[100]) - np.mean(excess[0]) - cost), "dates": len(ic)}


def without_limit_breaks(px):
    """A copy of the prices with each adjacent-day move beyond the limit set to no move.  Returns the copy and how many such days each stock has."""
    a = px.data["adj_close"].astype(float)
    new, count = a.copy(), np.zeros(a.shape[1], dtype=int)
    market = px.col[kr.MARKET]
    for j in range(a.shape[1]):
        if j == market:
            continue
        have = np.flatnonzero(np.isfinite(a[:, j]))
        if len(have) < 2:
            continue
        step = a[have[1:], j] / a[have[:-1], j]
        adjacent = np.diff(have) == 1
        bad = adjacent & (np.abs(step - 1) > LIMIT)
        count[j] = int(bad.sum())
        if bad.any():
            step = np.where(bad, 1.0, step)
            new[have, j] = a[have[0], j] * np.concatenate([[1.0], np.cumprod(step)])
    z = dict(px.data)
    with np.errstate(invalid="ignore", divide="ignore"):
        z["open"] = (px.data["open"].astype(float) * (new / a)).astype(np.float32)
    z["adj_close"] = new.astype(np.float32)
    return kr.KrPrices(z), count


def partial_ic(score, controls, px, rows, picks, h):
    out = []
    for n in picks:
        r, s = px.forward(rows[n], h), score[n].astype(float)
        ok = np.isfinite(r) & np.isfinite(s)
        for c in controls:
            ok &= np.isfinite(c[n])
        if ok.sum() < 100:
            continue
        x = np.column_stack([np.ones(ok.sum())] + [ranks(c[n][ok]) for c in controls])
        ry, rs_ = ranks(r[ok]), ranks(s[ok])
        ey = ry - x @ np.linalg.lstsq(x, ry, rcond=None)[0]
        es = rs_ - x @ np.linalg.lstsq(x, rs_, rcond=None)[0]
        out.append(np.corrcoef(es, ey)[0, 1])
    return {"ic": float(np.mean(out)), "t": validate.newey_west_t(out, max(1, h // kr.STEP)), "dates": len(out)}


def main():
    px, rows, _ = ke._inputs(ROOT)
    with np.load(ROOT / ke.FEATURES) as z:
        tensor = z["tensor"]
    score = ke.score_of(tensor)
    cost = config.round_trip_cost("KR")
    report = json.loads((ROOT / ke.REPORT).read_text(encoding="utf-8"))
    print("reading", report["reading"])

    print("--- 1. by hand against the report")
    for s, h in ke.HORIZONS.items():
        picks = kr.windows(px, rows, h)["test"]
        got = tiers_by_hand(score, px, rows, picks, h, cost)
        r = report["scores"]["EVENTS"][s]
        print(s, {k: round(v, 4) for k, v in got.items()}, "report ic", round(r["ic"], 4), "tiers", {t: round(r["tiers"][t]["excess"], 4) for t in r["tiers"]}, "spread_net", round(r["spread_net"], 4))

    print("--- 2. the signal shuffled across eligible stocks on each date")
    rng = np.random.default_rng(20261108)
    shuffled = score.copy()
    for n in range(len(rows)):
        have = np.flatnonzero(np.isfinite(score[n]))
        shuffled[n, have] = rng.permutation(score[n, have])
    for s, h in ke.HORIZONS.items():
        w = kr.windows(px, rows, h)["test"]
        e = en.evaluate(shuffled, px, rows, w, h, {}, cost)
        print(s, {k: round(e[k], 4) for k in ("ic", "t", "top_excess", "spread_net")})

    print("--- 3. without one-day moves beyond the limit")
    clean, count = without_limit_breaks(px)
    print("stocks with such a day", int((count > 0).sum()), "days", int(count.sum()))
    for s, h in ke.HORIZONS.items():
        w = kr.windows(clean, rows, h)["test"]
        e = en.evaluate(score, clean, rows, w, h, {}, cost)
        print(s, {k: round(e[k], 4) for k in ("ic", "t", "top_excess", "spread_net")}, en_tiers(score, clean, rows, w, h))
    ns = [n for n, i in enumerate(rows) if px.dates[i] >= ke.TEST_START]
    fin = np.array([np.nanmean(count[tensor[n, :, 0] == 1] > 0) for n in ns])
    non = np.array([np.nanmean(count[tensor[n, :, 0] == 0] > 0) for n in ns])
    print("share ever with such a day: financing", round(float(fin.mean()), 3), "no financing", round(float(non.mean()), 3))

    print("--- 4. what is left after size and the other themes")
    with np.load(ROOT / kf.FEATURES) as z:
        fund = kf.theme_ranks(z["tensor"])
    with np.load(ROOT / kr.FEATURES) as z:
        price = kr.theme_ranks(z["tensor"])
    cap = np.stack([px.data["cap"][i].astype(float) for i in rows])
    groups = report["overlap"]["fund_groups"]
    fund_score = en.combine(fund, groups)
    plan = {"size": [cap], "size_and_fund": [cap, fund_score], "size_fund_price": [cap, fund_score] + [price[t] for t in sorted(price)]}
    for s, h in ke.HORIZONS.items():
        w = kr.windows(px, rows, h)["test"]
        print(s, "plain", round(report["scores"]["EVENTS"][s]["ic"], 4), {name: {k: (round(v, 4) if isinstance(v, float) else v) for k, v in partial_ic(score, c, px, rows, w, h).items()} for name, c in plan.items()})

    print("--- 5. non-overlapping 252-session windows")
    h = 252
    w = kr.windows(px, rows, h)["test"][::h // kr.STEP]
    for n in w:
        e = en.evaluate(score, px, rows, [n], h, {}, cost)
        t = tiers_by_hand(score, px, rows, [n], h, cost)
        print(px.dates[rows[n]], {k: round(v, 4) for k, v in t.items() if k != "dates"}, "stocks", round(e["mean_stocks"]))

    print("--- 6. the current Korean scan")
    latest = ROOT / "data" / "qsf" / "latest_KR.json"
    if latest.exists():
        body = json.loads(latest.read_text(encoding="utf-8"))
        items = body.get("rows") or body.get("items") or body.get("results") or body
        print("scan keys", list(body)[:12] if isinstance(body, dict) else type(body).__name__)
        events = ke.load_events(ROOT / ke.DATA)
        day = px.dates[-1]
        first = px.dates[-1 - ke.WINDOW]
        rowsk = items if isinstance(items, list) else []
        stat = {}
        for r in rowsk:
            code = str(r.get("ticker") or r.get("symbol") or "")[:6]
            band = r.get("band") or r.get("rating") or r.get("label") or "?"
            by = events.get(code) or {}
            f = ke.seen_within(by.get("financing") or [], first, day)
            b = ke.seen_within(by.get("buyback") or [], first, day)
            x = stat.setdefault(str(band), {"names": 0, "financing": 0, "buyback": 0})
            x["names"] += 1
            x["financing"] += f
            x["buyback"] += b
        print("as of", day, stat)


def en_tiers(score, px, rows, picks, h):
    t = ke._tier_returns(score, px, rows, picks, h)
    return {k: round(v["excess"], 4) for k, v in t.items()}


if __name__ == "__main__":
    main()
