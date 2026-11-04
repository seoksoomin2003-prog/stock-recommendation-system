# P6-15 yfinance Forensic Audit
`yfinance` inherently applies survivorship bias. Identifiers like TWTR, SIVB, and FRC return absolutely no data.
It provides no stable GUID or CIK mappings. It defaults to heavily adjusted historical prices.
**Verdict:** Cannot be used as PRIMARY_CANONICAL for historical research.
