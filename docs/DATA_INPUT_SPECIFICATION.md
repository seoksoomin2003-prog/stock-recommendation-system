# Data-Input Specification (approved in P6-19)

This document defines what is **fed into** the frozen P6-11B core. It does not
change any frozen rule, formula, weight or threshold. The frozen engines
(`core/factor_engine.py`, `core/scoring_engine.py`, `core/ranking_engine.py`,
`core/decision_engine.py`, `contracts/decision.py`) are byte-identical to their
pre-P6-18 versions. Their sha256 hashes are pinned in
`tests/fixtures/frozen_source_sha256_p6_19.json` and recorded in every run's
`run_manifest.json`.

All four definitions below were introduced in P6-18 and independently reviewed
in P6-19:

| # | Definition | P6-19 verdict |
|---|---|---|
| 1 | ADV20 share volume | **KEEP** |
| 2 | Yahoo sector for the 40% cap | **KEEP** (frozen Technology-only limitation documented) |
| 3 | Data-quality exclusion before normalisation | **KEEP** |
| 4 | SEC fiscal-period selection | **REVISE**: the period-selection logic is kept; the *revenue-concept* choice and two provider-value plausibility rules (§4a, §4b) were added after the full live run exposed three input defects (CPT, FITB/DTE/HBAN/MTB, BRK-B) |

These are input definitions only. None of them changes a frozen formula, weight,
threshold or rule.

---

## 1. Average daily volume (input to the frozen 500,000 rule)

| Item | Definition |
|---|---|
| Frozen rule | `DecisionEngine._check_data_quality`: `volume >= 500000` (and `evaluate_portfolio`: `volume < 500000` → `LIQUIDITY_REJECTED`) |
| Input supplied as `volume` | **ADV20**: arithmetic mean of the last **20 valid daily share-volume observations** |
| Provider / field | yfinance `download(..., auto_adjust=True)` → `Volume` (shares per session, split-adjusted). It is **not** dollar volume. |
| Valid observation | One value per session, so duplicated timestamps keep the last value. NaN sessions are not observations. Negative values are invalid and dropped. A genuine `0` (for example a halt) is a valid observation. |
| Insufficient history | Fewer than 20 valid observations → ADV20 is *missing*, never zero. The candidate is quarantined with `REQUIRED_NUMERIC_DATA_MISSING`. |
| Freshness | The volume series must pass the same freshness gate as prices: last bar no more than 1 NYSE session behind, otherwise `STALE` → quarantined. |
| Boundaries (tested) | 499,999 → FAIL · 500,000 → PASS · 500,001 → PASS |
| Diagnostics | `adv20`, `adv20_window` (count, first and last session, unit) and `last_volume` (diagnostic only) in `candidate_flow.json` |
| Rationale | The frozen threshold is stated as an *average daily volume* rule (P6-11B; P6-12A researched it with 20-day ADV). The pre-P6-18 live route passed the last session's volume, which is a single-day figure, not an average. |
| Paths | The canonical pipeline is the only production route. Both Automated Market Scan and Direct Ticker Evaluation use it. |

## 2. Sector classification (input to the frozen 40% cap)

| Item | Definition |
|---|---|
| Frozen rule | `DecisionEngine._optimize_portfolio`: at most **2 of 5** TOP-5 slots (40%) where `sector == "Technology"`. The frozen code applies the cap **only** to the literal label `Technology`. |
| Input supplied as `sector` | yfinance `Ticker.info["sector"]`, used verbatim (for example `Technology`, `Healthcare`, `Financial Services`) |
| Missing sector | Recorded as `Unknown`, with `sector_source = null` and reason `SECTOR_UNKNOWN_CAP_NOT_APPLICABLE`. A sector is never guessed or mapped from another source. |
| Same-sector counting | All candidates with the same label count toward the same cap (tested with 8 Technology candidates → 2 selected, the rest go to the watchlist with `SECTOR_CAP_CONSTRAINT`) |
| Pipeline survival | The sector is carried into `candidate_flow.json`, `validation_result.json`, the reports and the forward-tracking ledger (tested) |
| Known frozen limitation (not changed) | Other sectors are **not** capped by the frozen engine, so five Healthcare names would give 100% Healthcare. P6-19 reports this in `sector_cap_warnings` (display only) and does not enforce it, because enforcing it would change frozen logic. See the P6-19 report, "Frozen-core conflicts". |
| Classification note | Yahoo's taxonomy is not GICS. For example GOOGL and META are `Communication Services` and AMZN is `Consumer Cyclical`. The Wikipedia GICS sector is kept in the universe record for reference but is not used for the cap. |

## 3. Data-quality eligibility (before normalisation)

| Item | Definition |
|---|---|
| Usable statuses | `REAL`, `CACHED`, `REAL_CURRENT`, `REAL_PIT_ELIGIBLE`, `CACHED_PIT_ELIGIBLE`. This is the frozen `DecisionEngine._check_data_quality` set. |
| Rejected statuses | `PARTIAL`, `UNAVAILABLE`, `STALE`, `MOCK` for price, volume or fundamentals |
| Where | `pipeline/canonical.py` step 3, **before** `FactorEngine` / cross-sectional standardisation / scoring |
| Effect | Excluded candidates contribute nothing to means, standard deviations, z-scores, percentiles or MODEL_RANK_E ranks. Tests change an excluded candidate's prices and fundamentals to extreme values and assert that every valid candidate's alpha, percentile, factor z-scores and rank are bit-identical. |
| Partial coverage | The frozen ScoringEngine can re-weight over the factors that are available, but the frozen decision gate rejects `fundamental_status = PARTIAL`. Applying the same rule before normalisation is therefore **not stricter** than the frozen contract. It only stops rejected names from distorting the statistics of valid ones. A PARTIAL ticker (for example a loss-making company with no trailing PE) is reported with `missing_fundamentals`. |
| Required numeric fields | `close`, `volume` (ADV20), `alpha`, `atr`, `ema20`. If any is missing → `REQUIRED_NUMERIC_DATA_MISSING`. |
| Fail-safe | No eligible candidates → `DATA-INCOMPLETE / NO VALID RECOMMENDATION`. No market data at all → `LIVE DATA UNAVAILABLE`, with no fundamentals requests made. |
| Cache status | A complete fundamentals observation served from the local cache (TTL 20 h) is labelled `CACHED`, not `REAL` (P6-19). |

## 4. SEC fiscal-period selection (ROE and profit margin)

| Item | Definition |
|---|---|
| Source | SEC EDGAR CompanyFacts (`data.sec.gov/api/xbrl/companyfacts`), queried **only** when `SEC_USER_AGENT` is a valid "<app> <contact e-mail>" identity. Otherwise SEC is not contacted and the status is `SEC_NOT_CONFIGURED`. |
| Annual flow (net income, revenue) | Forms `10-K`, `10-K/A`, `10-KT`, `20-F`, `40-F`. The duration must be **330–380 days**, which excludes quarterly and YTD values and accepts 52/53-week years. Only filings with `filed <= today` count. |
| Latest period | Highest fiscal **period end**, then the latest `filed` date for that same period. A restatement or amendment (10-K/A) for the same period therefore wins. A prior-year comparative re-reported in a later 10-K can never become "latest", because its period end is older. |
| Alignment | Revenue and stockholders' equity must have **the same period end** as the selected net income. Otherwise the metric is missing (never mixed across periods), and the field falls back to Yahoo with its own provenance. |
| Staleness | A latest annual period older than 550 days gives `STALE`, and SEC values are not used. |
| Metrics | ROE = NI / equity (equity > 0). Profit margin = NI / revenue (revenue > 0). |
| Provenance kept | Per field: `source` (`sec_edgar` / `yfinance` / null) and `status`. Per ticker: `_sec_status`, `_sec_fiscal_period_end`, and `_sec_filings` with concept, start, end, filed, form, accession number (`accn`), `fy` and `fp` for net income, equity and revenue. |
| Revenue concept (P6-19 REVISE) | Candidates: `Revenues`, `RevenueFromContractWithCustomerExcludingAssessedTax`, `RevenueFromContractWithCustomerIncludingAssessedTax`, `SalesRevenueNet`, `OperatingLeaseLeaseIncome`, `RealEstateRevenueNet`, `RevenuesNetOfInterestExpense` (see `SEC_REVENUE` in `data/loader.py`). Among the candidates reported **for the same period end as net income**, the **largest** value is used (`revenue_rule = max_same_period_total_revenue_concept`; all candidate values are kept in the detail). Before P6-19 the first concept in list order won, so CPT (a REIT that tags no `Revenues`) used a $13M ASC 606 slice instead of $1,574M lease income, which gave a 2,965% margin. |
| PER / PBR | Always from yfinance (`trailingPE`, `priceToBook`), with provenance |

### 4a. Revenue plausibility (P6-19)

| Item | Definition |
|---|---|
| Rule | If SEC net income **exceeds** the selected revenue value for the same period, that value cannot be total revenue (it is a slice such as fee income or lease income). The SEC profit margin is **rejected** (never reconstructed from other lines), and the field falls back to Yahoo `profitMargins` with `source = yfinance` and `sec_rejected = {reason: NET_INCOME_EXCEEDS_REVENUE_CONCEPT, concept, revenue, net_income}`. |
| Live cases | FITB and DTE (only `OperatingLeaseLeaseIncome` tagged for FY2025, giving margins of 3,153% and 2,397%) and HBAN and MTB (only the ASC 606 fee-income slice, giving 142% and 172%) |
| ROE | Unaffected (net income ÷ equity) |
| Accepted risk | A company whose net income genuinely exceeds revenue (for example a large one-off gain) also falls back to Yahoo. That is conservative: it substitutes a disclosed provider value and labels it. |

### 4b. Price-to-book consistency (P6-19, new rule, **flagged for user review**)

| Item | Definition |
|---|---|
| Rule | When Yahoo `marketCap` and same-filer SEC `StockholdersEquity` are both available, the implied ratio `marketCap / equity` is compared with Yahoo `priceToBook`. If they differ by more than **10×** in either direction, the Yahoo value is set to *missing* (`status = REJECTED_INCONSISTENT`, original value kept in `rejected_provider_value`). It is **never replaced** by the implied value. |
| Effect | The ticker becomes `PARTIAL` and is quarantined with `PROVENANCE_STATUS_REJECTED` and `PROVIDER_VALUE_REJECTED_PBR`, through the frozen data-quality rule (§3). |
| No check | If market cap or SEC equity is missing or not positive, the Yahoo value is used unchanged. |
| Live case | BRK-B: Yahoo `priceToBook = 0.00107` against an implied ≈1.4. This gave a value z-score of 21.1 and made BRK-B the #1 pick in the first P6-19 full run. |
| Why 10× | Share-class and currency mismatches cause errors of 1,000× or more, while legitimate timing differences (equity as of the last fiscal year end, market cap today) stay well inside 10×. In the live run every consistent ticker's ratio was within [0.1, 10]. |

### Fundamentals cache

The cache records a schema number (`FUNDAMENTALS_CACHE_SCHEMA`, currently **4**). An
entry with another schema, or one written with a different SEC configuration, is
refetched, so a rule change can never be masked by an old cached value.

### Known genuine outliers (not defects)

CL: ROE 39.5 (3,948%). SEC `StockholdersEquity` at 2025-12-31 is **$54M** in the
10-K and in every 10-Q (share buybacks), so the value is genuine. The frozen
standardisation does not winsorise, so a single genuine extreme value can
dominate a factor z-score. That behaviour is part of the frozen P6-11B core and
is reported, not changed.

## Status vocabulary

`REAL` (current provider observation) · `CACHED` (provider observation served
from the local cache inside its TTL) · `PARTIAL` (some required fields missing)
· `UNAVAILABLE` (provider returned nothing) · `STALE` (older than the freshness
limit) · `MOCK` (synthetic; never allowed into production). Missing data is
never relabelled as MOCK and never converted to zero.
