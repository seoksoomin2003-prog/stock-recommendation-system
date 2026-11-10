"""Versioned Korean accounting concept registry (KR-ACCT-0.3: EPS of continuing and discontinued operations, and one
alternative revenue id that is used only when the statement proves it is the whole; KR-ACCT-0.2 added capital spending).

Mapping is by **XBRL standard account ID** (OpenDART ``account_id``) and statement type (``sj_div``),
never by account-name string matching.  ``account_nm`` is kept only as provenance.  Rows whose
``account_id`` is "-표준계정코드 미사용-" (company-specific line) are never mapped.

applicability: which industry classes (markets.kr.security_master.FINANCIAL_CLASSES values, plus
NON_FINANCIAL) the concept is meaningful for.  A concept requested for a class it does not apply to
is NOT_APPLICABLE (e.g. "revenue" for banks and insurers, whose income statements have no single
comparable revenue line; "current assets" for unclassified financial balance sheets).
"""
from typing import Dict, List

from markets.kr import KR_ACCOUNT_MAPPING_VERSION

NON_STANDARD_ACCOUNT = "-표준계정코드 미사용-"
ALL = ("NON_FINANCIAL", "BANK", "INSURANCE", "SECURITIES_AND_FINANCIAL_SERVICES", "HOLDING_OR_OTHER_FINANCIAL")
NON_FIN = ("NON_FINANCIAL", "HOLDING_OR_OTHER_FINANCIAL")

# concept -> definition
REGISTRY: Dict[str, Dict] = {
    # ``alternatives``: another standard id some filers put the same line under.  It is read only when no row carries the ids above,
    # and only when it equals the sum of the accounts in ``equals_sum_of`` in the same statement: product sales are normally a
    # part of revenue, so the id is the whole only where revenue - cost of sales = gross profit holds with it.
    "revenue": {"account_ids": ["ifrs-full_Revenue"], "statements": ["IS", "CIS"], "kind": "FLOW",
                "alternatives": [{"account_ids": ["dart_RevenueFromSaleOfGoodsProduct"],
                                  "equals_sum_of": ["ifrs-full_GrossProfit", "ifrs-full_CostOfSales"]}],
                "applicability": NON_FIN, "confidence": "HIGH",
                "validation": "finite; > 0 for an operating company"},
    "operating_income": {"account_ids": ["dart_OperatingIncomeLoss"], "statements": ["IS", "CIS"], "kind": "FLOW",
                         "applicability": NON_FIN, "confidence": "HIGH",
                         "validation": "finite; DART-specific standard account (영업이익)"},
    "net_income": {"account_ids": ["ifrs-full_ProfitLoss"], "statements": ["IS", "CIS"], "kind": "FLOW",
                   "applicability": ALL, "confidence": "HIGH", "validation": "finite; includes NCI"},
    "net_income_parent": {"account_ids": ["ifrs-full_ProfitLossAttributableToOwnersOfParent"],
                          "statements": ["IS", "CIS"], "kind": "FLOW", "applicability": ALL,
                          "confidence": "HIGH", "validation": "finite; consolidated statements only"},
    "total_assets": {"account_ids": ["ifrs-full_Assets"], "statements": ["BS"], "kind": "INSTANT",
                     "applicability": ALL, "confidence": "HIGH", "validation": "> 0"},
    "total_liabilities": {"account_ids": ["ifrs-full_Liabilities"], "statements": ["BS"], "kind": "INSTANT",
                          "applicability": ALL, "confidence": "HIGH", "validation": ">= 0"},
    "total_equity": {"account_ids": ["ifrs-full_Equity"], "statements": ["BS"], "kind": "INSTANT",
                     "applicability": ALL, "confidence": "HIGH", "validation": "finite; includes NCI"},
    "equity_parent": {"account_ids": ["ifrs-full_EquityAttributableToOwnersOfParent"], "statements": ["BS"],
                      "kind": "INSTANT", "applicability": ALL, "confidence": "HIGH",
                      "validation": "finite; consolidated statements only"},
    "current_assets": {"account_ids": ["ifrs-full_CurrentAssets"], "statements": ["BS"], "kind": "INSTANT",
                       "applicability": NON_FIN, "confidence": "HIGH", "validation": ">= 0"},
    "current_liabilities": {"account_ids": ["ifrs-full_CurrentLiabilities"], "statements": ["BS"],
                            "kind": "INSTANT", "applicability": NON_FIN, "confidence": "HIGH",
                            "validation": ">= 0"},
    "cash_and_equivalents": {"account_ids": ["ifrs-full_CashAndCashEquivalents"], "statements": ["BS"],
                             "kind": "INSTANT", "applicability": ALL, "confidence": "HIGH", "validation": ">= 0"},
    "operating_cash_flow": {"account_ids": ["ifrs-full_CashFlowsFromUsedInOperatingActivities"],
                            "statements": ["CF"], "kind": "FLOW", "applicability": ALL, "confidence": "HIGH",
                            "validation": "finite"},
    "investing_cash_flow": {"account_ids": ["ifrs-full_CashFlowsFromUsedInInvestingActivities"],
                            "statements": ["CF"], "kind": "FLOW", "applicability": ALL, "confidence": "HIGH",
                            "validation": "finite"},
    "financing_cash_flow": {"account_ids": ["ifrs-full_CashFlowsFromUsedInFinancingActivities"],
                            "statements": ["CF"], "kind": "FLOW", "applicability": ALL, "confidence": "HIGH",
                            "validation": "finite"},
    "eps_basic": {"account_ids": ["ifrs-full_BasicEarningsLossPerShare"], "statements": ["IS", "CIS"],
                  "kind": "FLOW", "applicability": ALL, "confidence": "MEDIUM",
                  "validation": "finite; KRW per share; reported for the parent's ordinary shares"},
    # A filer with a discontinued business often reports the two parts and no total line; the reader adds them
    # (terminal.qsf.fundamentals.kr_basic_eps).  They are separate concepts so that a part is never taken for the total by itself.
    "eps_basic_continuing": {"account_ids": ["ifrs-full_BasicEarningsLossPerShareFromContinuingOperations"],
                             "statements": ["IS", "CIS"], "kind": "FLOW", "applicability": ALL, "confidence": "MEDIUM",
                             "validation": "finite; KRW per share; the total when no discontinued part is reported"},
    "eps_basic_discontinued": {"account_ids": ["ifrs-full_BasicEarningsLossPerShareFromDiscontinuedOperations"],
                               "statements": ["IS", "CIS"], "kind": "FLOW", "applicability": ALL, "confidence": "MEDIUM",
                               "validation": "finite; KRW per share; some filers repeat the continuing or preferred-share figure here"},
    "capex": {"account_ids": ["ifrs-full_PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities"],
              "statements": ["CF"], "kind": "FLOW", "applicability": ALL, "confidence": "MEDIUM",
              "validation": "finite; filers enter the outflow as positive or negative; property, plant and equipment only, as in the US figure"},
    "dividends_paid": {"account_ids": ["ifrs-full_DividendsPaidClassifiedAsFinancingActivities",
                                       "ifrs-full_DividendsPaidClassifiedAsOperatingActivities"],
                       "statements": ["CF"], "kind": "FLOW", "applicability": ALL, "confidence": "MEDIUM",
                       "validation": "finite; classification differs by company (financing or operating)"},
}

NOT_IN_STATEMENT_API = {
    "shares_outstanding": "not in fnlttSinglAcntAll; requires OpenDART stockTotqySttus (주식의 총수 현황) or "
                          "KRX LIST_SHRS -- UNAVAILABLE in KR-ACCT-0.3",
}


def concepts() -> List[str]:
    return sorted(REGISTRY)


def spec_rows() -> List[Dict]:
    return [{"concept": c, **d, "version": KR_ACCOUNT_MAPPING_VERSION} for c, d in sorted(REGISTRY.items())]
