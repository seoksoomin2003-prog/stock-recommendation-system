"""2026-11-25, user decisions after the third assessment's P1 list: the score is frozen at QSF-1.6.0 (US capital spending read
under more tags is its last change), the rules that turn a score into words carry their own label, and buying a new-high swing
candidate at once is recorded beside the paper book (EN-1) instead of changing the entry rule.  No network."""
import hashlib
import json
from pathlib import Path

import pytest

from terminal.qsf import config, engine, entry_book as eb, fund_trailing as ft, fundamentals as F, ledger, live_forward as lf, order_plan as op, paper_book as pb, readings as rd
from tests.test_order_plan_paper_book import calendar, filler, loader_of, snap
from tests.test_qsf import GOOD_FUND, ctx

ROOT = Path(__file__).resolve().parents[1]
FREEZE = "reports/QSF_FORMULA_FREEZE_2026_11_25.md"


def src(*parts):
    return ROOT.joinpath(*parts).read_text(encoding="utf-8")


# ---------------------------------------------------------------------- the frozen score
def test_the_score_formula_is_frozen_until_the_first_live_verdict():
    """This test failing means the score changed.  Read reports/QSF_FORMULA_FREEZE_2026_11_25.md before touching the numbers
    below: until the first live swing verdict a found input error is recorded beside the live score, not applied to it."""
    assert config.MODEL_VERSION == "QSF-1.6.0", FREEZE
    weights = {f"{m}_{s}": config.profile_for(m, s)["domains"] for m in ("US", "KR") for s in ("SWING", "LONG_TERM")}
    assert hashlib.sha256(json.dumps(weights, sort_keys=True).encode()).hexdigest() == "d5b7efdfaed532a652fcd70540045c42fd87dc7ca9b4e127e46c3c9103a083ea", FREEZE
    weak = {**GOOD_FUND, "roe": 0.03, "op_margin": 0.02, "rev_growth": -0.05, "eps_growth": -0.2}
    golden = {("SWING", None): 75.41523062652797, ("LONG_TERM", None): 87.42482191394319, ("SWING", "weak"): 71.15630205509942, ("LONG_TERM", "weak"): 77.05445154357284}
    for (strategy, kind), want in golden.items():
        got = engine.score(ctx(fund=weak) if kind else ctx(), strategy)["score"]
        assert got == pytest.approx(want, abs=1e-9), (strategy, kind, FREEZE)
    assert (ROOT / FREEZE).exists() and "QSF-1.6.0" in src(*FREEZE.split("/")) and (ROOT / "reports" / "QSF_1_6_0_2026_11_25.md").exists()


def test_bands_and_entry_rules_carry_their_own_label():
    r = engine.score(ctx(), "SWING")
    assert r["rules_version"] == config.RULES_VERSION == "R-1" and r["model_version"] == "QSF-1.6.0"
    assert "rules_version" in ledger.FIELDS


def test_the_live_verdicts_count_from_the_frozen_versions_first_session():
    assert lf.FIRST == rd.LEDGER_FIRST == "2026-11-25"
    doc = src("reports", "QSF_LIVE_FORWARD_PROTOCOL.md")
    assert "## 시작일 변경 (2026-11-25, 사용자 결정)" in doc and "QSF-1.5.3으로 기록된 날은 없다" in doc


# ---------------------------------------------------------------------- US capital spending under more tags
def _facts(tags):
    def rows(vals):
        return {"units": {"USD": [{"form": "10-K", "fp": "FY", "start": f"{y}-01-01", "end": f"{y}-12-31", "filed": f"{y + 1}-02-15", "val": v} for y, v in vals.items()]}}
    return {"facts": {"us-gaap": {k: rows(v) for k, v in tags.items()}}}


def test_another_capital_spending_tag_is_read_only_for_a_year_the_three_do_not_report():
    f = _facts({"PaymentsToAcquirePropertyPlantAndEquipment": {2023: 100.0}, "PaymentsToAcquireOtherProductiveAssets": {2023: 7.0, 2024: 120.0, 2025: 130.0},
                "NetCashProvidedByUsedInOperatingActivities": {2023: 300.0, 2024: 310.0, 2025: 320.0}})
    got = {r["end"][:4]: (r["val"], r["alias"]) for r in F.extract_us(f)["capex"]}
    assert got == {"2023": (100.0, "PaymentsToAcquirePropertyPlantAndEquipment"), "2024": (120.0, "PaymentsToAcquireOtherProductiveAssets"), "2025": (130.0, "PaymentsToAcquireOtherProductiveAssets")}
    assert len(F.US_FLOW["capex"]) == 3 and len(F.US_CAPEX_FALLBACK) == 7                         # the three still come first, alone


def test_a_property_company_and_a_net_inflow_stay_unread():
    estate = _facts({"PaymentsToAcquireOtherPropertyPlantAndEquipment": {2025: 2.0}, "PaymentsToDevelopRealEstateAssets": {2025: 440.0}})
    assert F.extract_us(estate)["capex"] == []                                                    # its "other equipment" is not its capital spending
    net = _facts({"PaymentsForProceedsFromProductiveAssets": {2024: -50.0, 2025: 80.0}})
    assert [r["val"] for r in F.extract_us(net)["capex"]] == [80.0]                               # proceeds above payments is not spending
    own = _facts({"NetCashProvidedByUsedInOperatingActivities": {2025: 500.0}})
    assert F.extract_us(own)["capex"] == []                                                       # a company on its own tags stays without a figure, never zero


def test_the_trailing_reader_follows_the_same_rule():
    f = _facts({"PaymentsToAcquirePropertyPlantAndEquipment": {2023: 100.0}, "PaymentsToAcquireOtherProductiveAssets": {2023: 7.0, 2025: 130.0}})
    got = sorted((r["end"][:4], r["val"]) for r in ft.us_periods(f)["flow"]["capex"])
    assert ("2023", 100.0) in got and ("2023", 7.0) not in got
    code = src("terminal", "qsf", "service.py")
    assert 'f"annual5:' in code and code.count('f"periods2:') == 2                                # stored copies of the former reading are not read


# ---------------------------------------------------------------------- EN-1: the entry comparison book
def _wait(ticker="A", band="BUY_CANDIDATE", **kw):
    return {**snap(ticker, score=75.0, price=10_000.0, atr=200.0, adv=1e11, entry="WAIT_FOR_PULLBACK", **kw), "band": band}


def test_a_new_high_buy_band_card_waiting_for_a_pullback_is_what_the_rule_adds():
    day = calendar(1)[0]
    assert op.breakout_wait(_wait(session=day))
    assert not op.breakout_wait(_wait(session=day, target=10_300.0))                      # a resistance stands above: the entry rule read the price
    assert not op.breakout_wait(_wait(band="HOLD_WATCH", session=day))                    # under the buy band
    assert not op.breakout_wait({**_wait(session=day), "strategy": "LONG_TERM"}) and not op.breakout_wait({**_wait(session=day), "entry_status": "ENTRY_NOW"})
    snaps = filler(day) + [_wait(session=day)]
    assert op.candidates(snaps, day) == []
    got = op.candidates(snaps, day, breakout=True)
    assert [(c["ticker"], c["via"]) for c in got] == [("A", "BREAKOUT")] and got[0]["stop"] == 9_600.0 and got[0]["target"] == 10_600.0


def test_the_comparison_book_parts_from_the_paper_book_by_that_rule_alone():
    day = calendar(1)[0]
    bars = pb.Bars(loader_of({"A": [(day, 10_000, 10_000)]}))
    snaps = filler(day) + [_wait(session=day)]
    assert pb.step(None, day, "KR", bars, snaps)["plan"]["orders"] == []                          # the paper book waits
    got = pb.step(None, day, "KR", bars, snaps, rules=dict(eb.RULES), version=eb.VERSION)
    assert [o["ticker"] for o in got["plan"]["orders"]] == ["A"] and got["rules"] == "EN-1"
    assert got["rule_events"] == [{"rule": "BREAKOUT_ENTRY", "ticker": "A", "style": "SWING", "score": 75.0}]
    assert eb.rule_counts([got]) == {"BREAKOUT_ENTRY": 1} and eb.RULES == {"breakout_entry": True} and eb.FIRST == "2026-11-25"


@pytest.mark.parametrize("mean,t,decision", [(0.0004, 3.2, "BREAKOUT_BETTER"), (-0.0004, -3.2, "PULLBACK_BETTER"), (0.0004, 1.1, "NOT_DISTINCT"), (0.0, None, "NOT_DISTINCT")])
def test_the_reading_says_which_book_did_better_and_changes_nothing(mean, t, decision):
    fig = {"return_pct": 1.0, "max_drawdown_pct": -2.0, "cost_pct": 0.3}
    got = eb.decide(fig, fig, mean, t, 2.0)
    assert got["decision"] == decision and decision in eb.DECISION_KO
    assert "applies_itself" in src("terminal", "qsf", "entry_book.py") and "set_switch" not in src("terminal", "qsf", "entry_book.py")      # no button: it reports


def test_the_entry_comparison_is_recorded_backed_up_shown_and_read_without_a_person(tmp_path):
    app, job = src("app.py"), src("terminal", "automation.py")
    assert 'res["entry_book"] = _entry_book_record(market, q, info, bench)' in app and '"entry-book-status": _qsf_turnover_book' in app
    assert '"entry_book_kr", "entry_book_us"' in job and "research_data/entry_book_kr/index.jsonl" in job
    assert job.index("self._rank_reading(st)\n") < job.index("self._entry_reading(st)\n") < job.index("self._store_watch(st)\n")
    assert '("GET", "/api/qsf/entry-book")' in src("terminal", "server.py")
    s = eb.status(tmp_path, "US")
    assert s["status"] == "NO_RECORD" and s["left"] == 240 and "rules_book" not in json.dumps(s)             # nothing of the book's value before the reading
    rows = {r["key"]: r for r in rd.status(tmp_path, __import__("datetime").date(2026, 11, 25))["readings"]}
    assert rows["EN-1_US"]["state"] == "WAITING" and rows["EN-1_KR"]["applies_itself"] is False
    doc = src("reports", "QSF_ENTRY_RULES_PROTOCOL.md")
    assert "EN-1" in doc and "아무것도 바꾸지 않는다" in doc and "2026-11-25" in doc
    # the real order plan never takes the rule: only the comparison book asks for it
    assert "breakout=" not in src("terminal", "services.py")
