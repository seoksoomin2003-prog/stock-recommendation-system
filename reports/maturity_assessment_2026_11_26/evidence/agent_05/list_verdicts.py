"""Reads recorded result files only: prints every key named verdict/reading/decision (no computation)."""
import json, sys
from pathlib import Path
KEYS = ("verdict", "reading", "decision", "supports", "conclusion", "status", "result")
def walk(o, path, out, depth=0):
    if depth > 4: return
    if isinstance(o, dict):
        for k, v in o.items():
            if isinstance(v, (str, bool)) and any(x in k.lower() for x in KEYS) and len(str(v)) < 90:
                out.append((path + "." + k, v))
            elif isinstance(v, (dict,)):
                walk(v, path + "." + k, out, depth + 1)
for p in sorted(Path("reports/qsf").glob("*.json")):
    try: d = json.loads(p.read_text())
    except Exception as e: print(p.name, "UNREADABLE"); continue
    out = []; walk(d, "", out)
    print("==", p.name, p.stat().st_size)
    for k, v in out[:25]: print("   ", k, "=", v)
