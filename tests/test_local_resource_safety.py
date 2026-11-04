#!/usr/bin/env python3
import sys
import os

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))  # P6-19: was a hardcoded Desktop path

def test_local_resource_safety():
    print("============================================================")
    print("            TEST 1 & 2: LOCAL RESOURCE SAFETY TEST           ")
    print("============================================================")

    # Set local mode
    os.environ["APP_MODE"] = "local"
    import utils.config
    utils.config.APP_MODE = "local"
    
    # 1. Importing the application should NOT initialize heavy components or load models
    print("1. Importing modules...")
    from core.rag_engine import RAGEngine
    from core.providers import ProviderFactory
    from alpha_engine.system import AlphaScoringEngine
    from main import QuantTradingSystemV2

    print("[PASS] Modules imported without loading heavy resources.")

    # 2. Construction should NOT trigger model loads or Chroma DB setups
    print("\n2. Instantiating components in Local Mode...")
    rag = RAGEngine()
    sentiment = ProviderFactory.get_sentiment_provider()
    fundamental = ProviderFactory.get_fundamental_provider()
    alias = ProviderFactory.get_alias_provider()

    print(f"- RAGEngine initialized. vector_db state: {rag.vector_db}")
    print(f"- Sentiment Provider class: {sentiment.__class__.__name__}")
    print(f"- Fundamental Provider class: {fundamental.__class__.__name__}")
    print(f"- Alias Provider class: {alias.__class__.__name__}")

    assert rag.vector_db is None, "RAGEngine constructed vector_db automatically in Local Mode!"
    assert rag.llm is None, "RAGEngine constructed LLM automatically in Local Mode!"
    assert sentiment.__class__.__name__ == "LocalSentimentProvider", "Local mode did not yield LocalSentimentProvider"
    assert fundamental.__class__.__name__ == "LocalFundamentalProvider", "Local mode did not yield LocalFundamentalProvider"
    assert alias.__class__.__name__ == "LocalAliasGenerationProvider", "Local mode did not yield LocalAliasGenerationProvider"

    print("[PASS] Construction does not load heavy resources.")
    print("============================================================")

if __name__ == "__main__":
    test_local_resource_safety()
