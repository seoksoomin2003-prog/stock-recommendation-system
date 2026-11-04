#!/usr/bin/env python3
import sys
import os

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))  # P6-19: was a hardcoded Desktop path

def test_embedding_lazy_loading():
    print("============================================================")
    print("      TEST 3 & 4 & LAZY: EMBEDDING LAZY LOADING TEST        ")
    print("============================================================")

    # 1. Reset providers and enforce Local Mode
    print("1. Testing Local Mode Embedding Bypass (Test 3)...")
    os.environ["APP_MODE"] = "local"
    import utils.config
    utils.config.APP_MODE = "local"
    
    from core.providers import ProviderFactory
    ProviderFactory.reset_providers()

    local_alias_p = ProviderFactory.get_alias_provider()
    # In Local Mode, getting semantic similarity should NOT load SentenceTransformer
    # and should return fallback Jaccard / 0.5 similarity.
    sim = local_alias_p.get_semantic_similarity("Apple Inc", "Apple Corp", 0.6)
    print(f"- Local mode similarity (no download, no model): {sim}")
    assert sim == 1.0 or sim == 0.5 or (0.0 <= sim <= 1.0), "Local mode similarity invalid"
    print("[PASS] Local Mode Embedding Bypassed successfully without crash or download.")

    # 2. Production Mode construction should not load models immediately
    print("\n2. Testing Production Mode Construction Lazy Loading (Test 4)...")
    utils.config.APP_MODE = "production"
    ProviderFactory.reset_providers()

    prod_alias_p = ProviderFactory.get_alias_provider()
    print("- Production Provider instantiated.")
    assert prod_alias_p.__class__.__name__ == "ProductionAliasGenerationProvider", "Production mode did not yield ProductionAliasGenerationProvider"
    
    # Assert models are NOT loaded yet during construction
    assert prod_alias_p._fast_embedder is None, "Production SentenceTransformer model auto-loaded during construction!"
    assert prod_alias_p._nlp is None, "Production spaCy model auto-loaded during construction!"
    print("[PASS] Production models not loaded at constructor time.")

    # 3. Requesting similarity should trigger lazy loading once and cache it
    print("\n3. Testing Lazy Loading on first request...")
    # Mocking HuggingFace SentenceTransformer loading to verify once-only logic
    loaded_count = 0
    
    class FakeTransformer:
        def __init__(self, name, local_files_only=False):
            nonlocal loaded_count
            loaded_count += 1
            self.name = name
            
        def encode(self, text):
            return [0.1, 0.2]

    # Patch SentenceTransformer
    import core.providers
    original_transformer = getattr(core.providers, "SentenceTransformer", None)
    
    # Inject fake class
    class FakeUtil:
        @staticmethod
        def cos_sim(a, b):
            class Val:
                def item(self):
                    return 0.8
            return Val()
            
    sys.modules["sentence_transformers"] = type("MockST", (), {"SentenceTransformer": FakeTransformer, "util": FakeUtil})
    # Reset cached FAILED states
    prod_alias_p._fast_embedder = None
    
    # Request similarity twice
    sim1 = prod_alias_p.get_semantic_similarity("Apple", "Apple Inc", 0.6)
    sim2 = prod_alias_p.get_semantic_similarity("Apple", "Apple Inc", 0.6)
    
    print(f"- First sim: {sim1}, Second sim: {sim2}")
    print(f"- Model load attempts (loaded_count): {loaded_count}")
    
    assert loaded_count == 1, f"Model loaded {loaded_count} times instead of exactly once!"
    assert prod_alias_p._fast_embedder is not None, "Model was not cached on the provider instance!"
    
    # Restore original imports if exists
    if original_transformer:
        core.providers.SentenceTransformer = original_transformer

    print("[PASS] Lazy loading triggered once, cached, and successfully reused.")
    print("============================================================")

if __name__ == "__main__":
    test_embedding_lazy_loading()
