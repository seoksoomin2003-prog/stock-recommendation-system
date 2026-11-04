# P6-22 Korean Account Mapping Registry: `KR-ACCT-0.1`

Source of truth: `markets/kr/account_mapping.py` (`REGISTRY`). The table below matches `spec_rows()`.

## Rules

1. Mapping is by **XBRL standard account ID** (OpenDART `account_id`) plus statement type (`sj_div`). Account names (`account_nm`) are kept as provenance only. Matching by name string is never done.
2. Rows with `account_id = "-표준계정코드 미사용-"` (company-specific lines) are never mapped.
3. One filing and one basis (CFS **or** OFS) per extraction; mixing the two raises an error.
4. Statement precedence: `IS` before `CIS`. Two different values for the same account in the same statement → `UNAVAILABLE` (`AMBIGUOUS_DUPLICATE_ACCOUNT_ROWS`).
5. Outcome per concept:
   - `REAL`, with full provenance: rcept_no, receipt date, basis, period, amount type, account id and name, unit, confidence, mapping version;
   - `UNAVAILABLE`, with one of the reasons `NOT_REPORTED_UNDER_STANDARD_ACCOUNT`, `VALUE_MISSING`, `RECEIVED_ON_OR_AFTER_AS_OF` or `AMBIGUOUS_DUPLICATE_ACCOUNT_ROWS`;
   - `NOT_APPLICABLE` for the industry class.

   A missing value is never zero.
6. Banks, insurers and securities firms have income statements and balance sheets without a single comparable "revenue" line, and their balance sheets are unclassified (no current/non-current split). Those concepts are therefore **NOT_APPLICABLE** for these classes. They are never approximated with a non-financial formula.

## Registry

Industry-class keys:

- NF = NON_FINANCIAL
- HO = HOLDING_OR_OTHER_FINANCIAL
- BK = BANK
- IN = INSURANCE
- SF = SECURITIES_AND_FINANCIAL_SERVICES

| Concept | XBRL account_id(s) | Statements | Kind | Applies to | Confidence | Validation |
|---|---|---|---|---|---|---|
| revenue | `ifrs-full_Revenue` | IS, CIS | FLOW | NF, HO | HIGH | finite; > 0 for an operating company |
| operating_income | `dart_OperatingIncomeLoss` | IS, CIS | FLOW | NF, HO | HIGH | DART-specific standard account (영업이익) |
| net_income | `ifrs-full_ProfitLoss` | IS, CIS | FLOW | all | HIGH | finite; includes NCI |
| net_income_parent | `ifrs-full_ProfitLossAttributableToOwnersOfParent` | IS, CIS | FLOW | all | HIGH | consolidated statements only |
| eps_basic | `ifrs-full_BasicEarningsLossPerShare` | IS, CIS | FLOW | all | MEDIUM | KRW per share |
| total_assets | `ifrs-full_Assets` | BS | INSTANT | all | HIGH | > 0 |
| total_liabilities | `ifrs-full_Liabilities` | BS | INSTANT | all | HIGH | ≥ 0 |
| total_equity | `ifrs-full_Equity` | BS | INSTANT | all | HIGH | finite; includes NCI |
| equity_parent | `ifrs-full_EquityAttributableToOwnersOfParent` | BS | INSTANT | all | HIGH | consolidated only |
| current_assets | `ifrs-full_CurrentAssets` | BS | INSTANT | NF, HO | HIGH | ≥ 0 |
| current_liabilities | `ifrs-full_CurrentLiabilities` | BS | INSTANT | NF, HO | HIGH | ≥ 0 |
| cash_and_equivalents | `ifrs-full_CashAndCashEquivalents` | BS | INSTANT | all | HIGH | ≥ 0 |
| operating_cash_flow | `ifrs-full_CashFlowsFromUsedInOperatingActivities` | CF | FLOW | all | HIGH | finite |
| investing_cash_flow | `ifrs-full_CashFlowsFromUsedInInvestingActivities` | CF | FLOW | all | HIGH | finite |
| financing_cash_flow | `ifrs-full_CashFlowsFromUsedInFinancingActivities` | CF | FLOW | all | HIGH | finite |
| dividends_paid | `ifrs-full_DividendsPaidClassifiedAsFinancingActivities`, `…AsOperatingActivities` | CF | FLOW | all | MEDIUM | classification differs by company |

**Not available from this endpoint:** `shares_outstanding`. It requires OpenDART `stockTotqySttus` (주식의 총수 현황) or KRX `LIST_SHRS`, so it is **UNAVAILABLE** in KR-ACCT-0.1. Per-share valuation ratios therefore cannot be built yet.

## Validation status

- **Offline:** registry structure, XBRL-only keys, applicability, basis separation, the receipt-date rule, ambiguity handling and missing ≠ 0 are covered by 9 tests in `tests/test_p6_22_kr_data.py`.
- **Live:** **not validated**. `OPENDART_API_KEY` is not configured. Before any fundamental factor may be activated, the following must be measured on live filings for the liquid-300 and recorded:
  - per-concept coverage by industry class;
  - the CFS/OFS split;
  - the share of `-표준계정코드 미사용-` rows for each concept.
