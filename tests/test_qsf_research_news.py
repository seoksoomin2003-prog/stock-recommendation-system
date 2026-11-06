"""Historical news research: dates cannot leak, roundups and repeats are removed, unknown stays unknown, the test runs once.  No network."""
import math

import pytest

from terminal.qsf import research_news as rn


def test_tone_counts_exact_words_only():
    assert rn.tone("Apple beats estimates, shares surge") == 1
    assert rn.tone("Boeing shares plunge after lawsuit") == -1
    assert rn.tone("Strong sales but a big loss") == 0
    assert rn.tone("Buyers return to the sellers market") == 0


def rows(*items):
    return [(f"{d} 00:00:00 UTC", title, t) for d, title, t in items]


def test_a_title_on_four_tickers_in_one_day_is_a_roundup():
    data = rows(*[("2012-01-03", "71 Biggest Movers", t) for t in "ABCD"], ("2012-01-03", "Apple beats", "A"))
    res = rn.extract(data, set("ABCD"))
    assert res["articles"] == {"A": [["2012-01-03", 1]]} and res["roundup_removed"] == 4


def test_the_same_title_on_three_tickers_is_kept():
    res = rn.extract(rows(*[("2012-01-03", "Peers rally", t) for t in "ABC"]), set("ABC"))
    assert sorted(res["articles"]) == ["A", "B", "C"]


def test_repeats_count_once_and_other_days_stay():
    res = rn.extract(rows(("2012-01-03", "X falls", "A"), ("2012-01-03", "x falls ", "A"), ("2012-01-04", "X falls", "A")), {"A"})
    assert res["articles"]["A"] == [["2012-01-03", -1], ["2012-01-04", -1]]


def test_outside_the_window_or_sample_is_dropped():
    res = rn.extract(rows(("2009-12-31", "old", "A"), ("2020-06-01", "late", "A"), ("2012-01-03", "other", "Z"), ("2012-01-03", "", "A")), {"A"})
    assert res["articles"] == {}


ARTICLES = [["2012-01-01", -1], ["2012-03-01", 1], ["2012-03-20", 0], ["2012-03-28", 1], ["2012-04-01", -1]]


def test_future_articles_are_never_read():
    f = rn.factors_at(ARTICLES, "2012-03-29")
    assert f["news_tone_7"] == pytest.approx(1.0) and f["news_count_91"] == pytest.approx(math.log1p(3 + 1))     # 01-01 is in the 91 days


def test_the_window_includes_the_evaluation_day():
    assert rn.factors_at(ARTICLES, "2012-04-01")["news_tone_7"] == pytest.approx(0.0)


def test_before_the_first_article_nothing_is_known():
    assert all(math.isnan(v) for v in rn.factors_at(ARTICLES, "2011-12-31").values())


def test_a_quiet_window_has_no_tone_but_a_true_zero_count():
    f = rn.factors_at([["2012-01-01", 1]], "2012-12-01")
    assert math.isnan(f["news_tone_7"]) and math.isnan(f["news_neg_share_30"])
    assert f["news_count_91"] == 0 and f["news_abnormal_7"] == 0


def test_abnormal_compares_the_week_with_the_prior_weeks():
    many = [[f"2012-03-{d:02d}", 0] for d in range(25, 32)]
    assert rn.factors_at(many, "2012-03-31")["news_abnormal_7"] == pytest.approx(math.log1p(7))


class Px:
    dates = [f"{y}-{m:02d}-15" for y in range(2010, 2021) for m in range(1, 13)]


def test_windows_do_not_overlap():
    rows_ = list(range(len(Px.dates) - 1))
    dev, test = rn.dev_rows(Px, rows_, 3), rn.test_rows(Px, rows_, 3)
    assert all(Px.dates[rows_[n] + 3] < rn.DEV_END and Px.dates[rows_[n]] >= rn.VALUES_FROM for n in dev)
    assert all(rn.TEST_FIRST <= Px.dates[rows_[n]] <= rn.SOURCE_END for n in test)
    assert dev and test and max(rows_[n] + 3 for n in dev) < min(rows_[n] for n in test)


def test_the_test_runs_once(tmp_path):
    (tmp_path / rn.TEST_REPORT).parent.mkdir(parents=True)
    (tmp_path / rn.TEST_REPORT).write_text("{}", encoding="utf-8")
    with pytest.raises(RuntimeError):
        rn.test_once(tmp_path)


def test_the_word_lists_do_not_overlap_and_directions_are_fixed():
    assert not rn.POSITIVE & rn.NEGATIVE
    assert [rn.GOOD_HIGH[f] for f in rn.FACTORS] == [True, True, False, False, False]
