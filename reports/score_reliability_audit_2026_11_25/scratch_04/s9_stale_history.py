"""Agent 4: per recorded session - stored-copy use (provenance.stale), fundamental factors missing, KR price source.  No outcomes."""
import gzip, json
from collections import Counter
from pathlib import Path
idx = [json.loads(l) for l in open("data/qsf/ledger/index.jsonl")]
void = {r["file"] for r in idx if r.get("type") == "VOID"}
print("session market version n | stale-copy cards | fund-domain all missing (stocks) | STALE-status factors | price source")
out = []
for r in idx:
    if r.get("type") == "VOID" or r["file"] in void: continue
    snaps = [json.loads(x) for x in gzip.open(Path("data/qsf/ledger")/r["file"], "rt")]
    stale_cards = sum(1 for s in snaps if (s.get("provenance") or {}).get("stale"))
    what = Counter(x.get("what") for s in snaps for x in ((s.get("provenance") or {}).get("stale") or []))
    nofund = sum(1 for s in snaps if s["strategy"] == "LONG_TERM" and all(f["status"] == "MISSING" for f in s["factors"] if f["domain"] == "FUNDAMENTAL"))
    stale_f = sum(1 for s in snaps for f in s["factors"] if f["status"] == "STALE")
    src = Counter(((s.get("provenance") or {}).get("price") or "")[:14] for s in snaps if s["strategy"] == "SWING")
    print(r["session"], r["market"], r["model_version"], len(snaps), "|", stale_cards, dict(what), "|", nofund, "|", stale_f, "|", dict(src))
    out.append({"session": r["session"], "market": r["market"], "n": len(snaps), "stale_cards": stale_cards, "no_fund": nofund, "stale_factors": stale_f})
json.dump(out, open(__file__.replace(".py", ".json"), "w"), indent=1)
