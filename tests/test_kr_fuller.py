"""Side record FI-1 (2026-11-25): the Korean score with gross profit, interest paid and own-share purchases read too, kept beside
the live score, which stays as it is (user decision; the score is frozen at QSF-1.6.0).  No network."""
from pathlib import Path

from terminal.qsf import fundamentals as F, kr_fuller as kf, ledger, service

ROOT = Path(__file__).resolve().parents[1]


def src(*parts):
    return ROOT.joinpath(*parts).read_text(encoding="utf-8")


def obs(account_id, value, statement="IS", year=2025, basis="CONSOLIDATED", amount_type="FY"):
    return {"account_id": account_id, "statement": statement, "amount_type": amount_type, "value": value, "fiscal_year": year, "period_end": f"{year}-12-31",
            "receipt_date": f"{year + 1}-03-15", "basis": basis}


ROWS = [obs("ifrs-full_GrossProfit", 400.0), obs("ifrs-full_GrossProfit", 400.0, "CIS"),
        obs("ifrs-full_InterestPaidClassifiedAsOperatingActivities", -30.0, "CF"), obs("ifrs-full_InterestPaidClassifiedAsFinancingActivities", -5.0, "CF"),
        obs("dart_AcquisitionOfTreasuryShares", -70.0, "CF"), obs("ifrs-full_PurchaseOfTreasuryShares", -999.0, "CF"),
        obs("ifrs-full_FinanceCosts", 500.0), obs("ifrs-full_Revenue", 1000.0)]


def test_the_three_lines_are_read_by_account_id_and_nothing_else():
    got = kf.read_year(ROWS, "NON_FINANCIAL")
    assert {k: v["value"] for k, v in got.items()} == {"gross_profit": 400.0, "interest": 35.0, "buyback": 70.0}      # interest: both places added; buyback: the first id, as a positive outflow
    assert got["gross_profit"]["period_end"] == "2025-12-31" and got["interest"]["receipt_date"] == "2026-03-15"
    assert "gross_profit" not in kf.read_year(ROWS, "BANK") and "buyback" in kf.read_year(ROWS, "BANK")           # no gross margin for a bank
    twice = ROWS + [obs("ifrs-full_GrossProfit", 410.0)]
    assert "gross_profit" not in kf.read_year(twice, "NON_FINANCIAL")                                              # two values for one account: unknown, never a guess
    assert kf.read_year([obs("ifrs-full_Revenue", 1000.0)], "NON_FINANCIAL") == {}
    assert kf.read_year([obs("ifrs-full_GrossProfit", 9.0, amount_type="YTD")], "NON_FINANCIAL") == {}             # annual figures only


def test_the_live_reading_is_unchanged_and_the_side_lines_are_put_aside():
    keep = {}
    run = kf.extractor(lambda o, klass: {"live": len(o), "klass": klass}, keep)
    assert run(ROWS, "NON_FINANCIAL") == {"live": len(ROWS), "klass": "NON_FINANCIAL"}                             # what the live reader gets is the base extract's own
    assert sorted(keep[2025]) == ["buyback", "gross_profit", "interest"]
    rows = kf.series(keep, ["CONSOLIDATED"])
    assert rows["gross_profit"] == [{"end": "2025-12-31", "val": 400.0, "filed": "2026-03-15", "basis": "CONSOLIDATED"}]
    assert kf.series(keep, ["SEPARATE"]) == {}                                                                      # never another basis beside the live figures
    live_names = F.extract_kr({})
    assert not {"gross_profit", "interest", "buyback"} & set(live_names)                                           # the live series has no place for them


def test_merging_adds_only_what_is_missing_and_the_record_keeps_both_scores():
    annual = {"revenue": [{"end": "2025-12-31", "val": 1000.0, "filed": "2026-03-15"}], "_bases": ["CONSOLIDATED"]}
    side = kf.series({2025: kf.read_year(ROWS, "NON_FINANCIAL")}, ["CONSOLIDATED"])
    full = kf.merged(annual, side)
    assert set(full) == {"revenue", "_bases", "gross_profit", "interest", "buyback"} and annual.keys() == {"revenue", "_bases"}      # a copy
    assert kf.merged(annual, {}) is None and kf.merged(annual, None) is None
    assert kf.merged({**annual, "gross_profit": [{"end": "x", "val": 1.0, "filed": "y"}]}, {"gross_profit": side["gross_profit"]}) is None
    m = F.metrics(full, 100.0, "2026-11-25", source="t")
    assert m["gross_margin"] == 0.4
    field = kf.card_field(63.882, 63.59, ["interest", "gross_profit"])
    assert field == {"version": "FI-1", "score": 63.882, "live_score": 63.59, "added": ["gross_profit", "interest"], "added_ko": ["매출총이익", "이자 지급액"]}
    rec = ledger.snapshot({"domains": {}, "factors": [], "levels": {}, "fuller_inputs": field})
    assert rec["fuller_inputs"] == field and "fuller_inputs" not in ledger.snapshot({"domains": {}, "factors": [], "levels": {}})


def test_the_side_score_is_wired_beside_the_live_one_and_decides_nothing():
    assert service._kr_side_key("005930", 12) == "krside1:005930" and service._kr_side_key("030960", 6) == "krside1:030960:fm06"
    code = src("terminal", "qsf", "service.py")
    assert "extract=kr_fuller.extractor(kr_dart.extract_concepts, keep)" in code and "self.cache.write(_kr_side_key(code, fm)" in code
    assert code.count("lambda: self._kr_annual(corp, code, klass,") == 2                                           # the scan and the stock screen fetch through one place
    assert 'out["fuller_inputs"] = kr_fuller.card_field(full_score, res["score"], fund["fuller"]["added"])' in code
    for name in ("engine.py", "holding.py", "order_plan.py", "top_picks.py", "live_forward.py", "stance.py", "paper_book.py"):
        assert "fuller" not in src("terminal", "qsf", name), name                                                  # no score, band, entry, plan or verdict reads it
    assert "function qsfFullerNote(c)" in src("terminal", "static", "qsf.js") and "실제 점수가 아니며" in src("terminal", "static", "qsf.js")
    doc = src("reports", "QSF_KR_FULLER_INPUTS_2026_11_25.md")
    assert "FI-1" in doc and "ifrs-full_GrossProfit" in doc and "실제 점수, 구간, 진입 판단, 주문 계획, 순위는 이 값을 읽지 않는다" in doc
