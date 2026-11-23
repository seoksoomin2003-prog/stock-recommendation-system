"""'사도 돼?' answers with one conclusion first (user decision 2026-11-24): 사도 됨 / 기다림 / 사지 않음, judged against the stance the
user chose (stance.judge, the same function as the ranking's stance mark), with the stance line always named.  An adverse US day keeps
the conclusion and adds the half size.  Read only: nothing is scored again and no record changes."""
from pathlib import Path

from terminal import assistant as A
from terminal.qsf import config, stance as qs
from tests.test_ui_batch_1 import body, node

ROOT = Path(__file__).resolve().parents[1]
CALM = {"score_100": 60.0, "label": "보통", "state": "NORMAL", "size_factor": 1.0}
BAD = {"score_100": 15.0, "label": "나쁨", "state": "ADVERSE", "size_factor": 0.5}


def snap(score=72.0, entry="ENTRY_NOW", strategy="SWING", **kw):
    factors = [{"factor": "trend_structure", "raw": {"ma20": 95.0}}, {"factor": "atr_risk", "raw": {"atr_pct": 0.02}}]
    return {"ticker": "X", "strategy": strategy, "score": score, "entry_status": entry, "actionability": "ACTIONABLE", "confidence": "HIGH", "price": 100.0,
            "factors": factors, "holding": {"reward_risk": 0.8}, **kw}


def verdict(s, level="NORMAL", strategy="SWING", market="US", **kw):
    args = dict(gates=[], marks=[], earnings={}, soon=False, level=level, wide=set(), state=CALM, held=False)
    args.update(kw)
    return A.buy_verdict(s, strategy, market, **args)


def test_entry_now_above_the_stance_line_is_ok_and_names_the_line():
    v = verdict(snap(72.0))
    assert v["key"] == "OK" and v["label"] == "사도 됨" and v["change"] is None and v["candidate"]
    assert "'기본'의 후보 선 70점" in v["basis"] and "방어적 75 · 기본 70 · 공격적 67" in v["basis"]


def test_the_chosen_stance_moves_the_line():
    s = snap(68.0)
    assert verdict(s, "NORMAL")["key"] == "WAIT" and "'기본'의 후보 선 70점에 2.0점 모자랍니다" in verdict(s, "NORMAL")["why"]
    assert verdict(s, "AGGRESSIVE")["key"] == "OK" and "'공격적'의 후보 선 67점" in verdict(s, "AGGRESSIVE")["basis"]
    assert verdict(snap(80.0), "DEFENSIVE", wide={"X"})["key"] == "WAIT" and "움직임이 큰 쪽" in verdict(snap(80.0), "DEFENSIVE", wide={"X"})["why"]
    # a line reached only because a factor has no data is not reached (the conservative score, as in the ranking)
    low = verdict(snap(71.0, conservative_score=66.0))
    assert low["key"] == "WAIT" and "기록된 점수는 71.0점" in low["why"]


def test_blocks_say_no_and_come_before_waits():
    assert verdict(snap(80.0), gates=["거래 정지"])["key"] == "NO"
    m = verdict(snap(80.0, entry="WAIT_FOR_PULLBACK"), marks=["고위험 표시: 변동성과 낙폭이 나쁜 쪽입니다."])
    assert m["key"] == "NO" and m["why"].startswith("고위험 표시") and any("눌림" in x for x in m["also"]) is False      # a NO lists only reasons of its own weight
    hold_start = config.BANDS[2][0]
    assert verdict(snap(hold_start - 0.1, entry="NO_VALID_ENTRY_SETUP"))["why"] == f"점수 {hold_start - 0.1:.1f}점이 관찰 기준 {hold_start:g}점 미만입니다."
    assert verdict(snap(60.0, entry="NO_VALID_ENTRY_SETUP"))["key"] == "NO"
    assert verdict(snap(80.0, actionability="INSUFFICIENT_DATA"))["key"] == "NO"


def test_waits_say_what_would_change_them():
    above = verdict(snap(75.0, entry="WAIT_FOR_PULLBACK", price=100.0))           # 20-day zone 94.0~95.5 is below the price
    assert above["key"] == "WAIT" and "$94.00~$95.50" in above["change"] and "내려오면" in above["change"] and "기준 1.5" in above["why"]
    below = verdict(snap(75.0, entry="WAIT_FOR_PULLBACK", price=94.5))            # already at or under the zone: not "come down"
    assert "이미" in below["change"] and "내려오면" not in below["change"]
    assert "밸류에이션" in verdict(snap(75.0, entry="OVERVALUED_AT_CURRENT_PRICE", strategy="LONG_TERM"), strategy="LONG_TERM")["change"]
    soon = verdict(snap(75.0), earnings={"next_earnings": "2026-11-27", "sessions": 3}, soon=True)
    assert soon["key"] == "WAIT" and "2026-11-27(3거래일 뒤)" in soon["why"]
    assert verdict(snap(75.0, strategy="LONG_TERM"), strategy="LONG_TERM", earnings={"next_earnings": "2026-11-27", "sessions": 3}, soon=True)["key"] == "OK"


def test_an_adverse_day_keeps_the_conclusion_and_adds_the_size():
    v = verdict(snap(75.0), state=BAD)
    assert v["key"] == "OK" and any("0.5배로 줄여" in x for x in v["notes"])
    assert any("이미 보유 중" in x for x in verdict(snap(75.0), held=True)["notes"])


def test_the_zone_is_the_holding_rule_rebuilt_from_the_record():
    assert A.pullback_zone(snap()) == [95.0 - 0.5 * 2.0, 95.0 + 0.5 * 2.0 * 0.5]
    assert A.pullback_zone({"price": 100.0, "factors": []}) is None
    assert "_zone(pull, atr, 0.5)" in (ROOT / "terminal" / "qsf" / "holding.py").read_text(encoding="utf-8")


def test_the_judge_is_the_rankings_own():
    assert set(qs.LEVELS) == {"DEFENSIVE", "NORMAL", "AGGRESSIVE"} and "qs.judge(snap, level, set(wide))" in (ROOT / "terminal" / "assistant.py").read_text(encoding="utf-8")


def test_no_advice_words():
    for key in ("OK", "WAIT", "NO"):
        for word in ("사세요", "매수하세요", "추천"):
            assert word not in A.VERDICT_KO[key] and word not in A.VERDICT_CAVEAT


def test_the_page_shows_the_conclusion_first():
    js = (ROOT / "terminal" / "static" / "assistant.js").read_text(encoding="utf-8")
    assert "${a.verdict ? asstVerdict(a.verdict) : a.summary ?" in js and 's.title === "다른 전략" ? []' in js
    got = node("""const esc = (s) => String(s);
""" + "const ASST_VERDICT_CLASS = { OK: \"v-ok\", WAIT: \"v-wait\", NO: \"v-no\" };\n" + body(js, "function asstVerdict(") + """
console.log(JSON.stringify(asstVerdict({ key: "WAIT", label: "기다림", strategy: "스윙", why: "이유", change: "조건", other: "장기: 사도 됨" })));""")
    assert got.startswith('<div class="asst-verdict v-wait"><div class="asst-v-head"><b>기다림</b>') and "바뀌는 조건: 조건" in got and "장기: 사도 됨" in got
    css = (ROOT / "terminal" / "static" / "style.css").read_text(encoding="utf-8")
    assert ".asst-verdict.v-ok { --v: var(--judge-buy); }" in css and ".asst-verdict.v-no { --v: var(--warn); }" in css
