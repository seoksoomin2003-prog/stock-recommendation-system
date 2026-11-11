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
    assert swing["universe"] == tr.LIVE_KR and swing["superseded"] is True and swing["reading_label"].startswith("시험했으나 기준 미달") and swing["pair_win"] == pytest.approx(0.5 + 0.008 / 3.14159265, abs=1e-6)
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
    assert long_["reading"] is None and long_["reading_label"].startswith("시험했으나 기준 미달")          # a t-value alone is never promoted to evidence here
    assert tr.pair_win(None) is None and tr.pair_win(0.0) == 0.5


US_DOC = {"tables": {"SWING|A|20": {"dates": 152, "lag": 1, "mean_n": 463.2, "ic": 0.0044, "t": 0.27, "spread_net": -0.0025, "buy_excess": -0.0002, "buy_dates": 152,
                                    "early": {"ic": 0.020, "spread_net": 0.0041}, "late": {"ic": -0.011, "spread_net": -0.0091}},
                     "SWING|TECHNICAL|20": {"ic": 0.0023, "t": 0.15, "early": {"ic": 0.014}, "late": {"ic": -0.009}},
                     "SWING|mom_12_1|20": {"ic": 0.0097, "t": 0.6},
                     "LONG_TERM|A|252": {"dates": 142, "lag": 12, "mean_n": 449.1, "ic": 0.031, "t": 1.83, "spread_net": 0.0042, "buy_excess": 0.011, "buy_dates": 142,
                                         "early": {"ic": 0.043, "spread_net": 0.033}, "late": {"ic": 0.020, "spread_net": -0.025}}},
          "buckets": {"SWING|A|20": {"0-40": {"n": 10269, "mean_vs_average": 0.0013, "mean_vs_bench_net": -0.0017, "beat_average_rate": 0.498}, "80-100": {"n": 0}}}}


def test_a_failed_row_says_which_of_the_five_conditions_it_missed_and_by_how_much(tmp_path):
    write(tmp_path, "US", US_DOC)
    got = tr.summary(tmp_path, "US")
    swing, long_ = got["rows"]
    assert swing["reading_label"] == "시험했으나 기준 미달 (조건 0/5 충족)" and [c["passed"] for c in swing["checks"]] == [False] * 5
    assert long_["reading_label"] == "시험했으나 기준 미달 (조건 3/5 충족)" and {c["key"] for c in long_["checks"] if not c["passed"]} == {"t", "spread_both_halves"}
    assert swing["checks"][1]["need"] == "2.24 이상" and swing["checks"][1]["value"] == "0.27" and swing["checks"][3]["value"] == "+0.41% / -0.91%"
    assert "자료가 모자라서가 아니라" in swing["why"][0] and "0과 구별되지 않았습니다" in swing["why"][1] and any("한쪽에서만" in w for w in swing["why"])
    assert "독립인 구간은 약 12개" in long_["why"][0] and "우연과 구별하기 어렵습니다" in long_["why"][0] and "조금 나았지만" in long_["why"][1]
    lo, hi = swing["pair_win_range"]
    assert lo < 0.5 < hi and swing["pair_win"] == pytest.approx((lo + hi) / 2) and tr.pair_win_range(0.0, 1.0) is None and tr.pair_win_range(0.01, None) is None
    assert [d["name"] for d in swing["domains"]] == ["차트"] and swing["domains"][0]["late_ic"] == -0.009 and long_["domains"] == []      # the momentum line is not a score domain
    assert swing["bands"] == [{"band": "0-40", "n": 10269, "vs_average": 0.0013, "vs_index_net": -0.0017, "beat_average_rate": 0.498}] and long_["bands"] == []
    assert swing["spread_net"] == -0.0025 and swing["not_stored_note"]


def test_stored_condition_marks_are_shown_as_stored_and_a_full_pass_is_worded_as_one(tmp_path):
    doc = json.loads(json.dumps(REPLAY_DOC))
    doc["tables"]["LONG_TERM|252"].update({"lag": 12, "mean_n": 254.6, "early": {"ic": 0.12, "spread_net": 0.046}, "late": {"ic": 0.15, "spread_net": 0.092}, "buy_excess": 0.043})
    doc["primary"]["LONG_TERM"]["condition_a"] = {"verdict": "WEAK_POSITIVE_EVIDENCE", "checks": {"ic": True, "t": True, "ic_both_halves": True, "spread_both_halves": True, "buy_band": True}}
    doc["domains"] = {"LONG_TERM|FUNDAMENTAL|252": {"ic": 0.162, "t": 20.7}}
    p = tmp_path / "reports/qsf/QSF_KR_LIVE_REPLAY.json"
    p.parent.mkdir(parents=True)
    p.write_text(json.dumps(doc), encoding="utf-8")
    (row,) = tr.summary(tmp_path, "KR")["rows"]
    assert row["reading_label"] == "순위만 설명" and row["checks_passed"] == 5 and [d["name"] for d in row["domains"]] == ["재무"]
    assert "어렵습니다" not in row["why"][0] and "모두 충족" in row["why"][1] and "시장을 이기지는 못했습니다" in row["why"][1]
    stored = json.loads(json.dumps(doc))
    stored["primary"]["LONG_TERM"]["condition_a"]["checks"]["buy_band"] = False          # the report's own mark wins over a recomputation
    p.write_text(json.dumps(stored), encoding="utf-8")
    assert tr.summary(tmp_path, "KR")["rows"][0]["checks"][4]["passed"] is False


def test_the_forward_count_reads_the_ledger_index_only(tmp_path):
    write(tmp_path, "US", US_DOC)
    f = tr.summary(tmp_path, "US")["forward"]
    assert f["first"] == "2026-11-09" and f["strategies"]["SWING"] == {"horizon": 20, "recorded": 0, "needed": 240, "expected": "2027년 12월쯤"}
    assert f["strategies"]["LONG_TERM"]["needed"] == 756 and f["strategies"]["LONG_TERM"]["horizon"] == 63
