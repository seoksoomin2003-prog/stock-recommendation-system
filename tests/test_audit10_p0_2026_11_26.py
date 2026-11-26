"""P0 of the institutional assessment (2026-11-26, user decisions): cards the buy check waits on leave the REAL order plan only,
the card and the buy check say why, template sentences that did not fit the company, and a second backup folder."""
import json
from pathlib import Path

from terminal import automation, plain, record_status
from terminal.qsf import holding, plan_checks

ROOT = Path(__file__).resolve().parents[1]


def snap(**kw):
    base = {"ticker": "AAA", "strategy": "SWING", "entry_status": "ENTRY_NOW", "price": 90.0, "confidence": "HIGH", "score": 60.0,
            "factors": [{"factor": "trend_structure", "raw": {"ma50": 100.0, "ma50_slope": -0.02}}]}
    return {**base, **kw}


def test_a_swing_entry_under_a_falling_50_day_line_is_named_and_a_missing_number_is_not_a_yes():
    assert "10.0% 아래" in plan_checks.trend_broken(snap()) and "정리 조건" in plan_checks.trend_broken(snap())
    assert plan_checks.trend_broken(snap(price=101.0)) is None                                         # above the line
    assert plan_checks.trend_broken(snap(factors=[{"factor": "trend_structure", "raw": {"ma50": 100.0, "ma50_slope": 0.01}}])) is None      # the line rises
    assert plan_checks.trend_broken(snap(factors=[{"factor": "trend_structure", "raw": {"ma50": 100.0, "ma50_slope": None}}])) is None      # unknown is not broken
    assert plan_checks.trend_broken(snap(strategy="LONG_TERM")) is None                                  # the long-term exit rule has no such condition
    assert plan_checks.reasons(snap(entry_status="WAIT_FOR_PULLBACK")) == []                             # only cards the entry rule reads as enterable


def test_the_three_reasons_and_the_split_of_the_real_plan():
    worse = {"flags": [{"code": "ROE_DOWN", "side": "down", "text": "ROE가 내려갔습니다."}], "pattern": None}
    codes = lambda s: [r["code"] for r in plan_checks.reasons(s)]      # noqa: E731
    assert codes(snap()) == ["SAME_DAY_EXIT"] and codes(snap(price=120.0)) == []
    assert codes(snap(price=120.0, fund_checks=worse)) == ["FIGURES_WORSENING"] and codes(snap(price=120.0, confidence="LOW")) == ["LOW_CONFIDENCE"]
    snaps = [snap(), snap(ticker="BBB", price=120.0), snap(ticker="CCC", strategy="LONG_TERM", confidence="LOW")]
    cands = [{"ticker": "AAA", "style": "SWING", "score": 60.0}, {"ticker": "BBB", "style": "SWING", "score": 61.0}, {"ticker": "CCC", "style": "LONG", "score": 75.0},
             {"ticker": "ZZZ", "style": "LONG", "score": 70.0}]
    kept, shown = plan_checks.split(cands, snaps, {"SWING": "SWING", "LONG": "LONG_TERM"})
    assert [c["ticker"] for c in kept] == ["BBB", "ZZZ"]                                                 # a candidate without its snapshot is kept
    assert shown["left_out"] == 2 and shown["left_out_by"] == {"같은 날 정리 조건에도 해당": 1, "신뢰도 낮음": 1} and "시험하지 않았습니다" in shown["note"]
    assert plan_checks.split(cands[1:2], snaps, {"SWING": "SWING", "LONG": "LONG_TERM"})[1]["note"] is None


def test_only_the_real_plan_the_card_and_the_buy_check_read_it():
    """The entry rule, the paper book and the comparison books keep the rules they were registered with."""
    readers = sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / "terminal").rglob("*.py") if "plan_checks" in p.read_text(encoding="utf-8") and p.name != "plan_checks.py")
    assert readers == ["terminal/assistant.py", "terminal/qsf/service.py", "terminal/services.py"]
    js = (ROOT / "terminal" / "static" / "qsf.js").read_text(encoding="utf-8")
    assert "qsfPlanChecks(c)" in js and "qsfPlanLeft(d.plan_checks)" in js and "진입 규칙은 충족하지만 내 계좌의 주문 계획에서는 뺍니다" in js


def test_the_buy_check_waits_on_a_swing_entry_that_meets_the_exit_condition():
    from terminal import assistant
    s = {**snap(), "actionability": "ACTIONABLE", "holding": {}, "market": "US"}
    out = assistant.buy_verdict(s, "SWING", "US", gates=[], marks=[], earnings={}, soon=False, level="NORMAL", wide=[], state={}, held=False)
    assert out["key"] == "WAIT" and "하락 중인 50일선" in json.dumps(out, ensure_ascii=False)
    ok = assistant.buy_verdict({**s, "price": 120.0}, "SWING", "US", gates=[], marks=[], earnings={}, soon=False, level="NORMAL", wide=[], state={}, held=False)
    assert "하락 중인 50일선" not in json.dumps(ok, ensure_ascii=False)                    # above the line: this reason is not given


def test_template_sentences_no_longer_claim_what_the_figures_do_not_say():
    assert "꾸준히 돈을 잘 버는" not in plain.FACTOR["business_quality"][0] and "꾸준히 늘었습니다" not in plain.FACTOR["growth_quality"][0]
    code = (ROOT / "terminal" / "plain.py").read_text(encoding="utf-8")
    assert "걱정할 점이 없다는 뜻은 아닙니다" in code
    committee = (ROOT / "terminal" / "committee" / "investors.py").read_text(encoding="utf-8") + (ROOT / "terminal" / "committee" / "council.py").read_text(encoding="utf-8")
    assert "자산이 가벼운 업종" not in committee and "치명 위험은 이 수치와 따로 읽습니다" in committee
    assert any("그대로 이어진다고 보지 않습니다" in m for m in holding._milestones({"fund": {"rev_growth": 2.563}}))
    assert any("256.3" not in m and "유지하는지" in m for m in holding._milestones({"fund": {"rev_growth": 0.08}}))
    bank = holding._milestones({"fund": {"rev_growth": 0.05, "fcf_margin": 0.307, "is_financial": True}})
    assert not any("FCF" in m for m in bank)


def test_a_second_backup_folder_is_off_until_set_and_its_absence_is_said(tmp_path, monkeypatch):
    monkeypatch.delenv("QPP_BACKUP_DIR_2", raising=False)
    base, first, second = tmp_path / "base", tmp_path / "first", tmp_path / "second"
    (base / "data" / "terminal").mkdir(parents=True)
    (base / "data" / "terminal" / "journal.jsonl").write_text("{}\n", encoding="utf-8")
    monkeypatch.setenv("QPP_BACKUP_DIR", str(first))
    assert automation.second_backup_root(base) is None and automation.second_backup_status(base)["on"] is False
    first.mkdir()
    alerts = record_status.second_backup_alerts(automation.second_backup_status(base))
    assert len(alerts) == 1 and "같은 디스크에만" in alerts[0]["text"]                        # tmp_path: both on one disk
    st = automation.set_second_backup(base, True, second)
    assert st["on"] and st["latest"] is None and "아직 없습니다" in record_status.second_backup_alerts(st)[0]["text"]
    d = automation.Daily(base)
    assert "두 번째 백업 1개 파일" in d._second_backup("2026-11-25") and (second / "2026-11-25" / "data" / "terminal" / "journal.jsonl").exists()
    assert record_status.second_backup_alerts(automation.second_backup_status(base, automation.date(2026, 11, 26))) == []
    second_file = second / "2026-11-25"
    assert second_file.is_dir() and automation.set_second_backup(base, False, second)["on"] is False and automation.Daily(base)._second_backup("2026-11-26") == ""
    assert ".env" not in " ".join(automation.BACKUP_GLOBS)                                   # keys go to neither backup
