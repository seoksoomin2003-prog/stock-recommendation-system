"""Agent 5: arithmetic on the RECORDED BT-1 accounts (reports/qsf/QSF_BACKTEST_CURRENT_{US,KR}.json).  No price is read.
band - index = (all scored before cost - index) - cost of the band + (band before cost - all scored before cost).
Mean cost per period = round-trip cost x mean turnover (exact for TOP_FIFTH and ALL_SCORED: backtest_current.py:199-200;
approximate for BUY_BAND when the band was empty on some days, since an empty day counts turnover 1.0 and pays nothing)."""
import json
for m in ("US", "KR"):
    d = json.load(open(f"reports/qsf/QSF_BACKTEST_CURRENT_{m}.json"))
    c = d["cost_round_trip_pct"]
    for s, sv in d["strategies"].items():
        a = sv["accounts"]["accounts"]
        allx, allc = a["ALL_SCORED"]["excess_per_period_pct"], c * a["ALL_SCORED"]["mean_turnover"]
        uni = allx + allc
        print(f"== {m} {s}  periods {a['INDEX']['periods']}  cost {c:.3f}%  index CAGR {a['INDEX']['cagr_pct']:.2f} vol {a['INDEX']['vol_pct']:.2f} sharpe {a['INDEX']['sharpe']:.2f} mdd {a['INDEX']['max_drawdown_pct']:.1f}")
        print(f"   ALL_SCORED: CAGR {a['ALL_SCORED']['cagr_pct']:.2f} vol {a['ALL_SCORED']['vol_pct']:.2f} sharpe {a['ALL_SCORED']['sharpe']:.2f} mdd {a['ALL_SCORED']['max_drawdown_pct']:.1f} excess/period {allx:+.3f}% (t {a['ALL_SCORED']['excess_t']:+.2f}) turnover {a['ALL_SCORED']['mean_turnover']:.3f} -> universe before cost {uni:+.3f}%/period")
        for k in ("TOP_FIFTH", "BUY_BAND"):
            x = a[k]
            cost = c * x["mean_turnover"]
            sel = x["excess_per_period_pct"] + cost - uni
            print(f"   {k}: CAGR {x['cagr_pct']:.2f} vol {x['vol_pct']:.2f} sharpe {x['sharpe']:.2f} sortino {x['sortino']:.2f} mdd {x['max_drawdown_pct']:.1f} names {x['mean_names']:.1f} turnover {x['mean_turnover']:.3f} "
                  f"beat {x['beat_index_share']:.2f} excess/period {x['excess_per_period_pct']:+.3f}% (t {x['excess_t']:+.2f}; early {x['excess_early_pct']:+.3f} late {x['excess_late_pct']:+.3f})")
            print(f"      split per period: universe {uni:+.3f}  cost {-cost:+.3f}  selection {sel:+.3f}  | x12 a year: universe {uni*12:+.2f}  cost {-cost*12:+.2f}  selection {sel*12:+.2f}  total {x['excess_per_period_pct']*12:+.2f}")
            print(f"      vs ALL_SCORED (same universe, both after own cost): {x['excess_per_period_pct']-allx:+.3f}%/period, CAGR diff {x['cagr_pct']-a['ALL_SCORED']['cagr_pct']:+.2f}pp, sharpe diff {x['sharpe']-a['ALL_SCORED']['sharpe']:+.2f}; CAGR vs index {x['cagr_pct']-a['INDEX']['cagr_pct']:+.2f}pp")
            yrs = x["by_year"]
            print(f"      years beating index: {sum(1 for v in yrs.values() if v > 0)}/{len(yrs)}  worst year {min(yrs, key=yrs.get)} {min(yrs.values()):+.1f}pp best {max(yrs, key=yrs.get)} {max(yrs.values()):+.1f}pp")
        for h, hv in sv["horizons"].items():
            f = hv["fifths"]
            print(f"   h{h}: fifths net {[round(v*100,2) for v in f['fifth_net']]} index {f['index']*100:.2f} top-bottom {f['top_minus_bottom']*100:+.2f} top-index {f['top_minus_index']*100:+.2f} monotone {f['monotone']} band-index {None if f['band']['minus_index'] is None else round(f['band']['minus_index']*100,2)} (names {f['band']['mean_names']:.1f}, dates {f['band']['dates']}, +share {f['band']['positive_share']:.2f})")
