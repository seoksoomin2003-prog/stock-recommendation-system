import pandas as pd
import numpy as np
from core.meta_alpha_engine import MetaAlphaEngine

def test_meta_alpha_ensemble():
    engine = MetaAlphaEngine()
    
    # 가상 점수 데이터
    tickers = ["AAPL", "MSFT", "GOOGL"]
    factor_scores = pd.Series([0.8, 0.6, 0.4], index=tickers)
    sentiment_scores = pd.Series([0.2, 0.5, 0.8], index=tickers)
    alt_data_scores = pd.Series([0.9, 0.1, 0.5], index=tickers)
    
    print("--- Meta-Alpha Ensemble Test ---")
    
    # 1. 초기 가중치 기반 결합
    initial_weights = engine.current_weights.copy()
    print(f"Initial Weights: {initial_weights}")
    
    # 2. 특정 알파(sentiment) 성능 하락 시뮬레이션
    print("\nSimulating Underperformance in Sentiment Alpha...")
    engine.performance_history["sentiment"] = [-0.15, -0.20, -0.18, -0.25] # Drift Threshold(-0.1) 이하
    
    # 3. 적응형 가중치 산출 및 결합
    final_score = engine.combine_scores(factor_scores, None, sentiment_scores, alt_data_scores)
    new_weights = engine.current_weights
    
    print(f"Updated Weights: {new_weights}")
    print(f"\nFinal Ensemble Scores:\n{final_score}")
    
    # 검증: 부진한 'sentiment'의 가중치가 초기보다 줄어들어야 함
    assert new_weights['sentiment'] < initial_weights['sentiment']
    
    print("\nVerification Successful! Multi-Alpha Ensemble is working dynamically.")

if __name__ == "__main__":
    test_meta_alpha_ensemble()
