"""Korean statement lines the live score does not read, and the score they would give (side record FI-1).
Rules: reports/QSF_KR_FULLER_INPUTS_2026_11_25.md.

The live Korean reader takes revenue, operating income, profit, equity, assets, liabilities, cash, cash flow, capital spending,
earnings per share and dividends.  It has no line for gross profit, interest or the buying of own shares, so gross margin,
interest cover and "returns capital by buybacks" are empty for every Korean stock (third assessment, 2026-11-25).  The user's
decision of the same day: the live Korean score stays as it is (its only past evidence was measured with this reading, and the
score is frozen at QSF-1.6.0); the score with the three lines read is recorded beside it.

What is read, by XBRL account id only, from the same annual statements as the live figures:
- gross profit: ``ifrs-full_GrossProfit`` (income statement);
- interest: cash interest paid, ``ifrs-full_InterestPaidClassifiedAsOperatingActivities`` and, where a company files it there,
  ``...ClassifiedAsFinancingActivities`` (cash-flow statement).  Finance costs are not used: they hold currency and valuation losses;
- own shares bought: ``dart_AcquisitionOfTreasuryShares`` or ``ifrs-full_PurchaseOfTreasuryShares`` (cash-flow statement).
The average share count is not in these statements and stays unread.

Nothing here feeds the live score, a band, an entry status or the order plan.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np

VERSION = "FI-1"
PROTOCOL = "reports/QSF_KR_FULLER_INPUTS_2026_11_25.md"
# series name the metrics read -> (statements, account ids in order, add the ids' values together)
LINES = {
    "gross_profit": (("IS", "CIS"), ("ifrs-full_GrossProfit",), False),
    "interest": (("CF",), ("ifrs-full_InterestPaidClassifiedAsOperatingActivities", "ifrs-full_InterestPaidClassifiedAsFinancingActivities"), True),
    "buyback": (("CF",), ("dart_AcquisitionOfTreasuryShares", "ifrs-full_PurchaseOfTreasuryShares"), False),
}
LINE_KO = {"gross_profit": "매출총이익", "interest": "이자 지급액", "buyback": "자기주식 취득"}
NO_GROSS = ("BANK", "INSURANCE", "SECURITIES_AND_FINANCIAL_SERVICES")       # a gross margin has no meaning there, as in the live reader's revenue
KEY = "krside1"


def read_year(observations: List[Dict[str, Any]], industry_class: str) -> Dict[str, Dict[str, Any]]:
    """One (filing, basis): {series: {"value", "period_end", "receipt_date", "basis"}} for the lines found.  A line whose rows
    disagree within one statement is left out: unknown, never a guess."""
    out: Dict[str, Dict[str, Any]] = {}
    for name, (statements, ids, add) in LINES.items():
        if name == "gross_profit" and industry_class in NO_GROSS:
            continue
        got = []
        for aid in ids:
            rows = [o for o in observations if o.get("account_id") == aid and o.get("statement") in statements and o.get("amount_type") == "FY"
                    and o.get("value") is not None and np.isfinite(o["value"])]
            if not rows:
                continue
            first = min(rows, key=lambda o: statements.index(o["statement"]))["statement"]
            vals = {o["value"] for o in rows if o["statement"] == first}
            if len(vals) != 1:
                got = None                      # the same account twice with two values
                break
            got.append(next(o for o in rows if o["statement"] == first))
            if not add:
                break
        if not got:
            continue
        o = got[0]
        out[name] = {"value": abs(sum(float(x["value"]) for x in got)), "period_end": o.get("period_end"), "receipt_date": o.get("receipt_date"), "basis": o.get("basis")}
    return out


def extractor(base_extract, keep: Dict[int, Dict[str, Dict[str, Any]]]):
    """``fundamentals.load_kr_statements``'s ``extract``: the live concepts unchanged, and this module's lines of the same
    observations put aside in ``keep`` by fiscal year (the year is read from the rows)."""
    def run(observations, industry_class):
        try:
            year = next((int(o["fiscal_year"]) for o in observations if o.get("fiscal_year")), None)
            if year is not None:
                keep[year] = read_year(observations, industry_class)
        except Exception:                       # the side reading never costs the live one
            pass
        return base_extract(observations, industry_class)
    return run


def series(keep: Dict[int, Dict[str, Dict[str, Any]]], bases: Optional[List[str]] = None) -> Dict[str, List[Dict[str, Any]]]:
    """The rows the metrics read, oldest first, for the lines found in any year.  A row on another basis than the live figures'
    (consolidated beside separate) is left out, as the live reader never mixes the two."""
    out: Dict[str, List[Dict[str, Any]]] = {}
    for year in sorted(keep):
        for name, r in keep[year].items():
            if bases and r.get("basis") not in bases:
                continue
            if r.get("period_end") and r.get("receipt_date"):
                out.setdefault(name, []).append({"end": r["period_end"], "val": r["value"], "filed": r["receipt_date"], "basis": r.get("basis")})
    return out


def merged(annual: Dict[str, Any], side: Optional[Dict[str, List[Dict[str, Any]]]]) -> Optional[Dict[str, Any]]:
    """The live series with the side lines added, or None when there is nothing to add.  A line the live reader already has
    (never, today) is not replaced."""
    add = {k: v for k, v in (side or {}).items() if k in LINES and v and not annual.get(k)}
    return {**annual, **add} if add else None


def card_field(score: Optional[float], live_score: Optional[float], added: List[str]) -> Dict[str, Any]:
    """What a card and its record keep: the score with the lines read, beside the live one."""
    return {"version": VERSION, "score": None if score is None else round(float(score), 3), "live_score": None if live_score is None else round(float(live_score), 3),
            "added": sorted(added), "added_ko": [LINE_KO[a] for a in sorted(added)]}
