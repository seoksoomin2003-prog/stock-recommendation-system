"""Agent 5: arithmetic on RECORDED BT-1 account figures for errata items 4 and 5.  No price is read.
Item 4 (backtest_current.py:168-169): recorded downside deviation = sqrt(sum(down^2)/n_down); the usual one divides by N.
  usual Sortino = recorded * sqrt(N / n_down), n_down/N ~= 1 - positive_share (exact unless a period return is exactly 0:
  not usable for a band account that sat in cash, i.e. Korean swing BUY_BAND).
Item 5 (backtest_current.py:30): a year is counted as 252 sessions in Korea too.  With S sessions a year the growth is the
  same and the years are periods*21/S."""
import json, math
KR_SESSIONS = 245          # assumption: about 245 KRX sessions a year (2019-2026); stated in the report
for m in ("US", "KR"):
    d = json.load(open(f"reports/qsf/QSF_BACKTEST_CURRENT_{m}.json"))
    for s, sv in d["strategies"].items():
        for k, x in sv["accounts"]["accounts"].items():
            f = math.sqrt(1 / (1 - x["positive_share"]))
            line = f"{m} {s:9s} {k:10s} sharpe {x['sharpe']:.2f} sortino recorded {x['sortino']:.2f} -> usual ~{x['sortino']*f:.2f}  turnover a year {x.get('mean_turnover', 0)*12:.2f}x  CAGR {x['cagr_pct']:.2f}"
            if m == "KR":
                yrs252, yrsS = x["periods"] * 21 / 252, x["periods"] * 21 / KR_SESSIONS
                cagr = ((1 + x["cagr_pct"] / 100) ** (yrs252 / yrsS) - 1) * 100
                line += f" -> with {KR_SESSIONS} sessions a year {cagr:.2f}; vol {x['vol_pct']:.2f} -> {x['vol_pct']*math.sqrt(KR_SESSIONS/252):.2f}; sharpe -> {x['sharpe']*math.sqrt(KR_SESSIONS/252):.2f}"
            print(line)
