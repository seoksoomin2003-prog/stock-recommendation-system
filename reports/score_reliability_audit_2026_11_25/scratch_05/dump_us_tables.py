"""Agent 5: read-only dump of recorded US validation tables. No return is computed; values are read from result files."""
import json, sys
FILES = ["QSF_1_2_VALIDATION", "QSF_PIT_VALIDATION", "QSF_OPEN_VALIDATION", "QSF_CORRECTED_OPEN_RUN1", "QSF_CORRECTED_OPEN", "QSF_OOS_TEST", "QSF_CORRECTED_OOS"]
NAMES = ["A", "B", "C", "TECHNICAL", "FUNDAMENTAL", "RISK", "mom_12_1"]
def fmt(v, p=4):
    return "None" if v is None else f"{v:+.{p}f}"
for f in FILES:
    d = json.load(open(f"reports/qsf/{f}.json"))
    tabs = d.get("tables") or (d.get("strict") or {}).get("tables") or {}
    print("=====", f, "| cost", d.get("cost_round_trip"), "| evals", d.get("evaluations"), "| note", d.get("note"), "| model", d.get("model"))
    for strat, hs in (("SWING", (5, 10, 20, 30)), ("LONG_TERM", (63, 126, 252))):
        for h in hs:
            for n in NAMES:
                t = tabs.get(f"{strat}|{n}|{h}")
                if not t or not t.get("dates"):
                    continue
                e, l = t.get("early") or {}, t.get("late") or {}
                print(f"{strat[:5]:5s} {n:11s} h{h:<3d} dates {t['dates']:3d} {t.get('first')}..{t.get('last')} n {t.get('mean_n',0):5.0f} IC {fmt(t['ic'])} t {fmt(t.get('t'),2)} pos {t.get('ic_positive_share',0):.2f} "
                      f"ICsn {fmt(t.get('ic_sector_neutral'))} spr {fmt(t.get('spread_net'))} buyex {fmt(t.get('buy_excess'))} bd {t.get('buy_dates')} | early IC {fmt(e.get('ic'))} spr {fmt(e.get('spread_net'))} | late IC {fmt(l.get('ic'))} spr {fmt(l.get('spread_net'))}")
