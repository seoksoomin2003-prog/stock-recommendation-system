"""Annual fundamentals for QSF, point-in-time by filing date.

US: SEC companyfacts 10-K.  KR: OpenDART annual statements, one basis only (consolidated, else separate; a company whose
years use different bases is flagged and growth is not computed across them).  Only the small extracted series is cached,
never the multi-megabyte source file.  This is display and scoring input for QSF; P6-11B keeps its own P6-20-A inputs.
"""
import re
from datetime import date, datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

# A newer annual report is due 12 months after the year-end plus the filing deadline (90 days for a Korean business report, 60 to 90
# for a 10-K).  Past that, with two weeks of grace, the figures are last year's and say so.  It was 540 days, which let a company
# whose newest year never arrived (CLX: 497 days) pass as current.
STALE_DAYS = 365 + 90 + 14
STOPPED_GAP_DAYS = 400   # a series ending this far before the company's newest year has stopped
YEAR_DAYS = (340, 400)   # two fiscal year-ends this far apart are consecutive years (52- and 53-week years included)

# Each list names the same accounting item; a period takes its first-listed tag.  Total revenue tags come before contract revenue,
# which leaves out rent, interest and insurance premiums.  Items with another meaning (pre-tax income for operating income) are not substitutes.
US_FLOW = {
    "revenue": ["Revenues", "RevenuesNetOfInterestExpense", "RegulatedAndUnregulatedOperatingRevenue", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet",
                "RevenueFromContractWithCustomerIncludingAssessedTax"],
    "gross_profit": ["GrossProfit"], "op_income": ["OperatingIncomeLoss"], "net_income": ["NetIncomeLoss", "NetIncomeLossAvailableToCommonStockholdersBasic", "ProfitLoss"],
    "ocf": ["NetCashProvidedByUsedInOperatingActivities", "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"],
    "capex": ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets", "PaymentsForCapitalImprovements"],
    "interest": ["InterestExpense", "InterestExpenseNonoperating", "InterestExpenseDebt", "InterestAndDebtExpense"],
    "buyback": ["PaymentsForRepurchaseOfCommonStock", "PaymentsForRepurchaseOfEquity"], "dividends": ["PaymentsOfDividendsCommonStock", "PaymentsOfDividends", "PaymentsOfOrdinaryDividends"],
    "shares_avg": ["WeightedAverageNumberOfDilutedSharesOutstanding"], "eps": ["EarningsPerShareDiluted"],
}
CONTRACT_REVENUE = ("RevenueFromContractWithCustomerExcludingAssessedTax", "RevenueFromContractWithCustomerIncludingAssessedTax")
US_INSTANT = {
    "equity": ["StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"], "assets": ["Assets"], "liabilities": ["Liabilities"],
    "current_assets": ["AssetsCurrent"], "current_liabilities": ["LiabilitiesCurrent"],
    "cash": ["CashAndCashEquivalentsAtCarryingValue", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"],
    # Debt: the company's own total when it tags one, otherwise three parts: long-term debt, the part of it due within a year, and
    # short-term borrowings.  Filers tag the parts differently and some tags already hold another part (LONG_HOLDS_CURRENT,
    # SHORT_HOLDS_BORROWINGS), so the alias decides what is added.
    "debt_total": ["DebtLongtermAndShorttermCombinedAmount", "DebtAndCapitalLeaseObligations"],
    # Convertible notes come last: for a company that tags no other long-term debt they are its long-term debt (several software and
    # device companies), and total liabilities, mostly deferred revenue there, would be far from it.
    "debt_long": ["LongTermDebtNoncurrent", "LongTermDebt", "LongTermDebtAndCapitalLeaseObligations", "LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities",
                  "ConvertibleLongTermNotesPayable", "ConvertibleDebtNoncurrent"],
    "debt_short": ["LongTermDebtCurrent", "LongTermDebtAndCapitalLeaseObligationsCurrent", "DebtCurrent", "ConvertibleNotesPayableCurrent", "ConvertibleDebtCurrent"],
    "debt_borrow": ["ShortTermBorrowings", "CommercialPaper"],
}
# Checked on the newest 10-K of every scanned company (2026-11-11): LongTermDebt equals its noncurrent and current parts together in 119
# of 136 companies that tag all three, so the current part is not added to it again.
LONG_HOLDS_CURRENT = {"LongTermDebt", "LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities"}
SHORT_HOLDS_BORROWINGS = {"DebtCurrent"}                                                          # all debt due within a year


MULTI_CLASS_GAP = 1.2       # market value / (price x shares)
MULTI_CLASS_SEC_GAP = 0.85  # Yahoo shares / SEC average shares
SHARE_SCALE_GAP = 100.0     # some filers enter shares in millions or thousands; no real change between two counts is this large
SHARE_BASIS_BREAK = 1.4     # two share counts this far apart are not one basis: a split, a bonus issue, a consolidation or an issue as large
PRICE_BASIS_GAP = 1.4       # today's close this far from the price stored with a share count: a split since (3:2 and larger), or a count a week stale after a crash
RESTATED = 0.03             # a figure a later report shows again within this is not restated
RESTATED_MATCH = 0.10       # a split restates the share count and EPS by the same factor; EPS is rounded, so the two agree within this


def _days(a: str, b: str) -> int:
    return (datetime.strptime(b, "%Y-%m-%d") - datetime.strptime(a, "%Y-%m-%d")).days


def extract_us(facts: Dict[str, Any]) -> Dict[str, List[Dict]]:
    """{metric: [{end, val, filed}]} from 10-K filings; aliases merge by period, first-listed concept wins per period."""
    gaap = (facts.get("facts") or {}).get("us-gaap") or {}
    out: Dict[str, List[Dict]] = {}

    def collect(metric, concepts, flow):
        got: Dict[str, Dict] = {}
        for name in concepts:
            units = (gaap.get(name) or {}).get("units") or {}
            for unit, rows in units.items():
                if unit not in ("USD", "shares", "USD/shares"):
                    continue
                for r in rows:
                    if r.get("form") not in ("10-K", "10-K/A") or r.get("val") is None or not r.get("end") or not r.get("filed"):
                        continue
                    if flow and not (r.get("start") and 340 <= _days(r["start"], r["end"]) <= 385):
                        continue
                    rec = {"end": r["end"], "val": float(r["val"]), "filed": r["filed"]}
                    # Every vintage is kept: the point-in-time reader picks what was on file at the time.
                    got.setdefault(f"{r['end']}|{r['filed']}", {**rec, "alias": name})
        out[metric] = sorted(got.values(), key=lambda x: (x["end"], x["filed"]))
    for m, c in US_FLOW.items():
        collect(m, c, True)
    for m, c in US_INSTANT.items():
        collect(m, c, False)
    return out


PRICE_CURRENCY_KR = "KRW"
EPS_PART_REPEAT = 0.02      # a "discontinued" EPS within this of the continuing one is the same figure tagged twice, not a second part


def kr_basic_eps(concepts: Dict[str, Dict]) -> Dict[str, Any]:
    """Total basic EPS of one statement: the total line when there is one, else continuing plus discontinued operations.
    Filers with a discontinued business often report only the two parts (measured on 5,976 statements: the parts add up to the
    total in 192 of 199 that report all three).  A discontinued line that repeats the continuing figure is not added."""
    total, cont, disc = (concepts.get(k) or {} for k in ("eps_basic", "eps_basic_continuing", "eps_basic_discontinued"))
    if total.get("status") == "REAL" or cont.get("status") != "REAL":
        return total
    value = float(cont["value"])
    part = float(disc["value"]) if disc.get("status") == "REAL" else None       # no discontinued line: the continuing figure is the total
    if part and abs(part - value) > EPS_PART_REPEAT * abs(value):
        value += part
    return {**cont, "value": value}


PARENT_OF = {"net_income": "net_income_all", "equity": "equity_all"}      # the parent's series and the whole group's
SAME_FIGURE = 0.001


def _real(row: Optional[Dict]) -> bool:
    return bool(row) and row.get("status") == "REAL"


def _no_outside_holders(concepts: Dict[str, Dict]) -> bool:
    """The whole is the parent's in this statement: no parent line (a separate statement, or a group without outside holders),
    or parent lines equal to the totals.  One parent line that differs from its total means outside holders exist."""
    for parent, total in (("net_income_parent", "net_income"), ("equity_parent", "total_equity")):
        p, t = concepts.get(parent), concepts.get(total)
        if _real(p) and _real(t) and abs(float(p["value"]) - float(t["value"])) > SAME_FIGURE * abs(float(t["value"])):
            return False
    return True


def extract_kr(statements: Dict[int, Dict[str, Dict]]) -> Dict[str, Any]:
    """``statements``: {year: {concept: extract_concepts row}}.  One basis across years or growth stops at the change.

    Profit and equity are the parent's.  A year whose statement has no parent line takes the total when that statement shows no
    outside holders: separate statements never have the line, so a company that moved between consolidated and separate reports
    used to lose profit and equity for every year on its current basis (131970, 010580, 033790)."""
    names = {"revenue": "revenue", "op_income": "operating_income", "net_income": "net_income_parent", "net_income_all": "net_income",
             "equity": "equity_parent", "equity_all": "total_equity", "assets": "total_assets", "liabilities": "total_liabilities",
             "current_assets": "current_assets", "current_liabilities": "current_liabilities", "cash": "cash_and_equivalents",
             "ocf": "operating_cash_flow", "capex": "capex", "eps": "eps_basic", "dividends": "dividends_paid"}
    out: Dict[str, Any] = {k: [] for k in names}
    bases = set()
    has_parent_line = {k: False for k in PARENT_OF}
    for year in sorted(statements):
        whole_is_parents = _no_outside_holders(statements[year])
        for metric, concept in names.items():
            r = kr_basic_eps(statements[year]) if metric == "eps" else statements[year].get(concept) or {}
            if metric in PARENT_OF:
                has_parent_line[metric] = has_parent_line[metric] or _real(r)
                if not _real(r) and whole_is_parents:
                    r = statements[year].get(names[PARENT_OF[metric]]) or {}
            if r.get("status") == "REAL":
                val = abs(float(r["value"])) if metric == "capex" else float(r["value"])    # filers differ on the sign of an outflow
                row = {"end": r["period_end"], "val": val, "filed": r["receipt_date"], "basis": r["basis"]}
                if r.get("currency") not in (None, "", PRICE_CURRENCY_KR):
                    row["currency"] = r["currency"]          # a few groups file in dollars; the price is in won
                out[metric].append(row)
                bases.add(r["basis"])
    for metric, whole in PARENT_OF.items():
        if not has_parent_line[metric]:       # no parent line in any year: the whole stands in and is not kept a second time
            out[metric] = out.pop(whole, [])
    out["_bases"] = sorted(bases)
    return out


def _vintage(rows: List[Dict], as_of: str) -> List[Dict]:
    """Latest vintage filed by ``as_of`` for each period, oldest period first."""
    per: Dict[str, Dict] = {}
    for r in rows:
        if r["filed"] <= as_of:
            cur = per.get(r["end"])
            if cur is None or r["filed"] >= cur["filed"]:
                per[r["end"]] = r
    return [per[k] for k in sorted(per)]


def drop_stale_series(annual: Dict[str, List[Dict]], max_gap_days: int = STOPPED_GAP_DAYS) -> Dict[str, List[Dict]]:
    """A series that stopped well before the company's newest year is empty, not current.
    Short-term debt stopping alone means long-term debt is the figure.  Long-term debt stopping leaves no debt figure,
    so every part goes and the fallback to total liabilities applies."""
    ends = [r["end"] for rows in annual.values() if isinstance(rows, list) for r in rows]
    if not ends:
        return annual
    newest = max(ends)
    gone = {k for k, rows in annual.items() if isinstance(rows, list) and rows and _days(max(r["end"] for r in rows), newest) > max_gap_days}
    if "debt_long" in gone:
        gone |= {"debt_short", "debt_borrow"}
    return {k: ([] if k in gone else v) for k, v in annual.items()}


# Listed as non-financial, with a financial business in the group's cash flow.  No standard account marks them, so this is a list.
# Look again when annual reports arrive.  Measured in reports/QSF_KR_CONSOLIDATION_CHECK_2026_11_07.md.
FINANCE_MIXED = {"005380": "금융 자회사의 채권 증감이 연결 영업현금에 섞여 현금흐름을 평가하지 않습니다",
                 "000880": "보험·금융 자회사의 현금이 연결 영업현금에 섞여 현금흐름을 평가하지 않습니다"}


def _scale_differs(a: Optional[float], b: Optional[float]) -> bool:
    """Two counts of the same company's shares that cannot both be in whole shares."""
    if not a or not b or a < 0 or b < 0:
        return False
    return max(a, b) / min(a, b) >= SHARE_SCALE_GAP


def _restated_factor(eps_rows: List[Dict], share_rows: List[Dict], old_filed: str, new_filed: str) -> Optional[float]:
    """Shares on the basis of the report filed ``new_filed`` per share on the basis of the one filed ``old_filed``.

    A split restates every period a later report shows again, so a period both reports show gives the factor: its share count
    multiplied and its EPS divided by the same number.  1.0 when nothing was restated.  None when no chain of reports links the two
    or the only link is a restatement the two series do not confirm together (profit restated, or a count in another unit)."""
    if old_filed == new_filed:
        return 1.0
    eps: Dict[str, Dict[str, float]] = {}
    sh: Dict[str, Dict[str, float]] = {}
    for src, dst in ((eps_rows, eps), (share_rows, sh)):
        for r in src:
            dst.setdefault(r["filed"], {})[r["end"]] = r["val"]
    filings = sorted(set(eps) | set(sh))

    def step(first: str, second: str):
        """Factor from the earlier report to the later one; False when they share no period, None when it cannot be trusted."""
        fs = fe = None
        both = set(sh.get(first, {})) & set(sh.get(second, {}))
        if both:
            a, b = sh[first][max(both)], sh[second][max(both)]
            if a > 0 and b > 0 and not _scale_differs(a, b):
                fs = b / a
        both_eps = set(eps.get(first, {})) & set(eps.get(second, {}))
        if both_eps:
            a, b = eps[first][max(both_eps)], eps[second][max(both_eps)]
            if a * b > 0:
                fe = a / b
        if not both and not both_eps:
            return False
        if fs is not None and fe is not None:
            if abs(fs / fe - 1) > RESTATED_MATCH:
                return None                         # the count and EPS moved differently: not a split the figures confirm
            return fs if abs(fs - 1) > RESTATED else 1.0
        one = fs if fs is not None else fe
        return 1.0 if one is not None and abs(one - 1) <= RESTATED else None

    seen, queue = {old_filed: 1.0}, [old_filed]
    while queue:
        cur = queue.pop(0)
        for nxt in filings:
            if nxt in seen:
                continue
            f = step(min(cur, nxt), max(cur, nxt))
            if not f:
                continue
            seen[nxt] = seen[cur] * (f if cur < nxt else 1 / f)
            if nxt == new_filed:
                return seen[nxt]
            queue.append(nxt)
    return None


def metrics(annual: Dict[str, Any], close: Optional[float], as_of: str, *, is_financial: bool = False, shares: Optional[float] = None,
            source: str = "SEC EDGAR 10-K", insider_pct: Optional[float] = None, count_unknown: bool = False) -> Dict[str, Any]:
    """One fiscal year per figure: every level and flow is the latest fiscal year's or None, a ratio needs both ends in the same
    year, and growth needs the year exactly one (or n) before.  A series that stopped gives no figure, never an older year's."""
    known = {k: [r for r in v if r["filed"] <= as_of] for k, v in annual.items() if isinstance(v, list) and not k.startswith("_")}
    series = {k: _vintage(v, as_of) for k, v in known.items()}
    # One basis only: a company that began consolidating uses the years on its latest basis, and growth stops at the change.
    tagged = [r for s in series.values() for r in s if r.get("basis")]
    latest_basis = max(tagged, key=lambda r: (r["end"], r["filed"]))["basis"] if tagged else None
    basis_changed = bool(latest_basis) and any(r["basis"] != latest_basis for r in tagged)
    if latest_basis:
        series = {k: [r for r in s if r.get("basis", latest_basis) == latest_basis] for k, s in series.items()}
        known = {k: [r for r in s if r.get("basis", latest_basis) == latest_basis] for k, s in known.items()}
    # One currency only, the newest statement's: a row says so only when it is not the price's currency.  Growth stops at a change, and
    # nothing in another currency is set against the price or the market value.
    rows = [r for s in series.values() for r in s]
    currency = max(rows, key=lambda r: (r["end"], r["filed"])).get("currency") if rows else None
    if any(r.get("currency") != currency for r in rows):
        series = {k: [r for r in s if r.get("currency") == currency] for k, s in series.items()}
        known = {k: [r for r in s if r.get("currency") == currency] for k, s in known.items()}

    if not series.get("net_income") and not series.get("revenue"):
        return {"status": "UNAVAILABLE", "reason": "재무 수치를 찾지 못했습니다."}
    latest = max((s[-1]["end"] for s in series.values() if s), default=None)
    filed = max((s[-1]["filed"] for s in series.values() if s and s[-1]["end"] == latest), default=None)

    def at(k, end=latest):
        """The value of the fiscal year ending ``end``; None when the series has no such year."""
        return next((r["val"] for r in reversed(series.get(k) or []) if r["end"] == end), None) if end else None

    def year_back(k, n=1):
        """End of the fiscal year ``n`` years before the latest in this series, or None when that year is not there."""
        lo, hi = YEAR_DAYS[0] + 365 * (n - 1), YEAR_DAYS[1] + 365 * (n - 1)
        near = [r["end"] for r in series.get(k) or [] if lo <= _days(r["end"], latest) <= hi]
        return min(near, key=lambda e: abs(_days(e, latest) - 365 * n)) if near else None

    def recent(k, years=5):
        """Rows of the latest ``years`` fiscal years, only when the series reaches the latest year."""
        if at(k) is None:
            return []
        return [r for r in series[k] if _days(r["end"], latest) <= 365 * (years - 1) + YEAR_DAYS[1] - 365]

    # Contract revenue leaves out rent, interest and insurance premiums.  It is the fallback tag, and for most companies it is all of
    # revenue; where it is below the same year's own profit it can only be a part (a bank's fees, a landlord's service income), and a
    # part gives no revenue, margin or revenue growth.
    revenue_note = None
    newest = next((r for r in reversed(series.get("revenue") or []) if r["end"] == latest), None)
    profits = [v for v in (at("net_income"), at("op_income")) if v is not None]
    if newest and newest.get("alias") in CONTRACT_REVENUE and profits and max(profits) > newest["val"]:
        series["revenue"] = [r for r in series["revenue"] if r.get("alias") not in CONTRACT_REVENUE]
        revenue_note = "계약 매출 항목이 그해 이익보다 작아 총매출이 아닙니다. 매출·마진·매출 성장률을 계산하지 않습니다."
    rev, ni, eq, assets = at("revenue"), at("net_income"), at("equity"), at("assets")

    def div(a, b):
        return a / b if a is not None and b not in (None, 0) else None

    def growth(k, back=1):
        a, b = at(k), at(k, year_back(k, back))
        return (a / b - 1) if a is not None and b is not None and b > 0 else None

    def cagr(k, n=3):
        a, b = at(k), at(k, year_back(k, n))
        return (a / b) ** (1 / n) - 1 if a is not None and b is not None and a > 0 and b > 0 else None

    def eps_count(end):
        """The share count behind the reported EPS of one year: the reported average count, else profit / EPS (Korea reports no count)."""
        n, e, avg = at("net_income", end), at("eps", end), at("shares_avg", end)
        implied = n / e if n and e and n * e > 0 and abs(e) >= 0.1 else None
        return avg if avg and avg > 0 and not _scale_differs(avg, implied) else implied

    def eps_basis(old, new):
        """Shares on the newer EPS figure's basis per share on the older one's, or None when the two cannot be compared.
        Same report: one basis.  Otherwise what later reports restated (US filings show three years).  Without such a link
        (Korea: one report per year) the counts behind the EPS of the two years and of every year between them must be within
        SHARE_BASIS_BREAK of each other; a larger jump gives no figure, because a split and a large share issue look the same
        in these numbers.  Years without a count are not checked: with fewer than two counts the reported figures stand."""
        factor = _restated_factor(known.get("eps") or [], known.get("shares_avg") or [], old["filed"], new["filed"])
        if factor is not None:
            return factor if abs(factor - 1) > RESTATED else 1.0
        counts = [c for c in (eps_count(r["end"]) for r in series["eps"] if old["end"] <= r["end"] <= new["end"]) if c and c > 0]
        return None if counts and max(counts) / min(counts) >= SHARE_BASIS_BREAK else 1.0

    def eps_pair(n):
        rows = {r["end"]: r for r in series.get("eps") or []}
        new, old = rows.get(latest), rows.get(year_back("eps", n))
        factor = eps_basis(old, new) if new and old else None
        return (new["val"], old["val"] / factor) if factor else (None, None)

    def eps_growth(n=1):
        a, b = eps_pair(n)
        if a is None or b is None or b <= 0:
            return None
        return a / b - 1 if n == 1 else ((a / b) ** (1 / n) - 1 if a > 0 else None)

    # Net income and equity are the parent's; liabilities, assets and cash flow are the whole group.  With outside holders in the subsidiaries
    # the group's figures meet the group's equity and profit, and the market value, which is the parent's, meets the parent's share of cash.
    group_equity, parent_share = None, None
    same = at("equity_all")
    if eq is not None and same and 0 < eq <= same:
        group_equity, parent_share = same, eq / same

    ocf, capex = at("ocf"), at("capex")
    ocf_ni = div(ocf, ni) if (ni or 0) > 0 else None
    group_ni = at("net_income_all")
    if group_equity and ocf is not None and group_ni is not None:
        ocf_ni = ocf / group_ni if group_ni > 0 else None
    burn_ni = group_ni if group_equity and ocf is not None and group_ni is not None else ni          # the profit the cash figure above was set against
    # Cash flow of one year less spending of another is no figure at all: a company whose capex tag stopped has no free cash flow.
    fcf = ocf - capex if ocf is not None and capex is not None else None
    by_end = {r["end"]: r["val"] for r in series.get("capex") or []} if fcf is not None else {}
    fcfs = [r["val"] - by_end[r["end"]] > 0 for r in recent("ocf") if r["end"] in by_end]
    nis = [r["val"] > 0 for r in recent("net_income")]
    # Debt is the company's own total, or the parts of the latest year.  Filers leave a zero untagged, so a part that was exactly 0 a
    # year earlier and is not in the latest report is still 0.  Long-term debt that stopped at an amount leaves no figure from the
    # parts (the others alone would understate it) and total liabilities apply; short-term debt that stopped leaves long-term debt.
    def debt_part(k):
        v = at(k)
        return 0.0 if v is None and at(k, year_back(k)) == 0 else v

    def alias_at(k):
        return next((r.get("alias") for r in reversed(series.get(k) or []) if r["end"] == latest), None)

    debt, debt_long, debt_short, debt_borrow = None, debt_part("debt_long"), debt_part("debt_short"), debt_part("debt_borrow")
    if alias_at("debt_long") in LONG_HOLDS_CURRENT:
        debt_short = None                                   # already inside the long-term figure
    if debt_short is not None and alias_at("debt_short") in SHORT_HOLDS_BORROWINGS:
        debt_borrow = None                                  # already inside the current figure
    long_stopped = bool(series.get("debt_long")) and debt_long is None
    # Commercial paper is issued by companies with term debt somewhere: alone it is not the company's debt (two REITs showed nothing else).
    paper_only = debt_long is None and debt_short is None and alias_at("debt_borrow") == "CommercialPaper"
    have_parts = not long_stopped and not paper_only and any(x is not None for x in (debt_long, debt_short, debt_borrow))
    parts = (debt_long or 0.0) + (debt_short or 0.0) + (debt_borrow or 0.0) if have_parts else None
    own_total = at("debt_total")
    # The total tag is misused by a few filers (a credit line's balance, or zero, next to billions of notes): a total below its own
    # long-term part is not a total, and a zero stands only when the parts say zero too.
    # Without any borrowings figure, total liabilities stand in.  They are an upper bound, not the debt: leaving the figure empty was
    # tried and read worse, because companies with heavy debt under tags of their own (a lender arm, a REIT) then lost the penalty
    # they deserve (2026-11-11 dry run: +8 to +9 points).  ``debt_basis`` says which of the three the figure is.  Korean statements
    # here carry no borrowings account, so every Korean company is read on total liabilities.
    debt_basis = None
    if own_total is not None and own_total >= (debt_long or 0.0) * (1 - RESTATED) and (own_total > 0 or parts == 0):
        debt, debt_basis = own_total, "OWN_TOTAL"
    elif parts is not None:
        debt, debt_basis = parts, "PARTS"
    elif at("liabilities") is not None:
        debt, debt_basis = at("liabilities"), "TOTAL_LIABILITIES"
    sec_shares, eps_reported = at("shares_avg"), at("eps")
    # Net income / EPS is the company's own share count in whole shares, so it tells a wrong scale from a real change.
    implied = abs(ni / eps_reported) if ni and eps_reported and abs(eps_reported) >= 0.1 else None
    sec_scale_error = _scale_differs(sec_shares, implied)
    change_scale_error = _scale_differs(sec_shares, at("shares_avg", year_back("shares_avg")))
    # ``count_unknown``: the price is on another basis than every count at hand (a split the provider's record has not caught up
    # with).  No count is used, the reported one included: it is from before the split too.  No market value, no PER.
    shares_used = None if count_unknown else shares or (None if sec_scale_error else sec_shares)
    mcap = close * shares_used if close and shares_used else None
    # Price over reported EPS is wrong when the EPS is on another share count than the price: after a split (BKNG 0.99 for 24.7) or
    # when the newest report has no EPS and an older one would be read.  Reported EPS is kept while the count behind it is within
    # SHARE_BASIS_BREAK of today's count: it is exact about share classes, preferred dividends and treasury shares, which a market
    # value built from one listed class is not.  Otherwise PER is market value over the parent's profit, and EPS that profit per
    # current share.  Without a current count nothing can be checked and the reported EPS is all there is.
    count = eps_count(latest)
    on_todays_basis = eps_reported is not None and bool(count) and bool(shares_used) and 1 / SHARE_BASIS_BREAK < shares_used / count < SHARE_BASIS_BREAK
    if count_unknown:
        pe, eps, pe_basis = None, None, "COUNT_UNKNOWN"
    elif mcap is None or on_todays_basis:
        pe, eps, pe_basis = div(close, eps_reported), eps_reported, "REPORTED_EPS"
    else:
        pe, eps, pe_basis = div(mcap, ni), div(ni, shares_used), "MARKET_VALUE"

    bb, dv = at("buyback"), at("dividends")
    prev = year_back("net_income")
    roe_prev = div(at("net_income", prev), at("equity", prev)) if (at("equity", prev) or 0) > 0 else None
    out = {
        "status": "STALE" if latest and _days(latest, as_of) > STALE_DAYS else "REAL", "source": source, "fiscal_end": latest, "filed": filed,
        "is_financial": is_financial, "basis": latest_basis, "basis_changed": basis_changed, "basis_conflict": False,
        # QSF-1.5.0: what the growth and cash-conversion figures cannot say when there is no profit to measure them by.  The figures
        # themselves stay None (they are not computed); the factors read these marks and score 0 instead of leaving the figure out.
        "loss_now": bool(ni is not None and ni <= 0), "cash_burn": bool(not is_financial and burn_ni is not None and burn_ni <= 0 and ocf is not None and ocf <= 0),
        "roe": div(ni, eq) if (eq or 0) > 0 else None, "roe_prev": roe_prev, "op_margin": div(at("op_income"), rev), "gross_margin": div(at("gross_profit"), rev),
        "net_margin": div(ni, rev), "rev_growth": growth("revenue"), "eps_growth": eps_growth(), "rev_cagr3": cagr("revenue"), "eps_cagr3": eps_growth(3),
        "debt_basis": debt_basis, "ocf_to_ni": None if is_financial else ocf_ni, "fcf": fcf, "fcf_margin": div(fcf, rev), "fcf_years_positive": sum(fcfs) / len(fcfs) if fcfs else None,
        "roe_years_positive": sum(nis) / len(nis) if nis else None, "debt_equity": 99.0 if (eq is not None and eq <= 0 and debt) else div(debt, group_equity or eq), "current_ratio": div(at("current_assets"), at("current_liabilities")),
        "interest_cover": div(at("op_income"), at("interest")), "cash_debt": div(at("cash"), debt), "equity_assets": div(group_equity or eq, assets),
        "share_change": None if change_scale_error else growth("shares_avg"), "share_scale_error": sec_scale_error or change_scale_error, "returns_capital": (bool((bb or 0) > 0 or (dv or 0) != 0) if (bb is not None or dv is not None) else None),
        "market_cap": mcap, "eps": eps, "eps_reported": eps_reported, "pe": pe, "pe_basis": pe_basis if pe is not None else None, "pb": div(mcap, eq) if (eq or 0) > 0 else None, "fcf_yield": div(fcf * parent_share if fcf is not None and parent_share else fcf, mcap), "parent_share": parent_share, "insider_pct": insider_pct,
    }
    if revenue_note:
        out["revenue_note"] = revenue_note
    if currency:
        out.update({k: None for k in ("pe", "pe_basis", "pb", "fcf_yield", "eps")}, currency=currency,
                   currency_note=f"재무제표가 {currency} 기준이라 원화 주가와 비교하는 PER·PBR·FCF 수익률·주당순이익을 계산하지 않습니다.")
    return out


def blank_mixed_cash_flow(m: Dict[str, Any], code: str) -> Dict[str, Any]:
    """No figure rather than a wrong one.  Other figures stay: reading the company as financial would change more than the error."""
    note = FINANCE_MIXED.get(code)
    if not note or m.get("status") == "UNAVAILABLE":
        return m
    return {**m, "fcf": None, "fcf_yield": None, "fcf_margin": None, "fcf_years_positive": None, "ocf_to_ni": None, "cash_flow_note": note}


_NAME_FILLER = {"INC", "CORP", "CORPORATION", "COMPANY", "CO", "THE", "AND", "HOLDINGS", "GROUP", "PLC", "LTD", "LIMITED", "INCORPORATED", "CLASS", "COMMON", "STOCK", "NEW"}


def _name_words(name: Optional[str]) -> set:
    return {w for w in re.sub(r"[^A-Za-z0-9 ]", " ", name or "").upper().split() if len(w) > 1 and w not in _NAME_FILLER}


def us_display_name(long_name: Optional[str], short_name: Optional[str], sec_name: Optional[str]) -> Optional[str]:
    """Yahoo's long name, unless it names another company: when it shares no word with either Yahoo's short name or the name SEC
    holds for the CIK the statements come from, and those two agree with each other, the short name is shown instead."""
    long_w, short_w, sec_w = _name_words(long_name), _name_words(short_name), _name_words(sec_name)
    if long_name and short_w and sec_w and (short_w & sec_w) and not (long_w & short_w) and not (long_w & sec_w):
        return short_name
    return long_name or sec_name


def price_basis_moved(info: Dict[str, Any], close: Optional[float]) -> bool:
    """Whether today's close and the price stored with Yahoo's share count are too far apart to be one basis.  False when the
    record carries no price of its own: nothing can be checked, as before."""
    own = info.get("currentPrice") or info.get("regularMarketPrice")
    if not own or not close or own <= 0 or close <= 0:
        return False
    return not (1 / PRICE_BASIS_GAP < close / own < PRICE_BASIS_GAP)


def us_total_shares(info: Dict[str, Any], close: Optional[float], annual: Optional[Dict[str, Any]] = None) -> Optional[float]:
    """Yahoo's share count covers only the listed class of a company with several, while its market value covers all of them.  The
    implied total is used only when market value is well above price x shares and SEC does not contradict it: SEC's average count must
    also exceed Yahoo's.  A price from another moment can open such a gap by itself, so without Yahoo's own price SEC must confirm it."""
    y, cap = info.get("sharesOutstanding"), info.get("marketCap")
    own = info.get("currentPrice") or info.get("regularMarketPrice")
    price = own or close
    if not y or not cap or not price or cap / (price * y) < MULTI_CLASS_GAP:
        return y
    rows = (annual or {}).get("shares_avg") or []
    sec = rows[-1].get("val") if rows else None
    if _scale_differs(sec, y):
        sec = None
    if sec and y / sec < MULTI_CLASS_SEC_GAP or (not sec and own):
        return cap / price
    return y


# SEC SIC codes whose balance sheet is the business itself, so debt ratios, current ratio, margins and free cash flow say nothing and
# the capital ratio is read instead.  Left out since QSF-1.1.9 (they were 6000-6797 before): 6200 exchanges, 6324 health plans,
# 6411 insurance brokers, 65xx real estate, 67xx royalty and holding codes other than 6799.  They have ordinary borrowings, classified
# balance sheets and operating margins.  6282 (asset managers) stays in: half of those in the S&P 500 carry an insurer's or their
# funds' liabilities (AMP, APO, KKR, ARES) and the code cannot tell them from the others.  6798 REITs were already out.
FINANCIAL_SIC = ((6000, 6199),      # banks, savings institutions, card and consumer lenders
                 (6210, 6229),      # security and commodity brokers and dealers
                 (6282, 6282),      # investment advice
                 (6300, 6323), (6325, 6399),      # insurance carriers: life, accident and health, property and casualty, surety, title
                 (6799, 6799))      # investors not elsewhere classified, as before


def is_financial_sic(sic: Any) -> bool:
    """True for the SIC codes in ``FINANCIAL_SIC``."""
    try:
        s = int(sic)
    except (TypeError, ValueError):
        return False
    return any(lo <= s <= hi for lo, hi in FINANCIAL_SIC)


KR_FINANCIAL_CLASSES = ("BANK", "INSURANCE", "SECURITIES_AND_FINANCIAL_SERVICES")
KR_MIXED_CLASS = "HOLDING_OR_OTHER_FINANCIAL"


def is_financial_kr(industry_class: Optional[str], annual: Optional[Dict[str, Any]]) -> bool:
    """Banks, insurers and securities firms use the financial rule.  KIND's "기타 금융업" mixes holding companies of industrial
    groups (SK, LG, GS, CJ, LS, HD Hyundai) with financial groups, card and capital companies, so the statements decide: a
    financial institution lists its balance sheet by liquidity, an industrial holding company splits current from non-current.
    A holding company with current assets and current liabilities in its statements is scored as a non-financial company.
    Any other class that is not NON_FINANCIAL stays financial, as before."""
    if not industry_class or industry_class == "NON_FINANCIAL":
        return False
    if industry_class != KR_MIXED_CLASS:
        return True
    a = annual or {}
    return not (a.get("current_assets") and a.get("current_liabilities"))


def last_business_year(as_of: date, fiscal_month: int = 12) -> int:
    """The newest business year that has ended by ``as_of``; DART names a business year by the calendar year it ends in.
    A December company's is last year.  A June company's is this year from July on (030960 was read a year late)."""
    end_of_month = date(as_of.year + (fiscal_month == 12), fiscal_month % 12 + 1, 1) - timedelta(days=1)
    return as_of.year if as_of > end_of_month else as_of.year - 1


def fiscal_month_of(text: Any) -> int:
    """'06월' or 6 -> 6; anything unreadable is December, the month of all but a few companies."""
    digits = "".join(ch for ch in str(text or "") if ch.isdigit())
    return int(digits) if digits and 1 <= int(digits) <= 12 else 12


def load_kr_statements(corp_code: str, code: str, industry_class: str, as_of: date, client: Any,
                       extract: Optional[Callable] = None, fiscal_month: int = 12) -> Dict[int, Dict[str, Dict]]:
    """Last four business years of annual statements, chosen per year as CFS then OFS and never mixed within a year."""
    from markets.kr import dart
    out = {}
    last = last_business_year(as_of, fiscal_month)
    for year in range(last - 3, last + 1):
        fetched = {fs: client.statements(corp_code, year, "11011", fs) for fs in ("CFS", "OFS")}
        chosen = dart.choose_basis(fetched)
        if not chosen.get("rows"):
            continue
        obs = dart.normalize_statements(chosen["rows"], corp_code=corp_code, ticker=code, year=year, reprt_code="11011", fs_div=chosen["fs_div"], fiscal_month=fiscal_month)
        out[year] = (extract or dart.extract_concepts)(obs, industry_class)
    return out
