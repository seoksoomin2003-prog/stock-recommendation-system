# P1 Provider Behavior Matrix

| Component | Local Mode (`APP_MODE=local`) | Production Mode (`APP_MODE=production`) |
| :--- | :--- | :--- |
| **Ollama** | **DISABLED** (Skipped, returns mock JSON templates) | **ENABLED** (HTTP client calls to local/remote daemon) |
| **RAG** | **DISABLED / Lazy** (Returns neutral fallbacks, skips vector DB loading) | **ENABLED / Lazy** (Initializes Chroma & OllamaEmbeddings on first method call) |
| **Embedding** | **Lazy / Optional** (Bypasses download using Jaccard fallback metrics) | **Lazy** (Loads SentenceTransformer on demand, cached at instance level) |
| **Trends** | **Timeout / Fallback** (Timeouts connect: 5s, read: 10s. Max 2 retries, fallback: 50.0) | **Full / Resilience** (Timeouts connect: 5s, read: 10s. Max 2 retries, returns full data) |
| **News** | **Timeout / Fallback** (Deterministic news sentiment, offline fallback) | **Full** (Sentiment APIs and database records) |
| **SEC** | **Timeout / Fallback** (Offline simulated SEC filing fallbacks) | **Full** (Requests EDGAR filing metadata details) |
| **Social** | **Timeout / Fallback** (Bypassed / returns neutral baseline scores) | **Full** (Crawls social channels for mentions) |
