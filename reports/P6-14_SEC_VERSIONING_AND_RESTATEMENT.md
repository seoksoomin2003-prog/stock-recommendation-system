# P6-14 SEC Versioning and Restatement

## Mechanism: IMMUTABLE VERSIONING

When an amended filing (e.g., `10-Q/A`) is submitted to the SEC:
1. The original fact remains immutable in the database.
2. The amended fact is inserted as a distinct record (`is_amended=True`).
3. For simulation dates between the original filing and the amendment filing, the model strictly uses the original (unamended) value.
4. The amendment only becomes visible for simulation dates `>=` the amendment's `filed_at` timestamp.
