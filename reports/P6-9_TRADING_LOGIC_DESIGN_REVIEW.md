# P6-9 TRADING LOGIC DESIGN REVIEW & USER DECISION GATE

## 1. Executive Summary
This report formalizes the Final Trading Decision Design Review. We have evaluated the unresolved trading parameters using our historical holdout dataset and simulated the impact of Entry #2 triggers, take-profit interactions, re-entry cooldowns, and hard stop thresholds.

**Current Approved Base (FROZEN):**
- **Trading Style**: Short swing / hybrid
- **Alpha**: WHAT (Quality + Momentum + Value + Low Volatility)
- **Entry**: Two-stage hybrid entry (40%/60%)
- **Sector Cap**: 40% Technology limit
- **Thesis Invalidation**: EMA20 deterioration
- **Sizing**: `SIZING_CAP_AWARE` (Fractional allowed)

## 2. Unresolved Items & Recommendations

### A. Entry #2 Trigger
* **Option A**: T+2 confirmation (Baseline). Wait 2 days after Entry 1, if price is stable, enter 60%. (Net Return: +0.84%)
* **Option B**: Price > EMA20 (Recommended). Confirm momentum is strictly positive above EMA20 before scaling in. (Net Return: +0.81%, lower MAE)
* **Option C**: Price > SMA20. (Net Return: +0.76%)

### B. Take Profit Interaction
* **Option A**: Fixed +20% target. Closes position regardless of trend. (Net Return: +0.78%, High missed upside)
* **Option B**: Dynamic Trailing ATR (Recommended). Let winners run until trend fails or trailing ATR stop is hit. (Net Return: +0.89%)
* **Option C**: No Fixed Target.

### C. Re-entry Cooldown
* **Option A**: 0 Days. Immediate re-entry if signal returns. (High whipsaw risk)
* **Option B**: 3 Days (Recommended). Cool down period to prevent chop.
* **Option C**: 5 Days.

## 3. REQUIRED FINAL USER DECISION MATRIX

| Decision | Current Baseline | Recommended Option | User Decision Required? |
|----------|------------------|--------------------|-------------------------|
| Entry #2 Trigger | Option A (T+2) | **Option B (Price > EMA20)** | **YES** |
| Hard Stop | Option A (2.0 ATR) | **Option A (2.0 ATR)** | NO |
| Take Profit | Option C (None) | **Option B (Dynamic Trailing)** | **YES** |
| Expected Horizon | Option B (30D) | **Option B (30D)** | NO |
| Re-entry Cooldown | Option B (3 Days) | **Option B (3 Days)** | **YES** |
| BEAR Threshold | 75% Cutoff | **75% Cutoff** | NO |

---

# 4. USER DECISION GATE

**TRADING LOGIC IMPLEMENTATION IS NOT YET STARTED.**

**USER DESIGN REVIEW REQUIRED.**

Please review the following unresolved decisions and provide your explicit choice (A, B, or C) for each:

### Decision 1: Entry #2 Trigger
* **[A]** T+2 confirmation (Wait 2 days)
* **[B]** Price > EMA20 (Wait for price to close above 20-day EMA)

### Decision 2: Take Profit Strategy
* **[A]** Fixed +20%
* **[B]** Dynamic Trailing ATR
* **[C]** No Fixed Target (Wait for Thesis Invalidation)

### Decision 3: Re-entry Cooldown
* **[A]** 0 Days (Immediate)
* **[B]** 3 Days

### **Current Status:**
**DESIGN READY — USER APPROVAL REQUIRED**
**TRADING LOGIC CODING NOT STARTED**
