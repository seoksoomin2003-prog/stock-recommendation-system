"""Agent 8, Q4/Q5: what the top fifth looks like on the recorded session (no returns): sector, financials, valuation raw values,
volatility, distance from the 52-week high, 12-1 month return already made, deal pins."""
import sys, json
import numpy as np
sys.path.insert(0, '.'); sys.path.insert(0, 'reports/score_reliability_audit_2026_11_25/scratch_08')
from load import sessions, snaps
from rk import spearmanr, rankdata
SESSION = '2026-11-24'
led, ss = sessions()
us_sec = {k: v.get('gics_sector') for k, v in json.load(open('data/sp500_universe_cache.json'))['constituents'].items()}
def raw(s, factor, key):
    for f in s['factors']:
        if f['factor'] == factor and isinstance(f.get('raw'), dict):
            return f['raw'].get(key)
def med(x):
    x = [v for v in x if v is not None and np.isfinite(v)]
    return float(np.median(x)) if x else float('nan')
for market in ('US', 'KR'):
    sn = snaps(led, market, SESSION)
    by = {}
    for s in sn: by.setdefault(s['ticker'], {})[s['strategy']] = s
    for strat in ('SWING', 'LONG_TERM'):
        rows = [s for s in sn if s['strategy'] == strat and s.get('score') is not None and s.get('confidence') != 'INSUFFICIENT']
        n = len(rows); score = np.array([s['score'] for s in rows]); k = n // 5
        order = np.argsort(-score); top = [rows[i] for i in order[:k]]; bot = [rows[i] for i in order[-k:]]; rest = [rows[i] for i in order[k:]]
        def fin(s):
            lt = by[s['ticker']].get('LONG_TERM') or s
            return any(f['factor'] in ('leverage', 'free_cash_flow', 'cash_flow_quality') and f.get('status') == 'NOT_APPLICABLE' for f in lt['factors'] + s['factors'])
        def get(s, factor, key):
            for st in ('SWING', 'LONG_TERM'):
                c = by[s['ticker']].get(st)
                if c:
                    v = raw(c, factor, key)
                    if v is not None: return v
        print(f"\n=== {market} {strat} judged n={n} top fifth {k}")
        rowsdef = [("financial company share", lambda g: np.mean([fin(s) for s in g])),
                   ("median PER (valuation raw)", lambda g: med([get(s, 'valuation', 'pe') for s in g])),
                   ("median PBR", lambda g: med([get(s, 'valuation', 'pb') for s in g])),
                   ("median FCF yield", lambda g: med([get(s, 'valuation', 'fcf_yield') for s in g])),
                   ("median ROE", lambda g: med([get(s, 'business_quality', 'roe') for s in g])),
                   ("median hist vol", lambda g: med([get(s, 'atr_risk', 'hist_vol') for s in g])),
                   ("median dist from 52w high", lambda g: med([get(s, 'breakout_volume', 'dist_high') for s in g])),
                   ("median 12-1m return", lambda g: med([get(s, 'momentum_persistence', 'ret_12_1') for s in g])),
                   ("median 6m rel. strength pct", lambda g: med([get(s, 'relative_strength', 'percentile') for s in g])),
                   ("median max drawdown 252", lambda g: med([get(s, 'drawdown_gap', 'max_drawdown_252') for s in g])),
                   ("median ADV", lambda g: med([get(s, 'liquidity', 'adv_value') for s in g])),
                   ("deal pinned", lambda g: sum(1 for s in g if s.get('deal_pin'))),
                   ]
        for name, fn in rowsdef:
            print(f"  {name:30s} top {fn(top):12.3f}   rest {fn(rest):12.3f}   bottom {fn(bot):12.3f}")
        # rank correlations of score with already-made return and with volatility
        def col(factor, key): return np.array([get(s, factor, key) if get(s, factor, key) is not None else np.nan for s in rows], float)
        for nm, (fa, ke) in {"12-1m return made": ('momentum_persistence', 'ret_12_1'), "6m RS percentile": ('relative_strength', 'percentile'), "dist from high": ('breakout_volume', 'dist_high'),
                             "hist vol": ('atr_risk', 'hist_vol'), "PER": ('valuation', 'pe'), "PBR": ('valuation', 'pb'), "ROE": ('business_quality', 'roe')}.items():
            x = col(fa, ke); m = np.isfinite(x)
            if m.sum() > 30: print(f"  spearman(score, {nm}) = {spearmanr(score[m], x[m])[0]:+.2f} (n {m.sum()})")
        if market == 'US':
            def secs(g):
                d = {}
                for s in g: d[us_sec.get(s['ticker'], '?')] = d.get(us_sec.get(s['ticker'], '?'), 0) + 1
                return d
            a, b = secs(top), secs(rows)
            print("  sector: top-fifth share / universe share / lift")
            for sec in sorted(b, key=lambda x: -(a.get(x, 0) / k) / (b[x] / n)):
                print(f"    {sec:26s} {a.get(sec,0)/k*100:5.1f}%  {b[sec]/n*100:5.1f}%  x{(a.get(sec,0)/k)/(b[sec]/n):.2f}")
            sc = {}
            for s in rows: sc.setdefault(us_sec.get(s['ticker'], '?'), []).append(s['score'])
            gm = score.mean(); between = sum(len(v) * (np.mean(v) - gm) ** 2 for v in sc.values()) / (n * score.var())
            print(f"  share of score variance explained by sector means: {between*100:.1f}%")
    # swing vs long score on the same stocks
    both = [(by[t]['SWING']['score'], by[t]['LONG_TERM']['score']) for t in by if 'SWING' in by[t] and 'LONG_TERM' in by[t] and by[t]['SWING'].get('score') is not None and by[t]['LONG_TERM'].get('score') is not None]
    a = np.array(both); print(f"\n{market}: spearman(swing score, long score) = {spearmanr(a[:,0], a[:,1])[0]:+.2f} n {len(a)}")
