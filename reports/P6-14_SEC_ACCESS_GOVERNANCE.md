# P6-14 SEC Access Governance

## Policy: ENFORCED

1. **User-Agent**: Explicitly declared as `Antigravity Research (contact@example.com)` per SEC fair-access guidelines.
2. **Rate Limiting**: The system implements automated backoff logic upon encountering HTTP 429 status codes.
3. **Ingestion**: Prefers incremental local parquet/sqlite caching to minimize redundant API requests.
