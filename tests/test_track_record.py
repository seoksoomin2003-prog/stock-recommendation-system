"""The past-record table next to the score: numbers come from stored one-run reports, nothing is computed again."""
import json

import pytest

from terminal.qsf import track_record as tr

def table(ic, t, first="2019-04-01", last="2025-09-24", **more):
    return {"dates": 77, "first": first, "last": last, "ic": ic, "t": t, **more}


CAP_DOC = {"tables": {"SWING|20": table(0.008, 0.47, last="2026-09-08"), "LONG_TERM|252": table(0.052, 2.46, top_fifth_excess=-0.014, bottom_fifth_excess=0.022, average_return=0.157, market_return=0.215)},
           "primary": {"SWING": {"horizon": 20, "reading": "NO_EVIDENCE"}, "LONG_TERM": {"horizon": 252, "reading": "NO_EVIDENCE"}}, "money": {"SWING": {"passed": False}, "LONG_TERM": {"passed": False}}}
REPLAY_DOC = {"tables": {"SWING|20": table(0.028, 1.9), "LONG_TERM|252": table(0.136, 8.2, bottom_fifth_excess=-0.043, average_return=0.079, market_return=0.215)},
              "primary": {"SWING": {"horizon": 20, "reading": "NO_EVIDENCE"}, "LONG_TERM": {"horizon": 252, "reading": "RANK_ONLY"}}, "money": {"SWING": {"passed": False}, "LONG_TERM": {"passed": False}}}
EARLY_DOC = {"primary": {"strategy": "LONG_TERM", "horizon": 252, "dates": 23, "first": "2016-04-01", "last": "2018-02-20", "ic": 0.093, "t": 2.05, "bottom_fifth_excess": -0.071,
                         "average_return": -0.040, "market_return": 0.077, "reading": "NOT_CONFIRMED"}, "money": {"LONG_TERM": {"passed": False}}}
FILES = {"reports/qsf/QSF_KR_UNIVERSE_TEST.json": CAP_DOC, "reports/qsf/QSF_KR_LIVE_REPLAY.json": REPLAY_DOC, "reports/qsf/QSF_KR_LONG_EARLY.json": EARLY_DOC}


def write(base, market, doc):
    p = base / tr.SOURCES[market]["file"]
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(doc), encoding="utf-8")


def write_kr(base, names=tuple(FILES)):
    for name in names:
        p = base / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(FILES[name]), encoding="utf-8")


def test_the_korean_rows_lead_with_the_live_universe_and_mark_the_former_one(tmp_path):
    assert tr.summary(tmp_path, "KR") == {"status": "UNAVAILABLE", "market": "KR"}
    write_kr(tmp_path)
    got = tr.summary(tmp_path, "KR")
    swing, long_, former, early = got["rows"]
    assert got["status"] == "REAL" and got["source"].endswith("QSF_KR_UNIVERSE_TEST_RESULTS.md") and len(got["caveats"]) == 5
    assert swing["universe"] == tr.LIVE_KR and swing["superseded"] is True and swing["reading_label"] == "근거 부족" and swing["pair_win"] == pytest.approx(0.5 + 0.008 / 3.14159265, abs=1e-6)
    assert long_["universe"] == tr.LIVE_KR and "superseded" not in long_ and long_["reading"] == "NO_EVIDENCE" and long_["beats_market"] is False and long_["ic"] == 0.052
    assert former["universe"] == tr.FORMER_KR and former["former_universe"] is True and former["reading_label"] == "순위만 설명" and former["universe_return"] == 0.079
    assert early["second_window"] is True and early["former_universe"] is True and early["reading_label"].startswith("확인 안 됨") and early["first"] == "2016-04-01" and early["bottom_fifth_excess"] == -0.071
    assert got["more_sources"] == ["reports/QSF_KR_LIVE_REPLAY_RESULTS.md", "reports/QSF_KR_LONG_EARLY_RESULTS.md"]
    assert any("탐색 시험" in c for c in got["caveats"]) and any("이전 구성" in c for c in got["caveats"])


def test_a_missing_report_only_drops_its_own_rows(tmp_path):
    write_kr(tmp_path, ("reports/qsf/QSF_KR_UNIVERSE_TEST.json",))
    got = tr.summary(tmp_path, "KR")
    assert [r["universe"] for r in got["rows"]] == [tr.LIVE_KR, tr.LIVE_KR] and got["more_sources"] == []
    write_kr(tmp_path / "b", ("reports/qsf/QSF_KR_LIVE_REPLAY.json",))
    assert [r["universe"] for r in tr.summary(tmp_path / "b", "KR")["rows"]] == [tr.FORMER_KR]


def test_the_us_rows_never_claim_more_than_the_report_and_a_missing_file_is_unavailable(tmp_path):
    assert tr.summary(tmp_path, "US") == {"status": "UNAVAILABLE", "market": "US"} and tr.summary(tmp_path, "JP")["status"] == "UNAVAILABLE"
    write(tmp_path, "US", {"tables": {"SWING|A|20": {"dates": 152, "ic": 0.0044, "t": 0.27, "buy_excess": -0.0002}, "LONG_TERM|A|252": {"dates": 142, "ic": 0.031, "t": 2.5, "buy_excess": 0.011}}})
    swing, long_ = tr.summary(tmp_path, "US")["rows"]
    assert swing["reading"] == "NO_EVIDENCE" and swing["top_fifth_excess"] is None and swing["beats_market"] is None and swing["horizon"] == 20
    assert long_["reading"] is None and long_["reading_label"] == "근거 부족"          # a t-value alone is never promoted to evidence here
    assert tr.pair_win(None) is None and tr.pair_win(0.0) == 0.5
