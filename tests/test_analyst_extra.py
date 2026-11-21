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


def test_the_additions_are_wired_into_the_note_the_list_and_the_documents():
    src = (ROOT / "terminal" / "assistant.py").read_text(encoding="utf-8")
    for needle in ('part("mix", mix)', 'part("marked", marked)', "ax.change_since(terminal.qsf.ledger", "ax.fund_age_lines(base", "ax.exposure(terminal.qsf._loader(market)(ticker)", '"매수 후보의 구성"'):
        assert needle in src, needle
    assert A.PART_KO["mix"] == "매수 후보의 구성" and A.PART_KO["marked"] == "회피 표시"
    mod = (ROOT / "terminal" / "analyst_extra.py").read_text(encoding="utf-8")
    assert "Nothing here feeds the score" in mod and "import requests" not in mod and "ledger.append" not in mod and ".write" not in mod
