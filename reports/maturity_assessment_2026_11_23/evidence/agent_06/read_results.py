"""Agent 06.  Reads the RESULT files of tests already run (reports/qsf/*.json).  Computes nothing from prices or records."""
import json, sys
from pathlib import Path
base = Path(__file__).resolve().parents[4] / "reports" / "qsf"
KEYS = ("verdict", "status", "protocol", "window", "first", "last", "dates", "universe", "ran_at", "run_at", "created", "cost_round_trip_pct")
def walk(d, path="", depth=0, out=None):
    out = [] if out is None else out
    if isinstance(d, dict) and depth < 4:
        for k, v in d.items():
            p = f"{path}.{k}" if path else k
            if k in ("verdict", "reading", "passed", "supports_challenger") and not isinstance(v, (dict, list)):
                out.append((p, v))
            elif k in ("ic", "t", "spread_net", "buy_excess", "dates", "t_bar") and isinstance(v, (int, float)) and depth <= 3:
                out.append((p, round(v, 4)))
            elif isinstance(v, dict):
                walk(v, p, depth + 1, out)
    return out
for f in sorted(base.glob("*.json")):
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f.name, "UNREADABLE", type(exc).__name__); continue
    if not isinstance(d, dict):
        print(f.name, "(list)"); continue
    head = {k: d[k] for k in KEYS if k in d and not isinstance(d[k], (dict, list))}
    print(f"== {f.name} ({f.stat().st_size // 1024} KB) {head}")
    got = walk(d)
    for p, v in got[:int(sys.argv[1]) if len(sys.argv) > 1 else 14]:
        print("   ", p, "=", v)
