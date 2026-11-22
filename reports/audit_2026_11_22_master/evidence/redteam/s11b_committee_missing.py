from common import *
sys.path.insert(0, REPO + "/tests")
import committee_cases as cc
from terminal.committee import investors as iv, council
def one(key, **over):
    f = cc.figures(**over); o = iv.ENGINES[key](f, False, None)
    return o
def show(key, label, present, absent):
    a, b = one(key, **present), one(key, **absent)
    print(f"{key:8s} {label}\n     present: {a['recommendation']:12s} score {a['score']} conf {a['confidence']} cov {a['coverage']}\n     absent : {b['recommendation']:12s} score {b['score']} conf {b['confidence']} cov {b['coverage']}")
    return a, b
print("== a single weak figure present vs absent (None), everything else the base stock ==")
show("MUNGER", "one loss year on file (profit_years 0.75) vs no profit history at all", dict(profit_years=0.75), dict(profit_years=None))
show("MUNGER", "debt/equity 2.5 + negative FCF + cash conversion 0.4 vs all three absent", dict(debt_equity=1.9, fcf_margin=-0.02, ocf_to_ni=0.4, share_change=0.06), dict(fcf_margin=None, ocf_to_ni=None, share_change=None))
cheap = dict(pe=8.0, pb=0.9, trailing_pe=8.0, fcf_yield=0.09)
show("GRAHAM", "cheap stock, weak balance sheet (current 0.9, D/E 1.9, cash/debt 0.05) vs the three figures absent", dict(cheap, current_ratio=0.9, debt_equity=1.9, cash_debt=0.05), dict(cheap, current_ratio=None, debt_equity=None, cash_debt=None))
show("GRAHAM", "cheap stock, value-trap signs (FCF margin -5%, cash conversion 0.3) vs both absent", dict(cheap, fcf_margin=-0.05, ocf_to_ni=0.3), dict(cheap, fcf_margin=None, ocf_to_ni=None))
show("LYNCH", "debt/equity 2.4 and cash conversion 0.4 vs both absent", dict(debt_equity=2.4, ocf_to_ni=0.4), dict(debt_equity=None, ocf_to_ni=None))
show("BUFFETT", "weak balance sheet (D/E 1.9, cash/debt 0.05, cover 2.0) vs the three absent", dict(debt_equity=1.9, cash_debt=0.05, interest_cover=2.0), dict(cash_debt=None, interest_cover=None, debt_equity=0.4) | dict())
show("DRUCKENMILLER", "falling earnings (EPS -20%, sales -5%, forward PE above trailing) vs absent", dict(eps_growth=-0.2, rev_growth=-0.05, forward_pe=21.0, trailing_pe=18.0), dict(eps_growth=None, rev_growth=None, forward_pe=None, trailing_pe=None))
print("\n== committee: the same stock with the weak facts present vs absent ==")
weak = dict(pe=8.0, pb=0.9, trailing_pe=8.0, forward_pe=7.5, fcf_yield=0.09, current_ratio=0.9, debt_equity=2.4, cash_debt=0.05, fcf_margin=-0.03, ocf_to_ni=0.3, profit_years=0.75, eps_growth=-0.25, rev_growth=-0.03)
gone = {k: None for k in ("current_ratio", "debt_equity", "cash_debt", "fcf_margin", "ocf_to_ni", "profit_years", "eps_growth", "rev_growth")}
for tag, over in (("weak facts present", weak), ("weak facts absent ", dict(weak, **gone))):
    f = cc.figures(**over); ops = iv.evaluate(f); d = council.decide(f, ops)
    print(f"   {tag}: " + " ".join(f"{o['investor'][:3]}={o['recommendation']}" for o in ops) + f" | committee {d['decision']} confidence {d['scores']['confidence']} attractiveness {d['scores']['attractiveness']} data {d['scores']['data']} risks {[r['name'] for r in d['material_risks']]}")
