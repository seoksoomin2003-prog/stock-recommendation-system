"""The past-record table next to the score: numbers come from stored one-run reports, nothing is computed again."""
import json

import pytest

from terminal.qsf import track_record as tr

KR_DOC = {"tables": {"SWING|20": {"dates": 88, "first": "2019-04-01", "last": "2026-09-08", "ic": 0.028, "t": 1.9, "top_fifth_excess": 0.011, "bottom_fifth_excess": -0.005,
                                  "buy_excess": 0.028, "buy_trades": 113, "average_return": -0.006, "market_return": 0.012},
                     "LONG_TERM|252": {"dates": 77, "first": "2019-04-01", "last": "2025-09-24", "ic": 0.136, "t": 8.2, "top_fifth_excess": 0.031, "bottom_fifth_excess": -0.043,
                                       "buy_excess": 0.043, "buy_trades": 2312, "average_return": 0.079, "market_return": 0.215}},
          "primary": {"SWING": {"horizon": 20, "reading": "NO_EVIDENCE"}, "LONG_TERM": {"horizon": 252, "reading": "RANK_ONLY"}},
          "money": {"SWING": {"passed": False}, "LONG_TERM": {"passed": False}}}


def write(base, market, doc):
    p = base / tr.SOURCES[market]["file"]
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(doc), encoding="utf-8")


def test_the_korean_rows_carry_the_reports_numbers_and_words(tmp_path):
    write(tmp_path, "KR", KR_DOC)
    got = tr.summary(tmp_path, "KR")
    swing, long_ = got["rows"]
    assert got["status"] == "REAL" and got["source"].endswith("QSF_KR_LIVE_REPLAY_RESULTS.md") and len(got["caveats"]) == 4
    assert swing["horizon"] == 20 and swing["reading_label"] == "근거 부족" and swing["pair_win"] == pytest.approx(0.5 + 0.028 / 3.14159265, abs=1e-6)
    assert long_["horizon"] == 252 and long_["reading_label"] == "순위만 설명" and long_["beats_market"] is False and long_["bottom_fifth_excess"] == -0.043
    assert long_["universe_return"] == 0.079 and long_["market_return"] == 0.215


def test_the_us_rows_never_claim_more_than_the_report_and_a_missing_file_is_unavailable(tmp_path):
    assert tr.summary(tmp_path, "US") == {"status": "UNAVAILABLE", "market": "US"} and tr.summary(tmp_path, "JP")["status"] == "UNAVAILABLE"
    write(tmp_path, "US", {"tables": {"SWING|A|20": {"dates": 152, "ic": 0.0044, "t": 0.27, "buy_excess": -0.0002}, "LONG_TERM|A|252": {"dates": 142, "ic": 0.031, "t": 2.5, "buy_excess": 0.011}}})
    swing, long_ = tr.summary(tmp_path, "US")["rows"]
    assert swing["reading"] == "NO_EVIDENCE" and swing["top_fifth_excess"] is None and swing["beats_market"] is None and swing["horizon"] == 20
    assert long_["reading"] is None and long_["reading_label"] == "근거 부족"          # a t-value alone is never promoted to evidence here
    assert tr.pair_win(None) is None and tr.pair_win(0.0) == 0.5
