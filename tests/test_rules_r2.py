"""Rules R-2 (user decision 2026-11-25): a band is named by its place.  The score, the lines and the recorded codes are unchanged;
"매수 후보" returns to one score only through its own live verdict (reports/QSF_RULES_R2_2026_11_25.md)."""
import json
import re
from pathlib import Path

import pytest

from terminal.qsf import config, engine, wording

ROOT = Path(__file__).resolve().parents[1]
OLD = ("매수 후보", "강력 매수", "매수 구간", "지금 진입 가능", "사도 됨", "신규 진입 회피", "매도·회피", "약세·축소", "분할 진입 기준 구간")


def test_the_codes_and_lines_stay_and_only_the_names_move():
    assert config.RULES_VERSION == "R-2" and config.MODEL_VERSION == "QSF-1.6.0"
    assert [(lo, code) for lo, code, _ in config.BANDS] == [(80.0, "STRONG_BUY_CANDIDATE"), (70.0, "BUY_CANDIDATE"), (55.0, "HOLD_WATCH"), (40.0, "WEAK_REDUCE"), (0.0, "SELL_AVOID")]
    assert [label for _, _, label in config.BANDS] == ["최상위 구간", "상위 구간", "보유·관찰", "하위 구간", "최하위 구간"]
    assert engine.classify(82.0) == {"band": "STRONG_BUY_CANDIDATE", "band_label": "최상위 구간"} and engine.classify(12.0)["band_label"] == "최하위 구간"
    assert engine.classify(68.0, "BUY_CANDIDATE")["band_label"].startswith("상위 구간(완충 구간")
    assert engine.action_for(75.0, False) == "BUY" and engine.action_for(30.0, True) == "SELL"            # the codes the books read
    assert not any("매수" in v or "매도" in v or "회피" in v for v in config.ACTION_LABELS.values())


def test_no_screen_or_message_text_says_the_old_words():
    """Source text outside comments.  wording.py holds the words a passed verdict gives back, and nothing else may."""
    hits = []
    for f in [*ROOT.glob("terminal/**/*.py"), *ROOT.glob("terminal/static/*.js"), *ROOT.glob("terminal/static/*.html"), ROOT / "app.py"]:
        if f.name == "wording.py":
            continue
        for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            code = re.split(r"(?:^|\s)(?:#|//)\s", line, maxsplit=1)[0]                     # what is before a comment
            if line.lstrip().startswith(('"""', "index fund SPY", "#", "//")) or '"""' in line:
                continue
            hits += [f"{f.relative_to(ROOT)}:{n}: {w}" for w in OLD if w in code]
    assert hits == []
    assert "'매수'를 쓰지 않습니다" in config.VALIDATION_NOTICE and config.VALIDATION_NOTICE in (ROOT / "terminal" / "static" / "qsf.js").read_text(encoding="utf-8")


def passed(market="KR", strategy="SWING", /, sessions=None, **change):
    """A report as the reading writes it when everything the word needs is there."""
    from terminal.qsf import live_forward as lf
    n = sessions or lf.NEED[strategy]
    doc = {"status": "REAL", "market": market, "strategy": strategy, "horizon": lf.PRIMARY[strategy], "sessions_used": n, "first": lf.FIRST, "verdict": "WEAK_POSITIVE_EVIDENCE",
           "condition_a": {"ic": True, "t": True, "ic_both_halves": True, "spread_both_halves": True, "buy_band": True}, "condition_b": True,
           "primary": {"t": 4.0, "t_bar": 3.33, "ic": 0.06, "all": {"spread_median": 0.004}},
           "money_split": {"condition_b_price_only": True, "early": {"score_effect": 0.002}, "late": {"score_effect": 0.003}}}
    doc.update({"versions": [config.MODEL_VERSION]} if sessions else {"by_version": {config.MODEL_VERSION: {"dates": n, "ic": 0.06}}})
    doc.update(change)
    return doc


def put(base, doc, sealed=True, market=None, strategy=None):
    m, s = market or doc["market"], strategy or doc["strategy"]
    name = f"QSF_LIVE_FORWARD_CONT_{m}_SWING_{doc['sessions_used']}.json" if "versions" in doc else f"QSF_LIVE_FORWARD_{m}_{s}.json"
    path = base / "reports" / "qsf" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc), encoding="utf-8")
    if sealed:
        wording.seal(base, path)
    return path


CARD = {"band": "BUY_CANDIDATE", "band_label": "상위 구간(완충 구간: 67점까지 유지)", "action": "BUY", "action_label": "상위 구간", "score": 68.0}


def test_the_buy_word_returns_only_on_rank_and_money_and_only_for_that_score(tmp_path):
    assert wording.restore(CARD, tmp_path, "KR", "LONG_TERM") is CARD and not wording.earned(tmp_path, "KR", "LONG_TERM")
    put(tmp_path, passed("KR", "LONG_TERM", verdict="RANK_ONLY", condition_b=False))
    assert wording.restore(CARD, tmp_path, "KR", "LONG_TERM") is CARD                                   # rank alone earns the place name it already has
    put(tmp_path, passed("KR", "SWING", verdict="NO_EVIDENCE", condition_b=False))
    put(tmp_path, passed("KR", "SWING", sessions=480, verdict="NO_EVIDENCE", condition_b=False))
    put(tmp_path, passed("KR", "SWING", sessions=720))                                                  # a registered continuation reading, with the ones before it on file
    got = wording.restore(CARD, tmp_path, "KR", "SWING")
    assert got["band_label"] == "매수 후보(완충 구간: 67점까지 유지)" and got["action_label"] == "매수 후보" and got["buy_word_earned"] and got["score"] == 68.0
    assert CARD["band_label"].startswith("상위 구간") and wording.restore(CARD, tmp_path, "US", "SWING") is CARD and wording.restore(CARD, tmp_path, "KR", "LONG_TERM") is CARD
    strong = wording.restore({"band": "STRONG_BUY_CANDIDATE", "band_label": "최상위 구간", "action": "HOLD", "action_label": "보유 유지"}, tmp_path, "KR", "SWING")
    assert strong["band_label"] == "강력 매수 후보" and strong["action_label"] == "보유 유지"
    low = {"band": "HOLD_WATCH", "band_label": "보유·관찰", "action": "WATCH"}
    assert wording.restore(low, tmp_path, "KR", "SWING") is low


@pytest.mark.parametrize("change, code", [
    ({"status": "DAMAGED"}, "NOT_THIS_READING"), ({"market": "KR"}, "NOT_THIS_READING"), ({"strategy": "LONG_TERM"}, "NOT_THIS_READING"),
    ({"horizon": 5}, "NOT_THE_REGISTERED_SAMPLE"), ({"sessions_used": 60}, "NOT_THE_REGISTERED_SAMPLE"), ({"first": "2026-11-09"}, "NOT_THE_REGISTERED_SAMPLE"),
    ({"condition_b": False}, "VERDICT_NOT_BACKED"), ({"primary": {"t": 3.0, "t_bar": 3.33, "all": {"spread_median": 0.004}}}, "VERDICT_NOT_BACKED"),
    ({"condition_a": {"ic": True, "t": True, "ic_both_halves": True, "spread_both_halves": False, "buy_band": True}}, "VERDICT_NOT_BACKED"),
    ({"condition_a": {"ic": True}}, "VERDICT_NOT_BACKED"),
    ({"money_split": {"condition_b_price_only": False, "early": {"score_effect": 0.002}, "late": {"score_effect": 0.003}}}, "MONEY_CHECKS"),
    ({"money_split": {"condition_b_price_only": True, "early": {"score_effect": 0.002}, "late": {"score_effect": -0.001}}}, "MONEY_CHECKS"),
    ({"primary": {"t": 4.0, "t_bar": 3.33, "all": {"spread_median": 0.0}}}, "MONEY_CHECKS"),
    ({"by_version": {"QSF-1.5.2": {"dates": 240}}}, "ANOTHER_FORMULA"), ({"by_version": {config.MODEL_VERSION: {}, "QSF-1.7.0": {}}}, "ANOTHER_FORMULA")])
def test_a_report_that_fails_one_check_does_not_give_the_word_back(tmp_path, change, code):
    """Each hole the audit's red team found on 2026-11-25: the word in a file is not enough, its own figures must back it."""
    assert wording.why_not(passed("US", "SWING"), "US", "SWING") == []
    doc = passed("US", "SWING", **change)
    assert code in wording.why_not(doc, "US", "SWING")
    put(tmp_path, doc, market="US", strategy="SWING")                      # under the name the check opens
    assert not wording.earned(tmp_path, "US", "SWING")


def test_a_hand_made_file_a_lone_continuation_and_another_formula_do_not_count(tmp_path, monkeypatch):
    path = put(tmp_path, {"verdict": "WEAK_POSITIVE_EVIDENCE", "market": "US", "strategy": "SWING"}, sealed=False)
    assert not wording.earned(tmp_path, "US", "SWING")                                                  # one line written by hand
    put(tmp_path, passed("US", "SWING"), sealed=False)
    assert not wording.earned(tmp_path, "US", "SWING")                                                  # every field right, but not a file the reading wrote
    put(tmp_path, passed("US", "SWING"))
    assert wording.earned(tmp_path, "US", "SWING")
    path.write_text(path.read_text(encoding="utf-8").replace("0.06", "0.07"), encoding="utf-8")
    assert not wording.earned(tmp_path, "US", "SWING")                                                  # edited after it was written
    other = tmp_path / "lone"
    put(other, passed("KR", "SWING", sessions=720))
    assert not wording.earned(other, "KR", "SWING")                                                     # a continuation without the verdict and the 480 reading before it
    put(other, passed("KR", "SWING", verdict="NO_EVIDENCE", condition_b=False))
    assert not wording.earned(other, "KR", "SWING")
    put(other, passed("KR", "SWING", sessions=480, verdict="NO_EVIDENCE", condition_b=False))
    assert wording.earned(other, "KR", "SWING")
    wrong = tmp_path / "wrong"
    put(wrong, passed("KR", "SWING", verdict="NO_EVIDENCE", condition_b=False))
    put(wrong, passed("KR", "SWING", sessions=480, market="US"), market="KR")
    assert not wording.earned(wrong, "KR", "SWING")                                                     # the file of another market under this name
    down = tmp_path / "down"
    put(down, passed("US", "LONG_TERM"))
    assert wording.earned(down, "US", "LONG_TERM")
    monkeypatch.setattr(config, "MODEL_VERSION", "QSF-1.7.0")
    assert not wording.earned(down, "US", "LONG_TERM") and wording.restore(CARD, down, "US", "LONG_TERM") is CARD      # the formula changed: the word leaves by itself
    (down / wording.SEALS).unlink()
    monkeypatch.undo()
    assert not wording.earned(down, "US", "LONG_TERM")                                                  # the seal list lost: no word, never the other way


def test_the_rule_is_written_down_with_how_rarely_the_word_returns():
    doc = (ROOT / "reports" / "QSF_RULES_R2_2026_11_25.md").read_text(encoding="utf-8")
    for needle in ("점수는 바뀌지 않습니다", "WEAK_POSITIVE_EVIDENCE", "`RANK_ONLY`로는 돌아오지 않습니다", "6.7~8.7%", "주문은 바뀌지 않습니다", "R-1로 기록된 거래일은 없습니다",
                   "가격만으로", "점수 효과가 전·후반 모두 양수", "중앙값 차이가 양수", "공식 버전이 바뀌면", "프로그램이 쓴 파일"):
        assert needle in doc
    assert "wording.restore(engine.score(ctx, strategy, held=bool(position)), self.base, market, strategy)" in (ROOT / "terminal" / "qsf" / "service.py").read_text(encoding="utf-8")


def test_a_scan_stored_before_r2_is_named_by_todays_rules_when_it_is_read(tmp_path):
    old = {"ticker": "AAA", "strategy": "SWING", "score": 68.0, "band": "BUY_CANDIDATE", "band_label": "매수 후보(완충 구간: 67점까지 유지)", "action": "BUY", "action_label": "매수 후보"}
    got = wording.relabel(old, tmp_path, "US")
    assert got["band_label"] == "상위 구간(완충 구간: 67점까지 유지)" and got["action_label"] == "상위 구간" and old["action_label"] == "매수 후보"      # the stored row is not rewritten
    low = wording.relabel({"strategy": "LONG_TERM", "band": "SELL_AVOID", "band_label": "매도·회피 후보", "action": "AVOID", "action_label": "신규 진입 회피"}, tmp_path, "KR")
    assert low["band_label"] == "최하위 구간" and low["action_label"] == "하위 구간"
    pinned = wording.relabel({"strategy": "SWING", "band": "HOLD_WATCH", "band_label": "보유·관찰 · 합병 절차로 가격이 묶여 매수 후보에서 뺌(x)", "action": "WATCH", "action_label": "관찰"}, tmp_path, "US")
    assert pinned["band_label"] == "보유·관찰 · 합병 절차로 가격이 묶여 상위 구간에서 뺌(x)" and wording.relabel({"band_label": None, "action": "?"}, tmp_path, "US")["band_label"] is None
    assert "wording.relabel(r, self.base, market)" in (ROOT / "terminal" / "qsf" / "views.py").read_text(encoding="utf-8")
