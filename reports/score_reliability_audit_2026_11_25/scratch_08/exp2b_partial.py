"""Agent 8, Q3b: sub-inputs missing INSIDE a factor (the factor then rests on what is left; the conservative score does not see it).
Read from the recorded raw values of 2026-11-24.  No returns.  Caveat: an EPS-growth figure that is None for a loss-maker is read
as 0 by the engine, not dropped; the ledger does not store that flag, so growth factors are reported apart."""
import sys, json
import numpy as np
sys.path.insert(0, '.'); sys.path.insert(0, 'reports/score_reliability_audit_2026_11_25/scratch_08')
from load import sessions, snaps
from rk import spearmanr, rankdata
SESSION = '2026-11-24'
SAFE = {"valuation", "business_quality", "free_cash_flow", "balance_dilution", "financial_resilience", "capital_allocation", "profitability", "balance_sheet", "insider_ownership", "atr_risk", "drawdown_gap", "downside_drawdown", "momentum_persistence", "long_trend"}
GROWTH = {"growth_quality", "earnings_revenue_quality", "cash_flow_quality"}
SKIP_KEYS = {"insider", "percentile", "benchmark", "breakout", "held_gap", "window_days", "cost_pct", "stop", "target"}
led, ss = sessions()
for market in ('US', 'KR'):
    sn = snaps(led, market, SESSION)
    for strat in ('SWING', 'LONG_TERM'):
        rows = [s for s in sn if s['strategy'] == strat and s.get('score') is not None and s.get('confidence') != 'INSUFFICIENT']
        n = len(rows); score = np.array([s['score'] for s in rows]); adj = []
        cnt = {}; detail = []
        for s in rows:
            tw = tc = 0.0; note = []
            for f in s['factors']:
                w = f.get('weight') or 0
                if not w: continue
                if f.get('status') == 'MISSING':
                    tw += w; tc += 0.5 * w; continue
                if f.get('normalized') is None: continue
                norm = f['normalized']; raw = f.get('raw') or {}
                if f['factor'] in SAFE and isinstance(raw, dict):
                    keys = [k for k in raw if k not in SKIP_KEYS]
                    miss = [k for k in keys if raw[k] is None]
                    if f['factor'] == 'insider_ownership':
                        keys = ['insider_pct', 'net']; miss = [k for k in ['insider_pct'] if raw.get('insider_pct') is None]
                    if miss and len(miss) < len(keys):
                        k = len(keys) - len(miss)
                        norm2 = (k * norm + 0.5 * len(miss)) / len(keys)
                        cnt[(f['factor'], tuple(miss))] = cnt.get((f['factor'], tuple(miss)), 0) + 1
                        note.append((f['factor'], miss, round(norm, 2), round(norm2, 2), w))
                        norm = norm2
                tw += w; tc += w * norm
            adj.append(100 * tc / tw); detail.append(note)
        adj = np.array(adj); lift = score - adj
        k = n // 5; top = set(np.argsort(-score)[:k]); top2 = set(np.argsort(-adj)[:k])
        print(f"\n=== {market} {strat} judged n={n}")
        print(f" stocks with at least one factor resting on part of its figures: {sum(1 for d in detail if d)} ({np.mean([bool(d) for d in detail])*100:.0f}%)")
        print(f" lift (score - score with absent figures and factors at 0.5): mean {lift.mean():+.2f}  sd {lift.std():.2f}  max {lift.max():+.2f}  min {lift.min():+.2f};  >=+2: {(lift>=2).sum()}  >=+4: {(lift>=4).sum()}  <=-2: {(lift<=-2).sum()}")
        print(f" top-fifth names replaced: {len(top-top2)} of {k};  spearman {spearmanr(score, adj)[0]:.4f};  mean lift top fifth {np.mean([lift[i] for i in top]):+.2f} vs rest {np.mean([lift[i] for i in range(n) if i not in top]):+.2f}")
        for line in (55, 70, 80):
            print(f"   at or over {line}: recorded {(score>=line).sum()}, with absent figures at 0.5: {(adj>=line).sum()}; crossing down {sum(1 for i in range(n) if score[i]>=line>adj[i])}, up {sum(1 for i in range(n) if adj[i]>=line>score[i])}")
        print(" most common absent figures:", sorted(((a[0], a[1], c) for a, c in cnt.items()), key=lambda x: -x[2])[:8])
        for i in np.argsort(-lift)[:4]:
            s = rows[i]
            print("   CASE", s['ticker'], f"score {score[i]:.1f} -> {adj[i]:.1f}  band {s.get('band')} held_back {s.get('band_held_back')} entry {s.get('entry_status')} conf {s.get('confidence')} cons {round(s.get('conservative_score') or 0,1)}", detail[i],
                  [(f['factor'], f['weight']) for f in s['factors'] if f.get('weight') and f.get('status') == 'MISSING'])
