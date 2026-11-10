"""US stocks without a next earnings date: the count from the ledger, the wording, the note, and the one telling by the daily job.  All offline."""
from datetime import datetime, timezone

import pytest

from terminal.automation import Daily, OK
from terminal.qsf import earnings_gap as eg

BEFORE = datetime(2026, 12, 14, 14, 0, tzinfo=timezone.utc)       # 2026-12-14 23:00 KST
DUE_DAY = datetime(2026, 12, 14, 23, 0, tzinfo=timezone.utc)      # 2026-12-15 08:00 KST
ITEM = "6. **미국 다음 실적 발표일 빈칸:** 503종목 중 265종목은 ..."


def snap(ticker, status="REAL", strategy="SWING", factor="earnings_calendar"):
    return {"market": "US", "ticker": ticker, "strategy": strategy, "factors": [{"factor": "momentum", "status": "REAL"}] + ([{"factor": factor, "status": status}] if status else [])}


class FakeLedger:
    rows = [{"market": "US", "session": "2026-12-11"}, {"market": "US", "session": "2026-12-14"}, {"market": "KR", "session": "2026-12-15"}]
    blank = 30

    def __init__(self, root):
        pass

    def _live_rows(self):
        return self.rows

    def _load(self, r):
        if r["session"] != "2026-12-14":
            return [snap(f"X{k}", "MISSING") for k in range(100)]
        dated = [snap(f"A{k}") for k in range(100 - self.blank - 2)] + [snap("STALE1", "STALE"), snap("STALE2", "STALE")]
        blank = [snap(f"B{k}", "MISSING") for k in range(self.blank - 1)] + [snap("NOFACTOR", None)]
        return dated + blank + [snap(f"A{k}", "MISSING", strategy="LONG_TERM") for k in range(100)]


@pytest.fixture
def led(monkeypatch):
    monkeypatch.setattr(eg, "Ledger", FakeLedger)
    monkeypatch.setattr(FakeLedger, "blank", 30)
    return FakeLedger


def daily(tmp_path, now, tg="SENT", mac="SENT"):
    sent, shown = [], []

    def telegram(text):
        sent.append(text)
        return {"status": tg}

    def macos(title, body):
        shown.append((title, body))
        return {"status": mac}
    return Daily(tmp_path, now=lambda: now, runner=lambda name, argv: 0, telegram=telegram, macos=macos, backup_dir=tmp_path / "bk"), sent, shown


def test_the_count_reads_the_newest_us_session_and_only_the_swing_rows(led, monkeypatch):
    assert eg.count("x") == {"session": "2026-12-14", "stocks": 100, "blank": 30, "share": 0.3}        # a stale date counts as a date, an absent factor as blank
    monkeypatch.setattr(FakeLedger, "rows", [{"market": "KR", "session": "2026-12-15"}])
    assert eg.count("x") is None


def test_the_message_gives_both_counts_and_says_nothing_was_changed():
    many = eg.text({"session": "2026-12-14", "stocks": 503, "blank": 236, "share": 0.4692})
    assert "503종목 중 236종목(47%)" in many and "503종목 중 265종목(53%)" in many and "아직 많이 비어" in many and "점수와 기록은 바꾸지 않았습니다" in many
    few = eg.text({"session": "2026-12-14", "stocks": 503, "blank": 20, "share": 0.0398})
    assert "503종목 중 20종목(4%)" in few and "대부분 채워졌습니다" in few and "아직 많이" not in few


def test_the_note_goes_under_its_item_once_and_nowhere_else(tmp_path):
    res = {"session": "2026-12-14", "stocks": 503, "blank": 236, "share": 0.4692}
    assert eg.write_note(tmp_path, res) is False                                                       # no decision list
    path = tmp_path / eg.NOTES
    path.parent.mkdir(parents=True)
    path.write_text("# 결정\n5. 다른 항목\n", encoding="utf-8")
    assert eg.write_note(tmp_path, res) is False and path.read_text(encoding="utf-8") == "# 결정\n5. 다른 항목\n"
    path.write_text(f"# 결정\n5. 다른 항목\n{ITEM}\n7. 다음 항목\n", encoding="utf-8")
    assert eg.write_note(tmp_path, res) is True
    lines = path.read_text(encoding="utf-8").split("\n")
    assert lines[2] == ITEM and "기준 거래일 2026-12-14" in lines[3] and "503종목 중 236종목(47%)" in lines[3] and lines[4] == "7. 다음 항목"
    assert eg.write_note(tmp_path, {**res, "blank": 1}) is True and path.read_text(encoding="utf-8").split("\n") == lines      # written once


def test_the_daily_job_counts_once_on_the_due_day_after_the_us_scores_are_in(tmp_path, led):
    early, sent, _ = daily(tmp_path, BEFORE)
    assert early._earnings_gap({}, {"QSF": {"status": OK}}) is None and not sent
    d, sent, shown = daily(tmp_path, DUE_DAY)
    st = {}
    assert d._earnings_gap(st, {"QSF": {"status": "FAILED"}}) is None and "earnings_gap" not in st and not sent     # waits for the scan
    got = d._earnings_gap(st, {"QSF": {"status": OK}})
    assert got["blank"] == 30 and got["stocks"] == 100 and got["delivered"] is True and got["noted"] is False and len(sent) == 1 and "100종목 중 30종목" in sent[0] and not shown
    assert d._earnings_gap(st, {"QSF": {"status": OK}}) is None and len(sent) == 1                                 # never twice


def test_an_undelivered_count_is_told_again_with_the_same_numbers(tmp_path, led, monkeypatch):
    d, sent, _ = daily(tmp_path, DUE_DAY, tg="FAILED")
    st = {}
    assert d._earnings_gap(st, {"QSF": {"status": OK}})["delivered"] is False and len(sent) == 1
    monkeypatch.setattr(FakeLedger, "blank", 60)                    # the ledger moved on: the count taken on the due day stays
    later, sent2, _ = daily(tmp_path, DUE_DAY)
    got = later._earnings_gap(st, {})                               # no fresh scan is needed to tell it again
    assert got["delivered"] is True and got["blank"] == 30 and "100종목 중 30종목" in sent2[0]


def test_without_telegram_the_mac_shows_it_and_an_error_never_stops_the_run(tmp_path, led, monkeypatch):
    d, sent, shown = daily(tmp_path, DUE_DAY, tg="NOT_CONFIGURED")
    st = {}
    assert d._earnings_gap(st, {"QSF": {"status": OK}})["delivered"] is True and len(shown) == 1 and "30종목" in shown[0][1]
    monkeypatch.setattr(eg, "count", lambda base: 1 / 0)
    st = {}
    assert d._earnings_gap(st, {"QSF": {"status": OK}})["error"] == "ZeroDivisionError" and st["earnings_gap"].get("delivered") is None


def test_a_whole_run_on_the_due_day_sends_the_summary_and_the_count(tmp_path, led):
    d, sent, _ = daily(tmp_path, DUE_DAY)
    assert d.run()["status"] == "DONE"
    assert len(sent) == 2 and "실적 발표일 빈칸 재집계" in sent[0] and "일일 요약" in sent[1]
    assert d.state()["earnings_gap"]["delivered"] is True
