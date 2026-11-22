"""The stance per market (terminal/qsf/stance.py) and the plain explanations (terminal/plain.py): user request and decisions 2026-11-22
(the stance changes which stocks are called candidates and the size of the real account's planned orders; three levels; per market)."""
import inspect
import json
import re

import pytest

from terminal import plain
from terminal.qsf import config, engine, holding, order_plan as op, stance
from tests.test_order_plan_paper_book import account, cand, snap
from tests.test_qsf import GOOD_FUND, bars, ctx


# ---------------------------------------------------------------------- the stance
def test_normal_is_the_program_without_a_stance_and_each_market_has_its_own(tmp_path):
    assert stance.level(tmp_path, "US") == "NORMAL" and stance.level(tmp_path, "KR") == "NORMAL"
    assert stance.PRESETS["NORMAL"] == {"line": 70.0, "min_confidence": None, "drop_volatile": False, "size": 1.0, "exposure_cap": None, "plan_needs_line": False}
    got = stance.set_level(tmp_path, "KR", "DEFENSIVE")
    assert got["level"] == "DEFENSIVE" and got["label"] == "방어적" and [x["level"] for x in got["levels"]] == ["DEFENSIVE", "NORMAL", "AGGRESSIVE"]
    assert stance.level(tmp_path, "KR") == "DEFENSIVE" and stance.level(tmp_path, "US") == "NORMAL"            # per market (user decision)
    stance.set_level(tmp_path, "US", "AGGRESSIVE")
    assert json.loads((tmp_path / stance.FILE).read_text(encoding="utf-8"))["KR"]["level"] == "DEFENSIVE" and stance.level(tmp_path, "US") == "AGGRESSIVE"
    with pytest.raises(ValueError, match="INVALID_STANCE"):
        stance.set_level(tmp_path, "US", "VERY_AGGRESSIVE")
    with pytest.raises(ValueError, match="INVALID_MARKET"):
        stance.set_level(tmp_path, "COIN", "NORMAL")
    (tmp_path / stance.FILE).write_text("{broken", encoding="utf-8")
    assert stance.level(tmp_path, "US") == "NORMAL"                                                         # an unreadable file is the normal stance, never a guess


def test_the_presets_say_what_they_do_and_reuse_the_programs_own_lines():
    d, a = stance.PRESETS["DEFENSIVE"], stance.PRESETS["AGGRESSIVE"]
    assert (d["line"], d["size"], d["exposure_cap"], d["plan_needs_line"]) == (75.0, 0.5, 0.5, True)
    assert (a["line"], a["size"], a["exposure_cap"], a["plan_needs_line"]) == (config.BUY_BAND_EXIT, 1.5, None, False)      # 67: the buffer's lower line, not a new number
    assert all(len(stance.describe(k)) == 6 for k in stance.LEVELS) and "검증한 값이 아닙니다" in stance.NOTE


def test_a_defensive_candidate_needs_the_line_the_data_and_a_calm_range():
    snaps = [{**snap(f"T{k}", score=80.0, price=100.0, atr=1.0 + k), "confidence": "HIGH"} for k in range(9)]      # T8 moves most
    snaps += [{**snap("LOWC", score=90.0, atr=1.0), "confidence": "LOW"}, {**snap("MID", score=72.0, atr=1.0), "confidence": "HIGH"},
              {**snap("BLK", score=95.0, atr=1.0, actionability="BLOCKED"), "confidence": "HIGH"}]
    wide = stance.volatile(snaps)
    assert wide == {"T8", "T7", "T6", "T5"} and stance.volatile(snaps[:2]) == set()                         # the widest third of twelve; too few stocks: nobody
    got = stance.marks(snaps, "DEFENSIVE")
    assert got[("T0", "SWING")] is None and got[("T8", "SWING")] == "VOLATILE" and got[("LOWC", "SWING")] == "CONFIDENCE" and got[("MID", "SWING")] == "LINE" and got[("BLK", "SWING")] == "NOT_ACTIONABLE"
    normal, bold = stance.marks(snaps, "NORMAL"), stance.marks(snaps, "AGGRESSIVE")
    assert normal[("T8", "SWING")] is None and normal[("LOWC", "SWING")] is None and normal[("MID", "SWING")] is None
    assert bold[("MID", "SWING")] is None and stance.judge({**snap("X", score=67.0)}, "AGGRESSIVE", set()) is None and stance.judge({**snap("X", score=66.9)}, "AGGRESSIVE", set()) == "LINE"


def test_the_plan_is_untouched_at_normal_smaller_when_defensive_and_larger_when_aggressive():
    cands = [cand("A", score=80.0), cand("B", score=60.0)]
    marks = {("A", "SWING"): None, ("B", "SWING"): "LINE"}
    state = {"size_factor": 1.0, "new_exposure_cap": None, "state": "FAVOURABLE"}
    kept, sized, shown = stance.for_plan(cands, state, marks, "NORMAL", op.STRATEGY_OF)
    assert kept == cands and sized == state and shown["note"] is None and shown["left_out"] == 0
    plain_plan = op.build(cands, account(), "KR", state=state)
    kept, sized, shown = stance.for_plan(cands, state, marks, "DEFENSIVE", op.STRATEGY_OF)
    assert [c["ticker"] for c in kept] == ["A"] and sized["size_factor"] == 0.5 and sized["new_exposure_cap"] == 0.5 and shown["left_out"] == 1 and shown["left_out_by"] == {"점수가 이 성향의 선 아래": 1}
    small = op.build(kept, account(), "KR", state=sized)
    kept, sized, shown = stance.for_plan(cands, state, marks, "AGGRESSIVE", op.STRATEGY_OF)
    assert kept == cands and sized["size_factor"] == 1.5 and sized["new_exposure_cap"] is None and "1.5배" in shown["note"]
    big = op.build(kept, account(), "KR", state=sized)
    share = lambda plan: next(o["shares"] for o in plan["orders"] if o["ticker"] == "A")                   # noqa: E731
    assert share(small) < share(plain_plan) < share(big) and [o["ticker"] for o in small["orders"]] == ["A"]
    # the market's own brake stays: the factors multiply and the smaller cap holds
    bad = {"size_factor": 0.5, "new_exposure_cap": 0.5, "state": "ADVERSE"}
    assert stance.for_plan(cands, bad, marks, "AGGRESSIVE", op.STRATEGY_OF)[1]["size_factor"] == 0.75
    assert stance.for_plan(cands, bad, marks, "AGGRESSIVE", op.STRATEGY_OF)[1]["new_exposure_cap"] == 0.5
    assert stance.for_plan(cands, bad, marks, "DEFENSIVE", op.STRATEGY_OF)[1]["size_factor"] == 0.25


def test_the_stance_touches_no_score_no_record_and_no_fixed_book():
    from terminal import services
    from terminal.qsf import ledger, paper_book, rank_book, turnover_book
    from terminal.committee import council, portfolios
    for module in (engine, holding, ledger, paper_book, rank_book, turnover_book, council, portfolios):
        assert not re.search(r"qsf_stance|import stance|qsf import[^\n]*\bstance\b|stance\.py", inspect.getsource(module)), module.__name__      # none of them reads the module
    src = inspect.getsource(services.Terminal.order_plan)
    assert "qsf_stance.for_plan" in src and "op.build(cands, account, market, st, sized" in src            # only the real account's plan
    card = engine.score(ctx(), "SWING")
    assert "stance" not in card and "stance" not in ledger.FIELDS


def test_the_rank_rows_are_marked_only_when_a_stance_is_chosen(tmp_path):
    from terminal.qsf.views import ScreenViews

    class Led:
        def _live_rows(self):
            return [{"market": "US", "session": "2026-11-20", "file": "x"}]

        def _load(self, r):
            return [{**snap(f"T{k}", score=80.0, atr=1.0 + k, session="2026-11-20"), "confidence": "HIGH"} for k in range(6)]

    class V(ScreenViews):
        base, ledger = tmp_path, Led()
    v = V()
    rows = lambda: {"session": "2026-11-20", "generated_at": "g", "rows": [{"ticker": f"T{k}", "strategy": "SWING", "score": 80.0, "actionability": "ACTIONABLE"} for k in range(6)]}      # noqa: E731
    out = rows()
    v._stance_rows("US", out)
    assert out["stance"] == {"level": "NORMAL", "label": "기본", "line": 70.0} and all("stance" not in r for r in out["rows"])
    stance.set_level(tmp_path, "US", "DEFENSIVE")
    out = rows()
    v._stance_rows("US", out)
    by = {r["ticker"]: r["stance"] for r in out["rows"]}
    assert out["stance"]["level"] == "DEFENSIVE" and out["stance"]["from_record"] is True and by["T0"] == {"ok": True, "why": None} and by["T5"] == {"ok": False, "why": "하루 움직임이 큰 쪽 3분의 1"}


# ---------------------------------------------------------------------- '쉽게 설명해줘'
def _clean(doc):
    text = " ".join(plain.texts(doc))
    return [w for w in plain.AVOID if re.search(rf"(?<![A-Za-z]){re.escape(w)}(?![A-Za-z])" if w.isascii() else re.escape(w), text)]


def test_every_sentence_the_module_owns_keeps_the_hard_words_out():
    own = [s for pair in plain.FACTOR.values() for s in pair] + list(plain.ENTRY.values()) + list(plain.ENTRY_NOW.values()) + list(plain.GATE.values()) + list(plain.BAND.values()) \
        + list(plain.PORTFOLIO.values()) + list(plain.WORDS.values()) + [plain.CAVEAT, plain.PORTFOLIO_CAVEAT] + [v for pair in plain.STYLE.values() for v in pair]
    assert _clean({"title": "", "parts": [{"h": "", "lines": own}], "words": []}) == []
    assert len(plain.AVOID) >= 20 and "손익비" in plain.AVOID and "ATR" in plain.AVOID


def test_every_factor_entry_status_and_block_reason_has_plain_words():
    scored = {f for p in config.PROFILES.values() for d in p["domains"].values() for f in d}
    assert scored <= set(plain.FACTOR), sorted(scored - set(plain.FACTOR))
    statuses = set(re.findall(r'"status": "([A-Z_]+)"', inspect.getsource(holding.entry_status)))
    assert statuses - {"ENTRY_NOW"} <= set(plain.ENTRY), sorted(statuses - set(plain.ENTRY))
    gates = set(re.findall(r'add\("([A-Z_]+)"', inspect.getsource(engine.hard_gates)))
    assert gates and gates <= set(plain.GATE), sorted(gates - set(plain.GATE))
    assert {b[1] for b in config.BANDS} == set(plain.BAND)


def test_a_card_is_told_in_everyday_words(tmp_path):
    from tests.test_qsf import service
    q = service(tmp_path)
    cards = q.evaluate("AAA")["cards"]
    for strategy in ("SWING", "LONG_TERM"):
        doc = cards[strategy]["plain"]
        heads = [p["h"] for p in doc["parts"]]
        assert heads[:3] == ["한 줄로", "좋게 본 점", "걱정되는 점"] and heads[-1] == "꼭 알아 둘 것" and "지금 사도 되나" in heads and _clean(doc) == []
        assert f"100점 만점에 {cards[strategy]['score']:.0f}점" in doc["parts"][0]["lines"][0] and "아직 확인되지 않았고" in doc["parts"][-1]["lines"][0]
    swing = cards["SWING"]["plain"]
    assert any(p["h"].endswith("미리 정해 둘 가격") for p in swing["parts"]) and {w["word"] for w in swing["words"]} >= {"손절 가격", "목표 가격"}
    assert not any(p["h"].endswith("미리 정해 둘 가격") for p in cards["LONG_TERM"]["plain"]["parts"])
    assert "plain" not in __import__("terminal.qsf.ledger", fromlist=["FIELDS"]).FIELDS                      # shown, never recorded


def test_a_factor_computed_from_part_of_its_figures_is_not_spoken_for():
    full = {"factor": "balance_dilution", "normalized": 1.0, "weight": 5, "status": "REAL", "inputs": {"have": 2, "total": 2}}
    part = {**full, "inputs": {"have": 1, "total": 2}}                                                  # Korea: the debt is known, the share count is not
    plainly = {"factor": "liquidity", "normalized": 0.9, "weight": 4, "status": "REAL"}
    good, bad, unsaid = plain._sides({"factors": [full, plainly]})
    assert good == [plain.FACTOR["balance_dilution"][0], plain.FACTOR["liquidity"][0]] and unsaid == 0
    good, bad, unsaid = plain._sides({"factors": [part, plainly, {**part, "factor": "leverage", "normalized": 0.5}]})
    assert good == [plain.FACTOR["liquidity"][0]] and unsaid == 1                                       # the middling partial factor had nothing to say anyway
    doc = plain.card_plain({"actionability": "ACTIONABLE", "score": 64.0, "band": "HOLD_WATCH", "strategy": "LONG_TERM", "market": "KR", "entry_status": "ENTRY_NOW", "factors": [part, plainly]})
    assert "말하지 않은 것" in [p["h"] for p in doc["parts"]] and "주식 수" not in " ".join(plain.texts(doc)) and _clean(doc) == []


def test_a_blocked_or_unjudged_card_says_so_first():
    b = [dict(x) for x in bars()]
    b[-30]["high"] = b[-30]["low"] * 0.9
    blocked = plain.card_plain({**engine.score(ctx(bars=b), "SWING"), "market": "US", "strategy": "SWING", "price": 100.0})
    assert "막아 둔 종목" in blocked["parts"][0]["lines"][0] and "가격 자료에 이상한 값" in blocked["parts"][0]["lines"][0] and "지금 사도 되나" not in [p["h"] for p in blocked["parts"]]
    none = plain.card_plain({"actionability": "INSUFFICIENT_DATA", "score": 55.0, "strategy": "LONG_TERM", "market": "KR"})
    assert "자료가 모자라서" in none["parts"][0]["lines"][0] and len(none["parts"]) == 2 and _clean(blocked) == [] and _clean(none) == []
    weak = {k: v for k, v in GOOD_FUND.items() if k not in ("pe", "pb", "fcf_yield")}
    held = plain.card_plain({**engine.score(ctx(fund={**weak, "roe": 0.08, "op_margin": 0.06, "gross_margin": 0.3, "rev_growth": 0.02, "eps_growth": 0.02, "rev_cagr3": 0.02, "eps_cagr3": 0.02}), "LONG_TERM"),
                             "market": "US", "strategy": "LONG_TERM"})
    assert any("없는 부분을 '보통'으로 치면" in s for s in held["parts"][0]["lines"])
    assert plain.money(70500.4, "KR") == "70,500원" and plain.money(342.5, "US") == "342.50달러"


def test_a_portfolio_is_told_with_amounts_of_an_imagined_million_won():
    p = {"key": "GRAHAM", "name": "그레이엄식 포트폴리오", "holdings": [{"ticker": "AAA", "name": "가나다", "weight": 0.05}, {"ticker": "BBB", "name": "라마바", "weight": 0.05}],
         "invested": 0.10, "cash": 0.90, "sectors": {"금융": 0.10}, "exits": [{"ticker": "CCC"}]}
    doc = plain.portfolio_plain(p)
    text = " ".join(plain.texts(doc))
    assert "싸고 튼튼한 회사" in text and "주식에 10만 원, 현금으로 90만 원" in text and "가나다 5%(5만 원)" in text and "현금이 많은 이유" in [x["h"] for x in doc["parts"]]
    assert "실제 의견이 아니라" in text and "빠진 종목이 1개" in text and _clean(doc) == []
    empty = plain.portfolio_plain({"key": "MUNGER", "name": "멍거식 포트폴리오", "holdings": [], "invested": 0.0, "cash": 1.0})
    assert "전부 현금" in " ".join(plain.texts(empty))
    crowded = plain.portfolio_plain({**p, "sectors": {"금융": 0.45}, "invested": 0.9, "cash": 0.1})
    assert "금융이 45%로 가장 많습니다. 한 업종이 많으면" in " ".join(plain.texts(crowded))
    assert plain._subject("헬스케어") == "헬스케어가" and plain._subject("기술") == "기술이" and plain._subject("Technology") == "Technology이(가)"
    assert plain._pct(0.36) == "0.4" and plain._pct(-5.4) == "5"
