"""Score audit of 2026-11-25, roadmap level P1 (reports/score_reliability_audit_2026_11_25/IMPROVEMENT_ROADMAP.md): what the score
says about itself.  No score, band, rule or record changes: the line of 70 is given its place of the day, a card with a missing
factor always shows its conservative score, inputs a whole market lacks are said, and the plan says it is not what the verdict reads."""
from pathlib import Path

from terminal.qsf import config, inventory, order_plan
from tests.test_ui_batch_1 import body, node

ROOT = Path(__file__).resolve().parents[1]
QSF = (ROOT / "terminal" / "static" / "qsf.js").read_text(encoding="utf-8")
PRE = 'const isNum = (v) => typeof v === "number" && isFinite(v); const esc = (s) => String(s); const qsfState = { strategy: "SWING" }; const QSF_STRAT = { SWING: "스윙", LONG_TERM: "장기" };\n'


def test_the_ranking_says_where_seventy_stands_today_and_what_the_korean_swing_verdict_reads():
    fn = PRE + body(QSF, "function qsfLineToday(")
    got = node(fn + """
const rows = Array.from({ length: 100 }, (_, k) => ({ score: 30 + k * 0.5 }));          // 30.0 .. 79.5: twenty at 70 or more
console.log(JSON.stringify([qsfLineToday(rows, "US"), qsfLineToday(rows.map((r) => ({ score: r.score - 20 })), "KR"), qsfLineToday(rows.slice(0, 10), "US")]));""")
    us, kr, few = got
    assert "오늘 70점 이상은 <b>20종목</b>" in us and "<b>상위 20%</b>" in us and "그날 상위 5분의 1은 70.0점 이상" in us and "같은 뜻이 아닙니다" in us
    assert "오늘은 70점 이상인 종목이 없습니다(최고 59.5점)" in kr and "한국 스윙의 실전 판정은 70점이 아니라 <b>그날 상위 5분의 1</b>(오늘 20종목, 50.0점 이상)" in kr
    assert few == ""                                                                    # too few scored stocks: nothing is said
    assert "${qsfLineToday(scoredRows, mk)}" in QSF and 'class="meta m0 qr-pct"' in QSF and "상위 ${r.pct}%" in QSF


def test_a_card_with_a_missing_factor_always_shows_its_conservative_score():
    fn = PRE + body(QSF, "function qsfConservative(")
    got = node(fn + """
console.log(JSON.stringify([qsfConservative({ missing: ["valuation"], conservative_score: 66.4, score: 71.2 }), qsfConservative({ missing: [], conservative_score: 71.2, score: 71.2 }),
  qsfConservative({ missing: ["x"], conservative_score: null, score: 60 })]));""")
    assert "<b>자료 없는 요인 1개</b>" in got[0] and "<b>66.4점</b>(−4.8)" in got[0] and "없는 자료가 점수를 올릴 수 있습니다" in got[0] and got[1] == "" and got[2] == ""
    assert "${qsfConservative(c)}${qsfInputsNote(c)}${qsfStaleNote(c)}" in QSF
    rank = PRE + body(QSF, "function qsfRankNote(")
    seen = node(rank + """
const r = (pct, market, strategy) => qsfRankNote({ market, strategy, rank_in_scan: { top_pct: pct, n: 300, session: "2026-11-26" } });
console.log(JSON.stringify([r(12.0, "KR", "SWING"), r(35.0, "KR", "SWING"), r(12.0, "US", "SWING"), r(12.0, "KR", "LONG_TERM")]));""")
    assert "판정이 읽는 묶음(그날 상위 5분의 1) 안" in seen[0] and "묶음(그날 상위 5분의 1) 밖" in seen[1] and "판정이 읽는" not in seen[2] and "판정이 읽는" not in seen[3]


def test_inputs_a_whole_market_lacks_are_said_on_the_card_and_never_recorded():
    assert set(config.MARKET_INPUT_NOTES) == {("KR", "LONG_TERM"), ("KR", "SWING")}
    long_, swing = config.MARKET_INPUT_NOTES[("KR", "LONG_TERM")], config.MARKET_INPUT_NOTES[("KR", "SWING")]
    assert "매출총이익률, 이자보상배율, 주식 수 변화 없이" in long_ and "두 번 셉니다" in long_ and "가격 추세 요인이 없고" in swing
    src = (ROOT / "terminal" / "qsf" / "service.py").read_text(encoding="utf-8")
    assert 'out["inputs_note"] = config.MARKET_INPUT_NOTES[(market, strategy)]' in src
    from terminal.qsf import ledger
    assert "inputs_note" not in ledger.FIELDS                                           # display only
    means = " ".join(inventory.SCORE_MEANS)
    assert "장기는 63거래일" in means and "보유 계획이고 판정 기간이 아닙니다" in means and "남은 요인의 평균으로 채워집니다" in means
    assert inventory.markdown() == (ROOT / "reports" / "QSF_FACTOR_INVENTORY.md").read_text(encoding="utf-8")


def test_the_plan_says_it_is_not_the_band_the_verdict_reads_and_leftover_words_are_gone():
    got = order_plan.annotate([{"ticker": "AAA", "style": "SWING", "score": 62.0}, {"ticker": "BBB", "style": "SWING", "score": 75.0}])
    assert "1종목은 점수 구간이 상위 구간" in got["note"] and "판정이 통과해도 이 계획의 종목이 검증된 것은 아닙니다" in got["note"]
    assert order_plan.annotate([{"ticker": "BBB", "style": "SWING", "score": 75.0}])["note"] is None
    sp = (ROOT / "terminal" / "static" / "sectorpicks.js").read_text(encoding="utf-8")
    assert "<h3>진입 조건</h3>" in sp and "<h3>정리 조건</h3>" in sp and "<h3>매수 시기</h3>" not in sp and "계획상 수익률 <span" not in sp
    ic = (ROOT / "terminal" / "static" / "committee.js").read_text(encoding="utf-8")
    assert "그 관점의 규칙을 채웠다는 뜻입니다" in ic and "아직 판정 전입니다" in ic
    assert "63거래일(약 3개월) 뒤의 수익으로 읽습니다" in QSF
    live = (ROOT / "reports" / "QSF_LIVE_FORWARD_PROTOCOL.md").read_text(encoding="utf-8")
    assert "판정이 재는 묶음과 주문 계획의 카드는 다릅니다" in live and "63거래일로만 판정합니다" in live
