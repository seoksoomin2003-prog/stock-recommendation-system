"""QSF 1.1 configuration: four independent profiles, score bands, gates and research defaults.

Every number here is a RESEARCH DEFAULT fixed in advance, not a fitted value.  Changing one requires a new
model version; nothing in the code tunes them.  QSF is a separate model: it never reads or changes P6-11B.
"""
from typing import Dict

MODEL_VERSION = "QSF-1.1.2"
STYLE_TO_STRATEGY = {"LONG": "LONG_TERM", "SWING": "SWING"}
SPEC_VERSION = "QSF_1_1_MASTER_SPECIFICATION"

MARKETS = ("US", "KR")
STRATEGIES = ("SWING", "LONG_TERM")
DOMAINS = ("TECHNICAL", "FUNDAMENTAL", "REGIME", "RISK", "EVENTS")
DOMAIN_LABELS = {"TECHNICAL": "기술적 분석", "FUNDAMENTAL": "기업 펀더멘털", "REGIME": "시장 국면",
                 "RISK": "위험·실행", "EVENTS": "이벤트·지배구조"}

# Factor tables: {domain: {factor_id: points}}.  Regime factors differ by market (spec 4.3).
_SWING_COMMON = {
    "TECHNICAL": {"trend_structure": 10, "relative_strength": 10, "momentum": 5, "breakout_volume": 10,
                  "volatility_structure": 5},
    "FUNDAMENTAL": {"earnings_revenue_quality": 3, "profitability": 2, "balance_sheet": 3, "cash_flow_quality": 2},
    "RISK": {"risk_reward": 6, "atr_risk": 5, "liquidity": 5, "drawdown_gap": 4},
    "EVENTS": {"earnings_calendar": 4, "material_disclosures": 3, "insider_activity": 3},
}
_LONG_COMMON = {
    "TECHNICAL": {"long_trend": 5, "relative_strength": 3, "momentum_persistence": 2},
    "FUNDAMENTAL": {"valuation": 15, "business_quality": 15, "growth_quality": 8, "free_cash_flow": 7,
                    "balance_dilution": 5},
    "RISK": {"financial_resilience": 7, "downside_drawdown": 5, "liquidity": 4, "leverage": 4},
    "EVENTS": {"governance": 3, "material_events": 3, "insider_ownership": 2, "capital_allocation": 2},
}
_US_REGIME_SWING = {"vix_regime": 5, "vix_term": 4, "credit_spread": 4, "index_trend_breadth": 7}
_KR_REGIME_SWING = {"vkospi_regime": 5, "index_trend": 5, "breadth": 4, "usdkrw_regime": 3, "credit_liquidity": 3}
# ASSUMPTION: the spec defers long-term regime factors to a QSF 1.0 document that is not in the repository.
# They are the swing factors scaled to 10 points, recorded as an assumption in the factor mapping.
_US_REGIME_LONG = {"vix_regime": 2, "vix_term": 2, "credit_spread": 3, "index_trend_breadth": 3}
_KR_REGIME_LONG = {"vkospi_regime": 2, "index_trend": 3, "breadth": 2, "usdkrw_regime": 2, "credit_liquidity": 1}


def _profile(market: str, strategy: str, common: Dict, regime: Dict) -> Dict:
    return {"id": f"{market}_{strategy}_V1", "market": market, "strategy": strategy,
            "domains": {**{k: dict(v) for k, v in common.items()}, "REGIME": dict(regime)}}


PROFILES: Dict[str, Dict] = {p["id"]: p for p in (
    _profile("US", "SWING", _SWING_COMMON, _US_REGIME_SWING),
    _profile("US", "LONG_TERM", _LONG_COMMON, _US_REGIME_LONG),
    _profile("KR", "SWING", _SWING_COMMON, _KR_REGIME_SWING),
    _profile("KR", "LONG_TERM", _LONG_COMMON, _KR_REGIME_LONG),
)}

# Minimum coverage per critical domain (spec 8); total is 70%.
MIN_TOTAL_COVERAGE = 0.70
MIN_DOMAIN_COVERAGE = {"SWING": {"TECHNICAL": 0.70, "RISK": 0.50},
                       "LONG_TERM": {"FUNDAMENTAL": 0.60, "RISK": 0.40}}
CONFIDENCE_BANDS = ((0.90, "HIGH"), (0.80, "MEDIUM"), (0.70, "LOW"))

BANDS = ((80.0, "STRONG_BUY_CANDIDATE", "강력 매수 후보"), (70.0, "BUY_CANDIDATE", "매수 후보"),
         (55.0, "HOLD_WATCH", "보유·관찰"), (40.0, "WEAK_REDUCE", "약세·축소 후보"),
         (0.0, "SELL_AVOID", "매도·회피 후보"))

COLORS = {"BUY": "#16A34A", "SELL": "#DC2626", "AVOID": "#DC2626", "HOLD": "#64748B", "WATCH": "#64748B",
          "REDUCE": "#D97706", "INSUFFICIENT_DATA": "#64748B", "BLOCKED": "#64748B"}
ACTION_LABELS = {"BUY": "매수 후보", "HOLD": "보유 유지", "WATCH": "관찰", "REDUCE": "비중 축소 검토", "SELL": "매도 검토",
                 "AVOID": "신규 진입 회피", "INSUFFICIENT_DATA": "판단 불가", "BLOCKED": "차단"}

# Hard gates.  KR's floor is a labelled hypothesis: the KR market config deliberately has no evidence-based floor.
GATES = {"US": {"min_price": 5.0, "min_adv_value": 20_000_000.0},
         "KR": {"min_price": None, "min_adv_value": 1_000_000_000.0}}
MIN_BARS = 200
EXTREME_MOVE = 0.60        # |1-day move| above this on the last 5 bars is a data anomaly until explained
EARNINGS_BLOCK_SESSIONS = 2

# Costs, one way.  KR tax: 0.20% on sells from 2026-01-01 (Securities Transaction Tax Act revision, verified
# 2026-11-05).  Commission and spread depend on the broker and are ASSUMPTIONS shown wherever a net figure appears.
COSTS = {"US": {"commission_bps": 0.0, "spread_slippage_bps": 10.0, "sell_tax_bps": 0.0,
                "basis": "수수료 0 가정, 스프레드·슬리피지 10bps 가정 (실제 값 아님)"},
         "KR": {"commission_bps": 1.5, "spread_slippage_bps": 15.0, "sell_tax_bps": 20.0,
                "basis": "매도 증권거래세 0.20%(2026년 세율) + 수수료 1.5bps·스프레드 15bps 가정"}}


def round_trip_cost(market: str) -> float:
    c = COSTS[market]
    return (2 * (c["commission_bps"] + c["spread_slippage_bps"]) + c["sell_tax_bps"]) / 1e4


BENCHMARK = {"US": "SPY", "KR_KOSPI": "^KS11", "KR_KOSDAQ": "^KQ11"}

# Holding policy (spec 5): research hypotheses.
SWING = {"min": 5, "max": 20, "review_every": 5, "time_stop": 30, "stop_atr": 2.0, "projection_atr": 3.0,
         "min_reward_risk": 1.5}
LONG_TERM = {"min_months": 12, "max_months": 36, "review_months": 3}
SWING_HORIZONS = (5, 10, 20, 30)
LONG_HORIZONS_MONTHS = (3, 6, 12, 24, 36)
BUCKETS = ((0, 40), (40, 55), (55, 70), (70, 80), (80, 100.0001))
MIN_INDEPENDENT = 12
