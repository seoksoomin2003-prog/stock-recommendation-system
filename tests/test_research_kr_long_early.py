"""The confirmation run of the Korean long score on 2016-2019: which days count per horizon, the words, and the single run.  All offline."""
import gzip
import json

import pytest

from terminal.qsf import research_kr_live as rl, research_kr_long_early as le
from tests.test_research_kr_tech import DATES


class Px:
    def __init__(self, dates):
        self.dates = dates


def test_days_start_in_2016_and_each_horizon_keeps_only_returns_that_ended_before_the_replay(monkeypatch):
    px = Px(DATES)                                           # mid 2011 to mid 2019
    monkeypatch.setattr(rl, "eval_rows", lambda p, first: list(range(next(i for i, d in enumerate(p.dates) if d >= first), len(p.dates), 21)))
    rows = le.eval_days(px)
    assert px.dates[rows[0]] >= le.FIRST and px.dates[rows[-1]] < le.BEFORE and 30 <= len(rows) <= 40
    by_i = {i: [] for i in rows}
    long_, mid, short = le.ended(px, by_i, 252), le.ended(px, by_i, 63), le.ended(px, by_i, 21)
    assert len(long_) < len(mid) < len(short) <= len(rows) and all(px.dates[i + 252] <= le.LAST_EXIT for i in long_)


def test_the_words_are_the_protocols():
    assert le.word(True, True) == "CONFIRMED_RANK_AND_MONEY" and le.word(True, False) == "CONFIRMED_RANK_ONLY" and le.word(False, True) == "NOT_CONFIRMED"


def test_the_run_needs_prepared_scores_and_is_written_once(tmp_path, monkeypatch):
    (tmp_path / rl.DATA).mkdir(parents=True)
    with pytest.raises(RuntimeError, match="prepare"):
        le.run_once(tmp_path)
    with gzip.open(tmp_path / rl.DATA / le.SCORES, "wt", encoding="utf-8") as fh:
        json.dump({"rows": [1, 2], "first": "2016-04-01", "last": "2019-03-06", "records": []}, fh)
    monkeypatch.setattr(rl, "load_panel", lambda base: object())
    monkeypatch.setattr(le, "evaluate", lambda px, recs: {"primary": {"reading": "CONFIRMED_RANK_ONLY"}})
    res = le.run_once(tmp_path, log=lambda *_: None)
    assert res["days"] == 2 and json.loads((tmp_path / le.REPORT).read_text(encoding="utf-8"))["primary"]["reading"] == "CONFIRMED_RANK_ONLY"
    with pytest.raises(RuntimeError, match="한 번만"):
        le.run_once(tmp_path)
