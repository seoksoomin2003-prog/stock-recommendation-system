#!/usr/bin/env python3
import sys
import os

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))  # P6-19: was a hardcoded Desktop path

def main():
    print("============================================================")
    print("         P0 RUNTIME IMPORT AND CONSTRUCTOR VALIDATION       ")
    print("============================================================")

    # 1. Import Validation
    print("1. Testing Imports...")
    try:
        from core.regime_engine import RegimeEngine
        from core.factor_engine import FactorEngine
        from core.meta_alpha_engine import MetaAlphaEngine
        from core.scoring_engine import ScoringEngine
        from core.ranking_engine import RankingEngine
        from core.portfolio_engine import PortfolioEngine
        from core.risk_engine import RiskEngine
        from core.learning_engine import LearningEngine
        from core.backtest_engine import BacktestEngine
        from core.alternative_data_engine import AlternativeDataEngine
        from core.cross_asset_engine import CrossAssetEngine
        from core.meta_controller import MetaController
        from core.monitoring_engine import MonitoringEngine
        from core.risk_systems import TailRiskEngine, CapacityEngine
        from core.analytics_systems import AlphaAttribution, RobustnessEngine
        from core.portfolio_state_engine import PortfolioStateEngine
        from core.rag_engine import RAGEngine
        from core.llm_fundamental_engine import LLMFundamentalEngine
        from core.llm_validation_layer import LLMValidationLayer
        from execution.execution_engine import ExecutionEngine
        from execution.execution_alpha_engine import ExecutionAlphaEngine
        from alpha_engine.system import AlphaScoringEngine
        from alpha_engine.input.resolver import EntityResolutionEngine
        from alpha_engine.input.pipeline import AliasGenerationPipeline
        from alpha_engine.data.sentiment_engine import LLMSentimentEngine
        from alpha_engine.data.sec_engine import SECInsiderEngine
        from alpha_engine.data.trends_engine import GoogleTrendsEngine
        from alpha_engine.data.fallback_engine import MultiApiFallbackEngine
        from alpha_engine.data.buzz_engine import BuzzEngine
        from alpha_engine.data.macro_engine import MacroEventEngine
        from alpha_engine.processor.pipeline import AlphaProcessor
        from alpha_engine.scorer.alpha_scorer import AlphaScorer
        from alpha_engine.output.standardizer import AlphaStandardizer
        from main import QuantTradingSystemV2
        print("[PASS] All core modules successfully imported.")
    except Exception as e:
        print(f"[FAIL] Core import failed: {type(e).__name__} - {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    # 2. Constructor Instantiation Validation
    print("\n2. Instantiating Major Components...")
    try:
        print("- EntityResolutionEngine...")
        resolver = EntityResolutionEngine()
        
        print("- FactorEngine...")
        factor = FactorEngine()
        
        print("- ScoringEngine...")
        scoring = ScoringEngine()
        
        print("- NewsEngine...")
        from core.news_engine import NewsEngine
        news = NewsEngine()
        
        print("- AlternativeDataEngine...")
        alt_data = AlternativeDataEngine()
        
        print("- Analytics Components (AlphaAttribution, RobustnessEngine)...")
        attribution = AlphaAttribution()
        robustness = RobustnessEngine()
        
        print("- QuantTradingSystemV2...")
        system = QuantTradingSystemV2(mode="backtest")
        
        print("- AlphaScoringEngine...")
        alpha_scoring = AlphaScoringEngine()
        
        print("[PASS] All core constructors successfully executed.")
    except Exception as e:
        print(f"[FAIL] Constructor instantiation failed: {type(e).__name__} - {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    print("\n============================================================")
    print("               ALL P0 RUNTIME CHECKS PASSED                 ")
    print("============================================================")

if __name__ == "__main__":
    main()
