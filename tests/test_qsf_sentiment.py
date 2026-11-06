"""Sentiment and risk test: no future reading, unknown stays empty, a second run is refused.  No network."""
import numpy as np
import pytest

from terminal.qsf import research_sentiment as se


def test_parse_reads_the_us_date_format_and_skips_bad_rows():
    v = se.parse_vix("DATE,OPEN,HIGH,LOW,CLOSE\n01/02/1990,17,17,17,17.24\nbad,1,1,1,x\n03/04/1990,1,1,1,\n")
    assert v == {"1990-01-02": 17.24}


def series(n=300, value=20.0):
    return {f"{2000 + i // 200}-{i % 200 + 1:03d}": value for i in range(n)}


def test_state_needs_a_year_of_history():
    v = series()
    keys = sorted(v)
    assert se.high_sentiment(v, [keys[100]]) == [None]
    assert se.high_sentiment(v, ["1999-01-01"]) == [None]


def test_state_compares_with_earlier_closes_only():
    v = series()
    keys = sorted(v)
    d = keys[280]
    assert se.high_sentiment({**v, d: 10.0}, [d]) == [True]
    assert se.high_sentiment({**v, d: 30.0}, [d]) == [False]
    later = dict(v)
    for k in keys[281:]:
        later[k] = 1000.0
    assert se.high_sentiment({**later, d: 10.0}, [d]) == [True]     # later closes change nothing


def test_score_turns_over_on_fearful_days_and_is_empty_when_unknown():
    low = np.array([[0.9, 0.1, np.nan]] * 3)
    s = se.conditional_score(low, [True, False, None])
    assert s[0, 0] == pytest.approx(0.9) and s[1, 0] == pytest.approx(0.1) and s[1, 1] == pytest.approx(0.9)
    assert np.isnan(s[2]).all() and np.isnan(s[0, 2]) and np.isnan(s[1, 2])


def test_the_second_run_is_refused(tmp_path):
    p = tmp_path / se.REPORT
    p.parent.mkdir(parents=True)
    p.write_text("{}")
    with pytest.raises(RuntimeError):
        se.run_once(tmp_path)
