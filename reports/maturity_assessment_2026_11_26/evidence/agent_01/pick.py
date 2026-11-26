import json, sys
from pathlib import Path
from terminal.qsf.ledger import Ledger
led = Ledger(Path('.'))
out = {}
for m, want in (("US", ["MSFT", "JPM"]), ("KR", ["005930"])):
    rows = [r for r in led._live_rows() if r["market"] == m]
    row = rows[-1]
    snaps = led._load(row)
    print(m, {k: row.get(k) for k in ("session", "name", "count", "model_version")}, "snaps", len(snaps), "keys", sorted(snaps[0].keys())[:40])
    for s in snaps:
        if s["ticker"] in want:
            out[f'{m}:{s["ticker"]}:{s["strategy"]}'] = {"session": s.get("session"), "score": s.get("score"), "band": s.get("band"), "coverage": s.get("coverage"), "confidence": s.get("confidence"), "data_date": s.get("data_date"),
                 "factors": {f["factor"]: f.get("normalized") for f in s.get("factors", [])} if isinstance(s.get("factors"), list) else s.get("norm") or s.get("factors")}
json.dump(out, open(sys.argv[1], "w"), ensure_ascii=False, indent=1)
print(len(out))
