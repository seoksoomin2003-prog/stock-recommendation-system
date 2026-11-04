# P2 News Engine Normalization Report

This document specifies the design, implementation details, and verification outcomes for the News Engine Normalization (P2) phase.

## 1. Contextual Sentiment Analysis
We replaced simple keyword matches with context-aware logic:
- Negation detection (e.g., flip or dampen scores for negative structures).
- Mixed sentiment and contrary phrases (e.g., `"shares fall despite strong earnings"` resolves to a negative/mixed score `-0.4` with reduced confidence `0.5`).
- Normalization bounds: Output is strictly clipped to `[-1.0, 1.0]` and robustly protected against `NaN` or `Inf`.

---

## 2. Event-Specific Decay & Priority
- Event categorization: Classifies articles into types (`earnings`, `guidance`, `revenue`, `profit`, `M&A`, `regulatory`, `management`, `Fed`, `geopolitical`, etc.).
- Event specific weights: Evaluated differently in max pooling.
- Decays per event type:
  - Fast decay (`lambda = 0.3-0.5`): product launches, analyst ratings, general news.
  - Medium decay (`lambda = 0.1-0.25`): earnings, guidance, macro events.
  - Slow decay (`lambda = 0.02-0.05`): structural acquisitions (M&A), legal disputes (lawsuits), management reshufflings, and geopolitical events.
- Prevent look-ahead bias: Calculate `days_ago` relative to the publication time relative to `evaluation_timestamp` (rejects future-dated news).

---

## 3. Article Deduplication
Filters repeating/duplicate reports:
- Jaccard similarity threshold: Word-level overlap similarity > 0.65.
- Time window constraint: Evaluated as a duplicate if published within 24 hours of each other.
- Duplicate penalty: Reduces confidence score by 50% for secondary duplicate items instead of raw removal if they contain distinct metadata.

---

## 4. News Source Weighting
Source Quality Scale:
- Tier 1 (`1.0`): WSJ, Reuters, CNBC, AP, Bloomberg, SEC, regulatory publications, official press releases.
- Tier 2 (`0.8`): Financial specialists (Financial Times, Yahoo Finance, Motley Fool, Seeking Alpha, MarketWatch, Investor's Business Daily, Nasdaq).
- Tier 3 (`0.4`): General media, blogs, aggregators (Reddit, Substack, Medium, Hackernews, Twitter).
- Tier 4 (`0.2`): Unknown.

---

## 5. Fail-Safe and Telemetry
- Robust exceptions wrapper: Protects against system crashes from rate-limits or malformed JSON payloads.
- Bounded default outputs: Returns neutral `0.0` or empty results on error.
- Telemetry format logging:
  `[TELEMETRY] ticker=... article_count=... unique_article_count=... sentiment=... buzz=... event_type=... status=OK`

---

## 6. Verification Outcomes
All tests are implemented in `tests/test_news_engine_normalization.py` and run fully mocked (no live network requests).

- **TEST 1 — Valid Headline Sentiment**: `[PASS]`
- **TEST 2 — Positive Headline ("earnings beat expectations")**: `[PASS]`
- **TEST 3 — Negative Headline ("faces lawsuit")**: `[PASS]`
- **TEST 4 — Mixed Headline ("shares fall despite strong earnings")**: `[PASS]`
- **TEST 5 — Event-Specific Time Decay**: `[PASS]`
- **TEST 6 — Jaccard Deduplication**: `[PASS]`
- **TEST 7 — Source Quality Penalty**: `[PASS]`
- **TEST 8 — High-Impact Event Weights (Fed)**: `[PASS]`
- **TEST 9 — API Fail-Safe & Fallback**: `[PASS]`
- **TEST 10 — NaN/Inf Protection**: `[PASS]`
- **TEST 11 — Look-Ahead Bias Prevention**: `[PASS]`
- **TEST 12 — Multiple Tickers Independence**: `[PASS]`
- **TEST 13 — Local Mode Safety (No Ollama/Model loads)**: `[PASS]`
