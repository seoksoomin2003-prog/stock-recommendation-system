"""Agent 4: the Korean replay's stored scores on its last evaluation day against the ledger's record of the same session.
Scores only.  The ledger rows are re-added with today's weights over the three domains the replay scores (no events, no regime),
so what is compared is the inputs, not the formula's parts the replay does not have.  No price, no return."""
import gzip, json
from pathlib import Path
import numpy as np
from terminal.qsf import config, validate
kd = json.load(gzip.open("research_data/krx_live/scores_current_cap.json.gz", "rt"))
dates = kd["dates"]
last_i = max(r["i"] for r in kd["records"])
day = dates[last_i]
replay = {r["t"]: r for r in kd["records"] if r["i"] == last_i}
idx = [json.loads(l) for l in open("data/qsf/ledger/index.jsonl")]
void = {r["file"] for r in idx if r.get("type") == "VOID"}
snaps = []
for r in idx:
    if r.get("type") != "VOID" and r["file"] not in void and r["market"] == "KR" and r["session"] == day:
        snaps += [json.loads(x) for x in gzip.open(Path("data/qsf/ledger")/r["file"], "rt")]
print("replay day", day, "replay names", len(replay), "ledger snapshots", len(snaps), "ledger version", {s["model_version"] for s in snaps})
out = {}
for strat in ("SWING", "LONG_TERM"):
    prof = config.profile_for("KR", strat)["domains"]
    live = {}
    for s in snaps:
        if s["strategy"] != strat: continue
        w = c = 0.0
        for f in s["factors"]:
            wt = prof.get(f["domain"], {}).get(f["factor"]) if f["domain"] in ("TECHNICAL", "FUNDAMENTAL", "RISK") else None
            if wt and f.get("normalized") is not None and f["status"] in ("REAL", "STALE"):
                w += wt; c += wt * f["normalized"]
        if w: live[s["ticker"]] = 100 * c / w
    both = [t for t in replay if replay[t].get(strat) is not None and t in live]
    a = np.array([replay[t][strat] for t in both]); b = np.array([live[t] for t in both])
    rc = float(np.corrcoef(validate.rank(a), validate.rank(b))[0, 1])
    d = np.abs(a - b)
    top = lambda x: {both[j] for j in np.argsort(-x)[:max(1, len(both)//5)]}
    print(strat, "replay scored", sum(1 for t in replay if replay[t].get(strat) is not None), "ledger names", len(live), "both", len(both), "only replay", len([t for t in replay if t not in live]), "only ledger", len([t for t in live if t not in replay]),
          "| rank corr", round(rc, 4), "median |diff|", round(float(np.median(d)), 2), "p90", round(float(np.percentile(d, 90)), 2), "max", round(float(d.max()), 2), ">5pt", int((d > 5).sum()),
          "| top-fifth overlap", f"{len(top(a) & top(b))}/{len(top(a))}")
    out[strat] = {"both": len(both), "rank_corr": rc, "median_abs_diff": float(np.median(d)), "p90": float(np.percentile(d, 90)), "over5": int((d > 5).sum())}
json.dump({"day": day, **out}, open(__file__.replace(".py", ".json"), "w"), indent=1)
