"""2026-11-25, the work after the third assessment's scores (user request: every category over 50).  None of it changes the
score, which is frozen: the direction of a company's figures said beside the card and the buy check, the sentences the assessment
found wrong, the factor inventory, the look-ahead audit over statements and filings, and two pre-registered early readings of
the live swing score (user decision "중간 판정 미리 등록").  No network."""
import json
from datetime import date
from pathlib import Path

import pytest

from terminal import assistant as A, fund_checks as fc, plain
from terminal.qsf import config, factors, holding, inventory, ledger, live_forward as lf, lookahead, readings as rd
from tests import test_live_forward as base
from tests.test_live_forward import CAL, FakeLedger, flat_bench, led, loader      # noqa: F401  (the fixture is used by name)

ROOT = Path(__file__).resolve().parents[1]
HMM = {"status": "REAL", "roe": 0.071, "roe_prev": 0.136, "rev_growth": -0.069, "rev_cagr3": -0.163, "eps_growth": -0.61, "ocf_to_ni": 1.76, "fcf_margin": 0.157,
       "fcf_years_positive": 0.75, "is_financial": False, "loss_now": False}


def src(*parts):
    return ROOT.joinpath(*parts).read_text(encoding="utf-8")


def card(**over):
    c = {"actionability": "ACTIONABLE", "score": 71.7, "band": "BUY_CANDIDATE", "strategy": "LONG_TERM", "market": "KR", "entry_status": "ENTRY_NOW", "confidence": "HIGH",
         "factors": [{"factor": "valuation", "normalized": 0.8, "status": "REAL"}, {"factor": "business_quality", "normalized": 0.5, "status": "REAL"}]}
    c.update(over)
    return c


# ---------------------------------------------------------------------- the direction of the figures
def test_a_cheap_company_whose_figures_are_falling_is_named_as_that():
    got = fc.read(HMM, card())
    assert got["direction"] == "DETERIORATING" and got["pattern"] == "CHEAP_AND_WORSENING" and got["checked"] == 4
    assert [x["code"] for x in got["flags"]] == ["ROE_DOWN", "SALES_DOWN", "EPS_DOWN"]
    assert "13.6%에서 7.1%" in got["flags"][0]["text"] and "보유 논리가 깨짐" in got["flags"][0]["text"]          # the holder's words, to an entrant
    assert fc.ROE_FALL == 0.05 and fc.ROE_LOW == 0.08 and "holding" in src("terminal", "fund_checks.py")           # the holding rule's own thresholds
    assert "f[\"roe\"] < f[\"roe_prev\"] - 0.05 and f[\"roe\"] < 0.08" in src("terminal", "qsf", "holding.py")


def test_direction_is_never_read_from_too_few_figures_and_good_news_is_said_too():
    assert fc.read({"status": "REAL", "roe": 0.2}, card())["direction"] == "UNKNOWN"
    assert fc.read(None)["status"] == "UNAVAILABLE"
    up = fc.read({"status": "REAL", "roe": 0.22, "roe_prev": 0.12, "rev_growth": 0.3, "rev_cagr3": 0.2, "eps_growth": 0.5, "ocf_to_ni": 1.1}, card())
    assert up["direction"] == "IMPROVING" and up["pattern"] == "CHEAP_AND_IMPROVING" and fc.lines(up) == []
    dear = fc.read({"status": "REAL", "roe": 0.3, "roe_prev": 0.3, "rev_growth": 0.05, "eps_growth": 0.05}, card(factors=[{"factor": "valuation", "normalized": 0.2, "status": "REAL"},
                                                                                                                    {"factor": "business_quality", "normalized": 0.9, "status": "REAL"}]))
    assert dear["direction"] == "STABLE" and dear["pattern"] == "GOOD_BUT_DEAR" and "좋은 회사와 좋은 투자는 다를 수" in fc.lines(dear)[0]
    bank = fc.read({"status": "REAL", "is_financial": True, "roe": 0.1, "roe_prev": 0.1, "rev_growth": 0.01, "ocf_to_ni": 0.1, "fcf_margin": -0.5}, card())
    assert [x["code"] for x in bank["flags"]] == []                                                              # a bank's cash flow is not read


def test_the_plain_text_the_record_and_the_buy_check_carry_it_and_nothing_decides_on_it():
    checks = fc.read(HMM, card())
    said = " ".join(line for part in plain.card_plain(card(fund_checks=checks), {})["parts"] for line in part["lines"])
    assert "뚜렷하게 걱정되는 점이 없습니다" not in said and "값은 싸게 읽히지만 재무가 나빠지는 중" in said and "최근 재무 수치의 방향: 나빠지는 중" in said
    rec = ledger.snapshot({"domains": {}, "factors": [], "levels": {}, "fund_checks": checks})
    assert rec["fund_checks"]["direction"] == "DETERIORATING" and "note" not in rec["fund_checks"]
    cautions = A.decision_cautions(object(), {"fund_checks": rec["fund_checks"]}, "011200", "KR", "LONG_TERM", "WAIT")
    assert len(cautions) == 3 and "가치 함정" in cautions[0]
    assert A.decision_cautions(object(), {"fund_checks": fc.read({"status": "REAL", "roe": 0.2, "roe_prev": 0.2, "rev_growth": 0.02}, card())}, "X", "US", "SWING", "WAIT") == []
    for name in ("engine.py", "holding.py", "order_plan.py", "stance.py", "top_picks.py", "live_forward.py"):
        assert "fund_checks" not in src("terminal", "qsf", name), name                                             # no score, entry, plan or verdict reads it
    assert "function qsfFundChecks(c)" in src("terminal", "static", "qsf.js")


# ---------------------------------------------------------------------- sentences the assessment found wrong
def test_the_wrong_sentences_are_gone():
    assert factors.pct(None) == "자료 없음" and factors.pct(0.123) == "12.3%"                                       # no figure is not "none"
    falling = holding._milestones({"fund": {"rev_growth": -0.069}})
    assert "유지하는지" not in falling[0] and "매출 감소(최근 -6.9%)가 멈추는지" in falling[0]                          # a fall is not something to keep
    assert "자기자본이익률(ROE) 9.0%" in holding._milestones({"fund": {"roe": 0.09}})[0]                             # a bank has figures: its return on equity
    assert "financial_resilience" in plain.DEBT
    inv = src("terminal", "committee", "investors.py")
    assert "걸리는 조건이 있습니다(" in inv and "부채와 현금흐름이 나아져야 다시 봅니다" not in inv                    # the trap sentence names what made it a trap
    assert "재무 항목은 금융업이라 따지지 않았습니다" in inv and "금융업이라 부채 기준은 따지지 않았습니다" in inv


# ---------------------------------------------------------------------- the factor inventory
def test_every_factor_of_every_profile_is_described_and_the_document_is_the_modules():
    rows = inventory.factors()
    used = {f for m in ("US", "KR") for s in config.STRATEGIES for part in ("domains", "reference") for fs in (config.profile_for(m, s).get(part) or {}).values() for f in fs}
    assert set(rows) == used == set(inventory.F) and len(rows) == 39
    for fid, r in rows.items():
        assert all(r[k] for k in ("measures", "why", "limit", "evidence")), fid
    assert rows["trend_structure"]["weights"] == {"US_SWING": 10} and rows["vix_regime"]["reference"] is True
    assert src("reports", "QSF_FACTOR_INVENTORY.md") == inventory.markdown()                                        # written by `qsf factor-inventory`, never by hand
    assert "기대 수익도 오를 확률도 아닙니다" in inventory.markdown() and "과거 수익에 맞춰 고른 값이 아니고" in inventory.markdown()
    from terminal import server
    assert ("GET", "/api/qsf/factors") in server.routes(object())
    js, svc = src("terminal", "static", "qsf.js"), src("terminal", "qsf", "service.py")
    assert "function qsfRankNote(c)" in js and "qsfFactorTip(f.factor)" in js and 'c["rank_in_scan"] = {"top_pct"' in svc


# ---------------------------------------------------------------------- the look-ahead audit over statements and filings
def _store(tmp_path, name, data):
    folder = tmp_path / "data" / "qsf" / "cache"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{name}.json").write_text(json.dumps({"data": data}), encoding="utf-8")


def _annual():
    def rows(vals):
        return [{"end": f"{y}-12-31", "val": v, "filed": f"{y + 1}-02-15"} for y, v in vals.items()]
    return {"revenue": rows({2022: 900.0, 2023: 1000.0, 2024: 1100.0, 2025: 1300.0}), "net_income": rows({2022: 90.0, 2023: 100.0, 2024: 120.0, 2025: 150.0}),
            "equity": rows({2022: 500.0, 2023: 550.0, 2024: 600.0, 2025: 700.0}), "eps": rows({2022: 0.9, 2023: 1.0, 2024: 1.2, 2025: 1.5})}


def test_the_statement_readers_do_not_read_a_later_filing_and_the_control_does(tmp_path):
    _store(tmp_path, "annual5_0001_x", _annual())
    _store(tmp_path, "krfund3_005930_x", _annual())
    _store(tmp_path, "submforms_0001_x", {"filings": [{"form": "8-K", "date": d, "items": "2.02", "accession": d, "doc": "x"} for d in ("2026-11-10", "2026-08-05", "2026-05-06")]})
    _store(tmp_path, "krlist2_00126380_x", {"rows": [{"rcept_dt": d, "report_nm": "분기보고서", "rcept_no": d} for d in ("20261116", "20260814", "20260515")], "complete": True})
    got = {f["id"]: f for f in lookahead.audit_statements(tmp_path)}
    for key in ("fundamentals.metrics.US", "fundamentals.metrics.KR", "events.classify_us", "events.classify_kr"):
        assert got[key]["ok"] and got[key]["moved"] == 0 and got[key]["days"] == 3, key
    c = got["control.metrics_without_a_day"]
    assert c["control"] and c["ok"] and c["moved"] == c["days"] == 3                                                # a reader that ignores the day is caught
    leak = lookahead._statement_item("x", "x", [_annual()], lambda a: ["2026-02-14"], lambda a, d: sorted(r["val"] for r in a["revenue"])[-1], lookahead._later_statements)
    assert leak["ok"] is False and leak["moved"] == 1
    assert lookahead.audit_statements(tmp_path / "empty")[0]["days"] == 0                                           # nothing stored: not checked, and not a problem
    assert "srow" in src("terminal", "static", "qsf.js") and '"statements": statements' in src("terminal", "qsf", "lookahead.py")


# ---------------------------------------------------------------------- two early readings of the live swing score
def test_the_early_readings_are_fixed_reference_readings_with_a_stricter_bar():
    assert lf.EARLY == {60: 5, 120: 5} and lf.EARLY_T == 2.5 and lf.EARLY_T > lf.validate.MIN_T
    rows = {e["key"]: e for e in rd.REGISTRY}
    for key in ("early_swing_60_kr", "early_swing_60_us", "early_swing_120_kr", "early_swing_120_us"):
        assert rows[key]["primary"] is False and rows[key]["horizon"] == 5 and "바뀌지 않습니다" in rows[key]["after"], key
    assert rows["early_swing_60_us"]["argv"] == ["--market", "US", "qsf", "live-forward-early-60"] and rd.wanted(rows["early_swing_120_kr"]) == 125
    assert set(lf.EARLY_KO) <= set(rd.VERDICT_KO)
    doc = src("reports", "QSF_LIVE_FORWARD_PROTOCOL.md")
    assert "## 중간 읽기 (2026-11-25" in doc and "결과가 하는 일: 없다." in doc and "첫 기록 전에 적음" in doc
    import app
    assert {"live-forward-early-60", "live-forward-early-120"} <= set(app.QSF_LIVE_HANDLERS) and {"live-forward-early-60", "live-forward-early-120"} <= set(app.QSF_ACTIONS)


def test_an_early_reading_reads_the_first_sessions_once_and_decides_nothing(led, tmp_path, monkeypatch):   # noqa: F811
    monkeypatch.setattr(FakeLedger, "days", 40)
    with pytest.raises(RuntimeError, match="아직 읽을 수 없습니다"):
        lf.early_once(tmp_path, "US", 60, loader(), flat_bench(), log=lambda *_: None)
    monkeypatch.setattr(FakeLedger, "days", 300)
    weak = lf.early_once(tmp_path / "weak", "US", 60, loader(), flat_bench(), log=lambda *_: None)
    assert weak["verdict"] == "EARLY_NOTHING" and weak["condition_a"]["t"] and not weak["condition_a"]["spread_both_halves"]      # ranks well, but five sessions do not pay the cost: not "positive"
    res = lf.early_once(tmp_path, "US", 60, loader(strength=0.004), flat_bench(), log=lambda *_: None)
    assert res["verdict"] == "EARLY_POSITIVE" and res["sessions_used"] == 60 and res["first"] == CAL[0] and res["last"] == CAL[59] and res["horizon"] == 5
    assert res["t_bar"] > 2.5 and res["applies_itself"] is False and len(res["reasons"]) == 4 and "바뀌지 않습니다" in res["reasons"][-1]
    with pytest.raises(RuntimeError, match="한 번만"):
        lf.early_once(tmp_path, "US", 60, loader(strength=0.004), flat_bench())
    assert not lf.report_path(tmp_path, "US", "SWING").exists()                                                     # the verdict's own file is untouched
    against = lf.early_once(tmp_path / "b", "US", 120, loader(strength=-0.004), flat_bench(), log=lambda *_: None)
    assert against["verdict"] == "EARLY_AGAINST" and against["sessions_used"] == 120
    flat = lf.early_once(tmp_path / "c", "US", 60, loader(strength=0.0), flat_bench(), log=lambda *_: None)
    assert flat["verdict"] == "EARLY_NOTHING"
    with pytest.raises(ValueError):
        lf.early_once(tmp_path, "US", 90, loader(), flat_bench())
