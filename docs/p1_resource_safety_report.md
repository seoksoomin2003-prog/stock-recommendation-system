# P1 Resource Safety & Runtime Resilience Report

This report documents the design, implementation, and verification of the Resource Safety and Network Resilience phase (P1) for the Alpha Scoring System.

## 1. Ollama Audit
Ollama HTTP POST calls were identified in:
- `ProductionFundamentalProvider.query_fundamental` (for financial insight scoring)
- `ProductionAliasGenerationProvider.run_llm_noise_filter` (for company entity alias classification)

**Safety Implementation:**
- Bypassed in Local Mode: When `APP_MODE=local`, the providers map to `LocalFundamentalProvider` and `LocalAliasGenerationProvider`, returning deterministic fallbacks and skipping Ollama entirely.
- Bypassed in RAGEngine: RAG lazy initialization checks `APP_MODE` and skips initializing Ollama connections when run locally.

## 2. RAG Audit
The LangChain-based PDF RAG components were identified in `core/rag_engine.py` (instantiating `Chroma`, `OllamaEmbeddings`, and `Ollama` LLM).

**Safety Implementation:**
- Lazy Construction: `RAGEngine.__init__` is now a zero-overhead constructor. It initializes all heavy components to `None` and does not call any database or network operations.
- Lazy Activation: All resource initialization is deferred to a private `_lazy_initialize` helper called at the beginning of method calls (`ingest_pdf`, `retrieve`, `generate_fundamental_insight`).
- Local Bypass: If `APP_MODE=local` is active, `_lazy_initialize` completes immediately without loading any LangChain, Chroma, or embedding classes.

## 3. Embedding Initialization Audit
HuggingFace `SentenceTransformer('all-MiniLM-L6-v2')` was loaded in `ProductionAliasGenerationProvider.__init__`.

**Safety Implementation:**
- Deferred Loading: Modified the provider constructor to only define `_fast_embedder = None`. The model is imported and loaded on the first call to `get_semantic_similarity` via a `_get_fast_embedder` helper.
- Memory Protection: Once loaded, the instance is cached at the provider level and reused across all tickers, preventing memory duplication.
- Local Bypass (No-Download): If `APP_MODE=local` is active, the SentenceTransformer is loaded with `local_files_only=True`, which prevents downloading from the Hugging Face Hub if missing, falling back to a lightweight Jaccard token metric.

## 4. API Call Audit
Network requests were identified in:
- `yfinance` download calls: `data/loader.py` (OHLCV prices, volume) and `core/cross_asset_engine.py` (Macro index changes).
- `yfinance` ticker calls: `data/loader.py` (Company financials).
- `newsapi` calls: `data/loader.py` (News headlines).
- `pytrends` calls: `alpha_engine/data/trends_engine.py` and `core/alternative_data_engine.py` (Investor attention).
- Ollama API post calls: `core/providers.py` (Fundamental/Alias queries).

## 5. Timeout Policy
All network requests are bound by central parameters in `utils/config.py`:
- `API_CONNECT_TIMEOUT = 5` (seconds)
- `API_READ_TIMEOUT = 10` (seconds)
A custom `TimeoutHTTPAdapter` mounts these parameters to the default session adapter to enforce constraints on yfinance and other requests calls.

## 6. Retry Policy
- `API_MAX_RETRIES = 2` (attempts: 1 initial + 2 retries).
- Retries transient errors only (Connect/Read timeouts, rate limits [429], and server errors [5xx]).
- Exponential backoff with random jitter is applied between attempts to prevent synchronization retry storms.
- Permanent errors (400, 401, 403, 404) fail immediately.

## 7. Fallback Policy
On request failure:
- **Market Data**: Reconstructs empty/neutral dataframes.
- **Financials**: Fills NaN for metrics.
- **News**: Falls back to offline mock news dataset.
- **Trends**: Generates a neutral score (e.g. 50.0).
- **Embeddings/LLM**: Bypasses optional layer and returns a degraded score.

## 8. Failure Telemetry
Exhausted network errors are written to logs using the format:
`[API_FAILURE] provider=... ticker=... attempts=... error=... fallback=NEUTRAL`
All credentials, API keys, and private tokens are excluded from logs.

## 9. Tests Performed
Three automated test suites were created and ran successfully:
1. `tests/test_local_resource_safety.py` (Tests 1 & 2)
2. `tests/test_embedding_lazy_loading.py` (Tests 3 & 4)
3. `tests/test_api_resilience.py` (Tests 5, 6, 7, 8, 9, 10)

## 10. Remaining Risks
- Rate limiting of public yfinance and Google Trends endpoints if the daily download quotas are exceeded by excessive backtesting runs.
