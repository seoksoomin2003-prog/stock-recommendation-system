# P6-10 FINAL TRADING LOGIC SPEC DRAFT

## Proposed State Machine
1. `CANDIDATE`: Passes basic liquidity & universe rules
2. `TOP5`: Ranked by MODEL_RANK_E, executable by SIZING_CAP_AWARE
3. `ENTRY_READY`: Technical setup valid (RSI pullback, SMA50 trend)
4. `ENTRY_1_EXECUTED`: 40% initial allocation placed
5. `ENTRY_2_PENDING`: Waiting for Close > EMA20 confirmation
6. `FULL_POSITION`: 100% target size achieved
7. `WATCH`: Early warning (e.g., BEAR regime risk reassessment)
8. `EXIT_CANDIDATE`: Thesis deterioration (Close < EMA20)
9. `EXIT_CONFIRMED`: Hard stop, Dynamic Trailing ATR, or confirmed deterioration
10. `EXITED`: Position zeroed
11. `REENTRY_COOLDOWN`: 3 trading day hold
12. `ELIGIBLE_AGAIN`: Can become a CANDIDATE again

## Priority Exit Conflict Resolution
If multiple exits trigger simultaneously, the most protective boundary wins:
`Hard Stop (ATR 2.0)` > `Thesis Invalidation (EMA20)` > `Dynamic Trailing ATR`
