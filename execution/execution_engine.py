import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from utils.logger import setup_logger

logger = setup_logger("ExecutionEngine")

class ExecutionEngine:
    """
    거래 실행 엔진 (현실적 거래 시뮬레이션)
    - 슬리피지 모델 (Slippage Model)
    - 거래 수수료 및 세금 (Transaction Costs)
    - 유동성 필터 (Liquidity Filter)
    - 분할 진입 전략 시뮬레이션 (Execution Alpha 통합)
    """
    def __init__(self, 
                 slippage_rate: float = 0.0005, 
                 commission_rate: float = 0.001,
                 volume_participation: float = 0.1,
                 alpha_engine: Optional[object] = None):
        self.slippage_rate = slippage_rate
        self.commission_rate = commission_rate
        self.volume_participation = volume_participation
        self.alpha_engine = alpha_engine 
        
        if self.alpha_engine is None:
            logger.info("Advanced execution disabled (alpha_engine not provided). Fallback to basic model active.")
        else:
            logger.info("ExecutionEngine successfully integrated with Advanced AlphaEngine.")

    def execute_orders(self, 
                       target_portfolio: pd.Series, 
                       current_prices: pd.Series, 
                       total_capital: float) -> Dict:
        """
        [LIVE/SIM] 포트폴리오 비중을 바탕으로 거래를 실행하고 최적화된 결과를 반환함.
        - returns: { "results": Dict[ticker, cost_info], "executed_weights": pd.Series }
        """
        logger.info(f"Executing Orders for {len(target_portfolio)} tickers.")
        raw_results = self.simulate_trade(target_portfolio, current_prices, total_capital)
        
        # [NEW] 체결 완료 후의 실질 비중 산출 (Slippage 및 Commission 반영됨)
        executed_values = pd.Series({t: info['total_value'] for t, info in raw_results.items()})
        total_executed_value = executed_values.sum()
        
        executed_weights = executed_values / total_executed_value if total_executed_value > 0 else executed_values
        
        return {
            "results": raw_results,
            "executed_weights": executed_weights,
            "total_cost": sum(info['commission'] for info in raw_results.values())
        }

    def filter_by_liquidity(self, 
                            tickers: List[str], 
                            volumes: pd.Series, 
                            threshold: float = 1e6) -> List[str]:
        """유동성이 낮은 종목 필터링 (거래량 미달 종목 제외)"""
        valid_tickers = []
        for t in tickers:
            if t not in volumes.index:
                logger.warning(f"Liquidity Filter: {t} rejected (Volume UNAVAILABLE / Missing Index)")
                continue
            vol = volumes[t]
            if pd.isna(vol):
                logger.warning(f"Liquidity Filter: {t} rejected (Volume UNAVAILABLE / NaN)")
                continue
            if vol == 0:
                logger.warning(f"Liquidity Filter: {t} rejected (Genuine Zero Volume)")
                continue
            if vol > threshold:
                valid_tickers.append(t)
            else:
                logger.warning(f"Liquidity Filter: {t} rejected (Volume {vol} < {threshold})")
                
        logger.info(f"Liquidity Filter: {len(tickers)} -> {len(valid_tickers)} tickers passed.")
        return valid_tickers

    def calculate_execution_cost(self, 
                                price: float, 
                                quantity: float, 
                                is_buy: bool = True,
                                avg_volume: Optional[float] = None,
                                volatility: Optional[float] = None) -> Dict:
        """
        슬리피지와 수수료를 포함한 실제 집행 가격 및 비용 계산
        - AlphaEngine (현실적 모델) -> Basic (기본 모델) 순으로 시도
        """
        method = "basic"
        
        # 1. Advanced Model (AlphaEngine) 사용 시도
        if self.alpha_engine is not None:
            try:
                # 데이터(Volume, Volatility)가 유효할 때만 Advanced 실행
                if avg_volume is not None and volatility is not None:
                    res = self.alpha_engine.simulate_execution_price(price, quantity, avg_volume, volatility, is_buy)
                    adjusted_price = res['optimized_price']
                    method = "advanced"
                else:
                    # 데이터 부족 시 안내 메시지 (기본 모델 폴백)
                    adjusted_price = self._basic_slippage_model(price, is_buy)
            except Exception as e:
                logger.error(f"Advanced Execution Error: {e}. Falling back to basic.")
                adjusted_price = self._basic_slippage_model(price, is_buy)
        else:
            # 2. Basic Model (고정 슬리피지) 사용
            adjusted_price = self._basic_slippage_model(price, is_buy)
        
        # 2. 거래 수수료 계산
        commission = adjusted_price * quantity * self.commission_rate
        total_value = adjusted_price * quantity + (commission if is_buy else -commission)
        
        return {
            "execution_price": adjusted_price,
            "commission": commission,
            "total_value": total_value,
            "method": method
        }

    def _basic_slippage_model(self, price: float, is_buy: bool) -> float:
        """기본 고정 슬리피지 모델"""
        sign = 1 if is_buy else -1
        return price * (1 + (sign * self.slippage_rate))

    def simulate_trade(self, 
                       target_portfolio: pd.Series, 
                       current_prices: pd.Series, 
                       total_capital: float) -> Dict:
        """
        포트폴리오 비중을 실제 주문으로 변환 및 성과 반영 (백테스트용)
        """
        execution_results = {}
        for ticker, weight in target_portfolio.items():
            if ticker in current_prices.index:
                price = current_prices[ticker]
                target_value = total_capital * weight
                quantity = target_value / price
                
                # 비용 차감 후 실제 집행
                cost_info = self.calculate_execution_cost(price, quantity)
                execution_results[ticker] = cost_info
                
        return execution_results
