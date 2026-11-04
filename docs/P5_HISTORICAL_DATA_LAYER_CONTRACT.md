# P5 Historical Market & Fundamental Data Layer

The P5 boundary is `HistoricalDataProvider -> HistoricalDataRepository -> PITInformationSet`.
It is deliberately not connected to `NormalizedData`, `QuantInputAdapter`, `FactorEngine`, execution, or backtesting. P5-6 owns that translation.

`HistoricalFinancialFact` persists the filing, reporting period, XBRL unit/period type, amendment/restatement, and source lineage. `HistoricalPriceBar` keeps raw `close` and `adjusted_close` separately. `CorporateActionEvent` retains both announcement and effective timestamps.

The repository is an indexed SQLite database at `data/historical_data.db`. Queries filter by `security_id` and date in SQL and return only selected rows; it does not load a historical dataset into pandas or bypass `MemoryGuard`. Parquet/DuckDB are not used because neither `pyarrow` nor `duckdb` is available in the audited local environment.

## PIT rules

- A financial fact is eligible only when `period_end <= as_of`, `filed_at <= as_of`, and, if supplied, `accepted_at <= as_of`.
- Eligible facts are selected deterministically for each normalized metric: latest period, then latest accepted-or-filed timestamp, filing timestamp, amended/restated flags, accession number, and stable database id. A later amendment/restatement cannot affect an earlier `as_of`.
- Metric unit compatibility is preserved as source metadata. A duration metric cannot be stored as an instant metric (and vice versa). Cross-unit conversion is intentionally not inferred.
- Derived ROE and profit margin are calculated only when their selected PIT source facts are both available. Missing values remain `None`, never zero.
- A price bar is eligible only when `bar.date <= as_of`. Prices are keyed by `security_id`, so ticker changes and ticker reuse cannot cross-link records.
- Corporate-action information becomes visible at `announced_at`; if it has no announcement timestamp, visibility begins at `effective_at`. The event's effective time remains distinct from visibility.
- Returns policy for later P5-7: raw close is the unadjusted trading price. Adjusted close may only be used with recorded source/methodology and an adjustment factor; P5 does not apply adjustments.

## Provider policy

`HistoricalProviderRegistry` reports provider availability without fabricating data. Sharadar/Nasdaq Data Link and Norgate require configured credentials and an installed adapter. The existing SEC client is not registered for this layer because its legacy failure path can emit simulated data. A future official-EDGAR adapter must require a compliant configured User-Agent and persist separate filing metadata plus facts.
