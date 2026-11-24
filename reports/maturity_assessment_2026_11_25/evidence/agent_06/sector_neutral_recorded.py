"""Agent 06 cross review: recorded raw vs sector-neutral IC in result files of tests already run.  Reads only."""
import json
from pathlib import Path
base = Path(__file__).resolve().parents[4] / "reports" / "qsf"
for f in sorted(base.glob("*.json")):
    d = json.loads(f.read_text(encoding="utf-8"))
    hits = []
    def walk(x, p=""):
        if isinstance(x, dict):
            if "ic_sector_neutral" in x and x.get("ic") is not None:
                hits.append((p, x.get("ic"), x.get("ic_sector_neutral"), x.get("t"), x.get("dates")))
            for k, v in x.items():
                walk(v, f"{p}.{k}")
    walk(d)
    for p, ic, sn, t, n in hits:
        if any(s in p for s in ("|C|20", "|C|252", "|A|20", "|A|252", "primary")):
            print(f"{f.name:32s} {p[:40]:40s} ic {ic:+.4f} sector_neutral {sn if sn is None else round(sn,4)} t {t if t is None else round(t,2)} dates {n}")
