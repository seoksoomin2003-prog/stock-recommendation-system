import unittest
import pandas as pd
import numpy as np
from datetime import datetime, timezone
from core.alternative_data_engine import AlternativeDataEngine
from core.news_engine import NewsEngine

class TestP614DataSemantics(unittest.TestCase):
    def test_missing_data_maps_to_unavailable(self):
        engine = AlternativeDataEngine()
        engine.fetch_google_trends = lambda t: pd.Series(dtype=float)
        score = engine.calculate_alternative_score("FAKE_TICKER")
        self.assertTrue(np.isnan(score))

    def test_provider_failure_maps_to_unavailable(self):
        engine = NewsEngine()
        engine.fetch_news = lambda t: []
        score = engine.get_company_sentiment([], "FAKE_TICKER")
        self.assertTrue(np.isnan(score))

    def test_pytrends_absence_does_not_crash_core(self):
        engine = AlternativeDataEngine()
        matrix = engine.get_alt_data_matrix(["AAPL"], {"AAPL": []})
        self.assertEqual(len(matrix), 1)
        self.assertTrue(np.isnan(matrix["AAPL"]))

    def test_newsapi_absence_does_not_crash_core(self):
        engine = NewsEngine()
        res = engine.get_company_sentiment([], "AAPL")
        self.assertTrue(np.isnan(res))

    def test_optional_alternative_data_does_not_create_new_hard_gate(self):
        from core.meta_alpha_engine import MetaAlphaEngine
        engine = MetaAlphaEngine()
        factor_scores = pd.Series({"AAPL": 0.8, "MSFT": 0.6})
        fundamental_scores = pd.Series({"AAPL": 0.7, "MSFT": 0.5})
        alt_data_scores = pd.Series({"AAPL": 0.5, "MSFT": np.nan})
        sentiment_scores = pd.Series({"AAPL": 0.2, "MSFT": np.nan})
        final_scores = engine.combine_scores(factor_scores, fundamental_scores, sentiment_scores, alt_data_scores)
        self.assertIn("MSFT", final_scores)
        self.assertFalse(np.isnan(final_scores["MSFT"]))
        self.assertTrue(final_scores["MSFT"] > 0)

if __name__ == '__main__':
    unittest.main()
