from execution.execution_alpha_engine import ExecutionAlphaEngine
import numpy as np

def test_execution_alpha():
    engine = ExecutionAlphaEngine()
    
    # 가상 시나리오 설정
    market_price = 100.0
    order_size = 10000     # 10,000주 주문
    avg_volume = 100000    # 일평균 거래량 100,000주 (참여율 10%)
    volatility = 0.02      # 일일 변동성 2%
    
    print("--- Execution Simulation Test ---")
    res = engine.simulate_execution_price(market_price, order_size, avg_volume, volatility, is_buy=True)
    
    print(f"Market Price: {res['market_price']:.2f}")
    print(f"Impact Cost: {res['impact']*10000:.2f} bps")
    print(f"Slippage Cost: {res['slippage']*10000:.2f} bps")
    print(f"Fixed Execution Price: {res['execution_price']:.2f}")
    print(f"Optimized Execution Price (Sliced): {res['optimized_price']:.2f}")
    print(f"Execution Alpha (bps): {res['execution_alpha']*10000:.2f}")
    
    # Slicing Test
    slices = engine.get_order_slices(order_size, method='TWAP')
    print(f"\nTWAP Slices (n={engine.n_slices}): {slices}")
    
    assert res['optimized_price'] < res['execution_price'] # 매수 시 최적화 가격은 더 낮아야 함
    print("\nVerification Successful!")

if __name__ == "__main__":
    test_execution_alpha()
