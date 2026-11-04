# P6-22 Korean Market Data Specification: `KR-DATA-0.1`

Date: 2026-11-04 · Scope: KOSPI + KOSDAQ common stocks · Currency: KRW · Timezone: Asia/Seoul (KST)

Every value in the KR engine carries a status: **REAL / PARTIAL / UNAVAILABLE / STALE / MOCK**.

- MOCK data exists only in offline tests (`tests/kr_fakes.py`) and never reaches a production run.
- A missing value stays missing. It is never set to zero, and a stale value is never presented as fresh.

## 1. Sources (verified 2026-11-04; terms checked, nothing bypassed)

| Source | Use | Access | Status in this build |
|---|---|---|---|
| KRX **KIND** listed-company list (`kind.krx.co.kr/corpgeneral/corpList.do?method=download`) | security master: name, market (유가/코스닥), 6-character issue code, KSIC industry (업종), listing date, settlement month, region | public download, no key | **REAL**. Live 2026-11-04: 829 KOSPI + 1,829 KOSDAQ rows |
| **OpenDART** (`opendart.fss.or.kr/api`) | financial statements (`fnlttSinglAcntAll.json`), corp-code map (`corpCode.xml`) | free key (`OPENDART_API_KEY`), normally 20,000 requests/day | **UNAVAILABLE**: no key configured. Adapter implemented and tested offline. |
| **KRX Open API** (`data-dbg.krx.co.kr/svc/apis`) | official daily trading: open, high, low, close, volume, traded value (거래대금), market cap, listed shares; index series | free key (`KRX_API_KEY`, sent as the `AUTH_KEY` header); service approval per API | **UNAVAILABLE**: no key. A request without a key returns HTTP 401 "Unauthorized Key" (verified). Adapter implemented and tested offline. |
| `data.krx.co.kr` website JSON | none | returns 403 to scripted clients | **not used**; never bypassed |
| **Yahoo Finance** via yfinance (`<code>.KS` / `<code>.KQ`, indices `^KS11` / `^KQ11`) | supplementary daily OHLCV and adjusted close | public, unofficial | **REAL (supplementary)**. Traded value is a labelled proxy. |

The provider is chosen by `market_data.select_provider()`:

- **KRX Open API** when `KRX_API_KEY` is set: `traded_value_basis = KRX_ACC_TRDVAL`, status OFFICIAL;
- **Yahoo** otherwise: `traded_value_basis = PROXY_CLOSE_X_VOLUME`, status SUPPLEMENTARY.

Every run records which provider and basis it used.

## 2. Security master

- **Identity:** `security_key = KR:<KOSPI|KOSDAQ>:<6-character code>`. The code is kept as a string, so leading zeros and alphanumeric codes (e.g. `0126Z0`) survive. The market comes from KIND's 시장구분 column, never from the code format. Each snapshot is saved with the source sha256 (`data/kr/security_master/`) and is reused for up to 20 hours.
- **Fields:**
  - from KIND: company name, market, exchange, currency (KRW), instrument type, listing date, settlement month, region, industry (KIND 업종);
  - derived: `industry_class`, `yahoo_symbol`, eligibility with reason, source, last-verified time.
  - `sector` is not provided by KIND, so it is `None` and never invented.
  - `shares_outstanding` and `market_cap` are `None` until the KRX key is available.
- **Exclusions,** applied before the universe is built and each with a stated reason:

| Rule | Reason code | Live count 2026-11-04 |
|---|---|---|
| name contains 스팩 / 기업인수목적 | `SPAC_EXCLUDED` | 70 |
| name contains 리츠 / REIT | `REIT_EXCLUDED_SEPARATE_TREATMENT` | 25 |
| region is not a Korean province or city (foreign issuer) | `FOREIGN_ISSUER_EXCLUDED_INITIAL_MODEL` | 19 |
| 업종 = 신탁업 및 집합투자업 (funds and trusts) | `COLLECTIVE_INVESTMENT_VEHICLE_EXCLUDED` | 13 |
| code length ≠ 6 | `INVALID_ISSUE_CODE` | 0 |
| row's market label ≠ the download it came from | `MARKET_LABEL_MISMATCH` | 0 |
| duplicate `security_key` | `DUPLICATE_SECURITY_KEY` | 0 |

  Eligible after exclusions: **2,531 of 2,658**.
- **Not in the KIND list:**
  - preferred shares (우선주), ETFs/ETNs and KONEX are outside the corpList download, so they are excluded by construction;
  - management-issue (관리종목) and trading-halt flags are not in KIND corpList. Halts are inferred from the data (§3) and labelled as suspected, not confirmed.
- **Financial classes** (from KIND 업종):

  | KIND 업종 | Class |
  |---|---|
  | 은행 및 저축기관 | BANK |
  | 보험업 / 재 보험업 / 보험 및 연금관련 서비스업 | INSURANCE |
  | 금융 지원 서비스업 | SECURITIES_AND_FINANCIAL_SERVICES |
  | 기타 금융업 | HOLDING_OR_OTHER_FINANCIAL |
  | anything else | NON_FINANCIAL |

  **Limitation:** "기타 금융업" mixes financial holding companies (e.g. KB금융, 신한지주) with non-financial holding companies. It is therefore its own class rather than BANK.

## 3. Daily market data

**Canonical row:**

- fields: `date, market, ticker, open, high, low, close, adj_close, volume, traded_value, traded_value_basis, provider, retrieved_at, observation_ts (15:30 KST close), adjustment, quality_status, quality_flags`;
- adjustment basis: Yahoo prices are split-adjusted OHLCV, and `adj_close` is also dividend-adjusted. KRX prices are unadjusted (as traded).

**Row validation.** A failing row becomes `INVALID`. Its numeric fields are set to NaN, never 0, and the reason is kept in `quality_flags`. Checks:

- `NON_POSITIVE_PRICE`, `MISSING_PRICE`, `MISSING_VOLUME`;
- `HIGH_BELOW_LOW`, `OPEN_OUTSIDE_RANGE`, `CLOSE_OUTSIDE_RANGE`;
- `NEGATIVE_VOLUME`, `NEGATIVE_TRADED_VALUE`;
- `DUPLICATE_DATE`.

**Series checks:**

| Flag | Meaning | Effect |
|---|---|---|
| `NO_VALID_BARS` | no REAL rows | status UNAVAILABLE |
| `MISSING_SESSIONS` | observed KRX sessions with no valid bar | recorded; factor windows see NaN (never filled) |
| `STALE` | last valid bar earlier than the latest completed session | status STALE; excluded |
| `ZERO_VOLUME_RUN_HALT_SUSPECTED` | the last 3 valid bars have zero volume | status HALTED; excluded |
| `CORPORATE_ACTION_SUSPECTED` | `adj_close/close` ratio jumps more than 2% | recorded with dates (informational) |

**Session completeness.** A daily bar is used only after 18:00 KST on its date. `calendar.drop_incomplete` removes intraday partial bars.

**Session calendar.** The KRX trading sessions are the dates with a KOSPI index (`^KS11`) bar. Holidays are therefore observed, not hard-coded. This is a known limitation: an unscheduled closure is only known after it happens.

**Caching.** Bars are cached as csv.gz under `data/kr/cache/`. The cache key is a hash of the symbol set plus the window, and the window end is the day after the latest complete session, so a new session triggers a refetch. Downloads use chunks of 50 symbols, a 1-second pause between chunks, and 3 attempts with backoff. A chunk that fails is recorded as an event; its data is absent, never fabricated.

## 4. Financial statements (OpenDART, inactive until a key exists)

- Endpoint: `fnlttSinglAcntAll.json`, parameters `corp_code`, `bsns_year` (≥ 2015), `reprt_code` (11013 Q1, 11012 half, 11014 Q3, 11011 annual) and `fs_div` (CFS consolidated, OFS separate).
- Status codes:
  - 000 → REAL;
  - 013 → UNAVAILABLE (`DART_NO_DATA`);
  - 020 → request limit (raises; never retried aggressively);
  - others raise `DART_STATUS_<code>`.
- The key is never logged and never appears in an exception, an artifact or a test output (there is a test for this).
- **Basis separation.** Consolidated and separate statements are never combined. `choose_basis` uses CFS when present, otherwise OFS with an explicit `SEPARATE` label and a note. `extract_concepts` raises if given mixed bases.
- **Amount types:**
  - balance sheet → `INSTANT` at the period end;
  - annual report → `FY` flow;
  - quarterly and half-year income statement → `QUARTER_3M` (`thstrm_amount`) and `YTD` (`thstrm_add_amount`), both kept and labelled;
  - quarterly cash flow → `YTD`.
- **Period dates** are derived from the KIND settlement month and labelled as derived. This handles non-December year ends.
- **Point in time.** The receipt date is the first 8 digits of `rcept_no`. No receipt time is available, so a filing is usable on an as-of date only if it was received strictly before that date. The result is a conservative one-day lag.
- **Account mapping:** XBRL `account_id` only; see `P6-22_KR_ACCOUNT_MAPPING.md`.

There is deliberately no universal normalisation function shared with the US SEC/US-GAAP pipeline. The KR normaliser emits KR-specific observations (`basis`, `fs_div`, `reprt_code`, `rcept_no`), and these cannot be passed to the frozen US core.

## 5. Universe: liquid-300

- **Input:** every eligible master row; bars over the last 70 calendar days.
- **Measure:** `ADTV20` = mean traded value over the last 20 valid sessions (Yahoo: proxy close × volume, labelled).
- **Exclusions,** with reasons:
  - `NO_MARKET_DATA`;
  - `STALE_LAST_BAR`;
  - `HALT_SUSPECTED`;
  - `INSUFFICIENT_VALID_OBSERVATIONS` (fewer than 20 valid bars);
  - `BELOW_LIQUID_300_RANK`.
- **Selection:** rank by ADTV20 descending, ties broken by `security_key`, and take the top 300. There is no absolute floor and no market quota, so the KOSPI/KOSDAQ composition is reported, not forced.
- **Snapshot:** every run writes the full table (`universe_snapshot.csv.gz`) with the cutoff ADTV, the median, the composition and the exclusion counts. Its sha256 goes into the KR ledger. `universe.stability(prev, cur)` reports overlap, entries, exits and Jaccard between runs.

## 6. Versioning

`KR-DATA-0.1` is written into every KR manifest, validation result and ledger record, alongside the account-mapping version `KR-ACCT-0.1` and the model version. Any change to a rule in this document requires a new version string. Observations from different versions are summarised separately.
