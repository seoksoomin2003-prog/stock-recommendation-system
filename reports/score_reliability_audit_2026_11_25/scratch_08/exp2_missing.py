"""Agent 8, Q3: can missing data lift a score / distort ranks?  Recorded session, factor values only, no returns."""
import sys, json
import numpy as np
sys.path.insert(0, '.'); sys.path.insert(0, 'reports/score_reliability_audit_2026_11_25/scratch_08')
from load import sessions, snaps
from rk import spearmanr, rankdata
SESSION = '2026-11-24'
led, ss = sessions()
for market in ('US', 'KR'):
    sn = snaps(led, market, SESSION)
    for strat in ('SWING', 'LONG_TERM'):
        rows = [s for s in sn if s['strategy'] == strat and s.get('score') is not None]
        score = np.array([s['score'] for s in rows])
        n = len(rows)
        # (a) whole-factor missing among scored factors
        miss_w, part, cons, neutral_all = [], [], [], []
        for s in rows:
            mw = 0; pw = 0; tw = tc = 0.0; tw2 = tc2 = 0.0
            for f in s['factors']:
                w = f.get('weight') or 0
                if not w: continue
                if f.get('status') == 'MISSING':
                    mw += w; tw2 += w; tc2 += 0.5 * w
                elif f.get('normalized') is not None and f.get('status') in ('REAL', 'STALE'):
                    tw += w; tc += w * f['normalized']; tw2 += w; tc2 += w * f['normalized']
                    inp = f.get('inputs') or {}
                    if inp.get('total') and inp['have'] < inp['total']:
                        pw += w
            miss_w.append(mw); part.append(pw); neutral_all.append(100 * tc2 / tw2 if tw2 else np.nan)
        miss_w, part, neutral_all = np.array(miss_w), np.array(part), np.array(neutral_all)
        lift = score - neutral_all
        k = max(1, n // 5)
        top = set(np.argsort(-score)[:k]); top2 = set(np.argsort(-neutral_all)[:k])
        print(f"\n=== {market} {strat} n={n}")
        print(f" stocks with a whole scored factor missing: {(miss_w>0).sum()} ({(miss_w>0).mean()*100:.0f}%); with a partly-filled factor: {(part>0).sum()} ({(part>0).mean()*100:.0f}%)")
        print(f" lift of score over 'missing read at 0.5': mean {np.nanmean(lift):+.2f}, max {np.nanmax(lift):+.2f}, min {np.nanmin(lift):+.2f}; lifted by >=2 points: {(lift>=2).sum()}, by >=5: {(lift>=5).sum()}; lowered by >=2: {(lift<=-2).sum()}")
        print(f" top fifth ({k}) changes if missing read at 0.5: {len(top-top2)} names; spearman {spearmanr(score, neutral_all)[0]:.4f}")
        print(f" share with missing factor: top fifth {np.mean([miss_w[i]>0 for i in top])*100:.0f}% vs rest {np.mean([miss_w[i]>0 for i in range(n) if i not in top])*100:.0f}%;  partial: top {np.mean([part[i]>0 for i in top])*100:.0f}% vs rest {np.mean([part[i]>0 for i in range(n) if i not in top])*100:.0f}%")
        # band crossings: 55 line (entry) and 70 line
        for line in (55, 70):
            up = [(rows[i]['ticker'], round(score[i], 1), round(neutral_all[i], 1), rows[i].get('band'), rows[i].get('entry_status'), rows[i].get('band_held_back')) for i in range(n) if score[i] >= line > neutral_all[i]]
            print(f" over {line} only because a factor is missing: {len(up)}", up[:8])
        worst = np.argsort(-lift)[:5]
        for i in worst:
            s = rows[i]
            print("  ", s['ticker'], f"score {score[i]:.1f} neutral {neutral_all[i]:.1f} conservative(rec) {s.get('conservative_score') and round(s['conservative_score'],1)} band {s.get('band')} entry {s.get('entry_status')} conf {s.get('confidence')} cov {round(s.get('coverage') or 0,2)} missing:",
                  [(f['factor'], f['weight']) for f in s['factors'] if f.get('weight') and f.get('status') == 'MISSING'],
                  "partial:", [(f['factor'], f['inputs']) for f in s['factors'] if f.get('weight') and f.get('inputs')])
        # (b) partial factors: which sub-inputs are absent?  rank position of partial stocks
        r = rankdata(score) / (n - 1)
        if (part > 0).sum() > 5:
            print(f" mean score percentile: partial-factor stocks {r[part>0].mean():.2f}, complete {r[part==0].mean():.2f};  missing-factor stocks {r[miss_w>0].mean() if (miss_w>0).any() else float('nan'):.2f}")
        cnt = {}
        for s in rows:
            for f in s['factors']:
                if f.get('weight') and f.get('inputs'):
                    cnt[f['factor']] = cnt.get(f['factor'], 0) + 1
        print(" partly-filled factors (count of stocks):", sorted(cnt.items(), key=lambda x: -x[1]))
