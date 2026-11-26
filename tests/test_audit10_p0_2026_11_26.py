"""P0 of the institutional assessment (2026-11-26, user decisions): cards the buy check waits on leave the REAL order plan only,
the card and the buy check say why, template sentences that did not fit the company, and a second backup folder."""
import json

import pytest
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


# ---------------------------------------------------------------------- P1 (2026-11-26)
def _ledger(base, session="2026-11-25"):
    """A real ledger with one small shard (the least a snapshot needs)."""
    from terminal.qsf import config
    from terminal.qsf.ledger import Ledger
    led = Ledger(base)
    led.append(session, "US", [{"market": "US", "ticker": f"S{j:02d}", "strategy": "SWING", "score": 50.0 + j, "data_date": session, "model_version": config.MODEL_VERSION,
                                "actionability": "ACTIONABLE", "domains": {}, "factors": [], "levels": {}} for j in range(5)])
    return led


def test_a_sample_of_two_formulas_or_two_statement_bases_is_named_before_any_return_is_read():
    from terminal.qsf import live_forward as lf
    row = lambda v, b: {"model_version": v, **({"fund_period": {"live": b}} if b else {})}      # noqa: E731
    one = {"d1": [row("QSF-1.6.0", "ANNUAL")], "d2": [row("QSF-1.6.0", None)]}                    # no basis written = annual (before 2026-11-23)
    assert lf.formula_mix(one, ["d1", "d2"]) is None
    two = lf.formula_mix({"d1": [row("QSF-1.6.0", "ANNUAL")], "d2": [row("QSF-1.6.0", "TRAILING")]}, ["d1", "d2"])
    assert two["fund_bases"] == ["ANNUAL", "TRAILING"] and "재무 기준이 둘 이상" in two["reasons"][0] and "수익도 읽지 않았습니다" in two["reasons"][0]
    ver = lf.formula_mix({"d1": [row("QSF-1.6.0", "ANNUAL")], "d2": [row("QSF-1.7.0", "ANNUAL")]}, ["d1", "d2"])
    assert ver["versions"] == ["QSF-1.6.0", "QSF-1.7.0"] and "점수 공식이 둘 이상" in ver["reasons"][0]
    code = (ROOT / "terminal" / "qsf" / "live_forward.py").read_text(encoding="utf-8")
    assert code.count("mixed = formula_mix(rows, used)") == 2 and code.index("mixed = formula_mix(rows, used)") < code.index("days = [d for d in (day_stats(s, rows[s], px, h, cost, variant)")
    doc = (ROOT / "reports" / "QSF_LIVE_FORWARD_PROTOCOL.md").read_text(encoding="utf-8")
    assert "MIXED_FORMULA" in doc and "2026-11-26" in doc


def test_late_days_are_counted_from_the_entry_session_and_change_no_condition():
    from terminal.qsf import live_forward as lf
    cal = ["2026-11-02", "2026-11-03", "2026-11-04", "2026-11-05"]
    rows = {"2026-11-02": [{"entry_session": "2026-11-03"}], "2026-11-03": [{"entry_session": "2026-11-05"}], "2026-11-04": [{"entry_session": None}]}
    got = lf.late_days(rows, list(rows), cal)
    assert got["late"] == 1 and got["sessions"] == ["2026-11-03"] and got["of"] == 3 and "판정 조건에는 쓰지 않는" in got["note"]


def test_a_us_store_is_timed_by_the_new_york_open():
    from datetime import datetime, timezone
    from terminal.qsf import kr_forward as kf
    at = datetime(2026, 11, 25, 22, 30, tzinfo=timezone.utc)                      # 07:30 KST on the 26th: before both next opens of the 25th
    assert at < kf.open_after("fund_period_us", "2026-11-25") and at < kf.open_after("krx_forward", "2026-11-25")
    noon = datetime(2026, 11, 26, 3, 0, tzinfo=timezone.utc)                      # 12:00 KST: Korea has opened, New York has not
    assert noon < kf.open_after("paper_book_us", "2026-11-25") and not noon < kf.open_after("paper_book_kr", "2026-11-25")


def test_the_committee_names_carry_no_buy_word_and_its_codes_are_the_same():
    from terminal.committee import council, investors as iv
    assert iv.REC_KO[iv.STRONG_BUY] == "편입 조건 강하게 충족" and iv.REC_KO[iv.BUY] == "편입 조건 충족" and council.DECISION_KO[council.CONDITIONAL_BUY] == "조건부 편입"
    assert (iv.STRONG_BUY, iv.BUY, council.CONDITIONAL_BUY) == ("STRONG_BUY", "BUY", "CONDITIONAL_BUY")
    for name in ("investors.py", "council.py", "portfolios.py", "service.py"):
        text = (ROOT / "terminal" / "committee" / name).read_text(encoding="utf-8")
        said = [ln for ln in text.splitlines() if "매수" in ln and "#" not in ln.split("매수")[0] and '"""' not in ln and "순매수" not in ln and "RED-07" not in ln]
        assert said == [], (name, said[:2])


def test_a_damaged_shard_comes_back_from_a_backup_whose_copy_matches_and_nothing_is_deleted(tmp_path, monkeypatch):
    from terminal import restore
    from terminal.qsf.ledger import Ledger
    monkeypatch.delenv("QPP_BACKUP_DIR_2", raising=False)
    base, first = tmp_path / "base", tmp_path / "first"
    monkeypatch.setenv("QPP_BACKUP_DIR", str(first))
    led = _ledger(base)
    assert restore.repair_ledger(base)["status"] == "NOTHING_TO_DO"
    automation.backup(base, "2026-11-25", first)
    shard = next(led.dir.glob("*.jsonl.gz"))
    good = shard.read_bytes()
    shard.write_bytes(good[: len(good) // 2])                                   # a file cut short
    assert Ledger(base).verify()["status"] == "BROKEN"
    res = restore.repair_ledger(base)
    assert res["status"] == "REPAIRED" and res["integrity"] == "OK" and shard.read_bytes() == good and len(list((led.dir / "damaged").iterdir())) == 1
    shard.write_bytes(b"x")
    (first / "qsf_ledger" / shard.name).write_bytes(b"y")                       # the backup's copy does not match either: left alone and named
    res = restore.repair_ledger(base)
    assert res["status"] == "NO_GOOD_COPY" and res["left"] == [shard.name] and shard.read_bytes() == b"x"
    import terminal.server as server
    src = (ROOT / "terminal" / "server.py").read_text(encoding="utf-8")
    assert '("POST", "/api/backup/repair-ledger")' in src and '("GET", "/api/backup/check")' in src and server._restore().check


def test_what_stayed_silent_is_now_said_in_the_days_message():
    from terminal.qsf import readings
    quiet = next(e for e in readings.REGISTRY if not e.get("notify"))
    st = {"readings": {quiet["key"]: {"failed": readings.GIVE_UP}}, "sector_archive": {"US": "WRITTEN", "KR": "TOO_FEW", "error": "KR TOO_FEW"}}
    said = " ".join(automation.Daily._notes(st))
    assert "보관으로 돌린 읽기 가운데 막힌 것" in said and quiet["label"] in said and "업종 분류 보관(KR TOO_FEW)" in said
    assert automation.Daily._notes({"readings": {quiet["key"]: {"failed": 1}}, "sector_archive": {"US": "KEPT", "KR": "KEPT"}}) == []
    assert '"IC1_*.json"' in (ROOT / "terminal" / "automation.py").read_text(encoding="utf-8")


def test_a_backup_whose_files_are_in_icloud_only_is_named_and_not_read(tmp_path, monkeypatch):
    from terminal import restore
    monkeypatch.delenv("QPP_BACKUP_DIR_2", raising=False)
    base, first = tmp_path / "base", tmp_path / "first"
    monkeypatch.setenv("QPP_BACKUP_DIR", str(first))
    _ledger(base)
    automation.backup(base, "2026-11-25", first)
    assert restore.in_cloud_only(first) == 0 and restore.check(base)["backups"][0]["status"] == "OK"
    monkeypatch.setattr(restore, "in_cloud_only", lambda root: 7)
    monkeypatch.setattr(automation, "check_backup", lambda root: (_ for _ in ()).throw(AssertionError("must not read")))
    got = restore.check(base)["backups"][0]
    assert got["status"] == "IN_CLOUD" and got["in_cloud_only"] == 7 and got["latest"] == "2026-11-25"
    monkeypatch.setattr(restore, "in_cloud_only", lambda root: 0)
    monkeypatch.setattr(automation, "check_backup", lambda root: (_ for _ in ()).throw(OSError("x")))
    assert restore.check(base)["backups"][0]["status"] == "UNREADABLE"
    assert "IN_CLOUD" in (ROOT / "terminal" / "static" / "lab.js").read_text(encoding="utf-8")


# ---------------------------------------------------------------------- P2 (2026-11-26)
def test_the_plans_totals_are_display_only_and_the_paper_book_record_is_as_it_was():
    from terminal.qsf import order_plan as op
    orders = [{"ticker": "A", "sector": "Tech", "shares": 10, "limit": 105.0, "stop": 95.0, "weight_pct": 10.0, "risk_pct": 0.5},
              {"ticker": "B", "sector": "Tech", "shares": 5, "limit": 52.0, "stop": 46.0, "weight_pct": 2.5, "risk_pct": 0.2},
              {"ticker": "C", "sector": None, "shares": 1, "limit": 11.0, "stop": 9.0, "weight_pct": 0.1, "risk_pct": 0.01}]
    t = op.totals(orders, 10_000.0)
    assert t["orders"] == 3 and t["weight_pct"] == pytest.approx(12.6) and t["risk_pct"] == pytest.approx(0.71)
    assert orders[0]["risk_at_limit_pct"] == pytest.approx(1.0) and t["risk_at_limit_pct"] == pytest.approx(1.0 + 0.3 + 0.02)
    assert t["largest_sector"] == {"sector": "Tech", "weight_pct": 12.5} and "합계에 거는 한도는 없습니다" in t["note"]
    code = (ROOT / "terminal" / "qsf" / "order_plan.py").read_text(encoding="utf-8")
    build = code[code.index("def build("):]
    assert "risk_at_limit_pct" not in build and "totals" not in build                       # the plan builder, read by the paper book, is unchanged
    assert "totals" not in (ROOT / "terminal" / "qsf" / "paper_book.py").read_text(encoding="utf-8")


def test_a_ranking_row_says_when_a_newer_quarter_moves_the_score_by_ten_points():
    from terminal.qsf import service
    card = lambda a, t, newer=True: {"fund_period": {"live": "ANNUAL", "annual": {"score": a}, "trailing": {"score": t, "newer_quarter": newer}}}      # noqa: E731
    assert service.fund_gap(card(64.3, 84.6)) == pytest.approx(20.3) and service.fund_gap(card(80.0, 62.3)) == pytest.approx(-17.7)
    assert service.fund_gap(card(64.3, 70.0)) is None and service.fund_gap(card(64.3, 84.6, newer=False)) is None and service.fund_gap({}) is None
    assert "qsfGapTag(r)" in (ROOT / "terminal" / "static" / "qsf.js").read_text(encoding="utf-8")


def test_the_persistence_figure_gives_both_shapes_and_the_inventory_gives_a_range():
    import numpy as np
    from terminal.qsf import inventory, live_forward as lf
    assert lf.PERSIST_POINTS[:4] == ((0.0, 1.25), (0.09, 2.5), (0.18, 3.9), (0.26, 5.4)) and lf.PERSIST_POINTS[-1] == (0.47, 14.6)
    assert all(np.interp(r, *zip(*lf.PERSIST_SLOW)) > np.interp(r, *zip(*lf.PERSIST_POINTS)) for r in (0.0, 0.1, 0.2, 0.3, 0.4))
    assert "2.6~10.1%" in inventory.markdown() and "상위 4.6%" not in inventory.markdown()
