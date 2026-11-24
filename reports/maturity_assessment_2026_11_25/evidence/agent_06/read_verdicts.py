"""Agent 06 (2026-11-25).  Reads verdict fields of RESULT files of tests already run.  Computes nothing from prices or records."""
import json
from pathlib import Path
base = Path(__file__).resolve().parents[4] / "reports" / "qsf"
def walk(d, path="", depth=0, out=None):
    out = [] if out is None else out
    if isinstance(d, dict) and depth < 5:
        for k, v in d.items():
            p = f"{path}.{k}" if path else k
            if k in ("verdict", "reading", "passed", "outcome", "decision") and isinstance(v, (str, bool)):
                out.append((p, v))
            elif isinstance(v, dict):
                walk(v, p, depth + 1, out)
    return out
n = 0
for f in sorted(base.glob("*.json")):
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f.name, "UNREADABLE", type(exc).__name__); continue
    n += 1
    got = walk(d) if isinstance(d, dict) else []
    vs = sorted({str(v) for p, v in got if p.split(".")[-1] in ("verdict", "reading", "outcome", "decision")})
    ps = [v for p, v in got if p.endswith("passed")]
    print(f"{f.name}: verdicts={vs[:8]} passed_true={sum(1 for v in ps if v is True)}/{len(ps)} mtime={f.stat().st_mtime:.0f}")
print("files", n)
