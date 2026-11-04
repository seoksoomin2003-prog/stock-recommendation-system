import pandas as pd
import numpy as np
from enum import Enum
from typing import Dict
from datetime import datetime, timezone
from data.loader import DataLoader
from core.regime_engine import RegimeEngine
from core.factor_engine import FactorEngine
from core.scoring_engine import ScoringEngine
from core.ranking_engine import RankingEngine
from core.decision_engine import DecisionEngine
from core.portfolio_state_engine import PortfolioStateEngine
from utils.config import DEFAULT_FACTOR_WEIGHTS, HYBRID_WEIGHTS, BACKTEST_SETTINGS, CAPACITY_SETTINGS, TAIL_RISK_SETTINGS, EXECUTION_SETTINGS
from utils.logger import setup_logger

logger = setup_logger("Main")

class RiskStatus(Enum):
    NORMAL = "NORMAL"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"

class QuantTradingSystemV2:
    """
    자율형 기관급 퀀트 트레이딩 시스템 (V2) 통합 모듈
    """
    def __init__(self, mode: str = "live", initial_capital: float = None, run_research: bool = False):
        self.mode = mode
        self.run_research = run_research
        # The live production bootstrap intentionally loads only the frozen
        # recommendation route.  Research engines are imported lazily below.
        self.data_loader = DataLoader()
        self.regime_engine = RegimeEngine()
        self.factor_engine = FactorEngine()
        self.scoring_engine = ScoringEngine(DEFAULT_FACTOR_WEIGHTS)
        self.ranking_engine = RankingEngine()
        self.decision_engine = DecisionEngine()
        
        # 실제 포트폴리오 상태 관리 엔진 초기화 (기본 자금 1억)
        capital_to_use = initial_capital if initial_capital is not None else BACKTEST_SETTINGS.get('initial_capital', 100000000)
        self.portfolio_state = PortfolioStateEngine(capital_to_use)
        
        from utils.memory_guard import MemoryGuard
        MemoryGuard.initialize()

        if mode != "live" or run_research:
            # Experimental/research dependencies are deliberately unavailable
            # to the canonical live runtime.
            from core.data_validation import DataValidation
            from core.news_engine import NewsEngine
            from core.portfolio_engine import PortfolioEngine
            from core.risk_engine import RiskEngine
            from core.factor_weight_optimizer import FactorWeightOptimizer
            from core.backtest_engine import BacktestEngine
            from core.learning_engine import LearningEngine
            from core.meta_controller import MetaController
            from core.monitoring_engine import MonitoringEngine
            from core.alternative_data_engine import AlternativeDataEngine
            from core.cross_asset_engine import CrossAssetEngine
            from core.meta_alpha_engine import MetaAlphaEngine
            from core.risk_systems import TailRiskEngine, CapacityEngine
            from core.analytics_systems import AlphaAttribution, RobustnessEngine
            from execution.execution_engine import ExecutionEngine
            from execution.execution_alpha_engine import ExecutionAlphaEngine
            from core.rag_engine import RAGEngine
            from core.llm_fundamental_engine import LLMFundamentalEngine
            self.validator = DataValidation()
            self.news_engine = NewsEngine()
            self.portfolio_engine = PortfolioEngine(method='risk-parity')
            self.risk_engine = RiskEngine()
            self.factor_optimizer = FactorWeightOptimizer()
            self.execution_alpha_engine = ExecutionAlphaEngine(EXECUTION_SETTINGS)
            self.execution_engine = ExecutionEngine(alpha_engine=self.execution_alpha_engine)
            self.monitoring_engine = MonitoringEngine()
            self.meta_controller = MetaController()
            self.learning_engine = LearningEngine()
            self.backtest_engine = BacktestEngine(execution_engine=self.execution_engine)
            self.alt_data_engine = AlternativeDataEngine()
            self.cross_asset_engine = CrossAssetEngine()
            self.meta_alpha_engine = MetaAlphaEngine()
            self.tail_risk_engine = TailRiskEngine()
            self.capacity_engine = CapacityEngine()
            self.attribution_engine = AlphaAttribution()
            self.robustness_engine = RobustnessEngine()
            self.rag_engine = RAGEngine()
            self.fundamental_engine = LLMFundamentalEngine(self.rag_engine)

    def _determine_risk_status(self, multiplier: float) -> RiskStatus:
        if multiplier == 0:
            return RiskStatus.CRITICAL
        elif multiplier < 1.0:
            return RiskStatus.WARNING
        return RiskStatus.NORMAL

    def run_live_cycle(self, tickers: list, ciks: dict = None):
        logger.info(f"--- [V2 Autonomous Pipeline Starting] Mode: {self.mode} ---")

        # P6-17.4: production is intentionally a small, auditable path.  The
        # legacy V2 flow below remains available for explicit research/backtest
        # work, where adaptive experiments belong, but can never be the live
        # recommendation architecture.
        if self.mode == "live" and not self.run_research:
            return self._run_frozen_live_cycle(tickers, ciks or {})
        
        from utils.memory_guard import MemoryGuard
        MemoryGuard.check_and_cleanup()
        
        # 1. Entity Resolution & Deduplication (P1 Local Workload Control)
        from alpha_engine.input.resolver import EntityResolutionEngine
        resolver = EntityResolutionEngine()
        resolved = [resolver.resolve_input(t) for t in tickers]
        
        canonical_tickers = []
        seen = set()
        for r in resolved:
            t = r.get("ticker")
            if t:
                t_upper = t.upper()
                if t_upper not in seen:
                    seen.add(t_upper)
                    canonical_tickers.append(t_upper)

        import utils.config
        
        # Override tickers with unique canonical ones
        tickers = canonical_tickers if canonical_tickers else tickers
        
        if utils.config.APP_MODE == "local":
            logger.info(f"Local workload control: Processing {len(tickers)} tickers in batches of {utils.config.MAX_LOCAL_TICKERS}")
            if len(tickers) > utils.config.MAX_LOCAL_TICKERS:
                return {
                    "status": "LIMIT_EXCEEDED",
                    "executable": False,
                    "max_tickers": utils.config.MAX_LOCAL_TICKERS,
                    "received": len(tickers),
                    "rejected": tickers[utils.config.MAX_LOCAL_TICKERS:]
                }

        # 2. 데이터 로드 및 검증 (Data Validation Layer)
        end_date = pd.Timestamp.now().strftime('%Y-%m-%d')
        if utils.config.APP_MODE == "local":
            start_date = (pd.Timestamp.now() - pd.DateOffset(days=utils.config.MAX_LOCAL_LOOKBACK_DAYS)).strftime('%Y-%m-%d')
        else:
            start_date = (pd.Timestamp.now() - pd.DateOffset(years=4)).strftime('%Y-%m-%d')
            
        # [NEW] Chunked Execution Architecture
        batch_size = utils.config.MAX_LOCAL_TICKERS if utils.config.APP_MODE == "local" else len(tickers)
        if batch_size == 0: batch_size = len(tickers)
        
        aggregated_prices = []
        aggregated_volumes = []
        aggregated_factor_matrices = []
        aggregated_sentiment = {}
        aggregated_alt_data = []
        aggregated_fundamental = {}
        aggregated_fundamental_statuses = {}
        
        for i in range(0, len(tickers), batch_size):
            batch = tickers[i:i + batch_size]
            logger.info(f"Processing batch {i//batch_size + 1}: {batch}")
            
            raw_prices = self.data_loader.get_price_data(batch, start_date, end_date)
            raw_volumes = self.data_loader.get_volume_data(batch, start_date, end_date)
            financials = self.data_loader.get_financial_data(batch, ciks=ciks)
            
            # [NEW] NaN Firewall & Data Availability Check
            valid_batch = []
            for t in batch:
                has_price = not raw_prices[t].isna().all() if t in raw_prices.columns else False
                has_volume = not (raw_volumes[t] == 0).all() if t in raw_volumes.columns else False
                has_financials = not np.isnan(financials.loc[t, 'per']) if t in financials.index else False
                if has_price and has_volume and has_financials:
                    valid_batch.append(t)
                else:
                    logger.warning(f"Excluding {t} due to DATA_UNAVAILABLE (price={has_price}, volume={has_volume}, financials={has_financials})")
            
            if not valid_batch:
                logger.warning(f"Batch {i//batch_size + 1} has no valid tickers after data checks.")
                continue
                
            # Keep only valid tickers for the rest of the batch
            batch = valid_batch
            raw_prices = raw_prices[batch]
            raw_volumes = raw_volumes[batch]
            financials = financials.loc[batch]
            
            prices_val = self.validator.validate_pipeline(raw_prices)
            
            # Factors
            factor_matrix = self.factor_engine.get_factor_matrix(prices_val, financials)
            
            # News & Sentiment
            news_data_dict = {t: self.data_loader.get_news_headlines(t) for t in batch}
            sentiment_scores = {t: self.news_engine.get_company_sentiment(news_data_dict[t], ticker=t) for t in batch}
            
            # Alt Data
            alt_data_scores = self.alt_data_engine.get_alt_data_matrix(batch, news_data_dict)
            
            # Fundamental RAG
            fundamental_results = self.fundamental_engine.batch_analyze_full(batch)
            fundamental_scores = {t: r["final_score"] for t, r in fundamental_results.items()}
            fundamental_statuses = {t: r["data_status"] for t, r in fundamental_results.items()}
            
            # Aggregation
            aggregated_prices.append(prices_val)
            aggregated_volumes.append(raw_volumes)
            aggregated_factor_matrices.append(factor_matrix)
            aggregated_sentiment.update(sentiment_scores)
            aggregated_alt_data.append(alt_data_scores)
            aggregated_fundamental.update(fundamental_scores)
            aggregated_fundamental_statuses.update(fundamental_statuses)
            
            # Memory Cleanup per batch
            del raw_prices, raw_volumes, financials, prices_val, factor_matrix, news_data_dict, alt_data_scores, fundamental_results
            MemoryGuard.check_and_cleanup()

        # Combine all batches globally
        prices = pd.concat(aggregated_prices, axis=1) if aggregated_prices else pd.DataFrame()
        raw_volumes = pd.concat(aggregated_volumes, axis=1) if aggregated_volumes else pd.DataFrame()
        factor_matrix = pd.concat(aggregated_factor_matrices) if aggregated_factor_matrices else pd.DataFrame()
        sentiment_series = pd.Series(aggregated_sentiment)
        alt_data_scores = pd.concat(aggregated_alt_data) if aggregated_alt_data else pd.Series(dtype=float)
        fundamental_scores = pd.Series(aggregated_fundamental)
        
        # [NEW] Stop if all candidates were excluded due to missing data
        if prices.empty:
            logger.error("NO_VALID_RECOMMENDATION: VERDICT: LIVE DATA UNAVAILABLE (All candidates missing required data)")
            return {
                "status": "LIVE DATA UNAVAILABLE",
                "recommendation_status": "DATA-INCOMPLETE / NO VALID RECOMMENDATION",
                "scores": pd.Series(dtype=float),
                "weights": pd.Series(dtype=float)
            }
            
        # [NEW] CANDIDATE-LEVEL QUARANTINE FIREWALL
        quarantined_candidates = []
        real_eligible_candidates = []
        for t in factor_matrix.index:
            if aggregated_fundamental_statuses.get(t) == "MOCK":
                quarantined_candidates.append({
                    "ticker": t,
                    "reason": "MOCK_FUNDAMENTALS",
                    "data_status": "MOCK"
                })
            else:
                real_eligible_candidates.append(t)
                
        if quarantined_candidates:
            logger.warning(f"Quarantined {len(quarantined_candidates)} candidates due to MOCK data: {[q['ticker'] for q in quarantined_candidates]}")
            
        if not real_eligible_candidates:
            logger.error("NO_VALID_RECOMMENDATION: VERDICT: DATA-INCOMPLETE (All candidates were quarantined)")
            return {
                "status": "SUCCESS",
                "recommendation_status": "DATA-INCOMPLETE / NO VALID RECOMMENDATION",
                "scores": pd.Series(dtype=float),
                "weights": pd.Series(dtype=float)
            }
            
        # Filter all structures to contain only eligible candidates
        factor_matrix = factor_matrix.loc[real_eligible_candidates]
        fundamental_scores = fundamental_scores.loc[real_eligible_candidates]
        sentiment_series = sentiment_series.loc[real_eligible_candidates]
        alt_data_scores = alt_data_scores.loc[real_eligible_candidates]
        prices = prices[real_eligible_candidates]
        raw_volumes = raw_volumes[real_eligible_candidates]
        
        # Determine recommendation status based on eligible candidate depth
        if len(real_eligible_candidates) >= 5:
            recommendation_status = "REAL RECOMMENDATION"
        else:
            recommendation_status = "DATA-INCOMPLETE / NO VALID RECOMMENDATION"
            logger.warning(f"Insufficient real candidates ({len(real_eligible_candidates)} < 5). Status downgraded to DATA-INCOMPLETE.")
            return {
                "status": "SUCCESS",
                "recommendation_status": recommendation_status,
                "scores": pd.Series(dtype=float),
                "weights": pd.Series(dtype=float),
                "eligible_candidates_count": len(real_eligible_candidates)
            }

        
        # 2. 시장 국면 판단 (Regime Detection)
        # (임시: 실제 지수가 없을 경우 유니버스 평균을 벤치마크로 사용)
        market_index = prices.mean(axis=1)
        
        # [신규] 포트폴리오 이력 시딩 (Risk Engine용 과거 데이터 생성)
        self.portfolio_state.seed_history(market_index)
        
        regime_info = self.regime_engine.detect_regime(market_index)
        
        # 3. 전략 선택 및 가중치 조정 (Meta Controller & Strategic Biasing)
        strategy = self.meta_controller.select_strategy_by_regime(regime_info)
        
        # [수정] 전략(Strategy)을 가중치 편향으로 매핑 (Decision-to-Action)
        # 1. 횡보장 또는 미정 상태: 기본 가중치로 복귀 (Fallback)
        if strategy in ["sideways_neutral", None]:
            logger.info("Regime is Neutral/Sideways. Reverting to balanced DEFAULT_FACTOR_WEIGHTS.")
            current_weights = DEFAULT_FACTOR_WEIGHTS.copy()
        else:
            # 2. Bull/Bear 전략에 따른 팩터 가중치 조정
            regime_context = 'bull' if strategy == "aggressive_momentum" else 'bear'
            current_weights = self.regime_engine.get_adjusted_weights(DEFAULT_FACTOR_WEIGHTS, regime_context)
            logger.info(f"Strategic Bias applied: {strategy}")

        # [NEW] 3b. 팩터 가중치 동적 최적화 (FactorWeightOptimizer 연동)
        # 최근 팩터 수익률( prices 기반)을 분석하여 가중치 미세 조정 (샤프지수 극대화)
        target_factors_returns = prices.pct_change().dropna()
        current_weights = self.factor_optimizer.update_dynamic_weights(target_factors_returns, current_weights)
        logger.info(f"Dynamically Optimized Factor Weights: {current_weights}")
        
        # GLOBAL 교차 섹션 표준화 (Ranking Engine)
        standardized_factors = self.ranking_engine.apply_cross_sectional_standardization(factor_matrix)
        
        # 5. 리스크 조정 스코어링 (Risk-adjusted Scoring) - 동적 가중치(current_weights) 반영
        # [수정] 레짐에 따른 가중치를 직접 점수 계산에 투입 (판단 -> 행동 연결)
        logger.info(f"Applying Dynamic Regime Weights: {current_weights}")
        raw_factor_scores = self.scoring_engine.calculate(standardized_factors, weights=current_weights)
        
        
        # 리스크 지표 산출용 변동성/MDD (최근 1년 데이터로 한정하여 과도한 방어 방지)
        recent_prices = prices.tail(252)
        volatility = recent_prices.pct_change().std() * np.sqrt(252)
        mdd = (recent_prices / recent_prices.cummax() - 1).min()
        
        # 5. 하이브리드 앙상블 스코어링 (Meta-Alpha Dynamic Weighting + Strategic Bias)
        # [수정] MetaController의 전략 결정(strategy)을 앙상블 엔진에 투입
        ensemble_scores = self.meta_alpha_engine.combine_scores(
            raw_factor_scores, 
            fundamental_scores, # [NEW]
            sentiment_series, 
            alt_data_scores,
            strategy=strategy
        )
        
        # [P6-16] Extract Provenance and Drop Insufficient Coverage Candidates
        provenance_data = getattr(ensemble_scores, "attrs", {}).get("provenance", {})
        valid_ensemble_mask = ensemble_scores.notna()
        ensemble_scores = ensemble_scores[valid_ensemble_mask]
        
        for t, p in provenance_data.items():
            if t in ensemble_scores.index:
                logger.info(f"[{t}] Provenance: Effective Coverage={p['effective_weight_coverage']:.2f}, "
                            f"Effective Weights={p['effective_runtime_weights']}")
            else:
                logger.warning(f"[{t}] Dropped due to insufficient model coverage (Coverage={p.get('effective_weight_coverage', 0):.2f} < 0.50)")
                        
        if len(ensemble_scores) < 5:
            logger.warning(f"Candidates dropped below 5 after model coverage check. Status downgraded to DATA-INCOMPLETE.")
            return {
                "status": "SUCCESS",
                "recommendation_status": "DATA-INCOMPLETE / NO VALID RECOMMENDATION",
                "scores": pd.Series(dtype=float),
                "weights": pd.Series(dtype=float),
                "provenance": provenance_data,
                "eligible_candidates_count": len(ensemble_scores)
            }
        
        # 6. 교차 자산 매크로 조정 (Cross-Asset Macro Overlay)
        macro_adjusted_scores = self.cross_asset_engine.get_macro_adjusted_scores(ensemble_scores)
        
        # 7. 리스크 조정 스코어링 (Risk-adjusted Scoring)
        # [수정] 동일 알파 중복 반영 방지를 위해 Fundamental Overlay 삭제 (Option 1 적용)
        risk_adjusted_scores = self.scoring_engine.apply_risk_penalties(
            macro_adjusted_scores, volatility, mdd, recent_prices.pct_change()
        )
        
        # 8. 실시간 포트폴리오 상태 업데이트 및 리스크 체크 (Portfolio State Integration)
        # 현재 가격 기준 총 평가액 갱신
        self.portfolio_state.update_portfolio_value(prices.iloc[-1])
        
        # 실제 시스템 수익률 이력 사용 (Stub 제거)
        portfolio_history = self.portfolio_state.get_history()
        
        # [수정] 8. 리스크 엔진 연동 및 킬스위치 체크 (Real-time Risk Guard)
        # 1. MDD 체크 (Kill Switch)
        current_mdd = self.portfolio_state.calculate_drawdown()
        if self.risk_engine.check_kill_switch(current_mdd):
            logger.critical("FORCED LIQUIDATION: Kill switch active. Halting all alpha operations.")
            # 전량 매도 주문 생성 (target_weights = 0)
            return {"status": "HALTED", "reason": f"MDD Kill Switch triggered at {current_mdd:.2%}"}
            
        # 2. 실시간 VaR 산출 및 노출도 제어 (Exposure Scaling)
        # 포트폴리오 수익률 이력 기반 VaR 산출 (Stub -> Real)
        portfolio_returns = portfolio_history.pct_change().dropna()
        current_var = self.risk_engine.calculate_var(portfolio_returns)
        scaling_factor = self.risk_engine.get_exposure_scaling_factor(current_var)
        
        # 테일 리스크 체크 및 노출도 제어 (기존 로직 보완)
        risk_multiplier = self.tail_risk_engine.get_risk_multiplier(portfolio_history, recent_prices.pct_change().mean(axis=1), recent_prices)
        
        # 최종 리스크 계수 (VaR Scaling * Tail Multiplier)
        final_risk_adj = scaling_factor * risk_multiplier
        
        # [수정] 명확한 상태 분기 및 중복 로그 제거
        risk_status = self._determine_risk_status(final_risk_adj)
        
        if risk_status == RiskStatus.CRITICAL:
            logger.critical(f"EMERGENCY EXIT: Risk Factor {final_risk_adj:.2f} too low. Liquidating positions.")
            return {"status": "LIQUIDATED", "reason": "Extreme Volatility/Risk Breach"}
            
        elif risk_status == RiskStatus.WARNING:
            logger.warning(f"Risk Guard Active: Scaling Exposure by {final_risk_adj:.2f}x.")
            risk_adjusted_scores *= final_risk_adj
            
        else:
            logger.info("Risk Status: NORMAL (Stable market conditions).")

        # 4. 운용 한도 검증 (Capacity Check)
        aum = CAPACITY_SETTINGS.get('target_aum', 10000000)
        # recent_prices의 마지막 행을 사용하여 가상의 ADV 생성
        adv_data = recent_prices.iloc[-1] * 1000000 
        capacity_report = self.capacity_engine.get_capacity_score(aum, risk_adjusted_scores/risk_adjusted_scores.sum(), adv_data)
        
        # 9. 거래 가능성 검증 (Liquidity & Execution Filter)
        # 저유동성 종목을 배분 전 단계에서 제거 (Paper Profit 방지)
        adv_20d = raw_volumes.tail(20).mean() # 20일 ADV 계산
        min_vol = EXECUTION_SETTINGS.get('min_volume_threshold', 500000)
        
        liquid_tickers = self.execution_engine.filter_by_liquidity(
            tickers=risk_adjusted_scores.index.tolist(),
            volumes=adv_20d,
            threshold=min_vol
        )
        
        # 필터링 결과 반영된 스코어 재정합
        tradable_scores = risk_adjusted_scores.loc[liquid_tickers]
        
        if capacity_report['is_over_capacity']:
            logger.warning(f"Capacity Limit Reached! Recommended Max AUM: {capacity_report['recommended_max_aum']:,.0f}")
        
        # 9b. [NEW] 포트폴리오 강건성 검증 (RobustnessEngine 연동)
        robust_info = None
        if self.run_research:
            logger.info("AnalyticsSystems: Running Robustness Perturbation Test with Live Risk Data...")
            # 가중치 미세 변동 시 스코어 일관성 확인 (Fragility Guard)
            robust_info = self.robustness_engine.run_perturbation_test(
                self.scoring_engine,
                self.meta_alpha_engine,
                factor_matrix.loc[liquid_tickers],
                sentiment_series.loc[liquid_tickers],
                alt_data_scores.loc[liquid_tickers],
                volatility.loc[liquid_tickers],
                mdd.loc[liquid_tickers],
                recent_prices.pct_change()[liquid_tickers]
            )
            logger.info(f"Portfolio Robustness Check: Score={robust_info['robustness_score']:.2f}")
            if robust_info['robustness_score'] < 0.6:
                logger.warning("Low Robustness Score detected! Portfolio may be overly sensitive to noise.")

        # 10. 포트폴리오 최적화 (Alpha & Risk-driven Construction)
        # [수정] PortfolioEngine을 필수 경로에 포함하고, Softmax 제약 및 Risk Parity 옵션 연동
        from utils.config import PORTFOLIO_SETTINGS
        p_method = PORTFOLIO_SETTINGS.get("method", "softmax-weighted")
        
        logger.info(f"--- [Portfolio weighting] Method: {p_method} | Assets: {len(tradable_scores)} ---")
        
        initial_target_weights = self.portfolio_engine.calculate_weights(
            scores=tradable_scores, # [수정] 필터링된 스코어 전달
            method=p_method,
            volatility=volatility.reindex(tradable_scores.index), # 리인덱싱 보장
            temperature=0.7
        )
        
        # 11. 실시간 리스크 엔진 검증 (Reactive Risk Management)
        # 현재 타겟 비중 기반의 예상 포트폴리오 VaR 계산
        returns_df = recent_prices.pct_change().dropna()
        # 타겟 종목들만 추출
        targets = initial_target_weights.index
        if not initial_target_weights.empty:
            portfolio_var = self.risk_engine.calculate_portfolio_var(initial_target_weights, returns_df[targets])
            risk_contribution = self.risk_engine.calculate_risk_contribution(initial_target_weights, returns_df[targets])
            scaling_factor = self.risk_engine.get_exposure_scaling_factor(portfolio_var)
            
            if scaling_factor < 1.0:
                logger.warning(f"VaR Limit Breach! Scaling exposure by {scaling_factor:.2f}x (VaR: {portfolio_var:.2%})")
                target_weights = initial_target_weights * scaling_factor
            else:
                target_weights = initial_target_weights
                logger.info(f"Risk Check Passed: Portfolio VaR is {portfolio_var:.2%}")
            
            # 리스크 기여도 상위 3개 로깅
            top_risk = risk_contribution.sort_values(ascending=False).head(3)
            logger.info(f"Top Risk Contributors: {top_risk.to_dict()}")
        else:
            target_weights = initial_target_weights
            portfolio_var = 0.0

        # [수정] 11. 실행 엔진 연결 (Alpha-to-Execution Linkage)
        # Simulation(Backtest)과 Live 모드 모두 ExecutionEngine을 통해 실질 체계 반영
        execution_report = self.execution_engine.execute_orders(
            target_weights, 
            prices.iloc[-1], 
            self.portfolio_state.cash
        )
        
        executed_weights = execution_report['executed_weights']
        total_cost = execution_report['total_cost']
        
        logger.info(f"Execution Completed: Total Commission = {total_cost:,.0f} | Portfolio Rebalanced.")
        
        # 12. 신호 및 포트폴리오 상태 저장 (Persistence)
        # [수정] 타겟 비중과 실제 집행 비중을 모두 저장
        self._save_trading_signals(risk_adjusted_scores, target_weights, executed_weights, regime_info)
        
        # 13. 포트폴리오 상태 업데이트 (Feedback Loop)
        # [수정] 타겟 비중이 아닌 '실제 체결된 비중'으로 상태 동기화
        self.portfolio_state.apply_trades(executed_weights, prices.iloc[-1])
        
        # 13. 피드백 및 학습 (Feedback & Learning Loop)
        # 실제 수익률 로드 (이전 봉 대비 현재 가격 변화)
        actual_returns = prices.pct_change().iloc[-1]
        
        # 가중치 학습 (Predicted Scores vs Actual Returns)
        # ScoringEngine의 팩터 가중치를 실적에 따라 업데이트
        new_factor_weights = self.learning_engine.update_weights(
            self.scoring_engine.weights,
            risk_adjusted_scores,
            actual_returns,
            factor_matrix
        )
        self.scoring_engine.update_weights(new_factor_weights)
        
        # Meta-Alpha Engine 성과 추적 (알파원천별 기여도 피드백)
        # (간단한 예시: 센티먼트와 가격 수익률의 상관관계 등을 성과로 입력)
        self.meta_alpha_engine.track_performance("factor", actual_returns.mean()) 
        self.meta_alpha_engine.track_performance("fundamental", actual_returns.mean()) 
        self.meta_alpha_engine.track_performance("sentiment", actual_returns.mean())
        self.meta_alpha_engine.track_performance("alt_data", actual_returns.mean())
        
        # 14. 성과 및 건전성 모니터링 (Monitoring Engine)
        exposure = risk_multiplier if risk_status != RiskStatus.CRITICAL else 0.0
        portfolio_var_hist = self.portfolio_state.calculate_var_historical()
        
        # 성과 모니터링 데이터 취합 및 로깅
        history_returns = self.portfolio_state.get_history().pct_change().dropna()
        if not history_returns.empty:
            sharpe = self.monitoring_engine.calculate_rolling_sharpe(history_returns).iloc[-1]
            mdd_val = self.monitoring_engine.monitor_mdd(history_returns)
            self.monitoring_engine.log_system_status({
                "portfolio_var": portfolio_var_hist, 
                "exposure": exposure,
                "rolling_sharpe": sharpe,
                "current_mdd": mdd_val,
                "regime": regime_info['regime']
            })
        
        logger.info("--- [V2 Autonomous Pipeline Cycle Completed] ---")
        top_3 = risk_adjusted_scores.sort_values(ascending=False).head(3)
        logger.info(f"Top 3 Scores (0-100 scale): {top_3.to_dict()}")
        
        # 12. [NEW] 알파 기여도 분석 (AlphaAttribution 연동)
        # 각 알파 소스가 현재 포트폴리오의 기대 PnL에 미치는 영향력 분해
        alpha_scores_dict = {
            "factor": raw_factor_scores,
            "fundamental": fundamental_scores,
            "sentiment": sentiment_series,
            "alt_data": alt_data_scores
        }
        # 최근 1일 수익률을 프록시로 사용하여 기여도 분석
        yesterday_returns = recent_prices.pct_change().iloc[-1].fillna(0)
        attr_report = self.attribution_engine.attribute_return(
            yesterday_returns, target_weights, alpha_scores_dict
        )
        logger.info(f"Alpha Attribution (Expected PnL Contribution): {attr_report}")
        
        return {
            "status": "SUCCESS",
            "recommendation_status": recommendation_status,
            "scores": risk_adjusted_scores,
            "weights": target_weights,
            "risk_multiplier": risk_multiplier,
            "capacity": capacity_report,
            "robustness": robust_info,
            "attribution": attr_report,
            "quarantined_candidates": quarantined_candidates,
            "eligible_candidates_count": len(real_eligible_candidates)
        }

    def _run_frozen_live_cycle(self, tickers: list, ciks: Dict[str, str], checkpoint=None) -> Dict:
        """Canonical live route (P6-18): delegates to the ONE shared pipeline.

        ``pipeline.canonical.CanonicalPipeline`` runs acquisition -> provenance
        gate -> frozen FactorEngine/ScoringEngine -> DecisionEngine (BEAR ->
        MODEL_RANK_E -> sector cap/sizing) -> final validity.  No regime weight
        adjustment, optimizer, learning update, LLM score, or synthetic
        alternative-data fallback participates.
        """
        from pipeline.canonical import CanonicalPipeline
        pipeline = CanonicalPipeline(self.data_loader, self.factor_engine, self.ranking_engine,
                                     self.scoring_engine, self.decision_engine, self.regime_engine,
                                     capital=self.portfolio_state.cash, checkpoint=checkpoint)
        return pipeline.evaluate(list(tickers), ciks or {})

    def _save_trading_signals(self, scores: pd.Series, target_weights: pd.Series, executed_weights: pd.Series, regime_info: Dict):
        """
        [수정] 타겟 신호와 실제 집행 결과를 모두 로컬 파일로 저장 (신뢰성 확보)
        """
        import os
        from datetime import datetime
        
        save_dir = "data/signals"
        if not os.path.exists(save_dir):
            os.makedirs(save_dir)
            
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # 1. 스코어, 타겟 비중, 실행 비중을 통합 저장
        signal_df = pd.DataFrame({
            "score": scores,
            "target_weight": target_weights,
            "executed_weight": executed_weights
        }).fillna(0)
        
        signal_path = f"{save_dir}/signals_{timestamp}.csv"
        signal_df.to_csv(signal_path)
        
        # 2. 메타데이터 저장 (레짐 정보 등)
        meta_path = f"{save_dir}/meta_{timestamp}.json"
        import json
        with open(meta_path, 'w') as f:
            json.dump(regime_info, f, indent=4)
            
        logger.info(f"Execution Transparency: Target vs Executed signals saved to {save_dir}")

    def run_system_audit(self, tickers):
        """시스템 성과 분석 및 강건성 검증 (Audit Mode)"""
        logger.info("--- [System Audit Mode] ---")
        
        # 1. 실제 데이터 기반 리스크 지표 추출 (최근 1년)
        end_date = pd.Timestamp.now().strftime('%Y-%m-%d')
        start_date = (pd.Timestamp.now() - pd.DateOffset(years=1)).strftime('%Y-%m-%d')
        prices = self.data_loader.get_price_data(tickers, start_date, end_date)
        
        returns_df = prices.pct_change().dropna()
        volatility = returns_df.std() * np.sqrt(252)
        mdd = (prices / prices.cummax() - 1).min()
        
        # 2. 분석용 가상 데이터 생성 (구조 유지)
        factor_scores = pd.DataFrame(np.random.rand(len(tickers), 3) * 100, index=tickers)
        sentiment_scores = pd.Series(np.random.rand(len(tickers)) * 100, index=tickers)
        alt_scores = pd.Series(np.random.rand(len(tickers)) * 100, index=tickers)
        macro_adj = pd.Series(np.random.normal(0, 1.0, len(tickers)), index=tickers)
        
        # 3. 알파 기여도 분석 (Attribution)
        alpha_scores_dict = {
            "factor": factor_scores.mean(axis=1),
            "sentiment": sentiment_scores,
            "alt_data": alt_scores,
            "macro": macro_adj
        }
        mock_returns = returns_df.mean() # 실제 수익률 기반
        
        # [수정] 감사 모드에서도 1/N 배분 제거 -> Softmax 배분 시뮬레이션
        combined_mock_scores = (factor_scores.mean(axis=1) + sentiment_scores + alt_scores) / 3
        mock_weights = self.portfolio_engine.calculate_weights(
            scores=combined_mock_scores,
            method=PORTFOLIO_SETTINGS["method"]
        )
        
        attr_report = self.attribution_engine.attribute_return(
            mock_returns, mock_weights, alpha_scores_dict
        )
        
        # 4. 강건성 테스트 (Robustness) - 리뉴얼된 엔진 호출
        robust_report = self.robustness_engine.run_perturbation_test(
            self.scoring_engine, 
            self.meta_alpha_engine,
            factor_scores, 
            sentiment_scores, 
            alt_scores,
            volatility,
            mdd,
            returns_df
        )
        
        logger.info(f"Audit Completed. Robustness Score: {robust_report['robustness_score']:.2f}")
        return {
            "attribution": attr_report,
            "robustness": robust_report
        }

if __name__ == "__main__":
    # P6-18: the command-line entry point is app.py.  ``python main.py`` keeps
    # working and runs the Automated Market Scan through the canonical pipeline.
    import sys
    from app import main as app_main
    sys.exit(app_main(["scan", *sys.argv[1:]]))
