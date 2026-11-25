"""Read-only loader of ledger snapshots (no outcomes). Agent 8."""
import sys, json, pickle, os
from pathlib import Path
sys.path.insert(0, '.')
from terminal.qsf.ledger import Ledger
from terminal.qsf import order_plan

def sessions():
    led = Ledger(Path('.'))
    rows = led._live_rows()
    out = {}
    for r in rows:
        out.setdefault(r['market'], set()).add(r['session'])
    return led, {m: sorted(s) for m, s in out.items()}

def snaps(led, market, session):
    return order_plan.session_snaps(led, market, session)

if __name__ == '__main__':
    led, ss = sessions()
    for m, s in ss.items():
        print(m, len(s), s)
    rows = led._live_rows()
    print(rows[-1].keys() if rows else None)
    sn = snaps(led, 'US', ss['US'][-1])
    print(len(sn)); s = sn[0]
    print({k: (v if not isinstance(v, (list, dict)) else type(v).__name__) for k, v in s.items()})
    print(json.dumps(s['factors'][:2], ensure_ascii=False)[:1200])
