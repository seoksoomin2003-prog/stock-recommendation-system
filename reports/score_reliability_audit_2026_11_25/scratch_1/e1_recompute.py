"""Agent 1, experiment E1 (no return): recompute the composite, coverage, conservative score and band of every ledger snapshot
from its own recorded factor rows, and compare with what was recorded.  Reads the ledger only (index + shards); writes one JSON."""
import gzip, json, sys, math
from collections import Counter, defaultdict
from pathlib import Path
sys.path.insert(0, ".")
from terminal.qsf import config, engine
from terminal.qsf.ledger import Ledger

OUT = Path("reports/score_reliability_audit_2026_11_25/scratch_1/e1_recompute.json")
Q = {"REAL": 1.0, "STALE": 0.5}
led = Ledger(Path("."))
rows = [r for r in led._live_rows()]
res = defaultdict(lambda: {"n": 0, "scored": 0, "max_gap": 0.0, "gaps_over_1e9": 0, "contrib_bad": 0, "cov_max_gap": 0.0, "cov_n": 0,
                           "cons_max_gap": 0.0, "cons_n": 0, "band_plain_mismatch": Counter(), "weights_differ": 0, "formula_fn_gap": 0.0,
                           "versions": Counter(), "sessions": set()})
for r in rows:
    for s in led._load(r):
        key = f"{s['market']}_{s['strategy']}"
        a = res[key]
        a["n"] += 1
        a["versions"][s.get("model_version")] += 1
        a["sessions"].add(r["session"])
        fr = s.get("factors") or []
        w = c = app = eff = miss_w = 0.0
        never = config.NEVER_AVAILABLE.get((s["market"], s["strategy"]), ())
        prof = config.profile_for(s["market"], s["strategy"])
        cur_w = {f: wt for d in prof["domains"].values() for f, wt in d.items()}
        for f in fr:
            if f.get("scored") is False:
                continue
            wt = float(f["weight"])
            if s.get("model_version", "") >= "QSF-1.4.1" and cur_w.get(f["factor"]) != f["weight"]:
                a["weights_differ"] += 1
            if f["status"] != "NOT_APPLICABLE":
                app += wt
            if f["status"] in Q and f.get("normalized") is not None:
                w += wt; c += wt * float(f["normalized"]); eff += wt * Q[f["status"]]
                if f.get("contribution") is None or abs(f["contribution"] - wt * float(f["normalized"])) > 1e-9:
                    a["contrib_bad"] += 1
            elif f["status"] == "MISSING" and f["factor"] not in never:
                miss_w += wt
        mine = 100 * c / w if w else None
        rec = s.get("score")
        if rec is None or mine is None:
            if (rec is None) != (mine is None):
                a["gaps_over_1e9"] += 1
            continue
        a["scored"] += 1
        g = abs(mine - rec)
        a["max_gap"] = max(a["max_gap"], g)
        if g > 1e-9:
            a["gaps_over_1e9"] += 1
        fs = engine.formula_score(fr, counted=())          # the engine's own helper on the same rows, reference domains left out
        if fs is not None:
            a["formula_fn_gap"] = max(a["formula_fn_gap"], abs(fs - rec))
        if s.get("coverage") is not None and app:
            a["cov_n"] += 1
            a["cov_max_gap"] = max(a["cov_max_gap"], abs(eff / app - s["coverage"]))
        if s.get("conservative_score") is not None and (w + miss_w):
            # only comparable under the rule of the snapshot's own version (NEVER_AVAILABLE from 1.5.2)
            if s.get("model_version", "") >= "QSF-1.5.2":
                a["cons_n"] += 1
                a["cons_max_gap"] = max(a["cons_max_gap"], abs(100 * (c + 0.5 * miss_w) / (w + miss_w) - s["conservative_score"]))
        plain = engine.classify(rec)["band"]
        if plain != s.get("band"):
            why = "held_back" if s.get("band_held_back") else "deal_held" if s.get("deal_held") else "buffer" if (s.get("band") == "BUY_CANDIDATE" and 67 <= rec < 70) else "OTHER"
            a["band_plain_mismatch"][why] += 1
out = {}
for k, a in sorted(res.items()):
    out[k] = {**{x: a[x] for x in ("n", "scored", "max_gap", "gaps_over_1e9", "contrib_bad", "cov_max_gap", "cov_n", "cons_max_gap", "cons_n", "weights_differ", "formula_fn_gap")},
              "band_plain_mismatch": dict(a["band_plain_mismatch"]), "versions": dict(a["versions"]), "sessions": len(a["sessions"]), "first": min(a["sessions"]), "last": max(a["sessions"])}
OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1))
print(json.dumps(out, ensure_ascii=False, indent=1))
