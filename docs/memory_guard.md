# Memory Guard Architecture & Design Report

Memory Guard is an autonomous runtime resource safety system built specifically to protect the Alpha Scoring Pipeline under memory constraints, preventing macOS swaps, processes OOM, and system freezing (especially on M2 MacBook 8GB memory environments).

---

## 1. Architecture Overview
Memory Guard operates as an admission control gating and cleanup subsystem integrated early into each pipeline execution loop.

```
Startup
  │
  ▼
MemoryGuard.initialize() ──► Measure baseline RSS & choose profile (Local vs Production)
  │
  ▼
Main.run_live_cycle()
  │
  ├─► MemoryGuard.check_and_cleanup()
  │     ├─► Sample Process RSS & System Available Memory
  │     ├─► Detect leaks (monotonic growth check)
  │     └─► Run cleanups if WARNING/CRITICAL/EMERGENCY (Clear caches, invoke gc.collect())
  │
  ▼
Task Admission Gating
  ├─► MemoryGuard.allow("llm")       ──► Block/Allow Ollama
  ├─► MemoryGuard.allow("rag")       ──► Block/Allow Chroma DB
  └─► MemoryGuard.allow("embedding") ──► Block/Allow SentenceTransformer
```

---

## 2. Platform-Agnostic Sensing Layers
To eliminate external dependencies, Memory Guard uses native shell & proc system integrations:
- **macOS Sensor**: Parses `ps -o rss=` for exact process RSS, and parses `vm_stat` page sizes/page counts for system available memory.
- **Linux Sensor**: Parses `/proc/self/status` (VmRSS) and `/proc/meminfo` (MemAvailable).
- **Fallback Sensor**: Uses Python's standard `resource.getrusage`.
- **Telemetry**: Exposes peak RSS, available system memory, leak status, and optional `tracemalloc` snapshots for hot path diagnostics.

---

## 3. Thresholds and State Machine
We enforce a thread-safe state machine utilizing the following threshold configurations:

### Local Profile (8GB M2 MacBook)
- **WARNING**: 1,000 MB RSS / 70% System Memory Used
- **CRITICAL**: 1,500 MB RSS / 80% System Memory Used
- **EMERGENCY**: 1,800 MB RSS / 84% System Memory Used
- **RECOVERY**: 800 MB RSS / 65% System Memory Used

### Production Profile (AWS Linux Server)
- **WARNING**: 4,000 MB RSS / 85% System Memory Used
- **CRITICAL**: 8,000 MB RSS / 93% System Memory Used
- **EMERGENCY**: 12,000 MB RSS / 97% System Memory Used
- **RECOVERY**: 3,500 MB RSS / 80% System Memory Used

### Hysteresis & Oscillation Prevention
Transitions to a higher severity state (NORMAL -> WARNING -> CRITICAL -> EMERGENCY) are instantaneous upon violation. However, recovering to a lower severity state (CRITICAL -> RECOVERY -> NORMAL) requires `MEMORY_RECOVERY_CYCLES = 3` continuous steps of stability below the recovery limits. If memory surges during this recovery window, recovery is aborted.

---

## 4. Priority-Based Degradation & Admission Control

| State | Concurrency Factor | Gated Workloads | Fallback / Degradation Behavior |
|---|---|---|---|
| **NORMAL** | 1.0 | None | Full functional pipeline execution. |
| **WARNING** | 0.5 | Caches cleared | Halves concurrency, flushes caches, continues calculation. |
| **CRITICAL** | 0.2 | LLM, RAG, Embeddings | Blocks Ollama, blocks vector DB init, blocks SentenceTransformer. Reverts to local Jaccard and neutral fundamental templates. |
| **EMERGENCY**| 0.0 | All Heavy + Optional | Additionally blocks optional data providers and new ticker runs. Core Factor scoring is preserved. |

---

## 5. Verification Outcome
All states, transitions, admission blocks, cache flushes, and mathematical scoring invariance were validated using unit tests inside `tests/test_memory_guard.py` and integration tests inside `tests/test_memory_integration.py`:
- **TEST 1 — NORMAL -> NORMAL**: `[PASS]`
- **TEST 2 — WARNING Threshold**: `[PASS]`
- **TEST 3 — CRITICAL Threshold**: `[PASS]`
- **TEST 4 — EMERGENCY Threshold**: `[PASS]`
- **TEST 5 — CRITICAL -> LLM Blocked**: `[PASS]`
- **TEST 6 — CRITICAL -> RAG Blocked**: `[PASS]`
- **TEST 7 — CRITICAL -> Embedding Blocked**: `[PASS]`
- **TEST 8 — Cache Cleanup Expired**: `[PASS]`
- **TEST 9 — Recovery Threshold**: `[PASS]`
- **TEST 10 — Recovery Cycles Complete**: `[PASS]`
- **TEST 11 — Hysteresis (No Oscillation)**: `[PASS]`
- **TEST 12 — Provider Failure Fallback**: `[PASS]`
- **TEST 13 — Leak Detection (Suspected)**: `[PASS]`
- **TEST 14 — Local Profile Applied**: `[PASS]`
- **TEST 15 — Production Profile Applied**: `[PASS]`
- **TEST 16 — Alpha Scoring Invariance**: `[PASS]`
- **Scenario A — Normal memory + AAPL**: `[PASS]`
- **Scenario B — WARNING + AAPL**: `[PASS]`
- **Scenario C — CRITICAL + AAPL (Heavy blocked, fallback used)**: `[PASS]`
- **Scenario D — EMERGENCY (New workloads blocked)**: `[PASS]`
- **Scenario E & F — Recovery to Normal**: `[PASS]`
