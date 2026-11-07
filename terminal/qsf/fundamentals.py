"""Annual fundamentals for QSF, point-in-time by filing date.

US: SEC companyfacts 10-K.  KR: OpenDART annual statements, one basis only (consolidated, else separate; a company whose
years use different bases is flagged and growth is not computed across them).  Only the small extracted series is cached,
never the multi-megabyte source file.  This is display and scoring input for QSF; P6-11B keeps its own P6-20-A inputs.
"""
from datetime import date, datetime
from typing import Any, Callable, Dict, List, Optional

STALE_DAYS = 540     # a fiscal year-end older than 18 months is STALE
STOPPED_GAP_DAYS = 400   # a series ending this far before the company's newest year has stopped

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
US_INSTANT = {
    "equity": ["StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"], "assets": ["Assets"], "liabilities": ["Liabilities"],
    "current_assets": ["AssetsCurrent"], "current_liabilities": ["LiabilitiesCurrent"],
    "cash": ["CashAndCashEquivalentsAtCarryingValue", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"],
    "debt_long": ["LongTermDebtNoncurrent", "LongTermDebt", "LongTermDebtAndCapitalLeaseObligations"],
    "debt_short": ["LongTermDebtCurrent", "ShortTermBorrowings", "LongTermDebtAndCapitalLeaseObligationsCurrent", "DebtCurrent"],
}


MULTI_CLASS_GAP = 1.2       # market value / (price x shares)
MULTI_CLASS_SEC_GAP = 0.85  # Yahoo shares / SEC average shares


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


def extract_kr(statements: Dict[int, Dict[str, Dict]]) -> Dict[str, Any]:
    """``statements``: {year: {concept: extract_concepts row}}.  One basis across years or growth stops at the change."""
    names = {"revenue": "revenue", "op_income": "operating_income", "net_income": "net_income_parent", "net_income_all": "net_income",
             "equity": "equity_parent", "equity_all": "total_equity", "assets": "total_assets", "liabilities": "total_liabilities",
             "current_assets": "current_assets", "current_liabilities": "current_liabilities", "cash": "cash_and_equivalents",
             "ocf": "operating_cash_flow", "eps": "eps_basic", "dividends": "dividends_paid"}
    out: Dict[str, Any] = {k: [] for k in names}
    bases = set()
    for year in sorted(statements):
        for metric, concept in names.items():
            r = statements[year].get(concept) or {}
            if r.get("status") == "REAL":
                out[metric].append({"end": r["period_end"], "val": float(r["value"]), "filed": r["receipt_date"], "basis": r["basis"]})
                bases.add(r["basis"])
    out["net_income"] = out["net_income"] or out.pop("net_income_all", [])
    out["equity"] = out["equity"] or out.pop("equity_all", [])
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
    so both go and the existing fallback to total liabilities applies."""
    ends = [r["end"] for rows in annual.values() if isinstance(rows, list) for r in rows]
    if not ends:
        return annual
    newest = max(ends)
    gone = {k for k, rows in annual.items() if isinstance(rows, list) and rows and _days(max(r["end"] for r in rows), newest) > max_gap_days}
    if "debt_long" in gone:
        gone.add("debt_short")
    return {k: ([] if k in gone else v) for k, v in annual.items()}


def metrics(annual: Dict[str, Any], close: Optional[float], as_of: str, *, is_financial: bool = False, shares: Optional[float] = None,
            source: str = "SEC EDGAR 10-K", insider_pct: Optional[float] = None) -> Dict[str, Any]:
    series = {k: _vintage(v, as_of) for k, v in annual.items() if isinstance(v, list) and not k.startswith("_")}
    # One basis only: a company that began consolidating uses the years on its latest basis, and growth stops at the change.
    tagged = [r for s in series.values() for r in s if r.get("basis")]
    latest_basis = max(tagged, key=lambda r: (r["end"], r["filed"]))["basis"] if tagged else None
    basis_changed = bool(latest_basis) and any(r["basis"] != latest_basis for r in tagged)
    if latest_basis:
        series = {k: [r for r in s if r.get("basis", latest_basis) == latest_basis] for k, s in series.items()}

    def last(k, back=0):
        s = series.get(k) or []
        return s[-1 - back]["val"] if len(s) > back else None

    if not series.get("net_income") and not series.get("revenue"):
        return {"status": "UNAVAILABLE", "reason": "재무 수치를 찾지 못했습니다."}
    latest = max((s[-1]["end"] for s in series.values() if s), default=None)
    filed = max((s[-1]["filed"] for s in series.values() if s and s[-1]["end"] == latest), default=None)
    rev, ni, eq, assets = last("revenue"), last("net_income"), last("equity"), last("assets")

    def div(a, b):
        return a / b if a is not None and b not in (None, 0) else None

    def growth(k, back=1):
        a, b = last(k), last(k, back)
        return (a / b - 1) if a is not None and b is not None and b > 0 else None

    def cagr(k, n=3):
        a, b = last(k), last(k, n)
        return (a / b) ** (1 / n) - 1 if a is not None and b is not None and a > 0 and b > 0 else None

    ocf, capex = last("ocf"), last("capex")
    fcf = ocf - capex if ocf is not None and capex is not None else None
    fcfs = []
    by_end = {r["end"]: r["val"] for r in series.get("capex") or []}
    for r in (series.get("ocf") or [])[-5:]:
        if r["end"] in by_end:
            fcfs.append(r["val"] - by_end[r["end"]] > 0)
    nis = [r["val"] > 0 for r in (series.get("net_income") or [])[-5:]]
    debt = None
    if last("debt_long") is not None or last("debt_short") is not None:
        debt = (last("debt_long") or 0.0) + (last("debt_short") or 0.0)
    elif last("liabilities") is not None:
        debt = last("liabilities")
    shares_used = shares or last("shares_avg")
    mcap = close * shares_used if close and shares_used else None
    eps = last("eps") if last("eps") is not None else div(ni, shares_used)
    bb, dv = last("buyback"), last("dividends")
    roe_prev = div(last("net_income", 1), last("equity", 1)) if (last("equity", 1) or 0) > 0 else None
    out = {
        "status": "STALE" if latest and _days(latest, as_of) > STALE_DAYS else "REAL", "source": source, "fiscal_end": latest, "filed": filed,
        "is_financial": is_financial, "basis": latest_basis, "basis_changed": basis_changed, "basis_conflict": False,
        "roe": div(ni, eq) if (eq or 0) > 0 else None, "roe_prev": roe_prev, "op_margin": div(last("op_income"), rev), "gross_margin": div(last("gross_profit"), rev),
        "net_margin": div(ni, rev), "rev_growth": growth("revenue"), "eps_growth": growth("eps"), "rev_cagr3": cagr("revenue"), "eps_cagr3": cagr("eps"),
        "ocf_to_ni": div(ocf, ni) if (ni or 0) > 0 else None, "fcf": fcf, "fcf_margin": div(fcf, rev), "fcf_years_positive": sum(fcfs) / len(fcfs) if fcfs else None,
        "roe_years_positive": sum(nis) / len(nis) if nis else None, "debt_equity": 99.0 if (eq is not None and eq <= 0 and debt) else div(debt, eq), "current_ratio": div(last("current_assets"), last("current_liabilities")),
        "interest_cover": div(last("op_income"), last("interest")), "cash_debt": div(last("cash"), debt), "equity_assets": div(eq, assets),
        "share_change": growth("shares_avg"), "returns_capital": (bool((bb or 0) > 0 or (dv or 0) != 0) if (bb is not None or dv is not None) else None),
        "market_cap": mcap, "eps": eps, "pe": div(close, eps), "pb": div(mcap, eq) if (eq or 0) > 0 else None, "fcf_yield": div(fcf, mcap), "insider_pct": insider_pct,
    }
    return out


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
    if sec and y / sec < MULTI_CLASS_SEC_GAP or (not sec and own):
        return cap / price
    return y


def is_financial_sic(sic: Any) -> bool:
    """SEC SIC 6000-6799: banks, insurers, brokers (6798 REITs have ordinary cash flows and stay non-financial)."""
    try:
        s = int(sic)
    except (TypeError, ValueError):
        return False
    return 6000 <= s < 6798 or 6799 == s


def load_kr_statements(corp_code: str, code: str, industry_class: str, as_of: date, client: Any,
                       extract: Optional[Callable] = None) -> Dict[int, Dict[str, Dict]]:
    """Last four business years of annual statements, chosen per year as CFS then OFS and never mixed within a year."""
    from markets.kr import dart
    out = {}
    for year in range(as_of.year - 4, as_of.year):
        fetched = {fs: client.statements(corp_code, year, "11011", fs) for fs in ("CFS", "OFS")}
        chosen = dart.choose_basis(fetched)
        if not chosen.get("rows"):
            continue
        obs = dart.normalize_statements(chosen["rows"], corp_code=corp_code, ticker=code, year=year, reprt_code="11011", fs_div=chosen["fs_div"])
        out[year] = (extract or dart.extract_concepts)(obs, industry_class)
    return out
