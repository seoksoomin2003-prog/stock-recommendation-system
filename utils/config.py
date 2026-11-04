import os

APP_MODE = os.getenv("APP_MODE", "local")

# Ollama Settings
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3")
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "120"))
MAX_CONCURRENT_LLM_REQUESTS = int(os.getenv("MAX_CONCURRENT_LLM_REQUESTS", "2"))

# Multi-factor weights
DEFAULT_FACTOR_WEIGHTS = {
    "momentum": 0.35,
    "quality": 0.25,
    "value": 0.20,
    "low_volatility": 0.20
}

# Hybrid Score weights (Alpha combination)
HYBRID_WEIGHTS = {
    "factor": 0.5,
    "fundamental": 0.2,       # [NEW] RAG 기반 펀더멘탈 알파 추가
    "sentiment": 0.15,
    "alt_data": 0.15
}

# Alternative Data Settings
ALT_DATA_WEIGHTS = {
    "google_trends": 0.4,
    "sns_sentiment": 0.3,
    "news_momentum": 0.3
}

# Cross-Asset Macro Settings
MACRO_ADJUSTMENT_WEIGHTS = {
    "yield_impact": 0.5,    # 금리 영향력
    "usd_impact": 0.3,      # 달러 영향력
    "oil_impact": 0.2       # 유가 영향력
}

# Sector Sensitivity (Macro Beta)
SECTOR_MACRO_BETA = {
    "growth": {"yield": -1.5, "usd": -0.5}, # 금리 상승 시 부정적
    "value": {"yield": 0.8, "usd": 0.2},    # 금리 상승 시 긍정적
    "energy": {"oil": 1.2},                 # 유가 상승 시 긍정적
    "tech": {"yield": -1.2}                 # 기술주 (금리 민감)
}

# Meta-Alpha (Ensemble) Settings
META_ALPHA_SETTINGS = {
    "performance_window": 60,   # 최근 60일 성과 기준 (Rank IC)
    "min_weight": 0.05,         # 최소 가중치 (0.05 이하로 떨어지지 않음)
    "max_weight": 0.70,         # 최대 가중치 (지나친 쏠림 방지)
    "decay_factor": 0.1,        # 가중치 변화 Smoothing 계수
    "drift_threshold": -0.1,    # 성과가 이 값 이하로 하락 시 비중 절반 축소 (Alpha Stop-loss)
    "min_learning_samples": 4   # [NEW] 최소 학습 샘플 (기존 하드코딩 제거)
}

# Backtest Settings
BACKTEST_SETTINGS = {
    "train_years": 3,
    "test_months": 6,
    "rebalance_freq": "M",
    "fee_rate": 0.0015, # 0.15% (Fee+Slippage)
    "top_k_pct": 0.2,
    "initial_capital": 100000000 # 1억 (기본 설정)
}

# Advanced Risk Settings
TAIL_RISK_SETTINGS = {
    "vol_spike_threshold": 2.5,   # 변동성 Z-score 임계값
    "mdd_limit": -0.15,          # 최대 허용 MDD (15%)
    "crash_prob_threshold": 0.7,  # 크래시 확률 임계값
    "emergency_stop_mdd": -0.20,  # 20% 하락 시 즉시 청산
    "risk_score_lambda": 20.0,   # 리스크 페널티 기본 가중치 (Deduction 모델)
    "tail_risk_percentile": 0.90  # 상위 10% 위험 종목 가중 처벌
}

CAPACITY_SETTINGS = {
    "max_adv_participation": 0.05, # 일평균 거래량(ADV)의 최대 5%까지만 점유
    "target_aum": 1000000000,     # 목표 운용 자산 (10억)
    "decay_half_life_aum": 5000000000 # 50억 도달 시 알파 반감기
}

# Learning Settings
LEARNING_RATE = 0.01
CLIPPING_VALUE = 0.5

# News & Alternative Data API Settings
# NewsAPI (newsapi.org)
# P6-18: secrets are never hardcoded.  The previous literal default was
# removed (it was flagged in P6-11A); NewsAPI is optional and not part of the
# canonical recommendation route.
NEWS_API_KEY = os.getenv("NEWS_API_KEY", "")

# Google Trends Settings
GOOGLE_TRENDS_CONFIG = {
    "hl": "en-US",    # 언어 설정 (en-US, ko-KR 등)
    "tz": 360,        # 타임존 (필수)
    "timeout": 10,    # API 타임아웃
    "retries": 3,     # 제시도 횟수
    "backoff_factor": 0.5
}

# Execution Alpha Settings
EXECUTION_SETTINGS = {
    "n_slices": 5,              # 주문 분할 횟수 (TWAP/VWAP)
    "impact_coefficient": 0.1,  # 시장 충격 계수 (k)
    "impact_exponent": 0.5,     # 시장 충격 지수 (alpha)
    "min_participation_rate": 0.01,
    "max_participation_rate": 0.1,
    "default_spread_pct": 0.0002, # 0.02% 기본 호가 스프레드
    "min_volume_threshold": 500000 # [NEW] 일평균 거래량 최소 50만주 (Liquidity Guard)
}

# Portfolio Optimization Settings
PORTFOLIO_SETTINGS = {
    "method": "softmax-weighted",   # 'softmax-weighted', 'linear', 'risk-parity' (Equal Weighting 금지)
    "temperature": 0.5,             # 낮을수록 고득점 종목에 가중치 집중 (Conviction)
    "min_score_threshold": 30.0,    # 이 점수 미만 종목은 제외
    "max_individual_weight": 0.30,  # 단일 종목 최대 비중 (30%) - P6 승인 기준
    "max_sector_exposure": 0.40     # 섹터별 최대 노출도 (40%) - P6 승인 기준
}

# Decision Architecture Settings (P6-11B)
DECISION_SETTINGS = {
    "entry_1_weight": 0.40,
    "entry_2_weight": 0.60,
    "hard_stop_atr_multiplier": 2.0,
    "expected_horizon_days": 30,
    "reentry_cooldown_days": 3,
    "bear_alpha_threshold": 0.75
}

# Real-time Risk Management Settings
RISK_MANAGEMENT_SETTINGS = {
    "max_allowed_daily_var": 0.02,  # 일간 최대 허용 VaR (2% of equity)
    "var_confidence_level": 0.95,   # VaR 신뢰수준
    "var_lookback_days": 252,       # VaR 계산용 룩백 기간
    "emergency_reduction_ratio": 0.5 # 극단적 상황 발생 시 기본 축소 비율
}

# [NEW] Fundamental RAG Settings
RAG_SETTINGS = {
    "db_path": "./data/vector_db",
    "embedding_model": "nomic-embed-text",
    "chunk_size": 1200,             # 금융 보고서 문맥 유지를 위해 약간 크게 설정
    "chunk_overlap": 250,
    "search_k": 8,                  # 더 넓은 컨텍스트 확보
    "score_threshold": 0.4          # 관련성 낮은 청크 필터링
}

# [NEW] Fundamental Engine Analysis Weights
FUNDAMENTAL_ANALYSIS_CONFIG = {
    "weights": {
        "cashflow": 0.25,           # 가중치 재조정 (25%씩 균등)
        "earnings_quality": 0.25,
        "growth_resilience": 0.25,
        "debt_quality": 0.25        # [NEW] 부채 질적 분석 추가
    },
    "score_mapping": {
        "HIGH": 95.0,
        "STABLE": 70.0,
        "NEUTRAL": 50.0,
        "WEAK": 25.0,
        "LOW": 5.0,
        "RED_FLAG": 0.0,
        "GOOD": 95.0,               # [NEW] 부채 분석용
        "BAD": 5.0                  # [NEW] 부채 분석용
    }
}

# Centralized Resilience Configuration
API_CONNECT_TIMEOUT = 5
API_READ_TIMEOUT = 10
API_MAX_RETRIES = 2
API_BACKOFF_BASE = 1.0
API_BACKOFF_MAX = 5.0

# Local Workload Control Limits
MAX_LOCAL_TICKERS = 3
MAX_LOCAL_LOOKBACK_DAYS = 365

# Memory Guard Configuration
MEMORY_GUARD_ENABLED = True
MEMORY_WARNING_PERCENT = 75.0      # 75% system memory usage
MEMORY_CRITICAL_PERCENT = 88.0     # 88% system memory usage
MEMORY_RECOVERY_PERCENT = 70.0     # 70% system memory usage
MEMORY_RECOVERY_CYCLES = 3         # Cycles of stability needed to recover
MEMORY_WARNING_RSS_MB = 1000.0     # 1GB process RSS limit
MEMORY_CRITICAL_RSS_MB = 1500.0    # 1.5GB process RSS limit
MEMORY_RECOVERY_RSS_MB = 800.0     # 800MB process RSS recovery limit
MEMORY_SAMPLE_INTERVAL = 1         # Sampling interval in seconds

# Canonical Research Runtime Feature Flag ('v2' or 'v1')
RESEARCH_RUNTIME = os.getenv("RESEARCH_RUNTIME", "v2")



# ---------------------------------------------------------------------------
# P6-18 Canonical live pipeline runtime settings (operational, NOT model math).
# None of these values participate in factor, scoring, MODEL_RANK_E, liquidity,
# BEAR, sizing, entry/exit or horizon calculations.
# ---------------------------------------------------------------------------
# SEC fair-access policy asks automated clients to declare a contact.  Set
# SEC_USER_AGENT to "<app name> <your contact email>" (shell or project .env).
# P6-19: there is NO default -- the previous default used a placeholder
# example.com address, i.e. a fabricated contact.  Without a valid value the
# SEC is not queried at all (see utils.runtime_config.sec_user_agent_status).
SEC_USER_AGENT = os.getenv("SEC_USER_AGENT", "").strip()
SEC_MAX_REQUESTS_PER_SECOND = 8.0          # SEC limit is 10/s; stay below it
YF_INFO_MAX_REQUESTS_PER_SECOND = 3.0      # conservative Yahoo pacing
FINANCIAL_FETCH_WORKERS = int(os.getenv("QPP_FINANCIAL_WORKERS", "4"))
MARKET_DOWNLOAD_CHUNK = int(os.getenv("QPP_MARKET_CHUNK", "100"))
PROVIDER_MAX_RETRIES = 2
LIVE_PRICE_LOOKBACK_DAYS = 430
ADV_WINDOW_DAYS = 20                       # 20-day average daily volume (P6-12A definition)
FINANCIAL_CACHE_TTL_HOURS = 20             # fundamentals freshness window for cached observations
SEC_ANNUAL_MAX_AGE_DAYS = 550              # latest annual period older than this is STALE
RUNS_DIR = os.getenv("QPP_RUNS_DIR", "runs")
# ".nosync" keeps iCloud from offloading the hot-path cache (offloaded reads block).
PROVIDER_CACHE_DIR = os.getenv("QPP_CACHE_DIR", "cache.nosync/provider")
