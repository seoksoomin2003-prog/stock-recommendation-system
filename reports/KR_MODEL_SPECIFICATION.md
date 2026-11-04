# KR Model Specification: `KR-EXP-0.1` (status: **EXPERIMENTAL**)

Code: `markets/kr/model.py`, `markets/kr/pipeline.py`. Data spec: `KR-DATA-0.1`. Account mapping: `KR-ACCT-0.1` (not used by this version). Research basis: `KR_MODEL_RESEARCH_SPECIFICATION.md`.

The model is **independent of P6-11B**:

- it shares no factor, weight, normalisation, threshold, cap or exit rule with the US engine;
- it imports nothing from `core/`, which a test enforces.

It is a pre-specified baseline for **prospective paper observation**. It is not validated, and it is not approved for use as a recommendation.

## 1. Universe

The KOSPI + KOSDAQ liquid-300 (`P6-22_KR_DATA_SPECIFICATION.md` §5), rebuilt at every run.

## 2. Gate (before normalisation)

A member is scored only if all of the following hold:

- its series status is REAL: not STALE, HALTED or UNAVAILABLE as of the latest completed session;
- every active factor is computable from valid bars.

Otherwise it is `QUARANTINED` with its reasons, and it does not influence the cross-sectional statistics. Missing values are never filled.

## 3. Factors (adjusted close; KRX sessions; no look-ahead)

| Factor | Definition | Direction | Minimum history |
|---|---|---|---|
| MOM_6_1 | adj(t−21) / adj(t−126) − 1 | higher is better | 127 sessions |
| REV_1M | −(adj(t) / adj(t−21) − 1) | higher is better | 22 |
| LOWVOL_60 | −std(daily log returns over the last 60 sessions), with ≥ 55 valid | higher is better | 61 |

## 4. Score and ranking

1. Winsorise each factor at the 1st/99th percentile of the gated cross-section, then z-score (population std). If a factor's std is 0, its z is NaN.
2. Score = equal-weight mean of the three z-scores (1/3 each). It is defined only when all three exist.
3. Rank by score descending; ties are broken by `security_key` ascending, which makes the ranking deterministic.

**Direct evaluation** (`app.py --market KR evaluate`):

- a security inside the universe gets its in-universe rank;
- an eligible security outside the universe is standardised **against** the universe's winsorisation bounds, mean and std. It never changes them. It gets a score and a percentile versus the universe.

Direct evaluations are never tracked.

## 5. Portfolio (paper only; no orders)

| Rule | Value |
|---|---|
| Positions | TOP-10 by rank |
| Weight | equal, 10% target each |
| Concentration | at most 3 names per KRX industry (KIND 업종). A name that would exceed the cap is skipped (`INDUSTRY_CAP`), and selection continues down the ranking. |
| Shares | whole shares: floor(capital × 10% / reference close). The remainder is cash (KRW). |
| Unfunded positions | If one share costs more than the 10% slice, the position gets 0 shares and is flagged `funded: false` / `unfunded_positions`, and the slice stays in cash. **Selection never depends on capital.** The tracked observation measures the signal regardless. Example: in the first live run, 삼성전기 at 1,115,000 KRW with 10M KRW capital. |
| Capital | explicit KRW (`--capital` or `QPP_CAPITAL_KRW`); no default; never converted from USD |
| Entry | open of the first KRX session on or after `entry_not_before` (`KR_TRACKING_SPECIFICATION.md` §3) |
| Exit / horizon | close of session 20; no stop-loss; no rebalancing inside the window |
| Status | `REAL RECOMMENDATION` only for a full liquid-300 run with all 10 positions; bounded runs are `PARTIAL`; `NO VALID RECOMMENDATION` otherwise |

## 6. Validation gates (all required before the status may change from EXPERIMENTAL)

Each gate needs explicit user approval, and passing any of them would require a new version string.

1. ≥ 30 completed prospective observations from ≥ 6 non-overlapping scan dates (20+ sessions apart).
2. Official KRX traded value (`KRX_API_KEY`) used for the universe in those runs.
3. Mean excess vs the matched index, net of the 25 bps/side scenario, reported with its dispersion. Positive results are not presumed, and nothing is optimised on this record.
4. Data-quality incident review: quarantine rates, stale rates and DATA_GAP outcomes.
5. A written decision record. An unfavourable result keeps the model EXPERIMENTAL or retires it.

## 7. Versioning

- Any change to the factors, weights, transformation, gate or portfolio rules requires a new version (`KR-EXP-0.2`, …).
- Tracking summaries are split by model version, and versions are never pooled.
- The pre-registered rule is reused for any new candidate.
