"""The rank rules beside the paper book (RK-1) and the reading that decides on them (reports/QSF_RANK_RULES_PROTOCOL.md).  All offline."""
import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from terminal.qsf import holding, kr_forward as kf, order_plan as op, paper_book as pb, rank_book as rk, turnover_book as tb
from tests.test_earnings_gap import daily
from tests.test_order_plan_paper_book import FakeLedger, account, calendar, cand, filler, held, loader_of, snap
from tests.test_qsf import GOOD_FUND, run

ROOT = Path(__file__).resolve().parents[1]
RULES = dict(rk.RULES)
AT = datetime(2027, 12, 1, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def no_switch(monkeypatch):
    monkeypatch.delenv(rk.ENV, raising=False)
    monkeypatch.delenv(tb.ENV, raising=False)


def crowd(session, n, strategy="SWING", score=90.0):
    """``n`` higher-scored stocks that are not enterable: they only push the others down the ranking."""
    return [snap(f"H{k:03d}", strategy, score=score, session=session, entry="WAIT_FOR_PULLBACK") for k in range(n)]


# ---------------------------------------------------------------------- the rank itself
def test_the_share_ahead_counts_higher_scores_of_the_same_strategy_and_ties_share_a_rank():
    snaps = [snap("A", score=90), snap("B", score=80), snap("C", score=80), snap("D", score=10), snap("A", "LONG_TERM", score=5), snap("E", "LONG_TERM", score=50),
             snap("OLD", score=99, session="2026-11-11"), {**snap("NONE"), "score": None}]
    got = op.ahead_share(snaps, "2026-11-12")
    assert got == {("A", "SWING"): 0.0, ("B", "SWING"): 0.25, ("C", "SWING"): 0.25, ("D", "SWING"): 0.75, ("A", "LONG_TERM"): 0.5, ("E", "LONG_TERM"): 0.0}
    cands = [cand("A"), cand("B"), cand("D"), cand("A", "LONG"), cand("ZZZ")]
    assert op.outside_top(cands, got, 0.25) == {("B", "SWING"), ("D", "SWING"), ("A", "LONG"), ("ZZZ", "SWING")}      # 0.25 is not inside the top 25%; an unknown rank is outside


def test_the_plan_skips_a_candidate_outside_the_entry_share_and_says_why():
    got = op.build([cand("A", score=70), cand("B")], account(), "KR", outside={("A", "SWING")})
    assert [o["ticker"] for o in got["orders"]] == ["B"] and got["skipped"][0]["code"] == "RANK_OUT" and "순위" in got["skipped"][0]["reason"]
    assert [o["ticker"] for o in op.build([cand("A", score=70), cand("B")], account(), "KR", outside={("A", "LONG")})["orders"]] == ["A", "B"]      # by style, not by ticker


# ---------------------------------------------------------------------- E: entry only inside the top share
def test_an_entry_candidate_outside_the_top_fifth_gets_no_order():
    days = calendar(1)
    bars = pb.Bars(loader_of({"A": [(days[0], 10_000, 10_000)]}))
    a = [snap("A", price=10_000.0, atr=200.0, session=days[0], adv=1e11)]              # score 60 over 210 fillers at 30
    inside = filler(days[0]) + crowd(days[0], 40) + a                                  # 40 of 251 ahead: 15.9%
    outside = filler(days[0]) + crowd(days[0], 60) + a                                 # 60 of 271 ahead: 22.1%
    assert [o["ticker"] for o in pb.step(None, days[0], "KR", bars, outside)["plan"]["orders"]] == ["A"]               # the paper book takes it either way
    got = pb.step(None, days[0], "KR", bars, inside, rules=RULES, version=rk.VERSION)
    assert [o["ticker"] for o in got["plan"]["orders"]] == ["A"] and got["rule_events"] == [] and got["rules"] == "RK-1" and "cooldown" not in got["state"]
    out = pb.step(None, days[0], "KR", bars, outside, rules=RULES)
    assert out["plan"]["orders"] == [] and out["plan"]["skipped_counts"] == {"RANK_OUT": 1} and out["rule_events"] == [{"rule": "RANK_ENTRY", "ticker": "A", "style": "SWING", "score": 60.0}]


# ---------------------------------------------------------------------- X: a long position leaves when its rank falls out of the top half
def long_day(days, score, ahead, total=10):
    """A's long score among ``total`` long scores, ``ahead`` of them higher."""
    others = [snap(f"L{k}", "LONG_TERM", score=95.0 if k < ahead else 5.0, session=days[1], entry="WAIT_FOR_EARNINGS") for k in range(total - 1)]
    return others + [snap("A", "LONG_TERM", score=score, price=10_100.0, atr=200.0, session=days[1], entry="WAIT_FOR_EARNINGS")]


def test_a_long_position_is_sold_when_half_the_scored_stocks_are_ahead_of_it():
    days = calendar(2)
    bars = pb.Bars(loader_of({"A": [(days[0], 10_000, 10_000), (days[1], 10_000, 10_100)]}))
    start = lambda: held(days, "LONG", target=None)                                    # noqa: E731
    doc = pb.step(start(), days[1], "KR", bars, long_day(days, 60.0, ahead=5), rules=RULES)
    assert doc["decisions"] == [{"ticker": "A", "reason": "RANK"}] and doc["rule_events"] == [{"rule": "RANK_EXIT", "ticker": "A", "ahead_pct": 50.0, "score": 60.0}]
    assert pb.step(start(), days[1], "KR", bars, long_day(days, 60.0, ahead=4), rules=RULES)["decisions"] == []            # 40% ahead: still inside the top half
    assert pb.step(start(), days[1], "KR", bars, long_day(days, 60.0, ahead=5))["decisions"] == []                         # the paper book: 60 is not under 40
    assert pb.step(start(), days[1], "KR", bars, long_day(days, 30.0, ahead=4))["decisions"] == [{"ticker": "A", "reason": "SCORE"}]
    assert pb.step(start(), days[1], "KR", bars, long_day(days, 30.0, ahead=4), rules=RULES)["decisions"] == []            # the rank rule replaces the under-40 rule
    assert pb.step(start(), days[1], "KR", bars, None, rules=RULES)["decisions"] == []                                     # no long score that day: not judged
    swing = pb.step(held(days), days[1], "KR", bars, long_day(days, 1.0, ahead=9), rules=RULES)
    assert swing["decisions"] == [] and swing["rule_events"] == []                                                          # a swing position is not read by the long rank
    nxt = pb.step(doc["state"], calendar(3)[2], "KR", pb.Bars(loader_of({"A": [(days[1], 10_000, 10_100), (calendar(3)[2], 10_050, 10_050)]})), None, rules=RULES)
    assert nxt["exits"][0]["reason"] == "RANK" and nxt["exits"][0]["label"] == pb.EXIT_LABELS["RANK"]


def test_each_rule_set_acts_only_through_its_own_keys():
    days = calendar(2)
    bars = pb.Bars(loader_of({"A": [(days[0], 10_000, 10_000), (days[1], 10_000, 10_100)]}))
    both = {**tb.RULES, **RULES}
    kept = pb.step(held(days, sessions=pb.SWING_TIME_STOP - 1), days[1], "KR", bars, [snap("A", score=70.0, price=10_100.0, atr=200.0, session=days[1], entry="WAIT_FOR_PULLBACK")], rules=both)
    assert kept["exits"] == [] and kept["rule_events"][0]["rule"] == "HOLD_EXTENDED" and kept["state"]["cooldown"] == {}
    rank_only = pb.step(held(days, sessions=pb.SWING_TIME_STOP - 1), days[1], "KR", bars, [snap("A", score=70.0, price=10_100.0, atr=200.0, session=days[1], entry="WAIT_FOR_PULLBACK")], rules=RULES)
    assert rank_only["exits"][0]["reason"] == "TIME" and "cooldown" not in rank_only["state"]              # the rank rules alone do not extend a swing or start a wait


# ---------------------------------------------------------------------- the daily record
def books(tmp_path, monkeypatch, n=7, read_at=5):
    """A paper book from 2026-11-12 through ``n`` sessions.  A is enterable every day but 60 stocks score higher from the third
    session on: the paper book buys it on the first plan and keeps it; nothing else happens."""
    monkeypatch.setattr(pb, "Ledger", FakeLedger)
    monkeypatch.setattr(rk, "READ_AT", read_at)
    days = calendar(n)
    FakeLedger.days = days
    FakeLedger.extra = {d: [snap("B", price=5_000.0, atr=100.0, session=d, adv=1e11, score=58.0)] + (crowd(d, 60) if k >= 2 else []) for k, d in enumerate(days)}
    FakeLedger.extra[days[0]] = []
    series = {"005930": [(d, 100, 100) for d in days], "B": [(d, 5_000, 5_000 + 5 * k) for k, d in enumerate(days)]}
    load = loader_of(series)
    assert pb.record(tmp_path, "KR", load, now=lambda: AT)["status"] == "OK"
    return days, load


def test_the_comparison_book_forks_from_the_paper_book_and_parts_where_the_rank_rule_acts(tmp_path, monkeypatch):
    days, load = books(tmp_path, monkeypatch)
    assert days[2] == rk.FIRST == tb.FIRST
    got = rk.record(tmp_path, "KR", load, now=lambda: AT)
    assert got["status"] == "OK" and got["written"] == days[2:] and kf.verify(tmp_path, rk.FOLDERS["KR"])["status"] == "OK"
    b = {d: kf._read_day(tmp_path / pb.FOLDERS["KR"], d) for d in days}
    r = {d: kf._read_day(tmp_path / rk.FOLDERS["KR"], d) for d in days[2:]}
    assert [o["ticker"] for o in b[days[1]]["plan"]["orders"]] == ["B"] and b[days[2]]["fills"][0]["ticker"] == "B" and r[days[2]]["fills"][0]["ticker"] == "B"      # the order planned before the fork fills in both
    assert r[days[2]]["rules"] == "RK-1" and r[days[2]]["equity"] == b[days[2]]["equity"] and "B" in r[days[-1]]["state"]["positions"]
    monkeypatch.setenv(tb.ENV, "on")                                # the paper book under the turnover rules: this book follows it
    days2, load2 = books(tmp_path, monkeypatch, n=8)
    rk.record(tmp_path, "KR", load2, now=lambda: AT)
    last = kf._read_day(tmp_path / rk.FOLDERS["KR"], days2[-1])
    assert last["state"]["cooldown"] == {} and "cooldown" not in r[days[-1]]["state"]


def test_the_paper_book_runs_under_whatever_rule_sets_are_in_force(tmp_path, monkeypatch):
    assert rk.paper_rules(tmp_path, "US") == (None, None)
    monkeypatch.setenv(tb.ENV, "on")
    assert rk.paper_rules(tmp_path, "US") == (tb.RULES, "PB-3")
    monkeypatch.setenv(rk.ENV, "on")
    assert rk.paper_rules(tmp_path, "US") == ({**tb.RULES, **rk.RULES}, "PB-5")
    monkeypatch.setenv(tb.ENV, "off")
    assert rk.paper_rules(tmp_path, "US") == (rk.RULES, "PB-4") and rk.status(tmp_path, "US")["paper_version"] == "PB-4"
    monkeypatch.setenv(rk.ENV, "auto")
    assert rk.active_rules(tmp_path, "US") is None
    p = tmp_path / rk.REPORTS["US"]
    p.parent.mkdir(parents=True)
    p.write_text(json.dumps({"status": "REAL", "decision": "ADOPT"}), encoding="utf-8")
    assert rk.active_rules(tmp_path, "US") == rk.RULES and rk.active_rules(tmp_path, "KR") is None
    p.write_text(json.dumps({"status": "REAL", "decision": "KEEP"}), encoding="utf-8")
    assert rk.active_rules(tmp_path, "US") is None


# ---------------------------------------------------------------------- the decision and the reading
@pytest.mark.parametrize("mean, t, decision, evidence, words", [
    (0.0004, 2.0, "ADOPT", "DISTINCT", "순위 규칙을 적용합니다"),
    (0.0004, 1.99, "KEEP", "NOT_DISTINCT", "낫다는 근거가 없었다는 뜻"),
    (0.0, None, "KEEP", "NOT_DISTINCT", "계산할 수 없음"),
    (-0.0004, -2.6, "KEEP", "DISTINCT", "순위 규칙 쪽이 낮아"),
    (-0.0001, -0.3, "KEEP", "NOT_DISTINCT", "구분되지 않아"),
])
def test_the_rank_rules_are_adopted_only_on_a_distinct_positive_difference(mean, t, decision, evidence, words):
    fig = {"cost_pct": 1.0, "return_pct": 3.0, "max_drawdown_pct": -5.0}
    got = rk.decide(fig, fig, mean, t)
    assert got["decision"] == decision and got["evidence"] == evidence and words in " ".join(got["why"]) and len(got["why"]) == 4 and f"{mean * 1e4:+.2f}bp" in got["why"][0]


def test_the_reading_is_made_once_by_the_daily_job_and_ends_the_record(tmp_path, monkeypatch):
    days, load = books(tmp_path, monkeypatch, n=6)
    rk.record(tmp_path, "KR", load, now=lambda: AT)
    d, sent, _ = daily(tmp_path, AT)
    assert d._rank_reading({}) == {} and not sent and rk.read_when_due(tmp_path, "KR") is None
    seen = rk.status(tmp_path, "KR")
    assert seen["status"] == "RECORDING" and seen["records"] == 4 and seen["left"] == 1 and "decision" not in seen and "paper_book" not in seen and "equity" not in json.dumps(seen)
    days, load = books(tmp_path, monkeypatch, n=7)
    rk.record(tmp_path, "KR", load, now=lambda: AT)
    got = d._rank_reading(st := {})
    rep = json.loads((tmp_path / rk.REPORTS["KR"]).read_text(encoding="utf-8"))
    assert got["KR"]["delivered"] is True and st["rank_reading"] == got and len(sent) == 1 and "[순위 규칙 판정 · 한국] 결정:" in sent[0] and "QSF_RANK_RULES" in sent[0]
    assert rep["decision"] == "KEEP" and rep["difference"]["days"] == 5 and rep["first"] == days[2] and rep["seed_session"] == days[1] and rep["rule_counts"] == {"RANK_ENTRY": 0, "RANK_EXIT": 0}
    assert d._rank_reading(st)["KR"]["delivered"] is True and len(sent) == 1
    with pytest.raises(RuntimeError, match="이미 읽었습니다"):
        rk.evaluate_once(tmp_path, "KR")
    assert rk.record(tmp_path, "KR", load, now=lambda: AT) == {"status": "DONE", "market": "KR", "written": []} and rk.status(tmp_path, "KR")["status"] == "DECIDED"
    assert "turnover_reading" not in st                                                 # each comparison keeps its own state


def test_a_broken_record_is_not_read(tmp_path, monkeypatch):
    days, load = books(tmp_path, monkeypatch, n=7)
    rk.record(tmp_path, "KR", load, now=lambda: AT)
    monkeypatch.setattr(kf, "verify", lambda base, store=None: {"status": "BROKEN"})
    got = rk.read_when_due(tmp_path, "KR")
    assert got["status"] == "NO_READING" and not (tmp_path / rk.REPORTS["KR"]).exists() and "읽지 못했습니다" in rk.text(got)


# ---------------------------------------------------------------------- the holding reading under the rules
def test_a_long_holding_outside_the_top_half_reads_as_reduce_only_under_the_rules():
    r, c = run("LONG_TERM", fund=GOOD_FUND)
    pos, today = {"opened": "2026-01-05"}, date(2026, 11, 5)
    plain = holding.evaluate_exit(r, c, {**pos, "ahead_share": 0.9}, today)
    assert "RANK_OUT" not in [h["code"] for h in plain["conditions"]]
    out = holding.evaluate_exit(r, c, {**pos, "rank_rules": rk.RULES, "ahead_share": 0.62}, today)
    hit = next(h for h in out["conditions"] if h["code"] == "RANK_OUT")
    assert hit["action"] == "REDUCE" and "상위 62% 지점" in hit["text"] and "상위 50%" in hit["text"] and out["action"] in ("REDUCE", "THESIS_INVALIDATED", "EXIT")
    for share in (0.49, None):
        assert "RANK_OUT" not in [h["code"] for h in holding.evaluate_exit(r, c, {**pos, "rank_rules": rk.RULES, "ahead_share": share}, today)["conditions"]]


# ---------------------------------------------------------------------- wiring
def test_the_rank_comparison_is_recorded_backed_up_shown_and_read_without_a_person():
    from terminal import automation
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    assert app.count("_rank_book_record(market, q, info, bench)") == 1 and app.index('res["turnover_book"] = ') < app.index('res["rank_book"] = ') and '"rank-book-status": _qsf_turnover_book' in app
    assert {"rank_book_kr", "rank_book_us"} <= set(automation.FORWARD_STORES) and sum("rank_book_" in g for g in automation.BACKUP_GLOBS) == 2 and "reports/qsf/QSF_RANK_RULES_*.json" in automation.BACKUP_GLOBS
    job = (ROOT / "terminal" / "automation.py").read_text(encoding="utf-8")
    assert job.index("self._turnover_reading(st)\n") < job.index("self._rank_reading(st)\n") < job.index("alerts = self._alerts()")
    assert '("GET", "/api/qsf/rank-book")' in (ROOT / "terminal" / "server.py").read_text(encoding="utf-8")
    js = (ROOT / "terminal" / "static" / "qsf.js").read_text(encoding="utf-8")
    assert "/api/qsf/rank-book?market=" in js and "순위 규칙 비교" in js and "QSF_RANK_RULES" in js and "상위 ${r.pct}%" in js
    plan = (ROOT / rk.PROTOCOL).read_text(encoding="utf-8")
    for words in ("상위 20% 안", "상위 50% 밖", "240개", "t가 2.0 이상", "`ADOPT`", "`KEEP`", "PB-4", "PB-5", "QSF_RANK_RULES", "2026-11-16 거래일"):
        assert words in plan
    assert rk.RULES == {"entry_top": 0.2, "long_exit_top": 0.5} and rk.READ_AT == 240 and rk.LAG == 20 and rk.MIN_T == 2.0 and rk.FIRST == "2026-11-16"
