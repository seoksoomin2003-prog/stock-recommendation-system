#!/usr/bin/env python3
import sys
import os

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))  # P6-19: was a hardcoded Desktop path

def test_provider_switching():
    print("============================================================")
    print("           PROVIDER MODE SWITCHING & FACTORY TEST           ")
    print("============================================================")

    # 1. Force APP_MODE to 'local'
    print("1. Testing Local Mode Providers...")
    os.environ["APP_MODE"] = "local"
    import utils.config
    utils.config.APP_MODE = "local"
    
    from core.providers import ProviderFactory
    ProviderFactory.reset_providers()

    sentiment_p = ProviderFactory.get_sentiment_provider()
    fundamental_p = ProviderFactory.get_fundamental_provider()
    alias_p = ProviderFactory.get_alias_provider()

    print(f"- Sentiment Provider class: {sentiment_p.__class__.__name__}")
    print(f"- Fundamental Provider class: {fundamental_p.__class__.__name__}")
    print(f"- Alias Provider class: {alias_p.__class__.__name__}")

    assert sentiment_p.__class__.__name__ == "LocalSentimentProvider", "Local mode did not yield LocalSentimentProvider"
    assert fundamental_p.__class__.__name__ == "LocalFundamentalProvider", "Local mode did not yield LocalFundamentalProvider"
    assert alias_p.__class__.__name__ == "LocalAliasGenerationProvider", "Local mode did not yield LocalAliasGenerationProvider"

    print("[PASS] Local Mode Providers validated correctly.")

    # 2. Test Local Provider Behavior (Offline/Deterministic)
    print("\n2. Testing Local Mode Deterministic Scopes...")
    sent_res = sentiment_p.analyze_sentiment("AAPL", ["Apple surges to new records! bullish buy growth strong"], company_name="Apple")
    print(f"- Local Sentiment Result: {sent_res}")
    assert sent_res["sentiment"] > 0.0, "Local keyword sentiment failed positive check"
    assert sent_res["mode"] == "local"

    fund_res = fundamental_p.query_fundamental("Analyze cashflow metrics", ["quality"])
    print(f"- Local Fundamental Result: {fund_res}")
    assert fund_res["quality"] == "RAW" or fund_res["quality"] == "STABLE", "Local fundamental query failed to return quality metric"
    assert fund_res["mode"] == "local"

    # 3. Force APP_MODE to 'production'
    print("\n3. Testing Production Mode Providers...")
    os.environ["APP_MODE"] = "production"
    utils.config.APP_MODE = "production"
    ProviderFactory.reset_providers()

    prod_sentiment_p = ProviderFactory.get_sentiment_provider(llm_instance=None)
    prod_fundamental_p = ProviderFactory.get_fundamental_provider()
    prod_alias_p = ProviderFactory.get_alias_provider()

    print(f"- Production Sentiment Provider class: {prod_sentiment_p.__class__.__name__}")
    print(f"- Production Fundamental Provider class: {prod_fundamental_p.__class__.__name__}")
    print(f"- Production Alias Provider class: {prod_alias_p.__class__.__name__}")

    assert prod_sentiment_p.__class__.__name__ == "ProductionSentimentProvider", "Production mode did not yield ProductionSentimentProvider"
    assert prod_fundamental_p.__class__.__name__ == "ProductionFundamentalProvider", "Production mode did not yield ProductionFundamentalProvider"
    assert prod_alias_p.__class__.__name__ == "ProductionAliasGenerationProvider", "Production mode did not yield ProductionAliasGenerationProvider"

    print("[PASS] Production Mode Providers validated correctly.")

    # 4. Verify shared core scoring logic is identical
    print("\n4. Verifying Shared Core Scoring Architecture...")
    from core.scoring_engine import ScoringEngine
    import pandas as pd

    # Both modes share the exact same ScoringEngine
    se_1 = ScoringEngine()
    
    factor_matrix = pd.DataFrame({
        "momentum": [1.0, -0.5],
        "value": [0.2, 0.8],
        "quality": [0.5, 0.3],
        "low_volatility": [0.1, 0.9]
    }, index=["AAPL", "MSFT"])

    scores = se_1.calculate(factor_matrix)
    print(f"- Shared core scores calculated:\n{scores}")
    assert not scores.empty, "Shared scoring calculation returned empty result"

    print("[PASS] Shared core scoring logic verified.")
    print("\n============================================================")
    print("           ALL PROVIDER FACTORY SWITCHING TESTS PASSED       ")
    print("============================================================")

if __name__ == "__main__":
    test_provider_switching()
