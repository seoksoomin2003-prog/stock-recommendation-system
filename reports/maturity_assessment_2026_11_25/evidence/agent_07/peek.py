import sys, json
sys.path.insert(0, '.')
from pathlib import Path
from terminal.qsf.ledger import Ledger
repo = Path('.').resolve()
led = Ledger(repo)
rows = [r for r in led._live_rows() if r["market"] == sys.argv[1]]
print(rows[-1])
snaps = led._load(rows[-1])
print(type(snaps), len(snaps))
s = snaps[0]
print(sorted(s.keys()))
print(json.dumps({k: s[k] for k in s if k not in ('factors',)}, ensure_ascii=False, default=str)[:2500])
print(json.dumps(s['factors'][0], ensure_ascii=False, default=str)[:800])
