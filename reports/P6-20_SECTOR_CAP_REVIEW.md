# P6-20 Sector-Cap Contract Review

Date: 2026-11-04 · Status: **DECISION REQUIRED IN A FUTURE PHASE.** The behaviour is unchanged in P6-20.

## Question

The frozen engine limits the TOP-5 to at most 40% (2 of 5 slots) in `Technology` only. Other sectors are
not capped; they are only reported when they exceed 40%. Is this the approved rule, or an implementation
limitation?

## 1. Original specification (documentary evidence)

| Source | Wording | Scope it implies |
|---|---|---|
| `reports/P6-9_USER_DECISION_GATE.md` ("Current Approved Base (FROZEN)") | "**Sector Cap**: 40% Technology limit" | Technology only |
| `reports/P6-10_FINAL_LIFECYCLE_VALIDATION.md` | "Sector Cap: 40% Technology" | Technology only |
| `reports/P6-11B_STRATEGY_IMPLEMENTATION_MATRIX.json` (the P6-11B freeze) | Decision "Sector Cap", Research Decision "**40% Technology**", User Approval "**Approved**", test `test_21_technology_le_40` | Technology only |
| `reports/P6-13_FINAL_JOINT_RESEARCH_REPORT.md` | "Technology Sector Cap: 40% (UNCHANGED)" | Technology only |
| `reports/P6-11A_REPAIR_REPORT.md`, `P6-11A5_FINAL_INTEGRITY_GATE.md` | "Max Sector: 40%" (config check) | ambiguous: describes `PORTFOLIO_SETTINGS` |
| `reports/P6-17_FROZEN_CORE_BASELINE.md`, `P6-17_MODEL_RANK_E_FREEZE.md` | "`technology_cap` / `max_sector_exposure` = 0.40"; "caps … sector exposure at 40%" | ambiguous: names both keys |
| `utils/config.py` `PORTFOLIO_SETTINGS["max_sector_exposure"] = 0.40` | comment: "섹터별 최대 노출도 (40%)", i.e. per-sector maximum exposure | every sector |
| P6-5/6/7 and P6-8 research (`P6-8_SECTOR_CAP_ANALYSIS.json`) | caps 0.30–1.00 tested; **identical** results for every cap value (60 trades, same return and drawdown) | the cap never bound in research data |

**Finding.** The rule the user approved and froze in P6-11B is "40% **Technology**". The implementation
matches it. The generic per-sector wording comes from the configuration comment and from later
descriptions that paraphrase it. The research never tested a binding sector cap, so no evidence favours
either reading.

## 2. Actual implementation (frozen, sha256-pinned)

`core/decision_engine.py::_optimize_portfolio`:

```python
max_tech = 2  # 40% cap on 5 slots
is_tech = c.get('sector') == 'Technology'
if is_tech and sector_counts.get('Technology', 0) >= max_tech:
    if len(top5) < 5:
        self._add_to_watchlist(watchlist5, c, idx, "SECTOR_CAP_CONSTRAINT")
    continue
```

- `DecisionEngine.config["technology_cap"]` is loaded from `PORTFOLIO_SETTINGS["max_sector_exposure"]`,
  but it is **never read**: the limit is the literal `max_tech = 2`.
- The comparison is an exact match on the provider label `Technology`, which is Yahoo's sector taxonomy
  (P6-18 input definition B2). Yahoo classifies GOOGL and META as `Communication Services` and AMZN as
  `Consumer Cyclical`, so they are not counted. That is not GICS "Information Technology".
- `core/portfolio_engine.py::_apply_sector_constraints` does apply a generic per-sector 40% cap. It belongs
  to the legacy `main.py` softmax/risk-parity path, which is **not** on the canonical recommendation route.
- Equal 20% sizing means 40% equals two names, so the generic cap would also be "at most 2 names per
  sector".

## 3. Observed behaviour (all recorded runs, 2026-11-04)

| Run | Scope | TOP-5 sector exposure | Cap bound? | Sector counts in ranked top 10 |
|---|---|---|---|---|
| `20261104T070854Z_market_scan_773448` | bounded 25 | Financial Services 40%, Utilities 40%, Healthcare 20% | no | Utilities 3, Financial Services 2, … |
| `20261104T071145Z_market_scan_e16f62` (pre-fix) | full | Technology 40%, others 20% | no | Technology 3 |
| `20261104T105421Z_market_scan_e320cd` | bounded 25 | Financial Services 40%, Utilities 40%, Healthcare 20% | no | Utilities 3 |
| `20261104T105453Z_market_scan_9072c9` (pre-fix) | full | Technology 40%, others 20% | no | Technology 3 |
| `20261104T110528Z_market_scan_4f4b37` (pre-fix) | full | Technology 40%, others 20% | no | Financial Services 3, Utilities 3 |
| `20261104T111004Z_market_scan_953827` (valid) | full | Technology 40%, Consumer Defensive / Utilities / Communication Services 20% each | no | **Financial Services 4**, Technology 2 |

- No run has produced `SECTOR_CAP_CONSTRAINT`, and no TOP-5 has exceeded 40% in any sector.
- Concentration in non-Technology sectors does appear in the ranked list: 4 Financial Services names in
  the valid run's top 10, and 3 Utilities in the bounded runs.
- A deterministic test (`tests/test_p6_20_prospective_tracking.py::TestDiagnostics::test_sector_exposure_reported_frozen_cap_unchanged`)
  confirms the frozen engine selects five Healthcare names, giving 100% Healthcare.

## 4. Risks

1. **Unbounded concentration outside Technology.** A sector-wide shock (rates for Utilities and Financials,
   regulation for Healthcare) could hit 3–5 of 5 positions at once. The frozen 2×ATR stops limit the loss
   per position, not the correlation between positions.
2. **Taxonomy dependence.** Whether a mega-cap counts as "Technology" depends on Yahoo's labels. A label
   change at the provider changes the cap's reach without any code change.
3. **Documentation drift.** Configuration and later reports describe a per-sector cap that the engine does
   not apply. P6-19/P6-20 reports, run warnings and this review now state the actual scope.

## 5. Does changing it require unfreezing?

**Yes.** Any of the following changes the approved P6-11B rule and the sha256-pinned
`core/decision_engine.py`, or adds a decision step after it, which alters which stocks are recommended:

- a generic 40% cap;
- a different taxonomy;
- enforcement in a post-processing overlay.

None of these is permitted without explicit user approval and a new parity baseline.

## 6. Options for a future decision (P6-21 or later; not implemented)

| Option | Change | Pros | Cons |
|---|---|---|---|
| A. Keep (status quo) | none; continue warnings | Preserves the approved, frozen rule and comparability of the prospective record | Non-Technology concentration remains possible |
| B. Generic per-sector 40% cap (max 2 names per Yahoo sector) | edit frozen `_optimize_portfolio`; new frozen hash and parity baseline | Matches the config comment; bounds every sector | Changes the model mid-observation: observations before and after cannot be pooled. Unvalidated, because research never had a binding cap. |
| C. Option B plus mapping to GICS-like groups (e.g. count Communication Services or Interactive Media with Technology) | as B, plus a classification mapping | Closer to an economic exposure cap | Needs a sourced mapping; Yahoo's taxonomy is not GICS; more input-definition risk |
| D. Advisory only (current P6-20 behaviour) | none | Visible in every report, diagnostic and run warning | Advisory, not enforced |

**Recommendation.** Keep option A/D for the whole P6-20 observation period, so the prospective record
measures one unchanged model. In P6-21, review how often non-Technology concentration above 40% *would*
have occurred, using the ranked lists in the ledger, before deciding on option B or C. **User approval is
required** before any change.

## 7. What P6-20 does

- The behaviour is unchanged. Frozen hashes match, and `TestFrozenSourcePinned` passes.
- Every run reports its full `sector_exposure` and `sector_cap_warnings` (any sector above 40%).
- Tracking diagnostics report TOP-5 exposure, any sector above 40%, the sector counts in the ranked top 20,
  and the frozen cap scope ("Technology only").
