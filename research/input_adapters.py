"""Pure transformations from NormalizedData to the existing Quant Engine inputs."""

import pandas as pd

from contracts.normalized_data import NormalizedData


def market_to_prices(market: NormalizedData) -> pd.DataFrame:
    close = market.data.get("close", {})
    index = pd.to_datetime(list(close.keys()))
    return pd.DataFrame({market.ticker: list(close.values())}, index=index)


def financial_to_frame(financial: NormalizedData) -> pd.DataFrame:
    fields = {"ticker": financial.ticker, **financial.data}
    return pd.DataFrame([fields]).set_index("ticker")
