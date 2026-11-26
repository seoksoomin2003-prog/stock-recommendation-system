"""What each verdict does, written before the first outcome of the sample matured (user decisions 2026-11-25,
reports/QSF_AFTER_VERDICT_RULES_2026_11_25.md): continuation readings of the swing verdict, the verdict report's fixed extras
(three-part money split, prices alone, median spread, one reference line), fewer notices and no "이 규칙 쓰기" buttons."""
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest

from terminal.qsf import calibrate, config, fund_period, live_forward as lf, rank_book, readings as rd, turnover_book
from tests.test_readings import fill, job

ROOT = Path(__file__).resolve().parents[1]
N = 40


def calendar(n, start=date(2026, 11, 25)):
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


CAL = calendar(540)


def bars_of(k, strength, dividend=0.0):
    """Stock k drifts with its rank.  ``dividend``: a daily amount paid out, in the adjusted close only (the price stays put)."""
    px, paid, out = 100.0, 1.0, []
    for n, d in enumerate(CAL):
        o = px
        px = px * (1 + strength * (k - N / 2) / N + 0.004 * np.sin(0.7 * n + k))
        paid *= 1 + dividend
        out.append({"date": d, "open": o, "high": max(o, px), "low": min(o, px), "close": px, "adj_close": px * paid, "volume": 1000})
    return out


def loader(strength=0.001, dividend=0.0):
    books = {f"T{k:02d}": bars_of(k, strength, dividend) for k in range(N)}
    return lambda t: books.get(t) or []


def never(_ticker):
    raise AssertionError("a reading that must not read a price asked for one")


def bench(n=len(CAL)):
    return [{"date": d, "open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0, "adj_close": 100.0, "volume": 1} for d in CAL[:n]]


def factors(k):
    """The live score's rows for stock k: momentum follows the rank; the risk/reward factor is the same for nearly everyone."""
    return [{"factor": "trend", "domain": "TECHNICAL", "weight": 10, "status": "REAL", "normalized": k / N},
            {"factor": "risk_reward", "domain": "RISK", "weight": 6, "status": "REAL", "normalized": 0.9 if k < 4 else 0.0},
            {"factor": "old", "domain": "TECHNICAL", "weight": 5, "status": "REAL", "normalized": 1.0, "scored": False, "reference_weight": 5}]


class FakeLedger:
    days, versions = 540, ("QSF-1.6.0",)

    def __init__(self, root):
        pass

    def verify(self):
        return {"status": "OK"}

    def _live_rows(self):
        return [{"market": "US", "session": d} for d in CAL[:self.days]]

    def _load(self, r):
        i = CAL.index(r["session"])
        v = self.versions[min(len(self.versions) - 1, i * len(self.versions) // len(CAL))]
        return [{"market": "US", "ticker": f"T{k:02d}", "strategy": s, "score": 35.0 + k, "actionability": "ACTIONABLE", "data_date": r["session"],
                 "entry_session": CAL[min(i + 1, len(CAL) - 1)], "model_version": v, "factors": factors(k)} for k in range(N) for s in ("SWING", "LONG_TERM")]


@pytest.fixture
def led(monkeypatch):
    monkeypatch.setattr(lf, "Ledger", FakeLedger)
    monkeypatch.setattr(FakeLedger, "days", 540)
    monkeypatch.setattr(FakeLedger, "versions", ("QSF-1.6.0",))
    return FakeLedger


quiet = lambda *_: None      # noqa: E731


# ---------------------------------------------------------------------- the verdict report's fixed extras
def test_the_money_condition_is_given_in_three_parts_with_one_of_three_sentences(led, tmp_path):
    res = lf.evaluate_once(tmp_path, "US", "SWING", loader(), bench(), log=quiet)
    ms, cost = res["money_split"], config.round_trip_cost("US")
    assert res["verdict"] == "WEAK_POSITIVE_EVIDENCE" and ms["reading"] == "PASSED" and ms["says"] == lf.SPLIT_SAYS["PASSED"]
    for part in ("all", "early", "late"):
        p = ms[part]
        assert p["band_minus_index"] == pytest.approx(p["universe_before_cost"] - p["cost"] + p["score_effect"]) and p["cost"] == cost
    flat = lf.evaluate_once(tmp_path / "flat", "US", "SWING", loader(strength=0.0), bench(), log=quiet)
    assert flat["verdict"] == "NO_EVIDENCE" and flat["money_split"]["reading"] in ("SCORE_SIDE_POSITIVE", "SCORE_SIDE_NOT_POSITIVE") and set(lf.SPLIT_SAYS) == {"PASSED", "SCORE_SIDE_POSITIVE", "SCORE_SIDE_NOT_POSITIVE"}
    s = {"all": {"universe_effect": -0.004, "buy_minus_index": -0.001, "score_effect": 0.003, "buy_minus_index_price": -0.002},
         "early": {"universe_effect": -0.004, "buy_minus_index": -0.001, "score_effect": 0.002, "buy_minus_index_price": -0.002},
         "late": {"universe_effect": -0.004, "buy_minus_index": -0.001, "score_effect": 0.004, "buy_minus_index_price": -0.002}}
    got = lf.money_split(s, 0.004, False, False)
    assert got["reading"] == "SCORE_SIDE_POSITIVE" and "대상" in got["says"] and "알 수 없습니다" in got["says"] and got["all"]["universe_before_cost"] == pytest.approx(0.0)
    assert lf.money_split({**s, "late": {**s["late"], "score_effect": -0.001}}, 0.004, False, False)["reading"] == "SCORE_SIDE_NOT_POSITIVE"


def test_prices_alone_are_kept_beside_the_adjusted_comparison_and_never_decide(led, tmp_path):
    """Stocks that only pay a dividend beat a price index on adjusted closes and not on prices: the verdict reads the adjusted
    closes as registered, and the report says what prices alone give."""
    paid = lf.evaluate_once(tmp_path, "US", "SWING", loader(strength=0.0, dividend=0.0006), bench(), log=quiet)
    assert paid["condition_b"] is True and paid["money_split"]["condition_b_price_only"] is False and "배당" in paid["money_split"]["price_only_note"]
    assert paid["money_split"]["all"]["band_minus_index"] > 0 > paid["money_split"]["all"]["band_minus_index_price_only"]
    same = lf.evaluate_once(tmp_path / "same", "US", "SWING", loader(), bench(), log=quiet)                 # no dividend: the two agree
    assert same["money_split"]["all"]["band_minus_index_price_only"] == pytest.approx(same["money_split"]["all"]["band_minus_index"])


def test_the_median_spread_and_one_reference_line_are_figures_without_a_verdict(led, tmp_path):
    res = lf.evaluate_once(tmp_path, "US", "SWING", loader(), bench(), log=quiet)
    assert res["primary"]["all"]["spread_median"] > 0 and res["primary"]["early"]["spread_median"] is not None
    (ref,) = res["reference"]
    assert ref["variant"] == "손익비 요인을 뺀 점수" and ref["status"] == "REAL" and ref["dates"] == 240 and ref["ic"] > 0.5 and ref["spread_median"] is not None
    assert not {"t", "t_bar", "verdict", "passed"} & set(ref) and "통과도 탈락도 없" in ref["note"] and "공식을 바꾸지 않습니다" in ref["note"]
    one = lf.without_factor("risk_reward")([{"factors": factors(30)}, {"factors": factors(1)}, {"factors": []}])
    assert one[0] == pytest.approx(75.0) and one[1] == pytest.approx(2.5) and np.isnan(one[2])            # the reference-only row and the left-out factor do not count
    assert lf.variant_of("LONG_TERM", None) == ("업종 평균을 뺀 점수(달마다 보관한 업종 분류, 없는 달은 판정 날의 분류)", None)                # no sector lookup: the line says it is unavailable
    name, fn = lf.variant_of("LONG_TERM", lambda t, day=None: "A" if int(t[1:]) % 2 else "B")
    v = fn([{"ticker": f"T{k:02d}", "score": float(k)} for k in range(8)])
    assert "없는 달은 판정 날의 분류" in name and v[:4].tolist() == [-3.0, -3.0, -1.0, -1.0]                    # each score less its sector's mean that day
    assert lf.reference_line([{"variant": None}], "x")["status"] == "UNAVAILABLE"


# ---------------------------------------------------------------------- continuation readings
def test_a_continuation_reading_waits_for_the_ones_before_it_and_reads_the_same_record_longer(led, tmp_path):
    with pytest.raises(ValueError):
        lf.continue_once(tmp_path, "US", 500, loader(), bench())
    with pytest.raises(RuntimeError, match="순서대로"):
        lf.continue_once(tmp_path, "US", 480, never, bench())                                    # the verdict itself has not been read
    first = lf.evaluate_once(tmp_path, "US", "SWING", loader(strength=0.0), bench(), log=quiet)
    assert first["verdict"] == "NO_EVIDENCE"
    with pytest.raises(RuntimeError, match="순서대로"):
        lf.continue_once(tmp_path, "US", 720, never, bench())                                    # 480 comes first
    res = lf.continue_once(tmp_path, "US", 480, loader(strength=0.0), bench(), log=quiet)
    assert res["kind"] == "CONTINUATION" and res["sessions_used"] == 480 and res["first"] == CAL[0] and res["last"] == CAL[479] and res["horizon"] == 20
    assert res["verdict"] == "NO_EVIDENCE" and res["t_nominal"] == lf.CONTINUE_T == 2.64 and res["t_bar"] == calibrate.bar(2.64, 480, 20, 1, 20) > first["t_bar"]
    assert res["applies_itself"] is False and "공식을 바꿀 이유가 아닙니다" in res["reasons"][-1] and res["money_split"]["says"] in res["reasons"] and res["versions"] == ["QSF-1.6.0"]
    with pytest.raises(RuntimeError, match="한 번만"):
        lf.continue_once(tmp_path, "US", 480, loader(), bench())
    led.days = 600
    with pytest.raises(RuntimeError, match="아직 읽을 수 없습니다"):
        lf.continue_once(tmp_path, "US", 720, loader(), bench())                                 # 540 sessions on the calendar: not yet
    assert lf.CONTINUE == (480, 720, 960) and 3 * calibrate.tail(lf.CONTINUE_T) == pytest.approx(0.0125, abs=2e-4)      # three looks, one verdict's chance together


def test_a_passed_verdict_ends_the_readings_and_a_mixed_record_is_not_read(led, tmp_path):
    assert lf.evaluate_once(tmp_path, "US", "SWING", loader(), bench(), log=quiet)["verdict"] == "WEAK_POSITIVE_EVIDENCE"
    done = lf.continue_once(tmp_path, "US", 480, never, bench(), log=quiet)                      # no price is asked for
    assert done["verdict"] == "ALREADY_PASSED" and "sessions_used" not in done and lf.continue_path(tmp_path, "US", 480).exists()
    other = tmp_path / "mixed"
    assert lf.evaluate_once(other, "US", "SWING", loader(strength=0.0), bench(), log=quiet)["verdict"] == "NO_EVIDENCE"
    led.versions = ("QSF-1.6.0", "QSF-1.7.0")
    mixed = lf.continue_once(other, "US", 480, never, bench(), log=quiet)
    assert mixed["verdict"] == "MIXED_FORMULA" and mixed["versions"] == ["QSF-1.6.0", "QSF-1.7.0"] and "primary" not in mixed and "수익도 읽지 않았습니다" in mixed["reasons"][0]
    assert rd.VERDICT_KO["ALREADY_PASSED"] and rd.VERDICT_KO["MIXED_FORMULA"]


# ---------------------------------------------------------------------- notices and buttons
def test_fifteen_readings_tell_and_the_rest_are_filed_quietly(tmp_path):
    told = [e["key"] for e in rd.REGISTRY if e["notify"]]
    assert len(rd.REGISTRY) == 36 and len(told) == 15 and rd.BOOKS_NOTIFY is False
    assert sorted({k.rsplit("_", 1)[0] for k in told} | {k for k in told if k == "kr_avoid_marks"}) == sorted(
        ["live_swing", "live_long", "early_swing_60", "early_swing_120", "cont_swing_480", "cont_swing_720", "cont_swing_960", "kr_avoid_marks", "kr_avoid"])
    by = {e["key"]: e for e in rd.REGISTRY}
    c = by["cont_swing_720_kr"]
    assert c["argv"] == ["--market", "KR", "qsf", "live-forward-continue-720"] and rd.wanted(c) == 740 and c["ledger"] == "KR" and "매수 후보" in c["after"] and "97%" in by["early_swing_60_us"]["after"]
    assert rd.REFERENCE_NOTE not in rd.text(c, {"verdict": "NO_EVIDENCE"}) and rd.REFERENCE_NOTE in rd.text(by["kr_cap_universe"], {"universe": {"reading": "NOT_DISTINGUISHED"}})
    fill(tmp_path, "kr_cap_universe", 260)                                                         # an archived reading comes due
    d, calls, sent, shown = job(tmp_path, writes={"kr_cap_universe": {"universe": {"reading": "UNIVERSE_BETTER"}}})
    got = d._readings({})["kr_cap_universe"]
    assert calls == [("READING", ["qsf", "kr-cap-universe-evaluate"])] and sent == [] and shown == []       # read and filed, nobody told
    assert got["verdict"] == "UNIVERSE_BETTER" and got["delivered"] is True and got["quiet"] is True and rd.report(tmp_path, by["kr_cap_universe"])
    st = rd.status(tmp_path, date(2026, 11, 26))
    rows = {r["key"]: r for r in st["readings"]}
    assert st["total"] == 42 and st["notified"] == 15 and rows["kr_cap_universe"]["notify"] is False and rows["live_swing_kr"]["notify"] is True and rows["TO-1_KR"]["notify"] is False
    assert "파일로만 남깁니다" in st["note"] and "보관" in st["quiet_note"]


def test_the_three_buttons_do_not_switch_a_rule_on_and_can_still_switch_one_off(tmp_path):
    assert config.APPLY_BUTTONS is False
    for got in (turnover_book.set_switch(tmp_path, "US", True), rank_book.set_switch(tmp_path, "KR", True), fund_period.set_period(tmp_path, "US", "TRAILING")):
        assert got["status"] == "REFUSED" and got["reason"] == config.APPLY_REFUSED and "2026-11-25 결정" in got["reason"]
    assert turnover_book.set_switch(tmp_path, "US", False)["status"] == "OK" and fund_period.set_period(tmp_path, "US", "ANNUAL")["status"] == "OK"
    assert turnover_book.status(tmp_path, "US")["buttons"] is False and rank_book.status(tmp_path, "KR")["buttons"] is False
    assert fund_period.status(tmp_path)["markets"]["US"]["buttons"] is False and fund_period.status(tmp_path)["markets"]["US"]["can_switch"] is False
    js = (ROOT / "terminal" / "static" / "qsf.js").read_text(encoding="utf-8")
    assert js.count("tb.buttons === false && !tb.active") == 1 and js.count("rb.buttons === false && !rb.active") == 1 and "r.switch.buttons === false" in js and "보관 · 알림 없음" in js


def test_the_rules_are_written_down_and_wired():
    doc = (ROOT / "reports" / "QSF_AFTER_VERDICT_RULES_2026_11_25.md").read_text(encoding="utf-8")
    for needle in ("공식을 바꿀 이유가 아닙니다", "3.66 / 3.52 / 3.44", "넷으로 닫음", "새 표본으로 한 번 더 등록할 자격", "한 번에 최대 하나", "MIXED_FORMULA", "가설", "APPLY_BUTTONS = True",
                   "수익은 하나도 읽지 않았습니다", "condition_b_price_only", "97% 넘게"):
        assert needle in doc, needle
    assert [calibrate.bar(lf.CONTINUE_T, n, 20, 1, 20) for n in lf.CONTINUE] == [3.66, 3.52, 3.44]
    import app
    acts = {f"live-forward-continue-{n}" for n in lf.CONTINUE}
    assert acts <= set(app.QSF_ACTIONS) and acts <= set(app.QSF_LIVE_HANDLERS)
    src = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "sector_of=_dated_sector(q, market)" in src and "kept(t, day) or (q._sector_of(market, t) or {}).get(\"sector\")" in src
    live = (ROOT / "reports" / "QSF_LIVE_FORWARD_PROTOCOL.md").read_text(encoding="utf-8")
    assert "2026-11-25 덧붙임" in live and "QSF_AFTER_VERDICT_RULES_2026_11_25.md" in live and "배당" in live


# ---------------------------------------------------------------------- the word's return, from the reading's own files (audit P0, 2026-11-25)
def test_a_real_passed_verdict_earns_the_word_and_a_dividend_only_pass_does_not(led, tmp_path, monkeypatch):
    from terminal.qsf import wording
    monkeypatch.setattr(config, "MODEL_VERSION", "QSF-1.6.0")                       # the version the made-up ledger records
    res = lf.evaluate_once(tmp_path, "US", "SWING", loader(), bench(), log=quiet)
    assert res["verdict"] == "WEAK_POSITIVE_EVIDENCE" and wording.why_not(res, "US", "SWING") == [] and wording.earned(tmp_path, "US", "SWING")
    assert json.loads((tmp_path / wording.SEALS).read_text(encoding="utf-8")).keys() == {"QSF_LIVE_FORWARD_US_SWING.json"}       # sealed by the reading itself
    paid = tmp_path / "paid"
    got = lf.evaluate_once(paid, "US", "SWING", loader(strength=0.0, dividend=0.0006), bench(), log=quiet)
    assert got["condition_b"] is True and "MONEY_CHECKS" in wording.why_not(got, "US", "SWING") and not wording.earned(paid, "US", "SWING")
    flat = tmp_path / "flat"
    lf.evaluate_once(flat, "US", "SWING", loader(strength=0.0), bench(), log=quiet)
    cont = lf.continue_once(flat, "US", 480, loader(), bench(), log=quiet)          # the same record read longer, now with a real effect
    assert cont["verdict"] == "WEAK_POSITIVE_EVIDENCE" and wording.why_not(cont, "US", "SWING", 480) == [] and wording.earned(flat, "US", "SWING")
    monkeypatch.setattr(config, "MODEL_VERSION", "QSF-1.7.0")
    assert not wording.earned(tmp_path, "US", "SWING") and not wording.earned(flat, "US", "SWING")       # another formula in force: the word leaves


def test_candidate_one_has_a_written_meaning_of_not_worse(led, tmp_path):
    res = lf.evaluate_once(tmp_path, "US", "SWING", loader(), bench(), log=quiet)
    c = res["candidate_1"]
    assert c["live_ic"] == res["primary"]["ic"] and c["reference_ic"] == res["reference"][0]["ic"] and c["live_spread_median"] == res["primary"]["all"]["spread_median"]
    assert c["not_worse"] is (c["reference_ic"] >= c["live_ic"] and c["reference_spread_median"] >= c["live_spread_median"]) and "자격" in c["note"]
    assert lf.candidate_1({"ic": 0.05, "all": {"spread_median": 0.01}}, {"status": "REAL", "ic": 0.05, "spread_median": 0.01})["not_worse"] is True
    assert lf.candidate_1({"ic": 0.05, "all": {"spread_median": 0.01}}, {"status": "REAL", "ic": 0.06, "spread_median": 0.009})["not_worse"] is False      # both figures, not one
    assert lf.candidate_1({"ic": 0.05, "all": {"spread_median": 0.01}}, {"status": "UNAVAILABLE"})["not_worse"] is None                                  # unknown is not "worse" and not "not worse"
    doc = (ROOT / "reports" / "QSF_AFTER_VERDICT_RULES_2026_11_25.md").read_text(encoding="utf-8")
    assert "'나쁘지 않다'의 정의" in doc and "candidate_1.not_worse" in doc and "둘 다" in doc and "수익 쪽 세 가지 확인" in doc
    from terminal import analyst_extra as ax
    line = ax.tilt_line({"top_n": 10, "vol_top": 0.2, "vol_all": 0.3, "near_high_top": 0.5, "near_high_all": 0.2})
    assert "덜 흔들렸지만" not in line and line.endswith("높은 점수가 더 오른다는 근거는 아직 확인되지 않았습니다.")       # no hypothesis cited before a reading is registered


# ---------------------------------------------------------------------- roadmap P3 (user decisions 2026-11-25)
def test_the_verdict_report_says_how_far_the_pay_off_carries_from_one_block_to_the_next(led, tmp_path):
    res = lf.evaluate_once(tmp_path, "US", "SWING", loader(), bench(), log=quiet)
    p = res["persistence"]
    assert p["status"] == "REAL" and p["blocks"] == 12 and p["block_sessions"] == 20 and -1.0 <= p["lag1"] <= 1.0 and p["rough_by"] == pytest.approx(1 / 12 ** 0.5)
    assert "바꾸지 않습니다" in p["note"] and "12개" in p["says"]
    days = lambda ics: [{"ic": v} for v in ics for _ in range(20)]                   # noqa: E731
    up = lf.persistence(days([0.10, 0.09, 0.08, 0.07, 0.06, 0.05, 0.04, 0.03, 0.02, 0.01]), 20)       # a slow drift: neighbours alike
    assert up["lag1"] > 0.26 and up["false_pass_pct_about"] > 5.4 and up["false_pass_pct_if_slow"] > up["false_pass_pct_about"] and "느린 쏠림" in up["says"]      # table extended and a slow-drift figure added 2026-11-26
    flip = lf.persistence(days([0.05, -0.05] * 5), 20)                               # neighbours opposite
    assert flip["lag1"] < 0 and flip["false_pass_pct_about"] == 1.25 and "1.25%쯤" in flip["says"]
    assert lf.persistence(days([0.05] * 5), 20)["status"] == "UNAVAILABLE" and lf.persistence(days([0.05] * 12), 20)["status"] == "UNAVAILABLE"      # too few blocks, or no variation: no figure
    assert lf.PERSIST_POINTS[0] == (0.0, 1.25) and [round(float(np.interp(r, *zip(*lf.PERSIST_POINTS))), 2) for r in (0.09, 0.135)] == [2.5, 3.2]
    flat = tmp_path / "flat"
    lf.evaluate_once(flat, "US", "SWING", loader(strength=0.0), bench(), log=quiet)
    assert lf.continue_once(flat, "US", 480, loader(strength=0.0), bench(), log=quiet)["persistence"]["blocks"] == 24


def test_sectors_are_kept_once_a_month_and_the_verdict_asks_the_dated_copy_first(tmp_path):
    from terminal.qsf import sector_archive as sa
    now = datetime(2026, 11, 26, 0, 30, tzinfo=timezone.utc)
    scan = lambda m: {"session": "2026-11-25", "rows": [{"ticker": f"T{k:03d}", "strategy": s, "sector": "기술" if k % 2 else "금융", "industry": "x"} for k in range(60) for s in ("SWING", "LONG_TERM")]}      # noqa: E731
    assert sa.save_when_due(tmp_path, now, scan) == {"US": "WRITTEN", "KR": "WRITTEN"}
    doc = json.loads(sa.path(tmp_path, "US", "2026-11").read_text(encoding="utf-8"))
    assert doc["stocks"] == 60 and doc["session"] == "2026-11-25" and doc["sectors"]["T001"] == {"sector": "기술", "industry": "x"}
    later = lambda m: {"rows": [{"ticker": f"T{k:03d}", "sector": "에너지"} for k in range(60)]}          # noqa: E731
    assert sa.save_when_due(tmp_path, now + timedelta(days=3), later) == {"US": "KEPT", "KR": "KEPT"}      # the month's file is written once and never rewritten
    assert sa.save_when_due(tmp_path, datetime(2026, 12, 2, tzinfo=timezone.utc), later)["US"] == "WRITTEN" and sa.months(tmp_path, "US") == ["2026-11", "2026-12"]
    few = lambda m: {"rows": [{"ticker": "A", "sector": "x"}]}                                            # noqa: E731
    assert sa.save_when_due(tmp_path, datetime(2027, 1, 4, tzinfo=timezone.utc), few) == {"US": "TOO_FEW", "KR": "TOO_FEW"} and "2027-01" not in sa.months(tmp_path, "US")

    def broken(m):
        raise OSError("disk")
    assert sa.save_when_due(tmp_path, datetime(2027, 2, 1, tzinfo=timezone.utc), broken) == {"US": "OSError", "KR": "OSError"}      # never stops the caller
    sector = sa.lookup(tmp_path, "US")
    assert sector("T001", "2026-11-30") == "기술" and sector("T001", "2026-12-15") == "에너지" and sector("T001", "2027-06-01") == "에너지"      # the newest copy at or before the day
    assert sector("T001", "2026-10-30") is None and sector("NOPE", "2026-12-15") is None and sa.lookup(tmp_path / "none", "US")("T001", "2026-12-01") is None
    name, fn = lf.variant_of("LONG_TERM", lambda t, day=None: sector(t, day) or "판정 날 분류")
    v = fn([{"ticker": f"T{k:03d}", "score": float(k), "data_date": "2026-11-27"} for k in range(8)])
    assert "달마다 보관한 업종 분류" in name and v[:4].tolist() == [-3.0, -3.0, -1.0, -1.0]             # the dated sectors: even and odd tickers apart
    auto = (ROOT / "terminal" / "automation.py").read_text(encoding="utf-8")
    assert "self._sector_archive(st)" in auto and '"data/qsf/sector_archive/*.json"' in auto and "def _sector_archive(self, st" in auto
    code = (ROOT / "terminal" / "qsf" / "sector_archive.py").read_text(encoding="utf-8")
    assert "ledger" not in code.replace("The ledger keeps no sector", "") and "outcome" not in code and "yahoo" not in code.lower()       # an input kept as it was: no record, no return, no network
