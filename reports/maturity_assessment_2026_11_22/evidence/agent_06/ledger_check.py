"""AGENT 6, system test F: ledger integrity and whether a recorded card can be re-added from its stored parts.
Reads scores and factor traces only. No price is read and no return is computed."""
import sys, json, collections
from pathlib import Path
REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
from terminal.qsf.ledger import Ledger
led = Ledger(REPO)
v = led.verify()
print("verify:", v)
rows = led.read_index()["rows"]
live = led._live_rows()
print("index rows", len(rows), "live", len(live))
by = collections.OrderedDict()
for r in live:
    by.setdefault((r["market"], r["session"]), []).append((r["records"], r.get("model_version")))
for k, vv in by.items():
    print(k, vv)
for market in ("US", "KR"):
    mr = [r for r in live if r["market"] == market]
    last = mr[-1]
    snaps = led._load(last)
    print("==", market, last["session"], "snapshots", len(snaps), "keys", sorted(snaps[0].keys()))
    bad = n = 0
    worst = 0.0
    late = 0
    mx = collections.defaultdict(lambda: -1.0)
    cnt70 = collections.Counter()
    for s in snaps:
        if s.get("score") is None:
            continue
        mx[s["strategy"]] = max(mx[s["strategy"]], s["score"])
        cnt70[s["strategy"]] += s["score"] >= 70
        tot = sum(f["contribution"] for f in s["factors"] if f.get("contribution") is not None and f.get("scored") is not False)
        pts = sum(d["points"] for k, d in s["domains"].items() if d.get("points") is not None and not d.get("reference"))
        n += 1
        worst = max(worst, abs(pts - tot))
    print("  factor contributions vs domain points: max abs diff", round(worst, 6), "over", n)
    f0 = snaps[0]
    print("  sample fields:", {k: f0.get(k) for k in ("ticker", "strategy", "model_version", "score", "coverage", "data_date", "recorded_at", "entry_session", "entry_status", "benchmark")})
    print("  sample factor:", json.dumps(f0["factors"][0], ensure_ascii=False)[:300])
    print("  domains:", json.dumps(f0["domains"], ensure_ascii=False)[:400])
    print("  provenance:", json.dumps(f0.get("provenance"), ensure_ascii=False)[:400])
    print("  max score by strategy:", dict(mx), "count >= 70:", dict(cnt70))
    # timestamps: recorded_at date vs entry_session
    order = collections.Counter()
    for s in snaps:
        ra, es = str(s.get("recorded_at"))[:10], s.get("entry_session")
        order["recorded_date<=entry_session" if es and ra <= es else "recorded_after_entry_or_none"] += 1
    print("  recorded_at vs entry_session:", dict(order), "entry_status:", dict(collections.Counter(str(s.get("entry_status")) for s in snaps)))
