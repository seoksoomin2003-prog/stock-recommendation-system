import sys, json, pathlib
repo = pathlib.Path.cwd(); sys.path.insert(0, str(repo))
from terminal.qsf.ledger import Ledger
led = Ledger(repo)
mk = sys.argv[1]
rows = [r for r in led._live_rows() if r["market"] == mk]
print({k: rows[-1][k] for k in rows[-1] if k in ("session","market","model_version","n","seq","rules_version")})
snaps = led._load(rows[-1])
print(type(snaps), len(snaps))
s = snaps[0] if isinstance(snaps, list) else list(snaps.values())[0]
def shape(o, d=0, k=""):
    if isinstance(o, dict):
        print("  "*d + k + " {")
        for kk, v in list(o.items())[:60]: shape(v, d+1, kk)
    elif isinstance(o, list):
        print("  "*d + k + f" [list {len(o)}]")
        if o and d < 6: shape(o[0], d+1, "[0]")
    else:
        print("  "*d + f"{k}: {str(o)[:110]}")
shape(s)
