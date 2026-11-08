"""After the one Korean holder-stake run: is the result real?  Rules, scores and the report are untouched; these only read them.

1. a shuffle of the signal across stocks on each date, many times, which should find nothing;
2. what is left after size and the other Korean themes (partial rank correlation);
3. non-overlapping 252-session windows, the real number of independent samples;
4. the same partial check inside the 300 most traded stocks, the universe the live Korean scan uses.
"""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from terminal.qsf import config, research_ensemble as en, research_kr as kr, research_kr_fund as kf, research_kr_holder as kh  # noqa: E402

sys.path.insert(0, str(ROOT / "scripts"))
from qsf_kr_events_checks import partial_ic  # noqa: E402

SHUFFLES = 100


def main():
    px, rows, top300 = kh._inputs(ROOT)
    with np.load(ROOT / kh.FEATURES) as z:
        tensor = z["tensor"]
    score = kh.score_of(tensor)
    cost = config.round_trip_cost("KR")
    report = json.loads((ROOT / kh.REPORT).read_text(encoding="utf-8"))
    print("reading", report["reading"])

    print(f"--- 1. the signal shuffled across stocks on each date, {SHUFFLES} times")
    rng = np.random.default_rng(20261109)
    for s, h in kh.HORIZONS.items():
        w = kr.windows(px, rows, h)["test"]
        t0, ics, ts = time.time(), [], []
        for _ in range(SHUFFLES):
            shuffled = score.copy()
            for n in w:
                have = np.flatnonzero(np.isfinite(score[n]))
                shuffled[n, have] = rng.permutation(score[n, have])
            e = en.evaluate(shuffled, px, rows, w, h, {}, cost)
            ics.append(e["ic"])
            ts.append(e["t"])
        real = report["scores"]["HOLDER"][s]
        print(s, "real ic", round(real["ic"], 4), "t", round(real["t"], 2), "| shuffled ic mean", round(float(np.mean(ics)), 4), "max", round(float(np.max(ics)), 4),
              "t max", round(float(np.max(ts)), 2), "share >= real ic", float(np.mean(np.array(ics) >= real["ic"])), f"{time.time() - t0:.0f}s")

    print("--- 2. what is left after size and the other themes")
    with np.load(ROOT / kf.FEATURES) as z:
        fund = kf.theme_ranks(z["tensor"])
    with np.load(ROOT / kr.FEATURES) as z:
        price = kr.theme_ranks(z["tensor"])
    cap = np.stack([px.data["cap"][i].astype(float) for i in rows])
    fund_score = en.combine(fund, report["overlap"]["fund_groups"])
    plan = {"size": [cap], "size_and_fund": [cap, fund_score], "size_fund_price": [cap, fund_score] + [price[t] for t in sorted(price)]}
    for s, h in kh.HORIZONS.items():
        w = kr.windows(px, rows, h)["test"]
        print(s, "plain", round(report["scores"]["HOLDER"][s]["ic"], 4),
              {name: {k: (round(v, 4) if isinstance(v, float) else v) for k, v in partial_ic(score, c, px, rows, w, h).items()} for name, c in plan.items()})

    print("--- 3. non-overlapping 252-session windows")
    h = 252
    for n in kr.windows(px, rows, h)["test"][::h // kr.STEP]:
        e = en.evaluate(score, px, rows, [n], h, {}, cost)
        print(px.dates[rows[n]], {k: round(e[k], 4) for k in ("ic", "spread_net", "top_excess")}, "stocks", round(e["mean_stocks"]))

    print("--- 4. inside the 300 most traded stocks: plain and after size")
    for s, h in kh.HORIZONS.items():
        w = kr.windows(px, rows, h)["test"]
        top = score.copy()
        for n in w:
            top[n, ~top300[n].astype(bool)] = np.nan
        plain = partial_ic(top, [], px, rows, w, h)
        sized = partial_ic(top, [cap], px, rows, w, h)
        print(s, "plain", {k: round(v, 4) if isinstance(v, float) else v for k, v in plain.items()}, "after size", {k: round(v, 4) if isinstance(v, float) else v for k, v in sized.items()})


if __name__ == "__main__":
    main()
