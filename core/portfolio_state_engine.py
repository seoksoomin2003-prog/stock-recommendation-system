import pandas as pd
import numpy as np
from typing import Dict, List, Optional
from utils.logger import setup_logger

logger = setup_logger("PortfolioStateEngine")

class PortfolioStateEngine:
    """
    실제 포트폴리오 상태 관리 및 리스크 데이터 공급 엔진
    - 포지션, 현금, 총 평가액 추적
    - 수익률 이력(Equity Curve) 관리
    - 역사적 시뮬레이션 VaR 및 Drawdown 계산
    """
    def __init__(self, initial_cash: float = 100000000):
        self.initial_cash = initial_cash
        self.cash = initial_cash
        self.positions = {} # {ticker: quantity}
        self.equity_history = pd.Series([initial_cash], index=[pd.Timestamp.now().floor('D') - pd.DateOffset(days=1)])
        self.peak_value = initial_cash

    def seed_history(self, benchmark_history: pd.Series):
        """
        과거 데이터 시딩: 성과 이력이 없을 때 벤치마크 데이터를 활용하여 소급 생성
        - RiskEngine 및 MDD 계산이 즉시 가능하도록 준비
        """
        if len(self.equity_history) > 1:
            return
            
        logger.info(f"Seeding historical portfolio data using benchmark (Periods: {len(benchmark_history)})")
        
        returns = benchmark_history.pct_change().fillna(0)
        cumulative_returns = (1 + returns).cumprod()
        
        seeded_equity = cumulative_returns * (self.initial_cash / cumulative_returns.iloc[-1])
        self.equity_history = seeded_equity
        self.peak_value = seeded_equity.max()

    def update_portfolio_value(self, current_prices: pd.Series):
        """현재 가격 반영하여 총 평가액 업데이트 및 이력 기록"""
        market_value = 0
        for ticker, qty in self.positions.items():
            if ticker in current_prices.index:
                market_value += qty * current_prices[ticker]
            
        total_equity = self.cash + market_value
        current_time = pd.Timestamp.now()
        
        self.equity_history = pd.concat([self.equity_history, pd.Series([total_equity], index=[current_time])])
        if total_equity > self.peak_value:
            self.peak_value = total_equity
            
        logger.info(f"Portfolio Updated: Equity={total_equity:,.0f} (Drawdown={self.calculate_drawdown():.2%})")

    def get_history(self) -> pd.Series:
        """수익률 이력 반환 (Risk Engine 공급용)"""
        return self.equity_history

    def calculate_drawdown(self) -> float:
        """현재 시점의 Drawdown 계산"""
        if self.peak_value == 0: return 0.0
        current_equity = self.equity_history.iloc[-1]
        drawdown = (current_equity / self.peak_value) - 1
        return drawdown

    def calculate_var_historical(self, window: int = 252, confidence: float = 0.95) -> float:
        """
        역사적 시기 시뮬레이션(Historical Simulation) VaR
        - 과거 수익률 분포의 하위 (1-confidence) 분위수 산출
        """
        if len(self.equity_history) < 5: 
            return 0.02 # 초기 데이터 부족 시 기본값 (2%)
            
        returns = self.equity_history.pct_change().dropna()
        if returns.empty: return 0.0
        
        # 최근 window 기간의 수익률 기반
        recent_returns = returns.tail(window)
        var = np.percentile(recent_returns, (1 - confidence) * 100)
        return abs(var)

    def apply_trades(self, target_weights: pd.Series, current_prices: pd.Series, commission_rate: float = 0.001):
        """
        포트폴리오 비중 조절 (거래 집행 시뮬레이션)
        """
        total_equity = self.equity_history.iloc[-1]
        new_positions = {}
        allocated_value = 0
        
        for ticker, weight in target_weights.items():
            if ticker in current_prices.index and weight > 0:
                target_value = total_equity * weight
                execution_cost = target_value * commission_rate
                effective_value = target_value - execution_cost
                
                new_positions[ticker] = effective_value / current_prices[ticker]
                allocated_value += target_value
        
        new_cash = total_equity - allocated_value
        if new_cash < 0:
            scale = total_equity / (allocated_value + 1e-9)
            new_positions = {k: v * scale for k, v in new_positions.items()}
            new_cash = 0
            
        self.positions = new_positions
        self.cash = new_cash
        logger.info(f"Rebalance Complete: {len(new_positions)} positions, Cash: {self.cash:,.0f}")

    def get_state_summary(self) -> Dict:
        """현재 상태 요약 보고"""
        return {
            "total_equity": self.equity_history.iloc[-1],
            "drawdown": self.calculate_drawdown(),
            "var_95": self.calculate_var_historical(),
            "num_positions": len(self.positions)
        }
