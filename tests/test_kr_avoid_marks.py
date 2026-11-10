"""The Korean avoid marks read against the live score: the marks of a day, the two readings and the refusals.  All offline."""
import json
from datetime import datetime, timezone

import pytest

from tests import test_live_forward as base_fixture
from terminal.qsf import kr_avoid_marks as am, kr_events_forward as kef, kr_forward as kf, live_forward as lf

NOW = datetime(2026, 11, 11, tzinfo=timezone.utc)
CAL, N = base_fixture.CAL, base_fixture.N


def write_marks(base, days, risky=range(0, 8), financing=(8, 9), missing=()):
    """Stocks T00..T07 are high risk, T08 and T09 have a financing filing; the fund record marks nobody new."""
    for d in days:
        price = [{"code": f"T{k:02d}", "low_risk": -1.0 if k in risky else 10.0 + k} for k in range(N)]
        fund = [{"code": f"T{k:02d}", "score": 50.0} for k in range(N)]
        events = [{"code": f"T{k:02d}", "financing": int(k in financing), "buyback": 0} for k in range(N)]
        for folder, rows in ((kf.FOLDER, price), (kf.FUND_FOLDER, fund), (kef.FOLDER, events)):
            if (folder, d) not in missing:
                kf.write_record(base, d, NOW, False, store=folder, scorer=lambda b, day, rows=rows: {"session": day, "rows": rows})


class KrLedger(base_fixture.FakeLedger):
    def _live_rows(self):
        return [{"market": "KR", "session": d} for d in CAL[:self.days]]

    def _load(self, r):
        i = CAL.index(r["session"])
        return [{**base_fixture.snap(k, r["session"], CAL[i + 1]), "market": "KR"} for k in range(N)]


@pytest.fixture
def led(monkeypatch):
    monkeypatch.setattr(lf, "Ledger", KrLedger)
    monkeypatch.setattr(am, "Ledger", KrLedger)
    monkeypatch.setattr(KrLedger, "days", 300)
    monkeypatch.setattr(KrLedger, "broken", False)


def test_the_marks_of_a_day_come_from_the_three_records_only(tmp_path):
    write_marks(tmp_path, [CAL[0]])
    m = am.marks_of(tmp_path, CAL[0])
    assert m["high_risk"] == {f"T{k:02d}" for k in range(0, 8)} and m["financing"] == {"T08", "T09"} and len(m["known"]) == N and len(m["any"]) >= 10
    assert am.marks_of(tmp_path, CAL[1]) is None                                           # no record of that day: the day is not used


def test_marked_stocks_that_lag_inside_the_watch_list_support_the_rule(tmp_path, led):
    # stock k earns more with k, so the low-numbered (marked) stocks lag; scores are 35 + k, so nobody marked reaches 55: add a second marked group there
    write_marks(tmp_path, CAL[:240], risky=range(0, 8), financing=(21, 22, 23, 24))
    res = am.evaluate_once(tmp_path, base_fixture.loader(), base_fixture.flat_bench(), log=lambda *_: None)
    assert res["sessions_used"] == 240 and res["days"] == 240 and res["reading_1"]["passed"] and res["reading_1"]["mean"] < 0
    assert res["reading_2"]["passed"] and res["reading_2"]["days"] == 240 and res["verdict"] == "AVOID_RULE_SUPPORTED"
    assert res["by_mark"]["high_risk"]["mean"] < 0 and res["by_mark"]["weak_fund"]["status"] == "UNAVAILABLE" and res["buy_band_filter"]["days_with_a_removal"] == 0 and res["unknown_share"] == 0
    with pytest.raises(RuntimeError, match="한 번만"):
        am.evaluate_once(tmp_path, base_fixture.loader(), base_fixture.flat_bench())


def test_marks_only_below_the_watch_list_say_the_score_already_knows(tmp_path, led):
    write_marks(tmp_path, CAL[:240])                                                         # every marked stock scores under 55
    res = am.evaluate_once(tmp_path, base_fixture.loader(), base_fixture.flat_bench(), log=lambda *_: None)
    assert res["verdict"] == "MARKS_FLAG_LOSERS_BUT_SCORE_KNOWS" and res["reading_2"]["status"] == "UNAVAILABLE" and not res["reading_2"]["passed"]


def test_marks_that_flag_winners_are_no_evidence_and_missing_records_are_refused(tmp_path, led):
    write_marks(tmp_path / "a", CAL[:240], risky=(28, 29, 30, 31, 36, 37, 38, 39), financing=())      # the marked stocks are the ones that earn most
    res = am.evaluate_once(tmp_path / "a", base_fixture.loader(), base_fixture.flat_bench(), log=lambda *_: None)
    assert res["verdict"] == "NO_EVIDENCE" and res["reading_1"]["mean"] > 0 and res["buy_band_filter"]["days_with_a_removal"] == 240 and res["buy_band_filter"]["mean_gain"] < 0
    write_marks(tmp_path / "b", CAL[:100])
    with pytest.raises(RuntimeError, match="모두 있는 날이 100일"):
        am.evaluate_once(tmp_path / "b", base_fixture.loader(), base_fixture.flat_bench())
    with pytest.raises(RuntimeError, match="만기 거래일 239개"):
        am.evaluate_once(tmp_path / "c", base_fixture.loader(), base_fixture.flat_bench(259))
    assert not (tmp_path / "b" / am.REPORT).exists()
