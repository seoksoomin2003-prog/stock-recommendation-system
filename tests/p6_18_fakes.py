"""Deterministic offline fakes for the P6-18 canonical pipeline tests (no network, no production files)."""
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from core.decision_engine import DecisionEngine
from core.factor_engine import FactorEngine
from core.ranking_engine import RankingEngine
from core.regime_engine import RegimeEngine
from core.scoring_engine import ScoringEngine
from utils.config import DEFAULT_FACTOR_WEIGHTS

FIXED_NOW = datetime(2026, 1, 15, 22, tzinfo=timezone.utc)


def make_market(tickers, seed=7, periods=430, end="2026-01-15"):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(end=end, periods=periods)
    n = len(tickers)
    rets = rng.normal(rng.normal(0.0005, 0.0005, n), rng.uniform(0.01, 0.02, n), size=(periods, n))
    prices = pd.DataFrame(100 * np.exp(np.cumsum(rets, axis=0)), index=dates, columns=tickers)
    volumes = pd.DataFrame(1_000_000.0, index=dates, columns=tickers)
    return prices, volumes


def make_financials(tickers, seed=11):
    rng = np.random.default_rng(seed)
    n = len(tickers)
    return pd.DataFrame({"per": rng.uniform(8, 40, n), "pbr": rng.uniform(1, 10, n),
                         "roe": rng.normal(0.18, 0.06, n), "profitMargin": rng.normal(0.15, 0.05, n)},
                        index=list(tickers))


class FakeLoader:
    """Implements the DataLoader contract used by CanonicalPipeline."""

    def __init__(self, prices, volumes, financials, price_status=None, volume_status=None,
                 fin_status=None, meta=None, raise_on=None):
        self.prices, self.volumes, self.financials = prices, volumes, financials
        self.price_status = price_status or {}
        self.volume_status = volume_status or {}
        self.fin_status = fin_status or {}
        self.meta = meta or {}
        self.raise_on = raise_on
        self.calls = {"price": 0, "volume": 0, "financial": 0}
        self.financial_requested = []
        self.request_counts = {"fake": 1}
        self.provider_events = []

    def _frame(self, src, tickers, overrides):
        if self.raise_on == "market":
            raise RuntimeError("simulated provider crash")
        frame = src.reindex(columns=tickers)
        status = {t: ("UNAVAILABLE" if frame[t].dropna().empty else "REAL") for t in tickers}
        status.update({t: s for t, s in overrides.items() if t in tickers})
        frame.attrs.update(provider="fake", provider_status=status, retrieved_at="2026-01-15T22:00:00+00:00",
                           last_bar={t: str(frame[t].dropna().index[-1].date()) for t in tickers if not frame[t].dropna().empty})
        return frame

    def get_price_data(self, tickers, start, end):
        self.calls["price"] += 1
        return self._frame(self.prices, tickers, self.price_status)

    def get_volume_data(self, tickers, start, end):
        self.calls["volume"] += 1
        return self._frame(self.volumes, tickers, self.volume_status)

    def get_financial_data(self, tickers, ciks=None):
        self.calls["financial"] += 1
        self.financial_requested = list(tickers)
        if self.raise_on == "financial":
            raise RuntimeError("simulated fundamentals crash")
        frame = self.financials.reindex(list(tickers))
        status = {t: ("REAL" if frame.loc[t].notna().all() else "PARTIAL" if frame.loc[t].notna().any() else "UNAVAILABLE")
                  for t in frame.index}
        status.update({t: s for t, s in self.fin_status.items() if t in frame.index})
        frame.attrs.update(
            provider_status=status,
            field_provenance={t: {f: {"source": "fake", "status": "REAL"} for f in frame.columns} for t in frame.index},
            security_meta={t: {"sector": "Energy", "quote_type": "EQUITY", "name": f"{t} Corp", "yf_info_ok": True,
                               **self.meta.get(t, {})} for t in frame.index})
        return frame


class FakeSystem:
    def __init__(self, loader, capital=10_000_000.0):
        self.data_loader = loader
        self.factor_engine = FactorEngine()
        self.ranking_engine = RankingEngine()
        self.scoring_engine = ScoringEngine(DEFAULT_FACTOR_WEIGHTS)
        self.decision_engine = DecisionEngine()
        self.regime_engine = RegimeEngine()
        self.portfolio_state = type("State", (), {"cash": capital})()


class FakeTickerMap:
    def __init__(self, mapping):
        self.mapping = mapping
        self.provenance = {"status": "REAL"}

    def cik(self, t):
        return self.mapping.get(t)


class FakeUniverse:
    def __init__(self, tickers, status="SUCCESS", freshness="REAL", extra_ciks=None):
        self.tickers, self.status, self.freshness = list(tickers), status, freshness
        self.ticker_map = FakeTickerMap(extra_ciks or {})

    def get_live_universe(self):
        return {"status": self.status, "freshness_status": self.freshness, "source": "FAKE_SP500",
                "retrieved_at": "2026-01-15T21:00:00+00:00", "tickers": list(self.tickers),
                "ciks": {t: str(1000 + i) for i, t in enumerate(self.tickers)}, "constituent_count": len(self.tickers),
                "reason": None if self.status == "SUCCESS" else "fake failure"}


def pipeline_for(loader, checkpoint=None, capital=10_000_000.0):
    from pipeline.canonical import CanonicalPipeline
    s = FakeSystem(loader, capital)
    return CanonicalPipeline(s.data_loader, s.factor_engine, s.ranking_engine, s.scoring_engine,
                             s.decision_engine, s.regime_engine, capital=capital, checkpoint=checkpoint,
                             now=lambda: FIXED_NOW)
