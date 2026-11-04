"""Deterministic offline fakes for the KR engine (no network).  All values are synthetic MOCK data."""
import hashlib
from datetime import datetime, timezone

import numpy as np
import pandas as pd

NOW = datetime(2026, 10, 30, 10, 0, tzinfo=timezone.utc)      # 19:00 KST Friday -> 2026-10-30 bar complete

HEADER = ["회사명", "시장구분", "종목코드", "업종", "주요제품", "상장일", "결산월", "대표자명", "홈페이지", "지역"]
INDUSTRIES = ["반도체 제조업", "자동차용 엔진 및 자동차 제조업", "기초 화학물질 제조업", "소프트웨어 개발 및 공급업",
              "의약품 제조업", "은행 및 저축기관", "기타 금융업", "통신 및 방송 장비 제조업"]


def kind_rows(market: str, n: int, start: int):
    label = "유가" if market == "KOSPI" else "코스닥"
    return [[f"가짜회사{start + i}", label, f"{start + i:06d}", INDUSTRIES[i % len(INDUSTRIES)], "제품",
             "2010-01-04", "12월", "대표", "", "서울특별시"] for i in range(n)]


def kind_html(rows) -> bytes:
    th = "".join(f"<th>{h}</th>" for h in HEADER)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f"<html><head><meta charset='euc-kr'></head><body><table><tr>{th}</tr>{body}</table></body></html>" \
        .encode("euc-kr")


def fake_kind(n_kospi=180, n_kosdaq=160, extra=None):
    extra = extra or {}
    data = {"KOSPI": kind_rows("KOSPI", n_kospi, 100000) + extra.get("KOSPI", []),
            "KOSDAQ": kind_rows("KOSDAQ", n_kosdaq, 200000) + extra.get("KOSDAQ", [])}
    return lambda market: kind_html(data[market])


def _seed(sym: str) -> int:
    return int(hashlib.sha256(sym.encode()).hexdigest()[:8], 16)


def sessions(start, end):
    return pd.bdate_range(start, pd.Timestamp(end) - pd.Timedelta(days=1))   # yfinance end is exclusive


def series(sym: str, idx: pd.DatetimeIndex):
    rng = np.random.default_rng(_seed(sym))
    base_days = pd.bdate_range("2024-01-01", "2027-12-31")
    r = rng.normal(0.0004, 0.02, len(base_days))
    close = pd.Series(10000 * np.exp(np.cumsum(r)), index=base_days).reindex(idx)
    open_ = close * (1 + pd.Series(rng.normal(0, 0.003, len(base_days)), index=base_days).reindex(idx))
    hi = np.maximum(open_, close) * 1.01
    lo = np.minimum(open_, close) * 0.99
    vol = pd.Series(rng.integers(50_000, 5_000_000, len(base_days)), index=base_days).reindex(idx).astype(float)
    if sym.startswith("^"):
        vol[:] = 0.0
    return pd.DataFrame({"Open": open_, "High": hi, "Low": lo, "Close": close, "Adj Close": close, "Volume": vol})


class FakeDownload:
    """yfinance.download stand-in: MultiIndex (field, symbol) columns; optional per-symbol mutations."""

    def __init__(self, drop=(), mutate=None):
        self.drop, self.mutate, self.calls = set(drop), mutate or {}, []

    def __call__(self, symbols, start, end):
        self.calls.append((tuple(symbols), start, end))
        idx = sessions(start, end)
        parts = {}
        for s in symbols:
            if s in self.drop:
                continue
            df = series(s, idx)
            if s in self.mutate:
                df = self.mutate[s](df)
            parts[s] = df
        if not parts:
            return pd.DataFrame()
        out = pd.concat(parts, axis=1).swaplevel(0, 1, axis=1).sort_index(axis=1)
        return out


def provider_factory(download):
    from markets.kr.market_data import YahooKRProvider
    return lambda: YahooKRProvider(download=download, sleep=lambda s: None)
