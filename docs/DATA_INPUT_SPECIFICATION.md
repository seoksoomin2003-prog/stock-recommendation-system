# Data-Input Specification: version **P6-20-A**

This document defines what is **fed into** the frozen P6-11B core. It does not change any frozen
formula, factor weight, normalisation rule, threshold or portfolio rule. The frozen engines
(`core/factor_engine.py`, `core/scoring_engine.py`, `core/ranking_engine.py`,
`core/decision_engine.py`, `contracts/decision.py`) are byte-identical to their pinned versions
(`tests/fixtures/frozen_source_sha256_p6_19.json`, re-verified after every P6-20 change).

| Version | Where in force | Recorded as |
|---|---|---|
| `P6-20-A` (this document) | runs created after commit `63c283d` | `run_manifest.json → data_input_spec_version`, every ledger observation |
| `P6-19-final` | run `20261104T111004Z_market_scan_953827` and other P6-19/P6-20 runs before the addendum | same field (inferred for older runs, see `pipeline/prospective_ledger.py::infer_data_input_spec`) |

The implementation constant is `data/loader.py::DATA_INPUT_SPEC_VERSION`. The fundamentals cache
schema is `FUNDAMENTALS_CACHE_SCHEMA = 5`. A cache entry with any other schema is refetched, so a
rule change can never be hidden behind an old cached value.

The P6-20 addendum rules are A1–A6. Summary:

| Rule | Input | P6-20-A change |
|---|---|---|
| A1 | P/B validation | Cross-check now uses **common** equity from the **latest eligible balance sheet**, with share-class scope, currency and staleness checks. Outcomes: CONSISTENT / INCONSISTENT (→ UNAVAILABLE) / NOT_VERIFIABLE / PROVIDER_VALUE_UNAVAILABLE |
| A2 | SEC total revenue | Replaces the P6-19 "largest of any revenue concept" rule with tiered **semantic** selection. Components are never total revenue. |
| A3 | Net margin | Margins above 100% go to an anomaly review. The Yahoo fallback is used only if **validated**. SEC net income is never divided by Yahoo revenue. |
| A4 | ADV20 | Definition unchanged; source and timestamp provenance added |
| A5 | Sector | Raw and normalised label, observation time and status. The frozen Technology-only cap is unchanged. |
| A6 | Gating | Unchanged (before normalisation, no imputation). Tests extended to the new rejection reasons. |
| — | Timestamp eligibility | **New**, common to A1–A3: EDGAR acceptance datetime (see §0) |

---

## 0. SEC timestamp eligibility (common to A1–A3)

| Item | Rule |
|---|---|
| Definition | A SEC fact may be used only if the filing that contains it was **public at the as-of timestamp**. The as-of timestamp is the fundamentals acquisition instant (`_sec_as_of` in provenance). It is never later than the recommendation timestamp (`RUN_COMPLETED`). |
| Source | `filed` (date) from CompanyFacts. `acceptanceDateTime` from EDGAR **submissions** (`data.sec.gov/submissions/CIK##########.json`, `filings.recent`), one extra zero-cost request per CIK at the same < 10 req/s pacing, cached with the fundamentals. |
| Policy | Acceptance datetime known → `accepted ≤ as_of`. Unknown (older than `filings.recent`, or the submissions request failed) → `filed` date **strictly before** the as-of US/Eastern date. A same-day filing whose acceptance time cannot be verified is excluded. |
| Clock | EDGAR suffixes `acceptanceDateTime` with `Z`, but the timestamp is US Eastern. It is read as US/Eastern, which is never earlier than the true instant, so a filing that is not yet public is never admitted. |
| Provenance | `accepted` on every selected fact. `_sec_accepted_datetime_source` per ticker (`edgar_submissions` or `UNAVAILABLE (…)`). |
| Cache | An entry is computed at its acquisition time and reused for up to 20 h. Its as-of is therefore earlier than any later run's timestamp, which is conservative. |
| Tests | `TestA1PriceToBook::test_filing_after_timestamp_is_never_used` (future filing; same-day unknown, after and before acceptance), `TestA2TotalRevenue::test_same_filing_preferred_and_future_filings_excluded` |

## A1. Price-to-book (Yahoo value, SEC cross-check)

| Item | Rule |
|---|---|
| Definition | The P/B fed to the frozen value factor is Yahoo `priceToBook`. It is **cross-checked**, never replaced, against a diagnostic P/B. |
| Formula | `diagnostic_pbr = marketCap / common_equity`. `common_equity = StockholdersEquity − PreferredStockValue` at the **same balance-sheet instant**. `ratio = priceToBook / diagnostic_pbr`. |
| Source | Yahoo `Ticker.info` (`priceToBook`, `marketCap`, `currentPrice` or `regularMarketPrice`, `sharesOutstanding`, `impliedSharesOutstanding`, `currency`, `financialCurrency`). SEC CompanyFacts `us-gaap:StockholdersEquity` and `us-gaap:PreferredStockValue` (USD, instant). |
| Timestamp policy | §0. The **latest** balance sheet public at as-of, from forms 10-K, 10-K/A, 10-KT, 10-Q, 10-Q/A, 10-QT, 20-F or 40-F (highest period end, then latest filing). Preferred stock is taken at that same instant, preferring the same filing (accession). |
| Accounting context | `StockholdersEquity` is the parent's equity: it excludes non-controlling interests and is entity-wide, covering all share classes. CompanyFacts contains only non-dimensional (consolidated) facts for one CIK. Preferred stock not tagged at that instant is recorded as `NOT_TAGGED_AT_INSTANT_TREATED_AS_ZERO`. An untagged preferred balance (e.g. JPM, about 5% of equity) moves P/B by far less than the 10× tolerance. |
| Share-class scope | SEC equity is entity-wide, so `marketCap` must value **all** classes. The check is `marketCap / price ≈ impliedSharesOutstanding` (or `sharesOutstanding` when no implied count exists), within **2%** → `COMPATIBLE`. A market cap equal to one class only (`≈ sharesOutstanding` while the implied count is larger) → `SINGLE_CLASS_MARKET_CAP_VS_ENTITY_EQUITY`. Otherwise → `MARKET_CAP_SHARE_COUNT_UNRECONCILED`. Live check 2026-11-04: BRK-B, GOOGL and FOX value all classes (e.g. BRK-B 557.07 × 2,140,709,794 = marketCap), so the BRK-B Class-A book-value defect is still caught. |
| Validation | All must hold for a diagnostic: SEC equity available, at most **200 days** old at as-of, `common_equity > 0`; `marketCap > 0`; scope `COMPATIBLE`; Yahoo `currency` and `financialCurrency` are USD (SEC values are USD). |
| Outcomes | `CONSISTENT`: ratio within [0.1, 10]. Yahoo value used. **`INCONSISTENT`**: ratio > 10 or < 0.1 (or Yahoo P/B ≤ 0 against a positive diagnostic). Yahoo P/B becomes **UNAVAILABLE** (`reason = PBR_INCONSISTENT_WITH_SEC_COMMON_EQUITY`), and the original value and the full check are kept in `rejected_provider_value`. The ticker becomes `PARTIAL` and is quarantined by the frozen data-quality rule (`PROVIDER_VALUE_REJECTED_PBR`). **`NOT_VERIFIABLE`**: the diagnostic cannot be computed validly (reasons listed). The Yahoo value is used unchanged and labelled; this is the P6-19 "no check" behaviour. `PROVIDER_VALUE_UNAVAILABLE`: no Yahoo P/B exists. The field stays missing and the diagnostic is recorded only. |
| Never | The diagnostic is never substituted for the Yahoo value. Nothing filed after as-of is used. |
| Provenance | `field_provenance[t].pbr.consistency_check` (or `.rejected_provider_value`): `rule`, `status`, `reasons`, `provider_value`, `diagnostic_pbr`, `ratio`, `market_cap`, `share_scope`, `sec_common_equity {status, common_equity, balance_sheet_date, age_days, preferred_treatment}`, `sec_equity_filing {concept, end, filed, accepted, form, accn, fy, fp}` |
| Missing data | Missing Yahoo P/B → field missing (`UNAVAILABLE`), never imputed |
| Tests | `tests/test_p6_20_input_rules.py::TestA1PriceToBook`: normal agreement; >10× (low, high, and exactly 10×); loader never replaces; zero or negative equity; preferred subtraction; missing market cap; stale SEC filing; filing after the timestamp; incompatible share-class scope and currency; multi-class all-class market cap; unavailable Yahoo P/B; SEC not configured |

## A2. SEC total revenue

| Item | Rule |
|---|---|
| Definition | Consolidated total revenue for **exactly** the fiscal period of the selected annual net income |
| Source | SEC CompanyFacts `us-gaap`, unit **USD** only |
| Timestamp policy | §0. Within the exact period, the fact from the **same filing (accession) as net income** is preferred; otherwise the latest eligible filing (restatement) is used. `same_filing_as_net_income` is recorded. |
| Semantic priority | **Tier 1**, concepts defined as total revenue: `Revenues`, `RevenuesNetOfInterestExpense`, `RegulatedAndUnregulatedOperatingRevenue`. **Tier 2**, single-stream concepts: `RevenueFromContractWithCustomerExcludingAssessedTax`, `…IncludingAssessedTax`, `SalesRevenueNet`. Accepted only if **no** other revenue stream (component) is reported for the same period. **Components**, never total: `OperatingLeaseLeaseIncome`, `LeaseIncome`, `OperatingLeasesIncomeStatementLeaseRevenue`, `RealEstateRevenueNet`, `InterestAndDividendIncomeOperating`, `NoninterestIncome`, `InterestIncomeExpenseNet`, `InterestIncomeExpenseAfterProvisionForLoanLoss`, `PremiumsEarnedNet`. Within a tier, the largest **positive** value is used. Candidates in one tier share meaning, period, unit and scope. |
| Extensions (priority 3) | CompanyFacts does not publish company-extension concepts (verified live: only `us-gaap`, `dei`, `srt`, `invest`, `ffd`, `ecd`). Extension revenue is therefore never used. A company that reports total revenue only through an extension gets `UNAVAILABLE`. |
| Validation | Form in the 10-K family (10-K, 10-K/A, 10-KT, 20-F, 40-F). Duration (not instant) of 330–380 days. `start` **and** `end` equal to the net-income period. Finite value. Consolidated: non-dimensional by construction, single CIK entity. |
| Never combined | Segment with consolidated (no dimensional facts are read). Quarterly or YTD with annual (the duration check and exact period). Different currencies or units (USD only). Facts across incompatible periods. Components are never summed. |
| Rejection | Tier 2 with components present → `SINGLE_STREAM_CONCEPT_WITH_OTHER_REVENUE_STREAMS`. Component → `COMPONENT_NOT_TOTAL_REVENUE`. Non-positive value → `NON_POSITIVE_REVENUE`. Nothing selectable → `status = UNAVAILABLE`, reason `NO_RELIABLE_TOTAL_REVENUE` (candidates existed) or `NO_REVENUE_CONCEPT_FOR_PERIOD` |
| Live cases (2026-11-04) | CPT (ASC 606 $13M + lease income $1,574M, no total) → UNAVAILABLE. P6-19 used lease income. FITB, HBAN and MTB (bank components only) → UNAVAILABLE. DTE → tier 1 `RegulatedAndUnregulatedOperatingRevenue` $15,814M (margin 9.2%). P6-19 rejected it. JPM, BRK-B, GOOGL and O → `Revenues`. AAPL, CL and MU → tier 2 ASC 606 (no other streams). |
| Provenance | `field_provenance[t].profitMargin.revenue_selection {rule, status, tier, reason, same_filing_as_net_income, candidates{concept: val, accn, filed, tier}, rejected[]}`. `_sec_filings.revenue {concept, taxonomy, unit, start, end, duration_days, filed, accepted, form, accn, fy, fp}` |
| Missing data | No SEC revenue → no SEC margin. The margin goes to the validated Yahoo fallback (A3). It is never reconstructed. |
| Tests | `TestA2TotalRevenue`: tier 1 over a larger component; largest only among compatible total concepts; tier 2 accepted and rejected; components never total or summed; quarterly, YTD and shifted periods; other units; same-filing preference and future filings; provenance fields. `TestP619LiveDefectRegressions::test_reit_revenue_component_is_never_total_revenue` (CPT) |

## A3. Net margin

| Item | Rule |
|---|---|
| Definition | `profitMargin = NetIncomeLoss / total revenue`. Same fiscal period, same entity, USD, both available at as-of, revenue passed A2. |
| SEC NI | Latest annual `NetIncomeLoss` (10-K family, 330–380 days, highest period end, then latest eligible filing). A period end older than 550 days → `STALE` and no SEC values. |
| Anomaly review | Margin > 100% is **reviewed, not declared impossible**. If `IncomeLossFromContinuingOperations` for the same period exists and is ≤ revenue, the margin is **ACCEPTED** and flagged (the excess comes from discontinued operations or exceptional items). Otherwise it is **REJECTED** (`NET_MARGIN_ABOVE_100PCT_UNEXPLAINED`, explanation recorded) and the field goes to the Yahoo fallback. |
| Yahoo fallback (CPT/FITB/DTE/HBAN/MTB class) | Used only if the SEC margin is unavailable or rejected. It must be validated: `profitMargins` is finite and ≤ 100%, and `mostRecentQuarter` is at most **200 days** old at acquisition. The definition is Yahoo's own TTM net income / TTM revenue (one provider, one period). Labelled `source = yfinance` with `yahoo_validation`. Otherwise UNAVAILABLE with `yahoo_rejected.reason` ∈ {`PROVIDER_VALUE_MISSING`, `FRESHNESS_UNVERIFIABLE_NO_MOST_RECENT_QUARTER`, `PROVIDER_PERIOD_STALE`, `ABOVE_100PCT_NOT_REVIEWABLE_FROM_PROVIDER`}. |
| Never | SEC net income divided by a Yahoo revenue. A margin built from components. |
| Provenance | `profitMargin.source`, `.sec_rejected {reason, concept, revenue, net_income, rejected_facts or review}`, `.anomaly_review {trigger, net_margin, decision, explanation}`, `.yahoo_validation` or `.yahoo_rejected {definition, provider_value, most_recent_quarter, age_days, status, reason}` |
| Missing data | UNAVAILABLE → ticker `PARTIAL` → quarantined by the frozen data-quality rule before normalisation (A6) |
| Tests | `TestA3NetMargin`: >100% explained and accepted; >100% unexplained, rejected, then validated Yahoo (and never SEC NI / Yahoo revenue); failed revenue rejects the SEC margin; four unvalidated-Yahoo cases; valid SEC margin kept |
| ROE (unchanged) | `NetIncomeLoss / StockholdersEquity` at the NI period end (equity > 0), preferring the same filing; otherwise Yahoo `returnOnEquity` |

## A4. Average daily volume (input to the frozen 500,000 rule)

| Item | Rule |
|---|---|
| Frozen rule | `DecisionEngine._check_data_quality`: `volume >= 500000` (unchanged; boundaries 499,999 FAIL / 500,000 PASS / 500,001 PASS are tested) |
| Definition and formula | **ADV20** = arithmetic mean of the last **20 valid session observations** of share volume. These are trading sessions, not calendar days, and it is not single-day volume. |
| Source | yfinance `download(…, auto_adjust=True)` → `Volume` (split-adjusted shares per session; not dollar volume) |
| Validation | One value per session (the duplicate timestamp's last value). NaN is not an observation. Negative values are invalid and dropped. A genuine 0 (halt) is valid. The series must pass the price freshness gate (at most 1 NYSE session behind). |
| Missing data | Fewer than 20 valid observations → ADV20 **missing** (never 0) → `REQUIRED_NUMERIC_DATA_MISSING` |
| Provenance | `candidate_flow[t].adv20`, `adv20_window {observations, first, last, unit, source, retrieved_at, rule}`, `last_volume` (diagnostic only) |
| Tests | `tests/test_p6_19_hardening.py` (threshold boundaries, duplicates, NaN, negatives), `TestA4A5A6Pipeline::test_adv20_provenance_and_missing_is_not_zero` |

## A5. Sector (input to the frozen Technology cap)

| Item | Rule |
|---|---|
| Frozen rule | At most 2 of 5 TOP-5 slots where `sector == "Technology"` (P6-11B approved, Technology only; see `reports/P6-20_SECTOR_CAP_REVIEW.md`). Unchanged. |
| Definition | `sector_raw` = Yahoo `info["sector"]` verbatim. `sector` = `sector_raw.strip()` (whitespace only; no mapping, no case change, no other taxonomy). The engine receives `sector`. Yahoo has not been observed to return padded labels, so in practice the cap's reach is unchanged. |
| Timestamp | `sector_observed_at` = provider retrieval time. `sector_status` = `REAL`, `CACHED` (served from the 20 h cache) or `MISSING` |
| Missing data | Empty or missing → `sector = "Unknown"`, `sector_source = null`, reason `SECTOR_UNKNOWN_CAP_NOT_APPLICABLE`. A sector is never invented or taken from another source. |
| Reporting | Every run reports full `sector_exposure` and `sector_cap_warnings` (any sector > 40%, display only). Tracking diagnostics do the same. |
| Tests | `TestA4A5A6Pipeline::test_sector_raw_and_normalised_preserved_and_missing_recorded`, `::test_loader_sector_normalisation`, `tests/test_p6_20_prospective_tracking.py::TestDiagnostics::test_sector_exposure_reported_frozen_cap_unchanged` |

## A6. Data-quality gating (before normalisation)

| Item | Rule |
|---|---|
| Usable statuses | `REAL`, `CACHED`, `REAL_CURRENT`, `REAL_PIT_ELIGIBLE`, `CACHED_PIT_ELIGIBLE` (the frozen `_check_data_quality` set) |
| Where | `pipeline/canonical.py` step 3, **before** `FactorEngine`, cross-sectional standardisation and scoring |
| Effect | Excluded candidates contribute nothing to means, standard deviations, z-scores, percentiles or ranks. There is no median imputation and there are no synthetic values. A field made UNAVAILABLE by A1 or A3 makes the ticker `PARTIAL`, which is quarantined (`PROVENANCE_STATUS_REJECTED`, plus `PROVIDER_VALUE_REJECTED_<FIELD>` for a rejected provider value). |
| Required numeric fields | `close`, `volume` (ADV20), `alpha`, `atr`, `ema20` → otherwise `REQUIRED_NUMERIC_DATA_MISSING` |
| Tests | `tests/test_p6_19_hardening.py::…test_excluded_candidate_values_cannot_change_valid_scores` (extreme values on an excluded name leave valid names bit-identical), `TestA4A5A6Pipeline::test_rejected_pbr_quarantines_before_normalisation` |

## PER (unchanged)

Yahoo `trailingPE`, with provenance. Missing (e.g. a loss-making company) → `PARTIAL`.

## Known genuine outliers (not defects)

CL: ROE ≈ 39.5 (3,948%). SEC `StockholdersEquity` at 2025-12-31 is $54M (buybacks), and Yahoo
P/B ≈ 264 agrees with marketCap / common equity (A1 CONSISTENT, ratio 1.0008). The frozen
standardisation does not winsorise. This is reported, not changed.

## Status vocabulary

`REAL` (current provider observation) · `CACHED` (served from the local cache inside its TTL) ·
`PARTIAL` (some required fields missing) · `UNAVAILABLE` (no usable value) · `STALE` (older than the
freshness limit) · `MOCK` (synthetic; never allowed in production). A1 check statuses: `CONSISTENT`,
`INCONSISTENT`, `NOT_VERIFIABLE`, `PROVIDER_VALUE_UNAVAILABLE`. Missing data is never relabelled as
MOCK, never converted to zero and never imputed.

## History

- P6-18: ADV20, Yahoo sector, gating before normalisation, period-aligned SEC selection.
- P6-19: revenue concept "largest same-period" (CPT), the NI > revenue rejection (FITB, DTE, HBAN,
  MTB), and the P/B 10× consistency rule (BRK-B). All three are **superseded** by A1–A3 above.
  Results produced under `P6-19-final` stay valid and are reported under their own spec version.
- P6-20-A (this version): addendum A1–A7 and SEC timestamp eligibility.
