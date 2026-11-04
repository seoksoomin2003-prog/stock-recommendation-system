# P6-15 Survivorship Analysis
We can cleanly separate the *Universe Selection* from the *Data Acquisition*.
We successfully solved Universe Selection survivorship bias by relying on SEC filing histories. However, Pricing Survivorship Bias fails because `yfinance` drops pricing data for those historical entities once they delist.
