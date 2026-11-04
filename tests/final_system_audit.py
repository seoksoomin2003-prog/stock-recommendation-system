import pandas as pd
import numpy as np
from main import QuantTradingSystemV2
from utils.logger import setup_logger

logger = setup_logger("FinalAudit")

def run_final_integration_audit():
    # 1. 시스템 초기화
    system = QuantTradingSystemV2(mode="backtest")
    tickers = ["AAPL", "MSFT", "GOOGL", "NVDA", "AMZN", "TSLA", "XOM", "JPM"]
    
    print("\n" + "!"*60)
    print("!!! INSTITUTIONAL QUANT SYSTEM FINAL INTEGRATION AUDIT !!!")
    print("!"*60 + "\n")
    
    # 2. 메인 사이클 실행 (1회)
    # 내부적으로 Meta Alpha, Cross-Asset, Tail Risk, Capacity, Attribution이 모두 호출됨
    cycle_result = system.run_live_cycle(tickers)
    
    # 3. 시스템 통합 감사 (Audit)
    # Robustness 테스트 및 Attribution 요약 리포트 출력
    system.run_system_audit(tickers)
    
    print("-" * 50)
    print("CYCLE RESULT EXCERPT:")
    print(f"- Risk Multiplier: {cycle_result['risk_multiplier']:.2f}")
    if 'capacity_report' in cycle_result:
        print(f"- Max ADV Participation: {cycle_result['capacity_report']['max_participation']:.2%}")
        print(f"- Alpha Decay Factor: {cycle_result['capacity_report']['alpha_decay_factor']:.4f}")
    print("-" * 50)
    
    print("\nAudit Completed Successfully!")

if __name__ == "__main__":
    run_final_integration_audit()
