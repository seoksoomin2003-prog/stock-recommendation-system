"""Rules R-2 (user decision 2026-11-25): a band is named by its place.  The score, the lines and the recorded codes are unchanged;
"매수 후보" returns to one score only through its own live verdict (reports/QSF_RULES_R2_2026_11_25.md)."""
import json
import re
from pathlib import Path

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


def test_the_buy_word_returns_only_on_rank_and_money_and_only_for_that_score(tmp_path):
    card = {"band": "BUY_CANDIDATE", "band_label": "상위 구간(완충 구간: 67점까지 유지)", "action": "BUY", "action_label": "상위 구간", "score": 68.0}
    assert wording.restore(card, tmp_path, "KR", "LONG_TERM") is card and not wording.earned(tmp_path, "KR", "LONG_TERM")
    d = tmp_path / "reports" / "qsf"
    d.mkdir(parents=True)
    (d / "QSF_LIVE_FORWARD_KR_LONG_TERM.json").write_text(json.dumps({"verdict": "RANK_ONLY"}), encoding="utf-8")
    assert wording.restore(card, tmp_path, "KR", "LONG_TERM") is card                                   # rank alone earns the place name it already has
    (d / "QSF_LIVE_FORWARD_KR_SWING.json").write_text(json.dumps({"verdict": "NO_EVIDENCE"}), encoding="utf-8")
    (d / "QSF_LIVE_FORWARD_CONT_KR_SWING_720.json").write_text(json.dumps({"verdict": "WEAK_POSITIVE_EVIDENCE"}), encoding="utf-8")
    got = wording.restore(card, tmp_path, "KR", "SWING")                                                # a registered continuation reading counts
    assert got["band_label"] == "매수 후보(완충 구간: 67점까지 유지)" and got["action_label"] == "매수 후보" and got["buy_word_earned"] and got["score"] == 68.0
    assert card["band_label"].startswith("상위 구간") and wording.restore(card, tmp_path, "US", "SWING") is card and wording.restore(card, tmp_path, "KR", "LONG_TERM") is card
    strong = wording.restore({"band": "STRONG_BUY_CANDIDATE", "band_label": "최상위 구간", "action": "HOLD", "action_label": "보유 유지"}, tmp_path, "KR", "SWING")
    assert strong["band_label"] == "강력 매수 후보" and strong["action_label"] == "보유 유지"
    low = {"band": "HOLD_WATCH", "band_label": "보유·관찰", "action": "WATCH"}
    assert wording.restore(low, tmp_path, "KR", "SWING") is low
    (d / "QSF_LIVE_FORWARD_US_SWING.json").write_text("not json", encoding="utf-8")
    assert not wording.earned(tmp_path, "US", "SWING")                                                  # an unreadable file is not a pass


def test_the_rule_is_written_down_with_how_rarely_the_word_returns():
    doc = (ROOT / "reports" / "QSF_RULES_R2_2026_11_25.md").read_text(encoding="utf-8")
    for needle in ("점수는 바뀌지 않습니다", "WEAK_POSITIVE_EVIDENCE", "`RANK_ONLY`로는 돌아오지 않습니다", "6.7~8.7%", "주문은 바뀌지 않습니다", "R-1로 기록된 거래일은 없습니다"):
        assert needle in doc
    assert "wording.restore(engine.score(ctx, strategy, held=bool(position)), self.base, market, strategy)" in (ROOT / "terminal" / "qsf" / "service.py").read_text(encoding="utf-8")
