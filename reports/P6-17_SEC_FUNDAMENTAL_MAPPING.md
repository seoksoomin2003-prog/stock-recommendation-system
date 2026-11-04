# P6-17 SEC Fundamental Data Mapping

## Overview
The frozen P6-11B `FactorEngine` expects four specific numerical fields for its Value and Quality factors:
1. `per` (Price-to-Earnings Ratio)
2. `pbr` (Price-to-Book Ratio)
3. `roe` (Return on Equity)
4. `profitMargin` (Profit Margin)

Currently, these are blindly fetched via `yfinance.Ticker.info`. To satisfy the zero-cost public data and institutional provenance requirement, we will use **SEC EDGAR Company Facts API** (`data.sec.gov/api/xbrl/companyfacts/`) as the primary authoritative source. 

## SEC XBRL Concept Mapping

To derive the required fields without fabricating data, we must extract the following raw US-GAAP concepts from the most recent SEC 10-K / 10-Q filings:

| Required Concept | SEC US-GAAP Tag | Description |
| :--- | :--- | :--- |
| **Net Income** | `NetIncomeLoss` | Trailing 12-month net income for EPS, ROE, Margin |
| **Equity** | `StockholdersEquity` | Total Book Value of Equity for PBR, ROE |
| **Revenue** | `Revenues` or `SalesRevenueNet` | Top-line revenue for Profit Margin |
| **Shares** | `EntityCommonStockSharesOutstanding` | Outstanding shares for per-share calculations |

## Derived Formulas

The live pipeline will calculate the inputs for P6-11B strictly as follows:

1. **PER (Price to Earnings)**
   - `EPS` = `NetIncomeLoss` / `EntityCommonStockSharesOutstanding`
   - `PER` = `Current Market Price` / `EPS`
   - *Condition*: If `EPS` <= 0, `PER` = `NaN` (UNAVAILABLE). Do not fabricate a median PER.

2. **PBR (Price to Book)**
   - `BPS` = `StockholdersEquity` / `EntityCommonStockSharesOutstanding`
   - `PBR` = `Current Market Price` / `BPS`
   - *Condition*: If `StockholdersEquity` <= 0, `PBR` = `NaN` (UNAVAILABLE).

3. **ROE (Return on Equity)**
   - `ROE` = `NetIncomeLoss` / `StockholdersEquity`
   - *Condition*: If `StockholdersEquity` <= 0, `ROE` = `NaN` (UNAVAILABLE).

4. **Profit Margin**
   - `Profit Margin` = `NetIncomeLoss` / `Revenues`
   - *Condition*: If `Revenues` <= 0, `Profit Margin` = `NaN` (UNAVAILABLE).

## Fallback & Status Policy
- **Primary**: SEC EDGAR. If the required concepts exist and the filing date (`filed_at`) is `<= runtime`, calculate the fields.
- **Secondary (Optional)**: If SEC data is structurally missing for a ticker, fallback to `yfinance` **ONLY IF** explicitly verified as a valid public source.
- **Failure**: If both fail or if the derived fields are mathematically invalid (e.g., negative equity), the specific field is marked `NaN`, and its status becomes `UNAVAILABLE`.
- **No Fabrication**: `fillna(0)` or synthetic industry-mean injections are strictly prohibited during data acquisition.
