"""UI audit items 1-3 (reports/UI_AUDIT_2026_11_23.md, user decisions 2026-11-23): the balance box on the score card, the ranking
table's notes, Today's figures and candidates with the job's own lines kept apart.  Display only: nothing here scores or records."""
from pathlib import Path

import pytest

from terminal import assistant as A
from terminal.qsf import rank_notes as RN
from terminal.services import Terminal
from tests.test_assistant import FakeTerminal, quiet_job  # noqa: F401  (quiet_job: autouse fixture)

ROOT = Path(__file__).resolve().parents[1]


def f(fid, w, n, scored=True, status="REAL"):
    return {"factor": fid, "weight": w, "normalized": n, "contribution": None if n is None else w * n, "scored": scored, "status": status, "reason": f"{fid} 근거"}


FACTORS = [f("trend_structure", 8, 0.95), f("momentum_12_1", 6, 0.7), f("relative_strength", 4, 0.62), f("rsi_state", 3, 0.55), f("valuation", 5, 0.2),
           f("insider_activity", 2, 0.1), f("atr_risk", 4, 0.35), f("liquidity", 3, 0.5), f("analyst_revision", 4, None, status="MISSING"),
           f("vix_regime", 0, 0.9, scored=False), {"factor": "volume_confirmation", "weight": 0, "normalized": 0.8, "contribution": None, "scored": False, "status": "REAL"}]


def engine_score(factors):
    used = [x for x in factors if x["contribution"] is not None and x["weight"] > 0 and x["scored"] is not False]
    return 100.0 * sum(x["weight"] * x["normalized"] for x in used) / sum(x["weight"] for x in used)


# ---------------------------------------------------------------------- the balance box
def test_the_pushes_add_up_to_the_score_minus_fifty_and_follow_the_engine_rule():
    b = RN.balance(FACTORS)
    assert b["points_sum"] == pytest.approx(engine_score(FACTORS) - 50.0, abs=1e-9)
    assert [p["factor"] for p in b["plus"]] == ["trend_structure", "momentum_12_1", "relative_strength"]          # 0.6 or more, largest push first, three
    assert [p["factor"] for p in b["minus"]] == ["valuation", "insider_activity", "atr_risk"]                    # 0.4 or less, largest pull first (-1.5, -0.8, -0.6 weighted)
    assert all(p["points"] > 0 for p in b["plus"]) and all(p["points"] < 0 for p in b["minus"])
    assert b["plus"][0]["points"] == pytest.approx(100 * 0.45 * 8 / 35)                                          # weights with data: 35
    assert b["missing"] == [RN._name("analyst_revision")] and "vix_regime" not in {p["factor"] for p in b["plus"]}  # reference rows never push
    assert b["labels"]["trend_structure"] == RN._name("trend_structure") and b["plus"][0]["text"] == "trend_structure 근거"


def test_no_scored_data_gives_no_balance_and_the_short_line_keeps_one_each_way():
    empty = RN.balance([f("valuation", 5, None, status="MISSING")])
    assert empty["points_sum"] is None and empty["plus"] == [] and empty["minus"] == [] and empty["missing"]
    s = RN.short(RN.balance(FACTORS))
    assert s["plus"]["label"] == RN._name("trend_structure") and s["minus"]["label"] == RN._name("valuation") and s["minus"]["points"] < 0
    assert RN.short({"plus": [], "minus": []}) == {"plus": None, "minus": None}


# ---------------------------------------------------------------------- the ranking notes, read from the ledger
class Ledger:
    def __init__(self, snaps):
        self.snaps = snaps

    def _index_stamp(self):
        return len(self.snaps)

    def _live_rows(self):
        return [{"market": m, "session": d} for m, d in sorted({(s["market"], s["session"]) for s in self.snaps})]

    def _load(self, r):
        return [s for s in self.snaps if s["market"] == r["market"] and s["session"] == r["session"]]


def snap(t, session, score, strategy="SWING", market="US", data_date=None, factors=FACTORS):
    return {"ticker": t, "market": market, "session": session, "strategy": strategy, "score": score, "data_date": data_date or session, "factors": factors}


def test_notes_carry_the_previous_score_and_skip_rows_from_another_day():
    led = Ledger([snap("AAA", "2026-11-19", 60.0), snap("AAA", "2026-11-20", 64.0), snap("BBB", "2026-11-20", 55.0), snap("CCC", "2026-11-20", 50.0, data_date="2026-11-19"),
                  snap("AAA", "2026-11-20", 64.0, market="KR")])
    got = RN.notes(led, "US", "2026-11-20")
    assert set(got) == {("AAA", "SWING"), ("BBB", "SWING")}                         # CCC's prices were a day old: not this session's row
    assert got[("AAA", "SWING")]["prev"] == 60.0 and got[("BBB", "SWING")]["prev"] is None and got[("AAA", "SWING")]["prev_session"] == "2026-11-19"
    assert got[("AAA", "SWING")]["plus"]["label"] == RN._name("trend_structure")
    assert RN.previous_session(led, "US", "2026-11-19") is None


class Qsf:
    def __init__(self, status="REAL"):
        self.status, self.calls = status, 0
        self.ledger = Ledger([snap("AAA", "2026-11-19", 60.0), snap("AAA", "2026-11-20", 64.0)])

    def latest(self, market):
        return {"status": self.status, "session": "2026-11-20", "generated_at": "2026-11-20T22:00:00"}

    def screen_rows(self, market):
        self.calls += 1
        return {"rows": [{"ticker": "AAA", "sector": "Technology"}]}


def test_the_terminal_serves_the_notes_once_per_scan_and_says_when_there_is_none(tmp_path):
    t = Terminal(tmp_path)
    t._qsf = Qsf()
    a, b = t.rank_notes("US"), t.rank_notes("US")
    assert a is b and t._qsf.calls == 1 and a["status"] == "REAL" and a["rows"]["AAA|SWING"]["prev"] == 60.0 and a["sectors"] == {"AAA": "Technology"}
    assert a["prev_session"] == "2026-11-19" and "총점 − 50" in a["note"]
    t._qsf.ledger.snaps.append(snap("BBB", "2026-11-20", 51.0))                     # a new snapshot in the ledger: read again
    assert "BBB|SWING" in t.rank_notes("US")["rows"]
    t._qsf = Qsf(status="NO_SCAN")
    assert t.rank_notes("KR") == {"status": "NO_SCAN", "market": "KR"}
    src = (ROOT / "terminal" / "services.py").read_text(encoding="utf-8")
    assert '"balance": rank_notes.balance(c.get("factors") or [])' in src                # the card's box comes from the card's own factors
    assert '("GET", "/api/qsf/rank-notes")' in (ROOT / "terminal" / "server.py").read_text(encoding="utf-8")


# ---------------------------------------------------------------------- Today: figures, candidates, the job's lines apart
def item(sym, name):
    return {"symbol": sym, "name": name, "close": 1.0, "change_pct": 0.1, "status": "REAL"}


def test_tiles_keep_a_fixed_order_and_leave_out_what_the_overview_lacks():
    ov = {"groups": [{"items": [item("^VIX", "VIX"), item("^GSPC", "S&P 500"), item("XLK", "기술")]}], "source": "Yahoo", "cache": {"fetched_at": "2026-11-23T00:00:00Z"}}
    got = A.tiles(ov, "US", {"score_100": 15.4, "state": "ADVERSE", "label": "나쁨", "size_factor": 0.5, "session": "2026-11-20", "factors": []})
    assert [i["symbol"] for i in got["items"]] == ["^GSPC", "^VIX"] and got["market_state"]["score_100"] == 15.4 and "factors" not in got["market_state"]
    assert got["source"] == "Yahoo" and got["fetched_at"] == "2026-11-23T00:00:00Z"
    assert A.tiles({"groups": []}, "KR", {"score_100": None})["market_state"] is None


def cand(t, score, strategy="SWING", entry="ENTRY_NOW", act="ACTIONABLE"):
    return {"ticker": t, "name": t, "strategy": strategy, "score": score, "entry_status": entry, "actionability": act, "band_label": "구간"}


def test_candidates_are_the_enter_now_rows_by_score_as_the_order_plan_reads_them():
    rows = [cand("A", 61.0), cand("B", 75.0), cand("C", 90.0, entry="WAIT_FOR_PULLBACK"), cand("D", 88.0, act="BLOCKED"), cand("E", 72.0), cand("F", None)] + \
           [cand(f"L{k}", 50.0 + k, "LONG_TERM") for k in range(8)]
    notes = {"session": "2026-11-20", "rows": {"B|SWING": {"plus": {"label": "추세 구조", "points": 6.2}, "minus": None, "prev": 73.0, "prev_session": "2026-11-19"}},
             "sectors": {"B": "Technology"}}
    got = A.candidates(rows, notes)
    sw, lt = got["styles"]["SWING"], got["styles"]["LONG_TERM"]
    assert [r["ticker"] for r in sw["rows"]] == ["B", "E", "A"] and sw["total"] == 3 and sw["buy_band"] == 2
    assert sw["rows"][0]["plus"]["label"] == "추세 구조" and sw["rows"][0]["prev"] == 73.0 and sw["rows"][0]["sector"] == "Technology" and "prev" not in sw["rows"][1]
    assert lt["total"] == 8 and len(lt["rows"]) == A.CANDIDATES_SHOWN == 5 and lt["buy_band"] == 0 and got["session"] == "2026-11-20"
    assert "매수 신호가 아닙니다" in got["note"]
    from terminal.qsf import order_plan
    assert order_plan.ENTRY_READY == "ENTRY_NOW"


class TodayTerminal(FakeTerminal):
    def __init__(self, base, notes_fail=False):
        super().__init__(base)
        self.notes_fail = notes_fail

    def overview(self, market="US"):
        return {"groups": [{"title": "지수", "items": [item("^KS11", "코스피"), item("KRW=X", "원/달러")]}], "source": "Yahoo", "cache": {"fetched_at": "2026-11-23T00:00:00Z"}}

    def rank_notes(self, market="US"):
        if self.notes_fail:
            raise OSError("ledger")
        return {"status": "REAL", "session": "2026-11-20", "rows": {}, "sectors": {}}


def test_the_briefing_adds_figures_and_candidates_and_marks_the_job_lines(tmp_path, monkeypatch):
    from terminal import automation
    monkeypatch.setattr(automation, "status", lambda base: {"installed": False, "steps": {}, "latest_session": "2026-11-20", "notes": []})
    b = A.briefing(TodayTerminal(tmp_path), "KR")
    assert [i["symbol"] for i in b["tiles"]["items"]] == ["^KS11", "KRW=X"] and b["tiles"]["market_state"]["label"] == "나쁨"
    assert set(b["candidates"]["styles"]) == {"SWING", "LONG_TERM"}
    ops = [i for i in b["items"] if i.get("ops")]
    assert ops and all(i["kind"] in A.OPS_KINDS for i in ops) and all(i["kind"] not in A.OPS_KINDS for i in b["items"] if not i.get("ops"))
    # the first line ends with the market-state clause on an adverse day (UI batch 1, user decision 2026-11-23); this stand-in's KR day is 25/100
    assert b["headline"] == A.headline(b["items"]) and b["headline_main"] == A.headline([i for i in b["items"] if not i.get("ops")]) + " 시장 상태 나쁨(25/100)."
    cut = A.briefing(TodayTerminal(tmp_path, notes_fail=True), "KR")
    assert cut["candidates"] is None and {"part": "candidates", "label": "오늘의 후보", "error": "OSError"} in cut["unread_parts"]
    plain = A.briefing(FakeTerminal(tmp_path), "KR")                               # a terminal without the notes: no candidates, nothing unread
    assert plain["candidates"] is None and not [p for p in plain["unread_parts"] if p["part"] == "candidates"]


# ---------------------------------------------------------------------- the screens
def body(src, start, end):
    i = src.index(start)
    return src[i:src.index(end, i)]


def test_the_screens_read_the_new_fields():
    qsf = (ROOT / "terminal" / "static" / "qsf.js").read_text(encoding="utf-8")
    detail = body(qsf, "function qsfDrawDetail(", "\n}")
    order = [detail.index(k) for k in ('<div class="qsf-cards">', "icCardHtml(d.committee", 'id="qsffc"', 'id="qsftoday"', 'id="qsfhistory"')]
    assert order == sorted(order)                                                 # scores first, the day's check folded near the end
    assert "qsfToday($(\"#qsftoday\")" in body(detail, "todayFold.addEventListener", "\n")
    card = body(qsf, "function qsfCard(", "\n}")
    assert "${qsfBalance(c.balance)}" in card and "qsfMarketState(" not in card and "names[f.factor] || f.factor" in card
    rank = body(qsf, "async function qsfRank(", "\n}")
    assert "/api/qsf/rank-notes?market=" in rank and "qsfRankRow(" in rank and "nt.session === d.session" in rank and rank.count("qsfMarketState(") == 0      # batch 2: the strip holds it
    assert "slice(0, 50)" in rank and "qsfFillRow(slot" in rank and 'class="qsf-exp-row"' in qsf and "QSF_RANK_COLS = 12" in qsf
    row = body(qsf, "function qsfRankRow(", "\n}")
    assert row.count("<td") == 10 and row.count("QSF_RANK_DOMAINS.map(dom)") == 1 and 'colspan="${QSF_RANK_COLS}"' in row     # 8 cells + 4 domain cells = 12, and the fold
    asst = (ROOT / "terminal" / "static" / "assistant.js").read_text(encoding="utf-8")
    today = body(asst, "async function renderToday(", "\n}")
    assert "d.headline_main || d.headline" in today and "asstTiles(d.tiles)" in today and "asstCands(d.candidates, d.note)" in today and "i.ops" in today
    assert "redrawers.delete(asstSparks)" in today and "spark(cv" in today
    css = (ROOT / "terminal" / "static" / "style.css").read_text(encoding="utf-8")
    assert ".qsf-rank-tbl .w, .qsf-rank-tbl .w2, .asst-cand .w { display: none; }" in body(css, "@media (max-width: 640px) {", "\n}") and ".qsf-balance {" in css
