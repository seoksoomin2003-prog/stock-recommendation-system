"""Agent 06: the recorded score-band tables (descriptive, pooled over dates) of tests already run.  Reads only."""
import json
from pathlib import Path
base = Path(__file__).resolve().parents[4] / "reports" / "qsf"
for name in ("QSF_PIT_VALIDATION.json", "QSF_CORRECTED_OPEN.json"):
    d = json.loads((base / name).read_text(encoding="utf-8"))
    for key, tab in d["buckets"].items():
        if not any(s in key for s in ("SWING|C|20", "LONG_TERM|C|252", "SWING|A|20", "LONG_TERM|A|252")): continue
        print(name, key)
        for band, v in tab.items():
            print("   ", band, {a: (round(b, 4) if isinstance(b, float) else b) for a, b in v.items() if a in ("n", "mean_vs_average", "beat_average_rate", "mean_vs_bench_net")})
