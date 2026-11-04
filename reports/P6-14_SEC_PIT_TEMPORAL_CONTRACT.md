# P6-14 SEC PIT Temporal Contract

## Mechanism: PIT-CAPABLE AFTER TEMPORAL SELECTION

Raw SEC Company Facts are not automatically Point-In-Time (PIT) safe. They only become PIT-compliant after strict temporal filtering.

**Selection Rule Enforced**:
For any simulation date `T`, a historical fact is only eligible if:
`filed_at <= T` AND `(accepted_at IS NULL OR accepted_at <= T)`

This physical firewall prevents future SEC amendments from leaking into past simulations.
