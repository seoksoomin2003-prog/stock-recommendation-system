"""Agent 06: spot-check recorded figures and list which risk/robustness metrics the result files record at all (key names only)."""
import json, re
from pathlib import Path
base = Path(__file__).resolve().parents[4] / "reports" / "qsf"
def load(n): return json.loads((base / n).read_text(encoding="utf-8"))
u = load("QSF_KR_UNIVERSE_TEST.json")["primary"]["LONG_TERM"]; print("KR_UNIVERSE LONG ic t reading", round(u["ic"],4), round(u["t"],3), u["reading"])
o = load("QSF_CORRECTED_OOS.json"); p = o.get("primary") or {}
for k, v in (p.items() if isinstance(p, dict) else []):
    if isinstance(v, dict): print("CORRECTED_OOS", k, {x: (round(v[x],4) if isinstance(v.get(x), float) else v.get(x)) for x in ("dates","first","last","ic","t","verdict") if x in v})
print("CORRECTED_OOS top keys", list(o)[:20])
pk = load("QSF_PICKS_SIMULATION.json"); print("PICKS keys", list(pk)); print("PICKS power", json.dumps(pk.get("power"))[:600])
pat = re.compile(r"sharpe|sortino|drawdown|turnover|bootstrap|decile|quintile|sensitiv|deflated|monoton|calmar|vol", re.I)
for f in sorted(base.glob("*.json")):
    keys = set()
    def walk(d, depth=0):
        if depth > 6: return
        if isinstance(d, dict):
            for k, v in d.items():
                if pat.search(str(k)): keys.add(str(k))
                walk(v, depth + 1)
        elif isinstance(d, list):
            for x in d[:3]: walk(x, depth + 1)
    walk(json.loads(f.read_text(encoding="utf-8")))
    if keys: print(f.name, sorted(keys)[:12])
