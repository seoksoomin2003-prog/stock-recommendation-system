import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from utils.config import EXECUTION_SETTINGS
from utils.logger import setup_logger

logger = setup_logger("ExecutionAlphaEngine")

class ExecutionAlphaEngine:
    """
    고급 주문 집행 알파 엔진 (Senior Quant Logic)
    주문 실행 품질(Execution Quality)을 개선하여 실제 수익률(Actual Alpha)을 확보하는 계층.
    
    핵심 기능:
    1. Order Slicing: 대량 주문을 N개로 분할하여 시장 충격 분산.
    2. Market Impact Model: 주문 규모에 따른 가격 변동성 추정.
    3. Slippage Model: 호가 스프레드 및 변동성 기반 정교한 슬리피지 계산.
    4. Simulation: 백테스트에서 전략의 '추정 체결가' 산출.
    """
    def __init__(self, config: Dict = EXECUTION_SETTINGS):
        self.n_slices = config.get("n_slices", 5)
        self.k = config.get("impact_coefficient", 0.1)  # 시장 충격 계수
        self.alpha = config.get("impact_exponent", 0.5)  # 시장 충격 지수
        self.default_spread = config.get("default_spread_pct", 0.0002)
        
    def calculate_market_impact(self, 
                                order_size: float, 
                                avg_volume: float, 
                                daily_volatility: float) -> float:
        """
        시장 충격(Market Impact) 모델: 선형/비선형 복합 모델
        Impact = sigma * k * (OrderSize / Volume) ^ alpha
        """
        if avg_volume <= 0: return 0.0
        
        # 참여율 (Participation Rate)
        participation_rate = order_size / avg_volume
        
        # 시장 충격 추정 (bps 단위 등으로 변환 가능, 여기서는 비율로 반환)
        impact = daily_volatility * self.k * (participation_rate ** self.alpha)
        return impact

    def calculate_dynamic_slippage(self, 
                                   volatility: float, 
                                   spread: Optional[float] = None) -> float:
        """
        동적 슬리피지 계산 (호가 스프레드 + 잔여 변동성 리스크)
        """
        actual_spread = spread if spread is not None else self.default_spread
        # 스프레드의 절반(집행 시 즉시 비용) + 변동성 기반 위험 프리미엄
        slippage = (actual_spread / 2) + (volatility * 0.05) 
        return slippage

    def get_order_slices(self, 
                         total_quantity: float, 
                         method: str = 'TWAP',
                         volumes_profile: Optional[List[float]] = None) -> List[float]:
        """
        주문 분할 로직 (Order Slicing)
        - TWAP: 균등 시간 분할
        - VWAP: 거래량 프로필에 따른 가중치 분할
        """
        if method == 'TWAP' or volumes_profile is None:
            # 균등 분할
            return [total_quantity / self.n_slices] * self.n_slices
        
        elif method == 'VWAP':
            # 거래량 비중에 따른 분할
            weights = np.array(volumes_profile) / sum(volumes_profile)
            return (total_quantity * weights).tolist()
            
        return [total_quantity]

    def simulate_execution_price(self, 
                                 market_price: float, 
                                 order_size: float, 
                                 avg_volume: float, 
                                 daily_volatility: float,
                                 is_buy: bool = True) -> Dict:
        """
        현실적인 '추정 체결가' 시뮬레이션 (Execution Simulation)
        """
        # 1. 시장 충격 산출
        impact = self.calculate_market_impact(order_size, avg_volume, daily_volatility)
        
        # 2. 기본 슬리피지 산출
        slippage = self.calculate_dynamic_slippage(daily_volatility)
        
        # 3. 최종 체결가 결정 (매수 시 상향, 매도 시 하향)
        sign = 1 if is_buy else -1
        execution_price = market_price * (1 + sign * (impact + slippage))
        
        # 4. 분할 집행 시의 이득 시뮬레이션 (분산 효과 적용)
        # 분할 집행 시 시장 충격은 n_slices의 루트만큼 감소하는 경향이 있음
        reduced_impact = impact / np.sqrt(self.n_slices)
        optimized_price = market_price * (1 + sign * (reduced_impact + slippage))
        
        alpha_gain = abs(execution_price - optimized_price) / market_price
        
        return {
            "market_price": market_price,
            "execution_price": execution_price,
            "optimized_price": optimized_price,
            "execution_alpha": alpha_gain,
            "impact": impact,
            "slippage": slippage
        }

    def execute_twap_sim(self, 
                         ticker: str, 
                         quantity: float, 
                         market_price: float,
                         avg_volume: float,
                         volatility: float) -> float:
        """
        TWAP 전략 시뮬레이션 결과 반영된 최종 가격 반환
        """
        res = self.simulate_execution_price(market_price, quantity, avg_volume, volatility)
        logger.info(f"[{ticker}] TWAP Execute: {market_price:.2f} -> {res['optimized_price']:.2f} (Alpha: {res['execution_alpha']*10000:.1f} bps)")
        return res['optimized_price']
