"""AGENT 7 scratch: read the QSF ledger (read-only) into one compact pickle.  No price, no return, no outcome is read.

For each market, session, strategy: tickers, the stored score, band, actionability, coverage, confidence, and per factor the
stored normalized value, status, stored weight and a few raw inputs.  Sectors are added from what is stored on disk
(US: the sector column of data/qsf/research/scores_current_us.json.gz; KR: the newest security master + terminal.kr_sectors).
"""
import gzip, json, pickle, sys
from pathlib import Path
sys.path.insert(0, ".")
from terminal.qsf.ledger import Ledger
from terminal import kr_sectors

OUT = Path("reports/score_reliability_audit_2026_11_25/scratch_07/ledger_compact.pkl")
led = Ledger(Path("."))
rows = led._live_rows()

us_sec = {}
d = json.load(gzip.open("data/qsf/research/scores_current_us.json.gz", "rt"))
for r in d["records"]:
    if r.get("sector"):
        us_sec[r["t"]] = r["sector"]
import pandas as pd
sdir = Path("data/kr/security_master")
meta = json.loads((sdir / "LATEST.json").read_text())
df = pd.read_csv(sdir / meta["file"], dtype=str)
kr_sec = {}
for c, i, n in zip(df["canonical_ticker"], df["industry"], df["company_name"] if "company_name" in df else [None] * len(df)):
    if isinstance(c, str) and isinstance(i, str) and i.strip():
        kr_sec[c] = kr_sectors.broad_sector(c, i, n if isinstance(n, str) else None)

data = {}
seen = set()
for r in rows:
    key = (r["market"], r["session"])
    snaps = led._load(r)
    dup = key in seen
    seen.add(key)
    for s in snaps:
        if s.get("data_date") != r["session"]:
            continue
        k = (r["market"], r["session"], s["strategy"])
        slot = data.setdefault(k, {"shards": set(), "model_versions": set(), "rows": {}})
        slot["shards"].add(r["file"])
        slot["model_versions"].add(s.get("model_version"))
        if s["ticker"] in slot["rows"]:
            continue            # the first shard of a session is the record; a later scan of the same session is left out
        fac = {}
        for f in s.get("factors") or []:
            raw = f.get("raw") if isinstance(f.get("raw"), dict) else {}
            fac[f["factor"]] = {"n": f.get("normalized"), "st": f.get("status"), "w": f.get("weight"), "dom": f.get("domain"), "scored": f.get("scored", True),
                                "raw": {a: b for a, b in raw.items() if isinstance(b, (int, float, bool)) or b is None}}
        sec = (us_sec if r["market"] == "US" else kr_sec).get(s["ticker"])
        slot["rows"][s["ticker"]] = {"score": s.get("score"), "band": s.get("band"), "act": s.get("actionability"), "cov": s.get("coverage"), "conf": s.get("confidence"),
                                     "icov": s.get("input_coverage"), "cons": s.get("conservative_score"), "held_back": s.get("band_held_back"), "sector": sec, "fac": fac,
                                     "domains": {a: (b or {}).get("score_100") for a, b in (s.get("domains") or {}).items()}}
for k, v in data.items():
    v["shards"] = sorted(v["shards"]); v["model_versions"] = sorted(str(x) for x in v["model_versions"])
pickle.dump(data, open(OUT, "wb"))
for k in sorted(data):
    v = data[k]
    n = len(v["rows"]); sc = sum(1 for x in v["rows"].values() if x["score"] is not None); nosec = sum(1 for x in v["rows"].values() if not x["sector"])
    print(k, v["model_versions"], "rows", n, "scored", sc, "no_sector", nosec, "shards", len(v["shards"]))
