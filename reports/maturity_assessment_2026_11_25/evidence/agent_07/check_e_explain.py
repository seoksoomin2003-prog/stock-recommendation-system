"""Cross review, System Test E (explainability), read-only.  For one high, one middle and one low long-term score per market of the
2026-11-23 ledger: the assistant's WHY path (breakdown + _signal_line), plain.card_plain, holding.what_would_change and service._why
fed from the stored snapshot.  No provider call, no write.  The ledger keeps no factor explanation text and no entry reason, so _why
is fed the assistant's signal lines and a placeholder entry reason (said in the output)."""
import sys, json
sys.path.insert(0, '.')
from pathlib import Path
from terminal.qsf.ledger import Ledger
from terminal.qsf import holding, service
from terminal import assistant as A, plain

repo = Path('.').resolve()
led = Ledger(repo)
for market in ('US', 'KR'):
    row = [r for r in led._live_rows() if r["market"] == market][-1]
    snaps = [s for s in led._load(row) if s['strategy'] == 'LONG_TERM' and s.get('actionability') == 'ACTIONABLE' and s.get('score') is not None]
    snaps.sort(key=lambda s: -s['score'])
    picks = [snaps[0], snaps[len(snaps) // 2], snaps[-1]]
    for s in picks:
        print('=' * 100)
        print(market, s['ticker'], 'LONG_TERM', round(s['score'], 2), s['band'], s['entry_status'], 'conf', s['confidence'], 'cons', round(s['conservative_score'] or 0, 2), 'held_back', s['band_held_back'])
        parts = A.breakdown(s)
        if not parts:
            print('  breakdown: None (stored figures do not rebuild the score)')
            continue
        lost = sorted((r for r in parts['rows'] if r['lost'] >= 0.5), key=lambda r: -r['lost'])[:3]
        kept = sorted((r for r in parts['rows'] if r['kept'] >= 0.5 and all(r['factor'] != x['factor'] for x in lost)), key=lambda r: -r['kept'])[:3]
        print('  [WHY] lost (100-score =', round(100 - s['score'], 1), '):')
        for r in lost:
            print('    -', A._signal_line(r, s, market, f"{r['lost']:.1f}점 잃음")[:330])
        print('  [WHY] kept:')
        for r in kept:
            print('    +', A._signal_line(r, s, market, f"{r['kept']:.1f}점 얻음", scale=False)[:330])
        print('  [WHY] not counted:', [(f['factor'], f.get('status'), f.get('reason')) for f in parts['empty']])
        partial = [f['factor'] for f in s['factors'] if f.get('status') == 'PARTIAL']
        print('  partial factors:', partial)
        pos = sorted((r for r in parts['rows'] if r['normalized'] >= 0.6), key=lambda r: -(r['normalized'] - 0.5) * r['weight'])[:3]
        neg = sorted((r for r in parts['rows'] if r['normalized'] <= 0.4), key=lambda r: (r['normalized'] - 0.5) * r['weight'])[:3]
        res = {**s, 'missing': [f['factor'] for f in parts['empty']],
               'top_positive': [{'factor': r['factor'], 'text': A._signal_line(r, s, market, 'x', scale=False).split('(x)')[1][:120]} for r in pos],
               'top_negative': [{'factor': r['factor'], 'text': A._signal_line(r, s, market, 'x', scale=False).split('(x)')[1][:120]} for r in neg]}
        print('  [what_would_change]', holding.what_would_change(res))
        c = {**res, 'band_label': s['band'], 'entry': {'reason': '(기록에 진입 사유 없음)'}}
        try:
            print('  [_why]', service._why(c)[:400])
        except Exception as e:
            print('  [_why] error', type(e).__name__, e)
        p = plain.card_plain(s)
        for part in p['parts']:
            print('  [plain]', part['h'], '|', ' / '.join(part['lines'])[:400])
