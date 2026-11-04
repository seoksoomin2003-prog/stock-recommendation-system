"""Deterministic P6-17.4 production-boundary invariants (no network/files)."""
import unittest
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from core.decision_engine import DecisionEngine
from core.factor_engine import FactorEngine
from core.ranking_engine import RankingEngine
from core.scoring_engine import ScoringEngine
from core.universe_provider import WikipediaSP500BootstrapProvider
from main import QuantTradingSystemV2
from utils.config import DEFAULT_FACTOR_WEIGHTS
from utils.market_calendar import expected_latest_trading_session


def candidate(i, **overrides):
    value = {"security_id": f"S{i}", "ticker": f"T{i}", "close": 100., "volume": 600000.,
             "alpha": 1. - i / 100, "atr": 2., "ema20": 95., "alpha_percentile": 1. - i / 100,
             "data_status": "REAL", "price_status": "REAL", "volume_status": "REAL", "fundamental_status": "REAL"}
    value.update(overrides)
    return value


class _Loader:
    def __init__(self):
        dates = pd.date_range("2024-01-01", periods=430, freq="B")
        self.prices = pd.DataFrame({f"T{i}": np.linspace(50 + i, 110 + 2*i, len(dates)) for i in range(5)}, index=dates)
        self.prices.attrs.update(provider="yfinance", provider_status={f"T{i}": "REAL" for i in range(5)})
        self.volumes = pd.DataFrame({f"T{i}": 600000. for i in range(5)}, index=dates)
        self.volumes.attrs.update(provider="yfinance", provider_status={f"T{i}": "REAL" for i in range(5)})
        self.financials = pd.DataFrame({"per": [10, 11, 12, 13, 14], "pbr": [1, 1.1, 1.2, 1.3, 1.4],
                                        "roe": [.2, .21, .22, .23, .24], "profitMargin": [.1, .11, .12, .13, .14]},
                                       index=[f"T{i}" for i in range(5)])
        self.financials.attrs.update(provider_status={f"T{i}": "REAL" for i in range(5)}, field_provenance={f"T{i}": {} for i in range(5)})
    def get_price_data(self, *args): return self.prices
    def get_volume_data(self, *args): return self.volumes
    def get_financial_data(self, *args, **kwargs): return self.financials


class TestP6174Reconciliation(unittest.TestCase):
    def test_final_portfolio_gate_prevents_real_status(self):
        # Six initially valid securities shrink to four due to the frozen 40%
        # technology cap; final status must not claim a real recommendation.
        items = [candidate(i, sector="Technology" if i < 3 else "Energy") for i in range(6)]
        result = DecisionEngine().evaluate_portfolio(datetime.now(timezone.utc), 10000, "BULL", items)
        self.assertEqual(len(result.top5), 5)  # two tech + three energy remains executable
        items[3]["sector"] = "Technology"
        items[4]["sector"] = "Technology"
        items[5]["sector"] = "Technology"
        result = DecisionEngine().evaluate_portfolio(datetime.now(timezone.utc), 10000, "BULL", items)
        self.assertEqual(len(result.top5), 2)
        self.assertEqual(result.data_quality, "DATA-INCOMPLETE / NO VALID RECOMMENDATION")

    def test_mock_partial_stale_and_unavailable_are_quarantined(self):
        engine = DecisionEngine()
        for state in ("MOCK", "PARTIAL", "STALE", "UNAVAILABLE"):
            self.assertFalse(engine._check_data_quality(candidate(1, price_status=state)), state)

    def test_live_route_is_frozen_decision_engine_route(self):
        system = object.__new__(QuantTradingSystemV2)
        system.data_loader = _Loader()
        system.factor_engine = FactorEngine()
        system.ranking_engine = RankingEngine()
        system.scoring_engine = ScoringEngine(DEFAULT_FACTOR_WEIGHTS)
        system.decision_engine = DecisionEngine()
        system.portfolio_state = type("State", (), {"cash": 100000.})()
        system.regime_engine = type("Regime", (), {"detect_regime": lambda *_: {"regime": "sideways"}})()
        # No optimizer / learner / meta-alpha is attached: a reference to any
        # adaptive live component would fail this test.
        result = system._run_frozen_live_cycle([f"T{i}" for i in range(5)], {})
        self.assertEqual(result["model_version"], "MODEL_RANK_E")
        self.assertEqual(result["strategy_version"], "FROZEN_v1")
        self.assertEqual(result["final_tradable_candidates_count"], 5)

    def test_exchange_calendar_covers_good_friday_and_weekend(self):
        good_friday_after_close = datetime(2024, 3, 29, 22, tzinfo=timezone.utc)
        saturday = datetime(2024, 3, 30, 12, tzinfo=timezone.utc)
        self.assertEqual(expected_latest_trading_session(good_friday_after_close).day, 28)
        self.assertEqual(expected_latest_trading_session(saturday).day, 28)

    def test_stale_universe_is_not_success(self):
        provider = WikipediaSP500BootstrapProvider(max_age_days=1)
        provider._fetch_from_wikipedia = lambda: {"status": "FAILED"}
        provider._load_cache = lambda: {"retrieved_at": "2020-01-01T00:00:00+00:00", "tickers": ["AAPL"]}
        self.assertEqual(provider.get_live_universe()["status"], "STALE")


if __name__ == "__main__":
    unittest.main()
