"""Read-only: the '사도 돼?' rule on TECH's recorded 2026-11-23 snapshots (what the assistant reads until the next record)."""
import sys, json
sys.path.insert(0, '.')
from pathlib import Path
from terminal.qsf.ledger import Ledger
from terminal import assistant as A
from terminal.qsf import stance as qs
repo = Path('.').resolve()
led = Ledger(repo)
row = [r for r in led._live_rows() if r["market"] == "US"][-1]
state = json.load(open('reports/maturity_assessment_2026_11_25/evidence/agent_07/big/mstate_us.json'))
for s in led._load(row):
    if s['ticker'] in ('TECH', 'BIIB'):
        v = A.buy_verdict(s, s['strategy'], 'US', gates=[g.get('text') for g in s.get('gates') or []], marks=[], earnings={}, soon=False,
                          level=qs.level(repo, 'US'), wide=set(), state=state, held=False)
        print(s['ticker'], s['strategy'], round(s['score'], 1), s['band'], s['entry_status'], 'deal_pin' in s, s.get('deal_pin'), '->', v['label'], '|', v['why'], '|', v['change'])
