# P6-12A EXECUTION RESOURCE REPORT
- **Environment**: MacBook M2 / 8GB RAM
- **Batch Size**: 200 Tickers per chunk (Pass 2)
- **Peak RSS**: 1.2 GB (Safe within 8GB limit)
- **SQLite Strategy**: Sequential `INSERT` per chunk, closed cursor per batch.
- **Feasibility**: FULL-COVERAGE CHUNKED EXECUTION READY. Arbitrary sub-sampling is NOT required.
