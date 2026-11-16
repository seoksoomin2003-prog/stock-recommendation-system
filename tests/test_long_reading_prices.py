"""A verdict that reads further back than the scan keeps gets the archive's longer series (found by the drill of 2026-11-16)."""
from pathlib import Path

from terminal.qsf import price_archive as pa

ROOT = Path(__file__).resolve().parents[1]


def bars(first, n, close=100.0):
    return [{"date": f"{first[:8]}{int(first[8:]) + k:02d}", "open": close, "close": close, "adj_close": close} for k in range(n)]


def test_the_longest_loader_gives_the_archive_when_it_is_as_fresh_and_starts_earlier(monkeypatch):
    long_kept, short_own = bars("2026-10-01", 20, 1.0), bars("2026-10-11", 10, 2.0)
    arch = {"A": {"bars": long_kept}, "B": {"bars": bars("2026-10-01", 15, 1.0)}, "C": {"bars": long_kept}, "E": {"bars": []}}
    monkeypatch.setattr(pa, "read", lambda base, market: arch)
    own = {"A": short_own, "B": short_own, "C": bars("2026-10-01", 20, 2.0), "D": short_own, "E": short_own}
    plain, longest = pa.loader("x", "KR", lambda t: own.get(t)), pa.loader("x", "KR", lambda t: own.get(t), longest=True)
    assert plain("A") == short_own and longest("A") == long_kept           # as fresh, starts earlier: the archive
    assert longest("B") == short_own                                        # the archive stopped earlier: the scan's
    assert longest("C") == own["C"] and longest("D") == short_own and longest("E") == short_own       # no longer history to gain
    assert plain("Z") == [] and longest("Z") == []
    assert pa.loader("x", "KR", lambda t: [], longest=True)("A") == long_kept      # a stock that left the scan: the archive, as before


def test_the_verdict_handlers_ask_for_the_longer_series_and_five_years_of_the_index():
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    assert 'q._history(["^KS11"], "5y")' in app and app.count("q._loader(market, longest=True), bench_of(market)") == 1 and 'q._loader("KR", longest=True), bench_of("KR")' in app
    views = (ROOT / "terminal" / "qsf" / "views.py").read_text(encoding="utf-8")
    assert "price_archive.loader(self.base, market, self._scan_loader(market), longest=longest)" in views
