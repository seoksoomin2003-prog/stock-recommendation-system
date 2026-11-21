"""What the assistant adds beside a score (terminal/analyst_extra.py): exposure, the candidates as a group, avoid marks on liked
stocks, what changed since earlier records, and the age of the statements.  Made-up prices and records, no network."""
import json
from pathlib import Path

import numpy as np
import pytest

from terminal import analyst_extra as ax, assistant as A

ROOT = Path(__file__).resolve().parents[1]
DAYS = [f"2026-{1 + k // 28:02d}-{1 + k % 28:02d}" for k in range(200)]


def bars(returns, start=100.0, level=False):
    """Daily bars from a list of moves: returns of a price, or with ``level`` the changes of a yield in percentage points."""
    out, px = [{"date": DAYS[0], "close": start}], start
    for d, r in zip(DAYS[1:], returns):
        px = px + r if level else px * (1 + r)
        out.append({"date": d, "close": px})
    return out


RNG = np.random.default_rng(3)
MARKET = RNG.normal(0, 0.01, 199)
THEME_OWN = RNG.normal(0, 0.01, 199)
RATE = RNG.normal(0, 0.03, 199)
NOISE = RNG.normal(0, 0.001, 199)
DATA = {"SPY": bars(MARKET), "SOXX": bars(1.2 * MARKET + THEME_OWN), "^TNX": bars(RATE, start=4.0, level=True)}


def test_exposure_separates_the_market_from_what_is_left_over():
    e = ax.exposure(bars(1.5 * MARKET + 0.8 * THEME_OWN - 0.05 * RATE + NOISE), DATA, "US")
    theme, rate = e["others"]
    assert e["days"] == 120 and e["beta"] == pytest.approx(1.5, abs=0.25) and theme["coef"] == pytest.approx(0.8, abs=0.05) and theme["partial_corr"] > 0.9
    assert rate["kind"] == "YIELD" and rate["coef"] == pytest.approx(-0.05, abs=0.01) and rate["partial_corr"] < -0.15
    lines = ax.exposure_lines(e)
    assert lines[0].startswith("시장 베타 1.") and "S&P 500 지수가 1% 움직인 날" in lines[0] and "시장보다 1% 더 오른 날 이 종목은 시장 대비 평균 +0.8" in lines[1]
    assert "금리가 0.10%p 오른 날 시장 대비 평균 -0.5" in lines[2] and "원인이 아니고" in lines[-1] and "120거래일" in lines[-1]
    plain = ax.exposure(bars(0.9 * MARKET + NOISE), DATA, "US")
    assert all(abs(o["partial_corr"]) < ax.CLEAR for o in plain["others"]) and "뚜렷한 관계가 없습니다" in ax.exposure_lines(plain)[1]
    assert ax.exposure(bars(MARKET[:30]), DATA, "US") is None and "60거래일" in ax.exposure_lines(None)[0]
    assert ax.exposure(bars(MARKET), {"SPY": DATA["SPY"]}, "US")["others"] == []                       # a reference series that did not arrive is left out, not guessed


def test_candidates_of_one_sector_that_move_together_are_said_to_be_one_bet():
    series = {f"T{k}": bars(0.5 * MARKET + 0.6 * THEME_OWN + RNG.normal(0, 0.002, 199)) for k in range(6)}
    sector = {"T0": "보험", "T1": "보험", "T2": "보험", "T3": "헬스케어", "T4": "헬스케어", "T5": None}
    c = ax.concentration(list(series), sector.get, series.get, DATA["SPY"])
    assert c["n"] == 6 and c["sectors"][0] == ("보험", 3) and c["measured"] == 6 and c["mean_corr"] > 0.8 and c["mean_beta"] == pytest.approx(0.5, abs=0.2)
    line = ax.concentration_line(c)
    assert "매수 구간 후보 6개의 업종: 보험 3, 헬스케어 2, 분류 없음 1." in line and "보험 한 업종이 50%" in line and "서로 같이 움직이는 편" in line and "방어주 쪽" in line and "6개로 나뉜 분산이 아닙니다" in line
    spread = {f"U{k}": bars(RNG.normal(0, 0.01, 199) + 1.1 * MARKET * (k % 2)) for k in range(8)}
    wide = ax.concentration(list(spread), {f"U{k}": f"업종{k}" for k in range(8)}.get, spread.get, DATA["SPY"])
    assert wide["mean_corr"] < ax.ALIKE and "분산이 아닙니다" not in ax.concentration_line({**wide, "mean_beta": 1.0})
    assert ax.concentration_line(ax.concentration(["T0", "T1"], sector.get, series.get, DATA["SPY"])) is None            # two stocks are not a group
    short = ax.concentration(list(series), sector.get, lambda t: [], DATA["SPY"])
    assert short["mean_corr"] is None and "평균 상관" not in ax.concentration_line(short)                                 # no prices: the sectors are still said


def test_marks_are_listed_for_stocks_the_score_likes_and_for_ones_own():
    rows = [{"ticker": "A", "name": "가", "strategy": "SWING", "score": 72.0, "filing_events": {"financing": True}}, {"ticker": "B", "name": "나", "strategy": "SWING", "score": 40.0, "high_risk": {"session": "x"}},
            {"ticker": "C", "name": "다", "strategy": "SWING", "score": 80.0}, {"ticker": "A", "name": "가", "strategy": "LONG_TERM", "score": 90.0, "filing_events": {"financing": True}},
            {"ticker": "D", "name": "라", "strategy": "SWING", "score": 55.0, "high_risk": {"session": "x"}, "filing_events": {"financing": True}}]
    got = ax.liked_but_marked(rows, ["B", "C"])
    assert [r["ticker"] for r in got["liked"]] == ["A", "D"] and got["liked"][1]["marks"] == ["자금 조달 공시", "고위험"] and [r["ticker"] for r in got["mine"]] == ["B"]
    items = A.marked_items(rows, ["B", "C"], "KR")
    assert [(i["level"], i["kind"]) for i in items] == [("DUE", "AVOID_MINE"), ("INFO", "AVOID_LIKED")] and "나(B, 고위험)" in items[0]["text"] and "가(72점, 자금 조달 공시)" in items[1]["text"]
    assert "근거가 나온 쪽은 점수가 아니라 이 표시" in items[1]["text"] and "시험한 적이 없습니다" in A.marked_items(rows, [], "US")[0]["text"] and A.marked_items([rows[2]], ["C"], "KR") == []


class Side:
    """A ledger with one shard per session and the light side fields only."""
    def __init__(self, scores, versions=None):
        self.scores, self.versions = scores, versions or {}

    def _rows(self):
        return [{"market": "US", "session": d, "file": d} for d in self.scores] + [{"market": "KR", "session": "2026-01-01", "file": "kr"}]

    def side(self, row):
        if row["market"] != "US":
            return {}
        score, tech, risk, band = self.scores[row["session"]]
        return {"AAA": {"SWING": {"score": score, "band": band, "data_date": row["session"], "model_version": self.versions.get(row["session"], "QSF-1.4.1"),
                                  "domains": {"TECHNICAL": {"score_100": tech}, "RISK": {"score_100": risk}, "REGIME": {"score_100": 10.0 * len(row["session"])}}}}}


def test_what_changed_is_read_from_the_records_of_a_week_and_a_month_ago():
    days = [f"2026-10-{d:02d}" for d in range(1, 31)]
    led = Side({d: (50.0 + k, 40.0 + 2 * k, 70.0 - k / 10, "WEAK_REDUCE" if k < 20 else "HOLD_WATCH") for k, d in enumerate(days)}, {days[8]: "QSF-1.4.0"})
    week, month = ax.change_since(led, "US", "AAA", "SWING")
    assert week["session"] == days[-6] and week["diff"] == pytest.approx(5.0) and week["domains"]["TECHNICAL"] == pytest.approx(10.0) and month["session"] == days[-22] and month["diff"] == pytest.approx(21.0)
    lines = ax.change_lines([week, month], {"WEAK_REDUCE": "약세·축소 후보", "HOLD_WATCH": "보유·관찰"}.get)
    assert lines[0] == f"1주 전({days[-6]}) 기록 대비: 점수 74.0 → 79.0(+5.0). 영역 점수 변화: 기술 +10."
    assert "1개월 전" in lines[1] and "기술 +42" in lines[1] and "구간이 '약세·축소 후보'에서 '보유·관찰'(으)로 바뀌었습니다" in lines[1] and "QSF-1.4.0 → QSF-1.4.1" in lines[1] and "시장 국면" not in lines[1]
    assert ax.change_since(Side({d: (50.0, 40.0, 70.0, "X") for d in days[:4]}), "US", "AAA", "SWING") == [] and ax.change_since(led, "US", "ZZZ", "SWING") == [] and ax.change_since(led, "JP", "AAA", "SWING") == []
    still = ax.change_lines(ax.change_since(Side({d: (50.0, 40.0, 70.0, "HOLD_WATCH") for d in days}), "US", "AAA", "SWING"))
    assert still[0].endswith("점수 50.0 → 50.0(+0.0). 영역 점수는 3점 넘게 움직인 곳이 없습니다.")


def test_the_age_of_the_statements_and_the_score_fresher_ones_would_give():
    snap = {"fund_period": {"live": "ANNUAL", "annual": {"score": 64.2, "fiscal_end": "2025-12-31", "filed": "2026-03-10"}, "trailing": {"score": 85.0, "fiscal_end": "2026-09-30", "newer_quarter": True}}}
    a, b = ax.fund_age_lines(snap, "2026-11-23")
    assert a == "점수가 읽은 재무: 2025-12-31까지(연간 보고서, 기준일에서 327일 지남, 보고서 제출 2026-03-10). 오래된 자료입니다."
    assert "최근 4분기 재무(2026-09-30까지)로 계산하면 85.0점으로, 지금 점수보다 20.8점 높습니다" in b and "라이브에 쓰지 않습니다" in b and "240거래일" in b
    same = {"fund_period": {"live": "ANNUAL", "annual": {"score": 50.0, "fiscal_end": "2026-09-26", "filed": "2026-11-03"}, "trailing": {"score": 50.0, "fiscal_end": "2026-09-26", "newer_quarter": False}}}
    assert ax.fund_age_lines(same, "2026-11-23") == ["점수가 읽은 재무: 2026-09-26까지(연간 보고서, 기준일에서 58일 지남, 보고서 제출 2026-11-03).", "연간 보고서보다 새로운 분기 보고서가 없어, 최근 4분기 기준 점수도 같습니다."]
    assert ax.fund_age_lines({"provenance": {"fund_filed": "2026-03-10"}}, "2026-11-20") == ["점수가 읽은 재무 보고서 제출일: 2026-03-10(255일 전)."] and ax.fund_age_lines({}, "2026-11-20") == []
    live = {"fund_period": {"live": "TRAILING", "trailing": {"score": 85.0, "fiscal_end": "2026-09-30", "filed": "2026-11-16"}, "annual": {"score": 64.2, "fiscal_end": "2025-12-31"}}}
    got = ax.fund_age_lines(live, "2026-11-23")
    assert "최근 4분기" in got[0] and "오래된" not in got[0] and "연간 보고서(2025-12-31까지)로 계산하면 64.2점" in got[1]


def test_the_stocks_own_sector_and_a_yield_are_read_before_the_markets_own_list():
    own = bars(1.1 * MARKET + RNG.normal(0, 0.008, 199))
    stock = bars(1.0 * MARKET + 0.9 * (np.array([b["close"] for b in own[1:]]) / np.array([b["close"] for b in own[:-1]]) - 1 - 1.1 * MARKET) + NOISE)
    data = {**DATA, "XLF": own, "KTB3Y": bars(RATE, start=3.0, level=True)}
    e = ax.exposure(stock, data, "US", extra=[("XLF", "자기 업종(금융 ETF)", "RETURN"), ("SOXX", "다시 적힌 것", "RETURN")])
    assert [o["symbol"] for o in e["others"]] == ["XLF", "SOXX", "^TNX"] and e["others"][0]["partial_corr"] > 0.9 and e["others"][0]["coef"] == pytest.approx(0.9, abs=0.05)      # a key given twice is read once
    assert ax.exposure_lines(e)[1].startswith("자기 업종(금융 ETF): 시장보다 1% 더 오른 날 이 종목은 시장 대비 평균 +0.9")
    assert ax.KR_YIELD == ("KTB3Y", "국고채 3년 금리", "YIELD") and ax.SECTOR_KO["Financial Services"] == "금융" and len(ax.SECTOR_KO) == 11

    class Qsf:
        class cache:
            @staticmethod
            def read(key):
                return {"data": {"treasury": [["2026-11-19", 2.9], ["2026-11-20", None], ["2026-11-21", 2.95]], "corporate": []}} if key == "ecos:kr_credit_spread" else None

    class Term:
        qsf = Qsf()
        ROTATION = {"US": ("SPY", "S&P 500 (SPY)", [("XLK", "기술"), ("XLF", "금융")])}
        asked = []

        class src:
            @staticmethod
            def yahoo_history(syms, period):
                Term.asked.append((tuple(syms), period))
                return {"XLF": own, "SPY": DATA["SPY"]}

        class cache:
            @staticmethod
            def cached(key, ttl, fetch):
                return {"data": fetch()} if key == "rotation:US:2y" else {"data": None}
    assert ax.kr_yield(Term()) == [{"date": "2026-11-19", "close": 2.9}, {"date": "2026-11-21", "close": 2.95}]
    sym, name, rows = ax.own_sector(Term(), "US", {"ticker": "JPM", "sector": "Financial Services"})
    assert (sym, name) == ("XLF", "자기 업종(금융 ETF)") and rows == own and Term.asked == [(("SPY", "XLK", "XLF"), "2y")]      # the market tab's own stored download
    assert ax.own_sector(Term(), "US", {"ticker": "X", "sector": "Utilities"}) is None and ax.own_sector(Term(), "US", None) is None


def test_stocks_whose_two_scores_are_far_apart_are_counted_and_ones_own_are_named():
    def s(ticker, annual, trailing, strategy="LONG_TERM", newer=True):
        return {"ticker": ticker, "strategy": strategy, "fund_period": {"live": "ANNUAL", "annual": {"score": annual, "fiscal_end": "2025-12-31"}, "trailing": {"score": trailing, "newer_quarter": newer}}}
    snaps = [s("A", 64.2, 85.0), s("B", 70.0, 58.0), s("C", 50.0, 59.9), s("D", 40.0, 60.0, newer=False), s("E", 40.0, 60.0, strategy="SWING"), {"ticker": "F", "strategy": "LONG_TERM"}, s("G", 30.0, None)]
    got = ax.fund_gaps(snaps, ["B", "A", "C"])
    assert got["all"] == 2 and got["up"] == 1 and [(r["ticker"], round(r["diff"], 1)) for r in got["listed"]] == [("A", 20.8), ("B", -12.0)] and got["listed"][0]["annual_end"] == "2025-12-31"
    assert ax.fund_gaps(snaps, [])["listed"] == [] and ax.fund_gaps(snaps, ["E"], strategy="SWING")["all"] == 1 and ax.fund_gaps([], ["A"]) == {"all": 0, "up": 0, "listed": []}


def test_a_mark_is_new_when_the_record_before_knew_the_stock_and_did_not_mark_it(tmp_path, monkeypatch):
    from terminal.qsf import kr_events_forward, kr_forward
    fin = {0: {"session": "2026-11-20", "financing": ["A", "B", "N"], "buyback": [], "known": ["A", "B", "C", "N"]}, 1: {"session": "2026-11-19", "financing": ["A"], "buyback": [], "known": ["A", "B", "C"]}}
    risk = {0: {"session": "2026-11-20", "codes": ["C", "R"], "ranked": ["A", "B", "C", "R"]}, 1: {"session": "2026-11-19", "codes": ["R"], "ranked": ["A", "B", "C", "R"]}}
    monkeypatch.setattr(kr_events_forward, "marks", lambda base, back=0: fin[back])
    monkeypatch.setattr(kr_forward, "high_risk", lambda base, back=0: risk[back])
    new = ax.newly_marked(tmp_path)
    assert new["financing"] == ["B"] and new["high_risk"] == ["C"] and new["session"] == "2026-11-20" and new["previous"] == "2026-11-19"      # N is new to the record, not newly marked
    rows = [{"ticker": t, "name": n, "strategy": "SWING", "score": 30.0} for t, n in (("A", "가"), ("B", "나"), ("C", "다"))]
    watched = A.marked_items(rows, ["B"], "KR", new)
    assert [(i["level"], i["kind"]) for i in watched] == [("DUE", "AVOID_NEW")] and "직전 기록(2026-11-19) 뒤 새로 붙은 회피 표시: 자금 조달 공시 나; 고위험 다." in watched[0]["text"] and "날마다 드나듭니다" in watched[0]["text"]
    plain = A.marked_items(rows, [], "KR", {**new, "high_risk": []})
    assert plain[0]["level"] == "INFO" and "날마다" not in plain[0]["text"] and A.marked_items(rows, [], "KR", {**new, "financing": ["ZZ"], "high_risk": []}) == []      # a stock outside the scan is not named
    monkeypatch.undo()
    assert ax.newly_marked(tmp_path) == {"financing": [], "high_risk": [], "session": None, "previous": None}             # no record yet
    assert kr_events_forward.marks(tmp_path, 1)["session"] is None and kr_forward.high_risk(tmp_path, 3) == {"session": None, "codes": [], "ranked": []}


def test_the_note_opens_with_three_lines_made_by_fixed_rules():
    rows = {"LONG_TERM": {"score": 64.2, "band_label": "보유·관찰"}, "SWING": {"score": 53.9, "band_label": "보유·관찰"}}
    base = {"strategy": "LONG_TERM", "fund_period": {"live": "ANNUAL", "annual": {"score": 64.2, "fiscal_end": "2025-12-31"}, "trailing": {"score": 85.0, "newer_quarter": True}}}
    change = [{"label": "1주 전", "session": "2026-11-13", "diff": 3.4, "then": 60.8, "now": 64.2, "domains": {"TECHNICAL": 8.0, "RISK": -2.0, "REGIME": 30.0}, "band": ("X", "X"), "versions": ("v", "v")}]
    down = [{"factor": "valuation", "normalized": 0.48, "lost": 8.7}]
    a, b, c = A.key_lines(rows, base, change, [], [], None, down, "KR")
    assert a == "점수: 장기 64.2점('보유·관찰'), 스윙 53.9점('보유·관찰')."
    assert b == "달라진 것: 1주 전 기록보다 +3.4점(가장 크게 바뀐 영역: 기술 +8). 재무 기준이 2025-12-31까지의 연간 보고서이고, 최근 4분기 재무로는 장기 85.0점(+20.8)입니다."
    assert c == f"먼저 볼 위험: 점수를 가장 많이 깎는 것은 {A.FACTOR_KO['valuation']}입니다(48/100, -8.7점)."
    order = [A.key_lines(rows, {"strategy": "LONG_TERM"}, [], g, m, s, down, "KR")[2] for g, m, s in ((["중대한 공시"], ["고위험"], "묶임"), ([], ["자금 조달 공시", "고위험"], "묶임"), ([], [], "묶임"))]
    assert order[0] == "먼저 볼 위험: 차단 조건 1건(중대한 공시)." and order[1] == "먼저 볼 위험: 회피 표시(자금 조달 공시, 고위험)." and "거의 움직이지 않는 종목" in order[2]
    none = A.key_lines({}, {"strategy": "SWING"}, [], [], [], None, [], "US")
    assert none == ["점수: 최신 기록에 점수가 없습니다.", "달라진 것: 비교할 지난 기록이 아직 없습니다.", "먼저 볼 위험: 걸린 차단 조건과 회피 표시가 없습니다. 안전하다는 뜻은 아닙니다."]
    close = {"strategy": "LONG_TERM", "fund_period": {"annual": {"score": 64.2}, "trailing": {"score": 70.0, "newer_quarter": True}}}
    assert "최근 4분기" not in A.key_lines(rows, close, [], [], [], None, [], "KR")[1]                 # under ten points apart: not said


def test_the_days_list_names_ones_own_stocks_whose_two_scores_are_far_apart(tmp_path, monkeypatch):
    from terminal import automation
    from terminal.qsf import fund_period
    from tests.test_assistant import FakeTerminal
    monkeypatch.setattr(automation, "status", lambda base: {"installed": True, "steps": {}, "latest_session": "2026-11-20", "notes": []})
    monkeypatch.setattr(automation, "readings_state", lambda base: {})
    monkeypatch.delenv(fund_period.SWITCH, raising=False)
    term = FakeTerminal(tmp_path, held=["005930"])
    assert "FUND_GAP" not in [i["kind"] for i in A.briefing(term, "KR")["items"]]                      # no record carries both scores yet: nothing is said
    A._SNAPS.clear()
    for s in term.qsf.ledger.snaps:
        if s["ticker"] == "005930" and s["strategy"] == "LONG_TERM":
            s["fund_period"] = {"live": "ANNUAL", "annual": {"score": 64.2, "fiscal_end": "2025-12-31"}, "trailing": {"score": 85.0, "fiscal_end": "2026-09-30", "newer_quarter": True}}
    b = A.briefing(term, "KR")
    gap = next(i for i in b["items"] if i["kind"] == "FUND_GAP")
    assert b["unread_parts"] == [] and gap["level"] == "INFO" and gap["tab"] == "qsf"
    assert gap["text"] == ("장기 점수가 재무 기준(연간 → 최근 4분기)에 따라 10점 넘게 달라지는 종목이 1개입니다(최근 4분기 쪽이 높은 종목 1개). 보유·관심·매수 후보 가운데: 삼성전자 64→85점(+21). "
                           "라이브 점수는 연간 재무를 읽습니다. 이런 종목은 점수 카드의 참고 점수를 함께 보세요.")
    A._SNAPS.clear()
    other = FakeTerminal(tmp_path)                                                                     # the same records, the stock neither held nor watched nor a candidate
    other.qsf.ledger.snaps = term.qsf.ledger.snaps
    assert "보유·관심·매수 후보 가운데는 없습니다." in next(i for i in A.briefing(other, "KR")["items"] if i["kind"] == "FUND_GAP")["text"]
    A._SNAPS.clear()


def test_the_additions_are_wired_into_the_note_the_list_and_the_documents():
    src = (ROOT / "terminal" / "assistant.py").read_text(encoding="utf-8")
    for needle in ('part("mix", mix)', 'part("marked", marked)', 'part("gaps", gaps)', 'sections.insert(0, {"title": "핵심 세 줄"', "ax.own_sector(terminal, market", "ax.newly_marked(base) if market == \"KR\" else None", "ax.SECTOR_KO.get(", "ax.change_since(terminal.qsf.ledger", "ax.fund_age_lines(base", "ax.exposure(terminal.qsf._loader(market)(ticker)", '"매수 후보의 구성"'):
        assert needle in src, needle
    assert A.PART_KO["mix"] == "매수 후보의 구성" and A.PART_KO["marked"] == "회피 표시" and A.PART_KO["gaps"] == "재무 기준에 따른 점수 차이"
    mod = (ROOT / "terminal" / "analyst_extra.py").read_text(encoding="utf-8")
    assert "Nothing here feeds the score" in mod and "import requests" not in mod and "ledger.append" not in mod and ".write" not in mod
