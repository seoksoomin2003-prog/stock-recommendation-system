"""Read-only: show the decision fields of the three evaluated cards and run the '사도 돼?' rule (pure function) on them."""
import sys, json
sys.path.insert(0, '.')
from pathlib import Path
from terminal import assistant as A
from terminal.qsf import stance as qs
repo = Path('.').resolve()
ev = Path('reports/maturity_assessment_2026_11_25/evidence/agent_07')
for t in sys.argv[1:]:
    d = json.load(open(ev / 'big' / f'eval_{t}.json'))
    m = d['market']
    state = json.load(open(ev / 'big' / f'mstate_{m.lower()}.json'))
    print('=' * 20, t, m, 'held_strategy', d.get('held_strategy'), 'high_risk', d.get('high_risk'), 'risk_grade', json.dumps(d.get('risk_grade'), ensure_ascii=False)[:300])
    print('filing_events', json.dumps(d.get('filing_events'), ensure_ascii=False)[:400])
    print('committee_note', d.get('committee_note'))
    c = d.get('committee') or {}
    print('committee keys', list(c.keys()))
    print('committee', json.dumps({k: c.get(k) for k in ('decision', 'label', 'summary', 'headline', 'for', 'against', 'risks', 'strongest_for', 'strongest_against') if k in c}, ensure_ascii=False)[:1500])
    for s, card in d['cards'].items():
        if not isinstance(card, dict) or card.get('score') is None:
            print('--', s, 'no card', str(card)[:200]); continue
        print('--', s, round(card['score'], 1), card['band_label'], '| entry', card['entry_status'], '|', (card.get('entry') or {}).get('reason'), '| conf', card['confidence'], '| held', card.get('held'))
        print('   why_summary:', card.get('why_summary'))
        print('   surface_note:', card.get('surface_note'))
        print('   what_would_change:', card.get('what_would_change'))
        h = card.get('holding') or {}
        print('   holding:', json.dumps({k: h.get(k) for k in ('invalidation', 'checkpoints', 'scenarios', 'exit', 'thesis', 'monitor', 'review') if k in h}, ensure_ascii=False)[:1500])
        print('   holding keys:', list(h.keys()))
        print('   fund_period:', json.dumps(card.get('fund_period'), ensure_ascii=False))
        for part in (card.get('plain') or {}).get('parts', []):
            print('   [plain]', part['h'], '|', ' / '.join(part['lines'])[:700])
        gates = [g.get('text') or g.get('code') for g in card.get('gates') or []]
        v = A.buy_verdict(card, s, m, gates=gates, marks=[], earnings={}, soon=False, level=qs.level(repo, m), wide=set(), state=state, held=bool(card.get('held')))
        print('   VERDICT', v['label'], '|', v['why'], '| change:', v['change'], '| also:', v['also'], '| notes:', v['notes'])
