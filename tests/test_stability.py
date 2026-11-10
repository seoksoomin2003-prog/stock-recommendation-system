"""Day-to-day movement of the live score, from the ledger only."""
import pytest

from terminal.qsf import stability as st


def day(session, version, scores):
    return {"session": session, "versions": {version}, "scores": scores}


def test_two_sessions_are_compared_stock_by_stock():
    a = {f"T{k}": 40.0 + k for k in range(40)}                       # 40 .. 79, ten at 70+
    b = {**{f"T{k}": 40.0 + k for k in range(40)}, "T39": 60.0, "T29": 71.0, "NEW": 90.0}
    got = st.compare(a, b)
    assert got["stocks"] == 40 and got["buy_before"] == 10 and got["buy_after"] == 10 and got["buy_turnover"] == pytest.approx(2 / 11)
    assert got["mean_abs_change"] == pytest.approx((19 + 2) / 40) and got["moved_5_points_share"] == pytest.approx(1 / 40) and got["band_changed_share"] == pytest.approx(2 / 40)
    assert 0.9 < got["rank_correlation"] < 1 and st.compare(a, {"T1": 50.0}) is None


def test_a_version_change_is_never_counted_as_instability():
    s = {f"T{k}": 40.0 + k for k in range(40)}
    moved = {t: 100 - v for t, v in s.items()}
    days = [day("2026-11-06", "QSF-1.1.3", s), day("2026-11-09", "QSF-1.1.8", moved), day("2026-11-10", "QSF-1.1.8", moved), day("2026-11-11", "QSF-1.1.8", s)]
    got = st.measure(days)
    assert got["pairs"] == 2 and got["sessions"] == 4 and got["last"]["from"] == "2026-11-10" and got["last"]["version"] == "QSF-1.1.8"
    assert got["rank_correlation"] == pytest.approx(0.0) and st.measure(days[:2]) == {"pairs": 0, "sessions": 2, "rank_correlation": None, "mean_abs_change": None,
                                                                             "moved_5_points_share": None, "band_changed_share": None, "buy_turnover": None, "last": None}


def test_bands_follow_the_configured_floors():
    assert st.band_of(85) == "STRONG_BUY_CANDIDATE" and st.band_of(70) == "BUY_CANDIDATE" and st.band_of(54.9) == "WEAK_REDUCE" and st.band_of(0) == "SELL_AVOID"
