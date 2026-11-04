import pandas as pd
from core.cross_asset_engine import CrossAssetEngine

def test_cross_asset_adjustment():
    engine = CrossAssetEngine()
    
    # 테스트 데이터: TSLA(growth), JPM(value)
    base_scores = pd.Series({
        "TSLA": 0.5,
        "JPM": 0.3
    })
    
    print("--- Cross-Asset Macro Adjustment Test ---")
    print(f"Initial Scores: TSLA={base_scores['TSLA']}, JPM={base_scores['JPM']}")
    
    # 매크로 조정 적용 (시뮬레이션 데이터: 금리 +2% 상승 가정)
    adjusted_scores = engine.get_macro_adjusted_scores(base_scores)
    
    print(f"\nAdjusted Scores:")
    print(f"TSLA (Growth): {adjusted_scores['TSLA']:.4f} (Change: {adjusted_scores['TSLA'] - base_scores['TSLA']:+.4f})")
    print(f"JPM (Value): {adjusted_scores['JPM']:.4f} (Change: {adjusted_scores['JPM'] - base_scores['JPM']:+.4f})")
    
    # 검증: 금리 상승 시 성장주(TSLA)는 하락, 가치주(JPM)는 상승해야 함
    assert adjusted_scores['TSLA'] < base_scores['TSLA']
    assert adjusted_scores['JPM'] > base_scores['JPM']
    
    print("\nVerification Successful!")

if __name__ == "__main__":
    test_cross_asset_adjustment()
