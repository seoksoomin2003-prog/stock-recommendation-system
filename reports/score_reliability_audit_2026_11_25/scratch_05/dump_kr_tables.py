"""Agent 5: read-only dump of recorded Korean replay tables. No return is computed; values are read from result files."""
import json
def fmt(v, p=4):
    return "None" if v is None else f"{v:+.{p}f}"
def row(name, t):
    e, l = t.get("early") or {}, t.get("late") or {}
    print(f"{name:26s} dates {t.get('dates')} {t.get('first')}..{t.get('last')} n {t.get('mean_n') or 0:5.0f} IC {fmt(t.get('ic'))} t {fmt(t.get('t'),2)} pos {t.get('ic_positive_share') or 0:.2f} spr {fmt(t.get('spread_net'))} "
          f"buyex {fmt(t.get('buy_excess'))} bd {t.get('buy_dates')} top {fmt(t.get('top_fifth_excess'))} bot {fmt(t.get('bottom_fifth_excess'))} avg {fmt(t.get('average_return'))} mkt {fmt(t.get('market_return'))} | "
          f"early IC {fmt(e.get('ic'))} spr {fmt(e.get('spread_net'))} | late IC {fmt(l.get('ic'))} spr {fmt(l.get('spread_net'))}")
for f in ("QSF_KR_LIVE_REPLAY", "QSF_KR_UNIVERSE_TEST"):
    d = json.load(open(f"reports/qsf/{f}.json"))
    print("=====", f, d.get("first"), d.get("last"), "days", d.get("evaluation_days"), "cost", d.get("cost_round_trip"), "note", d.get("note"))
    for k, t in d["tables"].items():
        row(k, t)
    for k, t in d.get("reference_2022", {}).items():
        row("ref2022 " + k, t)
    for k, t in d["domains"].items():
        row("dom " + k, t)
    for s, m in d["money"].items():
        print("money", s, json.dumps(m, ensure_ascii=False))
    for s, p in d["primary"].items():
        print("primary", s, json.dumps({k: p[k] for k in ("horizon", "condition_a", "condition_b", "reading")}, ensure_ascii=False))
    if "universe" in d:
        print("universe", json.dumps(d["universe"], ensure_ascii=False))
        print("scored_share", d.get("scored_share"), "why", d.get("why_not_scored"))
    for k, m in d.get("top3", {}).items():
        print("top3", k, json.dumps({x: m.get(x) for x in ("days", "mean_excess", "early_excess", "late_excess", "percentile_vs_random", "reading")}, ensure_ascii=False))
d = json.load(open("reports/qsf/QSF_KR_LIVE_REPLAY_FIDELITY.json")); print("FIDELITY", json.dumps(d, ensure_ascii=False)[:1500])
d = json.load(open("reports/qsf/QSF_KR_LONG_EARLY.json"))
print("===== LONG_EARLY", {k: d[k] for k in ("first", "last", "days", "last_exit")})
row("primary", d["primary"]); print(" verdict", {k: v for k, v in d["primary"].items() if k in ("verdict", "checks", "reading", "condition_a", "condition_b")})
for k, t in (d.get("others") or {}).items():
    row("other " + k, t)
print("money", json.dumps(d.get("money"), ensure_ascii=False)[:1500])
for k, t in (d.get("domains") or {}).items():
    row("dom " + k, t)
d = json.load(open("reports/qsf/QSF_KR_TECH_EARLY.json"))
print("===== TECH_EARLY", json.dumps(d, ensure_ascii=False)[:3500])
