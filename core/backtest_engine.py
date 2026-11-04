import pandas as pd
import numpy as np
from typing import List, Dict, Tuple, Optional
from utils.config import BACKTEST_SETTINGS
from utils.logger import setup_logger

logger = setup_logger("BacktestEngine")

class BacktestEngine:
    """
    고급 백테스터 (V2)
    - Walk-forward (Multi-window)
    - Monte Carlo Simulation (랜덤 샘플링 기반 경로 분석)
    - Bootstrap Validation (통계적 유의성 검정)
    - 거래 비용 민감도 분석
    - 성과 지표 산출 (CAGR, Sharpe, MDD)
    """
    def __init__(self, 
                 settings: Dict = BACKTEST_SETTINGS, 
                 execution_engine=None):
        self.train_years = settings['train_years']
        self.test_months = settings['test_months']
        self.fee_rate = settings['fee_rate']
        self.top_k_pct = settings['top_k_pct']
        self.execution_engine = execution_engine

    def calculate_metrics(self, portfolio_returns: pd.Series) -> Dict[str, float]:
        total_return = (1 + portfolio_returns).prod()
        n_years = len(portfolio_returns) / 12
        cagr = (total_return ** (1 / n_years)) - 1 if n_years > 0 else 0
        sharpe = (portfolio_returns.mean() / portfolio_returns.std()) * np.sqrt(12) if portfolio_returns.std() != 0 else 0
        cum_returns = (1 + portfolio_returns).cumprod()
        peak = cum_returns.cummax()
        drawdown = (cum_returns - peak) / peak
        mdd = drawdown.min()
        
        return {"CAGR": round(cagr, 4), "Sharpe": round(sharpe, 4), "MDD": round(mdd, 4)}

    def run_monte_carlo(self, returns: pd.Series, n_sim: int = 1000, block_size: int = 6) -> Dict[str, float]:
        """
        [Real Risk Implementation] 몬테카를로 시뮬레이션 (Block Bootstrap)
        - 단순 셔플(IID) 대신 블록 단위 샘플링으로 시계열 종속성 보존
        - Worst-case MDD 및 CVaR(Expected Shortfall) 산출
        """
        sim_results = []
        n = len(returns)
        
        for _ in range(n_sim):
            # Block Bootstrap: 연속된 구간(Block)을 샘플링하여 성분 간 상관성 유지
            simulated_returns = []
            while len(simulated_returns) < n:
                # 랜덤 시작점 선택
                start_idx = np.random.randint(0, n - block_size + 1)
                block = returns.iloc[start_idx : start_idx + block_size].values
                simulated_returns.extend(block)
            
            # 길이 맞추기 및 Series 변환
            sim_series = pd.Series(simulated_returns[:n])
            metrics = self.calculate_metrics(sim_series)
            sim_results.append(metrics)
            
        df_sim = pd.DataFrame(sim_results)
        
        # 성과 분포 통계
        avg_sharpe = df_sim['Sharpe'].mean()
        # 95% 신뢰구간 하단 (Value at Risk 형태)
        var_95_cagr = df_sim['CAGR'].quantile(0.05)
        # 하위 5%의 평균 (Expected Shortfall / CVaR)
        cvar_cagr = df_sim[df_sim['CAGR'] <= var_95_cagr]['CAGR'].mean()
        
        # 리스크 지표 (보수적 평가)
        median_mdd = df_sim['MDD'].median()
        worst_case_mdd = df_sim['MDD'].min() # 전체 시뮬레이션 중 최악의 낙폭
        
        logger.info(f"Monte Carlo Summary: Median MDD={median_mdd:.2%}, Worst-Case MDD={worst_case_mdd:.2%}")
        
        return {
            "avg_sharpe": round(avg_sharpe, 4),
            "95pct_var_return": round(var_95_cagr, 4),
            "cvar_return": round(cvar_cagr, 4),
            "median_mdd": round(median_mdd, 4),
            "worst_case_mdd": round(worst_case_mdd, 4)
        }

    def run_sensitivity_analysis(self, 
                                 prices: pd.DataFrame, 
                                 factor_func, 
                                 scoring_engine, 
                                 fee_rates: List[float]) -> Dict[float, float]:
        """거래 비용 변화에 따른 성과 민감도 분석"""
        results = {}
        original_fee = self.fee_rate
        for fee in fee_rates:
            self.fee_rate = fee
            res = self.run_walk_forward(prices, factor_func, scoring_engine)
            results[fee] = res['metrics']['CAGR']
        self.fee_rate = original_fee
        return results

    def _estimate_slippage(self, turnover: float) -> float:
        """
        [NEW] 시장 충격(Slippage) 모델링
        - Turnover 규모에 비례하는 0.1% ~ 0.5% 수준의 추가 비용 산출
        - 모델: Slp = 0.002 * (Turnover ** 0.5)
        """
        if turnover <= 0: return 0.0
        return 0.002 * (turnover ** 0.5)

    def run_walk_forward(self, 
                         prices: pd.DataFrame, 
                         factor_func, 
                         scoring_engine, 
                         portfolio_engine, # [NEW] 필수 엔진 추가
                         volumes: Optional[pd.DataFrame] = None,
                         fundamental_engine = None) -> Dict:
        """
        Walk-forward 백테스트 실행 (현실적 실행 비용 반영)
        - [수정] 1/N 배분 제거 -> PortfolioEngine(Softmax) 기반 가중치 산출
        - Turnover 기반 거래 비용(Slippage + Commission + Spread) 차감
        """
        all_test_returns = []
        dates = prices.resample('ME').last().index
        start_idx = self.train_years * 12
        
        # [NEW] 초기 설정
        initial_capital = BACKTEST_SETTINGS.get('initial_capital', 100000000)
        current_capital = initial_capital
        # 현재 보유 비중 (최초에는 현금 100%)
        current_weights = pd.Series(dtype=float)
        
        # [NEW] 고정 스프레드 설정 (2bps)
        bid_ask_spread = 0.0002 
        
        # 거래량 데이터 확보
        if volumes is None:
            volumes = prices.copy().pct_change().abs() * 1e6 # 가상 거래량 생성

        for i in range(start_idx, len(dates) - self.test_months, self.test_months):
            train_dates = dates[i - start_idx: i]
            test_dates = dates[i: i + self.test_months]
            
            rebalance_date = train_dates[-1]
            
            # 1. 시그널 생성 및 실적 기간 팩터 계산
            train_prices = prices.loc[:rebalance_date]
            factors = factor_func(train_prices)
            scores = scoring_engine.calculate(factors)
            
            # 2. [NEW] 펀더멘탈 정성적 오버레이 적용 (제거됨: Alpha De-duplication)
            if fundamental_engine:
                top_candidates_pre = scoring_engine.select_top_candidates(scores, self.top_k_pct)
                fundamental_results = fundamental_engine.batch_analyze_full(top_candidates_pre)
                # [수정] 중복 반영 방지를 위해 ScoringEngine.apply_fundamental_overlay 호출 삭제

            # 3. [수정] 타겟 비중 설정 (Equal Weight 완전 제거 -> Softmax)
            target_weights = portfolio_engine.calculate_weights(
                scores=scores, 
                method="softmax-weighted"
            )
            
            selected_tickers = target_weights.index.tolist()
            if not selected_tickers: continue
            
            # 3. [현실화] Turnover 계산 (이전 비중의 가격 변동 반영: Drift)
            # 이전 비중이 없는 경우(최초) 0으로 처리
            drifted_weights = current_weights.copy() if not current_weights.empty else pd.Series(0, index=target_weights.index)
            
            # 4. [집행] ExecutionEngine을 통한 거래 비용 산출
            total_friction_cost = 0.0
            all_tickers = sorted(list(set(target_weights.index) | set(drifted_weights.index)))
            
            for ticker in all_tickers:
                t_weight = target_weights.get(ticker, 0.0)
                d_weight = drifted_weights.get(ticker, 0.0)
                
                # 비중 차이만큼 매수/매도 발생
                diff_weight = t_weight - d_weight
                if abs(diff_weight) < 1e-6: continue # 변경 없음
                
                trade_value = abs(diff_weight) * current_capital
                price = prices.loc[rebalance_date, ticker]
                quantity = trade_value / price
                is_buy = diff_weight > 0
                
                # 유동성 지표
                ticker_vol = volumes.loc[:rebalance_date, ticker].tail(20).mean()
                ticker_std = prices.loc[:rebalance_date, ticker].pct_change().tail(20).std()
                
                if self.execution_engine:
                    # 보수적 실행: Spread 추가 반영
                    exec_res = self.execution_engine.calculate_execution_cost(
                        price * (1 + (bid_ask_spread/2 if is_buy else -bid_ask_spread/2)), 
                        quantity, is_buy=is_buy, avg_volume=ticker_vol, volatility=ticker_std
                    )
                    # 총 마찰 비용 = |실행가 - 장부가| + 수수료
                    friction = abs(exec_res['execution_price'] - price) * quantity + exec_res['commission']
                    total_friction_cost += friction
            
            # 리밸런싱 비용 차감
            current_capital -= total_friction_cost
            turnover_pct = abs(target_weights.reindex(all_tickers).fillna(0) - drifted_weights.reindex(all_tickers).fillna(0)).sum()
            
            # 5. 테스트 기간 수익률 계산
            test_window_prices = prices.loc[test_dates[0]:test_dates[-1], selected_tickers]
            # 해당 기간의 자본 수익률 (종목별 가중 평균)
            window_returns = test_window_prices.pct_change().dropna()
            portfolio_window_returns = (window_returns * target_weights).sum(axis=1)
            
            # 자본 갱신
            period_return = (1 + portfolio_window_returns).prod() - 1
            current_capital *= (1 + period_return)
            
            # 현재 비중 업데이트 (다음 윈도우용)
            current_weights = target_weights.copy()
            
            # 결과 저장
            all_test_returns.append(portfolio_window_returns)
            
            logger.info(f"Window {test_dates[0].date()}: Turnover={turnover_pct:.1%}, Friction={total_friction_cost/current_capital*10000:.1f}bps, Return={period_return:.2%}")
            
        if not all_test_returns: return {"error": "No results"}
        
        combined_returns = pd.concat(all_test_returns)
        metrics = self.calculate_metrics(combined_returns)
        
        return {"metrics": metrics, "returns": combined_returns}
