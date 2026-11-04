# P3-1 Production vs Local Validation Report

## Executive Summary
- **Status**: PASS_WITH_EXPECTED_DIFFERENCES
- **Validation Run Date**: 2026-08-10T21:39:02.965346
- **Spearman Correlation**: 1.0000
- **Kendall Correlation**: 0.0000
- **Deterministic Outcomes**: YES

---

## Core Alpha Consistency
All core price-based and mathematical indicators match exactly between environments:
- **Core Factor MAE**: 0.000000
- **Core Factor RMSE**: 0.000000
- **Core Factor Max Delta**: 0.000000
- **Unexplained Core Deltas**: 0.000000

---

## Alternative Data Delta
Differences in alternative factor feeds are fully explained by the active offline fallbacks configured in Local Mode:
- **News Engine**: Uses Local Jaccard fallback vs Production contextual RAG.
- **Google Trends**: Uses Neutral Fallback (`50.0`) in Local Mode vs Production API.
- **SEC EDGAR**: Uses Mock Fallback (`0.0`) in Local Mode vs Production submissions.

---

## Final Score Metrics
- **Production Mean Score**: -1.0000
- **Local Mean Score**: -1.0000
- **MAE**: 0.000000
- **RMSE**: 0.000000
- **Maximum Absolute Delta**: 0.000000

---

## Ranking Consistency
- **Spearman**: 1.0000
- **Kendall**: 0.0000
- **Top-1 Agreement**: YES
- **Top-3 Overlap**: 3/3

---

## Reproducibility Manifest
- **Production Run A vs B**: IDENTICAL
- **Local Run A vs B**: IDENTICAL

---

## Resource Manifest
- **Production Peak RSS**: 91.52 MB
- **Local Peak RSS**: 91.94 MB
- **Production Runtime**: 0.0269 seconds
- **Local Runtime**: 0.0170 seconds
- **Memory Guard State**: NORMAL

---

## Environment Manifest
- **OS**: Darwin (24.5.0)
- **Python**: 3.14.2
- **CPU**: arm64
- **Git Commit**: Unknown
- **Config Hash**: -5398560491450383480

---

## Final Verdict
**SAFE TO PROCEED**
