# P6-14 Optional Provider Isolation

## Verdict: ISOLATED (REJECTED-FOR-PRODUCTION)

1. **PyTrends**: Archived status, strict 429 rate limits.
2. **NewsAPI**: Limited 30-day historical window on free tiers.

**Action**: Both dependencies were refactored to gracefully return `UNAVAILABLE` (`np.nan`) when missing or failing. This prevents arbitrary program crashes.
**Quarantine Update**: Missing alternative data does NOT trigger the candidate-level quarantine firewall because these features are non-mandatory for the frozen P6-11B logic.
