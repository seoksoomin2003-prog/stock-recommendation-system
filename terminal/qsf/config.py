"""QSF 1.1 configuration: four independent profiles, score bands, gates and research defaults.

Every number here is a RESEARCH DEFAULT fixed in advance, not a fitted value.  Changing one requires a new
model version; nothing in the code tunes them.  QSF is a separate model: it never reads or changes P6-11B.
"""
from typing import Dict

MODEL_VERSION = "QSF-1.5.0"     # 1.5.0 (user decisions 2026-11-22 after the audit of that day, reports/QSF_1_5_0_2026_11_22.md):
                                # (1) a company losing money now gets 0 for the earnings-growth figures it cannot have, and 0 for cash
                                # conversion when both profit and operating cash flow are at or below zero; they were "missing", which
                                # left the factor to its better figures (27 US loss-makers, 6 with a growth factor of 0.7 or more).
                                # A turnaround from a loss base stays missing.  (2) the buy band has a buffer: in at 70, out under 67.
                                # (3) gates: a day of more than 45% anywhere in the last year, and doubled or backward price rows.
                                # Weights, anchors and every other formula are unchanged.
                                # 1.4.0: the regime domain no longer counts in any of the four scores; it is shown apart as the market state
                                # 1.4.1 (inputs only): the whole Korean filing list instead of its first 100 rows; a US share count
                                # from before a split is not used with a price from after it.  reports/QSF_INPUTS_3_2026_11_17.md
#                                  (MARKET_STATE_*), and on a US day under its middle the order plan halves the risk per trade.  User decision
#                                  2026-11-16 after reports/QSF_MARKET_STATE_RESULTS.md; the former formula is written down every session
#                                  (reports/QSF_SCORE_SPLIT_PROTOCOL.md).  1.3.2: US costs are the broker's published fees (Toss Securities: 0.1% each way, SEC fee on sells) instead of an assumed
#                                  zero commission, so the US swing risk/reward factor reads a 0.40% round trip (user decision 2026-11-12); Korea already matched.
#                                  1.3.1: a missing next earnings date is estimated from the company's own past dates (earnings_estimate), labelled
#                                  as an estimate and read with a wider window; user decision 2026-11-11.  1.3.0: the live Korean scan covers the 300 largest companies by market value instead of the 300 most traded
#                                  (KR_UNIVERSE, user decision 2026-11-11); the score itself is unchanged.  1.2.1: inputs the 2026-11-11 audit left (US debt read from its parts and never from total liabilities, annual figures
#                                  STALE once a newer report is overdue, no cash-flow ratio for financial companies, business years of
#                                  non-December Korean companies) and the Korean credit factor read from Bank of Korea yields; formulas and
#                                  weights unchanged.  1.2.0: the Korean swing score no longer counts the technical domain (profile KR_SWING_V2, user decision
#                                  2026-11-11 after reports/QSF_KR_TECH_EARLY_RESULTS.md); its factors are still computed and stored as reference,
#                                  and chart position stays in the entry assessment (holding.entry_status).  US and Korean long-term: unchanged.
#                                  1.1.9: fundamental inputs after the 2026-11-11 audit (one fiscal year per figure, share bases, Korean account ids,
#                                  currency, who is scored as financial); factor formulas and weights unchanged.  1.1.8: Korean daily bars from KRX
VALIDATION_NOTICE = ("미국 S&P 500 과거 검증(2014~2026)에서 점수가 높을수록 수익이 좋다는 근거를 찾지 못했습니다. "
                     "한국 스캔 대상은 2026-11-11부터 시가총액 상위 300종목입니다. 이 대상 안에서 점수는 과거 시험(2019~2026)의 기준에 못 미쳤고(장기 점수는 순위와 약한 양의 관계, 상위 종목은 시장 수준), "
                     "이전 대상(거래대금 상위 300)에서는 장기 점수가 한 구간에서만 순위를 설명했으며 그 대상 자체가 시장보다 크게 부진했습니다. "
                     "한국 스윙 점수는 2026-11-11에 차트 항목을 뺀 새 구성이라 과거 성적이 없습니다. "
                     "2026-11-16부터 네 점수 모두 시장 국면을 빼고 '시장 상태'로 따로 보여 줍니다(종목 순위는 거의 그대로이고 매수 후보 수가 달라집니다). 참고용으로만 쓰세요.")
STYLE_TO_STRATEGY = {"LONG": "LONG_TERM", "SWING": "SWING"}
# Which Korean stocks the live scan scores.  MARKET_CAP: the 300 largest by market value on the newest KRX day on file, by the rule of
# reports/QSF_KR_CAP_UNIVERSE_PROTOCOL.md.  TRADED_VALUE: the 300 most traded over 20 sessions, the live rule until QSF-1.2.1; it is
# still scored every day as a separate record (reports/QSF_KR_TRADED_UNIVERSE_PROTOCOL.md).  Setting TRADED_VALUE here goes back.
KR_UNIVERSE = "MARKET_CAP"
KR_UNIVERSE_MAX_AGE_DAYS = 10      # the newest KRX day on file may be this many calendar days before the session; older is no universe
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


# Domains a profile computes and stores but does not count in the score.  Korea, swing: the technical domain ranked stocks the
# wrong way round in past windows (2012-2019 and 2019-2026; the 2016-2019 check lies inside the first, so it is not a third), so its 40 points left the score on 2026-11-11.
# Every profile: the regime domain is one value for every stock of a day, so it cannot move a rank; it moved all scores together.  In the
# index test of 2026-11-16 (MKT-1) a low value was not followed by a worse market (US: by a better one, at about 1.9 times the
# volatility), so it left the score on 2026-11-16 and is shown apart as the market state, a risk reading.
_REFERENCE_ONLY = {("US", "SWING"): ("REGIME",), ("US", "LONG_TERM"): ("REGIME",), ("KR", "SWING"): ("TECHNICAL", "REGIME"), ("KR", "LONG_TERM"): ("REGIME",)}
_VERSION = {("US", "SWING"): "V2", ("US", "LONG_TERM"): "V2", ("KR", "SWING"): "V3", ("KR", "LONG_TERM"): "V2"}


def _profile(market: str, strategy: str, common: Dict, regime: Dict) -> Dict:
    ref = _REFERENCE_ONLY.get((market, strategy), ())
    domains = {**{k: dict(v) for k, v in common.items()}, "REGIME": dict(regime)}
    return {"id": f"{market}_{strategy}_{_VERSION.get((market, strategy), 'V1')}", "market": market, "strategy": strategy,
            "domains": {k: ({} if k in ref else v) for k, v in domains.items()},
            "reference": {k: domains[k] for k in ref}}


PROFILES: Dict[str, Dict] = {p["id"]: p for p in (
    _profile("US", "SWING", _SWING_COMMON, _US_REGIME_SWING),
    _profile("US", "LONG_TERM", _LONG_COMMON, _US_REGIME_LONG),
    _profile("KR", "SWING", _SWING_COMMON, _KR_REGIME_SWING),
    _profile("KR", "LONG_TERM", _LONG_COMMON, _KR_REGIME_LONG),
)}
_LIVE = {(p["market"], p["strategy"]): p for p in PROFILES.values()}


def profile_for(market: str, strategy: str) -> Dict:
    return _LIVE[(market, strategy)]


# The market state: the regime factors under the swing weights, one reading per market and day whichever card it is read from.
# It is in no score.  Under the middle of its scale a day is ADVERSE.
# The buy band's buffer (QSF-1.5.0): a stock recorded in the buy band at its previous session stays in it down to this score.
# The line of 70 made a stock change its label on a move of 0.01 point; it now enters at 70 and leaves under 67.
BUY_BAND_EXIT = 67.0
MARKET_STATE_WEIGHTS = {"US": dict(_US_REGIME_SWING), "KR": dict(_KR_REGIME_SWING)}
MARKET_STATE_MID = 50.0
MARKET_STATE_LABELS = {"FAVOURABLE": "좋음", "ADVERSE": "나쁨", "UNKNOWN": "알 수 없음(자료 부족)"}
# Under this share of its factors the state is not read at all.  Until 2026-11-22 one factor of four was enough: the fear index
# alone gave "100, favourable" (audit RED-03).  An unknown state is treated as an adverse one where the market has a brake.
MARKET_STATE_MIN_COVERAGE = 0.5
# What an adverse day does to the order plan: the risk per trade and the weight limit of a new order are both multiplied by this, so
# the order is at most half its usual size whichever limit binds (with a 1% risk and a 10% weight limit the weight usually binds,
# and halving the risk alone would change almost nothing).  US only (user decision 2026-11-16, "미국만 크기 절반"): the index test
# found about 1.9 times the volatility after such days in the US and no difference in Korea.
ADVERSE_SIZE_FACTOR = {"US": 0.5}
# The most the new orders of one plan may add up to on an adverse (or unknown) day, as a share of the account.  Halving each order
# did not bound the plan: on 2026-11-20 the state was 15/100 and an all-cash account was planned 98% invested (audit RED-03).
# US only, like the size factor: the index test found nothing for Korea (user decision 2026-11-22, "한도와 표시").
ADVERSE_NEW_EXPOSURE_CAP = {"US": 0.5}
MARKET_STATE_NOTES = {
    "US": "종목 점수에 들어가지 않는 위험 표시입니다. 과거 시험(2009~2026, 지수 기준)에서 이 값이 50 미만인 날 뒤 20거래일은 변동성이 약 1.9배였고, 지수 수익은 낮지 않았습니다. "
          "50 미만이거나 요인의 절반 이상이 비어 값을 읽을 수 없는 날에는 주문 계획이 새 주문의 거래당 위험 한도와 종목 비중 한도를 절반으로 계산하고, 새 주문의 합계를 계좌의 50%까지만 잡습니다.",
    "KR": "종목 점수에 들어가지 않는 참고 표시입니다. 과거 시험(2010~2026, 지수 기준)에서 한국은 이 값으로 이후 수익도 변동성도 구분되지 않았습니다. "
          "VKOSPI는 받을 수 없어 들어 있지 않습니다. 주문 계획의 크기는 바꾸지 않습니다."}

# Minimum coverage per critical domain (spec 8); total is 70%.  A domain the profile does not count is not asked for.
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
EXTREME_MOVE_YEAR = 0.45   # and above this anywhere in the last year (252 bars): a 2-for-1 split left unadjusted is a 50% day, which
#                            the line above never saw, and five bars later nothing saw it (audit ENG-06; user decision 2026-11-22).
#                            On 2026-11-20 one scanned stock of 804 had such a day.
# A whole scan is recorded as the day only when this share of its stocks has usable statements: prices alone used to decide, so a
# day on which the statement sources were down would have been stored for good with the fundamental domain empty (audit ENG-02;
# user decision 2026-11-22).  The share has been 99% or more on every recorded day.
FUND_RECORD_SHARE = 0.80
EARNINGS_BLOCK_SESSIONS = 2
EARNINGS_BLOCK_SESSIONS_ESTIMATE = 5     # an estimated date: five weekdays either side held 96% of the actual Korean dates (2026-11-11 check)

# Costs, one way.  Commission and exchange fee: Toss Securities' published schedule, read 2026-11-12 at
# corp.tossinvest.com/ko/business?tab=commission (user decision 2026-11-12: the user's broker).  Korea 0.015% each way (KRX; NXT is
# 0.014%) and 0.20% tax on sells (KOSPI 0.05% + 0.15% rural tax, KOSDAQ 0.20%).  US 0.1% each way and the SEC fee of 0.00206% on
# sells.  Currency exchange (0.05% in Korean banking hours, 0.5% outside) is NOT in the per-trade cost: the dollar account is kept
# apart and converted on its own schedule; FX_BPS carries it for the screens that show it.  Spread and slippage stay ASSUMPTIONS
# and are shown as such wherever a net figure appears; the order plan estimates them per stock (terminal/qsf/order_plan.py).
COSTS = {"US": {"commission_bps": 10.0, "spread_slippage_bps": 10.0, "sell_tax_bps": 0.0, "sell_fee_bps": 0.206,
                "basis": "토스증권 수수료 편도 0.1% + 매도 SEC 수수료 0.00206%(2026-11-12 확인) + 스프레드·슬리피지 10bps 가정. 환전 수수료 제외"},
         "KR": {"commission_bps": 1.5, "spread_slippage_bps": 15.0, "sell_tax_bps": 20.0, "sell_fee_bps": 0.0,
                "basis": "토스증권 수수료 편도 0.015%(2026-11-12 확인) + 매도 증권거래세 0.20%(2026년 세율) + 스프레드·슬리피지 15bps 가정"}}
COSTS_CHECKED = "2026-11-12"
FX_BPS = {"regular": 5.0, "off_hours": 50.0}      # Toss currency exchange, one way: Korean business days 09:00-15:30 / any other time


def round_trip_cost(market: str) -> float:
    c = COSTS[market]
    return (2 * (c["commission_bps"] + c["spread_slippage_bps"]) + c["sell_tax_bps"] + c.get("sell_fee_bps", 0.0)) / 1e4


def fees_only(market: str) -> float:
    """The published part of a round trip (commission, tax, exchange fee): no spread or slippage assumption in it."""
    c = COSTS[market]
    return (2 * c["commission_bps"] + c["sell_tax_bps"] + c.get("sell_fee_bps", 0.0)) / 1e4


BENCHMARK = {"US": "SPY", "KR_KOSPI": "^KS11", "KR_KOSDAQ": "^KQ11"}

# Holding policy (spec 5): research hypotheses.
SWING = {"min": 5, "max": 20, "review_every": 5, "time_stop": 30, "stop_atr": 2.0, "projection_atr": 3.0,
         "min_reward_risk": 1.5}
LONG_TERM = {"min_months": 12, "max_months": 36, "review_months": 3}
SWING_HORIZONS = (5, 10, 20, 30)
LONG_HORIZONS_MONTHS = (3, 6, 12, 24, 36)
BUCKETS = ((0, 40), (40, 55), (55, 70), (70, 80), (80, 100.0001))
MIN_INDEPENDENT = 12
