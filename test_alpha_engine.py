from alpha_engine.system import AlphaScoringEngine
import pandas as pd

def test_engine():
    print("Initializing Institutional Alpha Scoring Engine...")
    engine = AlphaScoringEngine()
    
    tickers = ["AAPL", "NVDA", "TSLA", "UNKNOWN_TICKER"]
    print(f"Executing pipeline for: {tickers}")
    
    try:
        results = engine.run_research_pipeline(tickers)
        print("\n--- [FINAL ALPHA SCORES] ---")
        print(results)
    except Exception as e:
        print(f"Engine failure: {str(e)}")

if __name__ == "__main__":
    test_engine()
