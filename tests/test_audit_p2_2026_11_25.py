"""Score audit of 2026-11-25, roadmap level P2: how far a score moves in a day, the risk domain beside the rest, the shape of the
long-term top fifth, two small defects, and documents that had fallen behind the code.  No score, band line or record changes."""
import math
from pathlib import Path

import pytest

from terminal import analyst_extra as ax
from terminal.qsf import engine, inventory, rank_notes, sector_picks
from tests.test_ui_batch_1 import body, node

ROOT = Path(__file__).resolve().parents[1]
QSF = (ROOT / "terminal" / "static" / "qsf.js").read_text(encoding="utf-8")
PRE = 'const isNum = (v) => typeof v === "number" && isFinite(v); const esc = (s) => String(s); const qsfState = { strategy: "SWING" };\n'


class Book:
    """Two recorded sessions of 40 stocks: every swing score moves by its index over ten."""

    def __init__(self, versions=("QSF-1.6.0", "QSF-1.6.0"), n=40):
        self.versions, self.n = versions, n

    def _live_rows(self):
        return [{"market": "US", "session": "2026-11-25"}, {"market": "US", "session": "2026-11-26"}, {"market": "KR", "session": "2026-11-26"}]

    def _load(self, r):
        if r["market"] != "US":
            return []
        late = r["session"] == "2026-11-26"
        return [{"ticker": f"T{k:02d}", "strategy": s, "score": 50.0 + (k / 10 if late and s == "SWING" else 0.0), "data_date": r["session"], "model_version": self.versions[late]}
                for k in range(self.n) for s in ("SWING", "LONG_TERM")]


def test_the_daily_move_is_read_from_the_two_newest_sessions():
    got = rank_notes.daily_move(Book(), "US", "2026-11-26")
    sw, lt = got["SWING"], got["LONG_TERM"]
    assert sw["n"] == 40 and sw["median"] == pytest.approx(2.0) and sw["p90"] == pytest.approx(3.6) and sw["prev_session"] == "2026-11-25" and sw["same_formula"] is True
    assert lt["median"] == 0.0 and lt["p90"] == 0.0
    assert rank_notes.daily_move(Book(versions=("QSF-1.5.2", "QSF-1.6.0")), "US", "2026-11-26")["SWING"]["same_formula"] is False     # the move includes the formula's change
    assert rank_notes.daily_move(Book(), "US", "2026-11-25") == {} and rank_notes.daily_move(Book(n=10), "US", "2026-11-26") == {}       # no day before, or too few stocks: nothing
    assert '"daily_move": rank_notes.daily_move(self.qsf.ledger, market, session)' in (ROOT / "terminal" / "services.py").read_text(encoding="utf-8")
    fn = PRE + body(QSF, "function qsfMoveLine(")
    lines = node(fn + """
const m = { median: 1.1, p90: 3.5, n: 504, prev_session: "2026-11-25", same_formula: true };
console.log(JSON.stringify([qsfMoveLine({ daily_move: { SWING: m } }), qsfMoveLine({ daily_move: { SWING: { ...m, same_formula: false } } }), qsfMoveLine({ daily_move: {} }), qsfMoveLine(null)]));""")
    assert "절반이 1.1점 안에서, 열에 하나는 3.5점 넘게" in lines[0] and "내일 다른 구간일 수 있습니다" in lines[0] and "공식이 달라" not in lines[0]
    assert "공식이 바뀐 몫도 섞여 있습니다" in lines[1] and lines[2] == "" and lines[3] == ""
    assert "${qsfLineToday(scoredRows, mk)}${qsfMoveLine(notes)}" in QSF


def test_the_card_puts_the_risk_domain_beside_the_rest():
    fn = PRE + body(QSF, "function qsfRiskBeside(")
    got = node(fn + """
const c = { domains: { TECHNICAL: { score_100: 80, max_points: 40 }, FUNDAMENTAL: { score_100: 40, max_points: 10 }, RISK: { score_100: 66, max_points: 20 }, EVENTS: { score_100: null, max_points: 10 },
  REGIME: { score_100: 10, max_points: 20, reference: true } } };
console.log(JSON.stringify([qsfRiskBeside(c), qsfRiskBeside({ domains: { RISK: { score_100: 50, max_points: 20, reference: true } } }), qsfRiskBeside({ domains: { RISK: { score_100: 50, max_points: 20 } } })]));""")
    assert "위험 영역 <b>66</b>/100 · 그 밖의 영역 <b>72</b>/100" in got[0] and "위험이 낮다는 뜻입니다" in got[0]      # (80*40 + 40*10) / 50, the reference domain and the empty one left out
    assert got[1] == "" and got[2] == "" and "${qsfRiskBeside(c)}" in QSF


def long_snap(k, n=50):
    """Long-term stock k of n: a higher score goes with a lower PER, a higher ROE and a calmer price."""
    return {"ticker": f"T{k:02d}", "strategy": "LONG_TERM", "score": 30.0 + k, "actionability": "ACTIONABLE",
            "factors": [{"factor": "valuation", "raw": {"pe": 40.0 - 0.5 * k}}, {"factor": "business_quality", "raw": {"roe": 0.02 + 0.004 * k}}, {"factor": "downside_drawdown", "raw": {"downside_vol": 0.50 - 0.006 * k}}]}


def test_the_long_term_top_fifth_is_described_by_its_shape():
    snaps = [long_snap(k) for k in range(50)] + [{**long_snap(49), "strategy": "SWING"}]
    t = ax.tilt_long(snaps)
    assert t["n"] == 50 and t["top_n"] == 10 and t["pe_top"] == pytest.approx(40 - 0.5 * 44.5) and t["roe_all"] == pytest.approx(0.02 + 0.004 * 24.5)
    line = ax.tilt_long_line(t)
    assert line.startswith("장기 점수 상위 5분의 1(10종목)의 모양: PER 중앙값 17.8배(스캔 전체 27.8배, 흑자 회사만), ROE 중앙값 20%(전체 12%), 하방 변동성 중앙값 23%(전체 35%).")
    assert line.endswith("더 오른다는 근거는 아직 확인되지 않았습니다.") and "덜 흔들렸" not in line
    loss = [{**long_snap(k), "factors": [{"factor": "valuation", "raw": {"pe": -5.0}}]} for k in range(50)]
    assert ax.tilt_long_line(ax.tilt_long(loss)) is None and ax.tilt_long(snaps[:20]) is None            # no positive PER on file, or too few stocks: nothing is said
    src = (ROOT / "terminal" / "assistant.py").read_text(encoding="utf-8")
    assert 'part("mix", tilt_long)' in src and "ax.tilt_long_line(ax.tilt_long(_snaps(terminal, market, session)))" in src


def test_a_score_that_is_not_a_number_is_no_score_and_the_sector_count_includes_the_band_of_eighty():
    assert engine.classify(float("nan")) == {"band": "NONE", "band_label": "점수 없음"} and engine.action_for(float("nan"), False) == "INSUFFICIENT_DATA"
    assert engine.classify(12.0)["band"] == "SELL_AVOID" and engine.classify(None)["band"] == "NONE" and math.isnan(float("nan"))
    src = (ROOT / "terminal" / "qsf" / "sector_picks.py").read_text(encoding="utf-8")
    assert 'r.get("band") in ("STRONG_BUY_CANDIDATE", "BUY_CANDIDATE")' in src and sector_picks is not None


def test_the_documents_say_what_the_code_does():
    f = inventory.factors()
    assert "스캔이 없으면" in f["relative_strength"]["measures"] and "63거래일 변화" in f["usdkrw_regime"]["measures"] and "0.925가 상한" in f["breakout_volume"]["limit"]
    assert "0.6이 상한" in f["material_disclosures"]["limit"] and "새것 8건만" in f["insider_activity"]["limit"]
    assert any(case.startswith("오래된 자료(STALE)") for case, _ in inventory.MISSING_RULES) and any("한국 스윙 37점 만점" in w for w in inventory.WEIGHTS_WHY)
    assert inventory.markdown() == (ROOT / "reports" / "QSF_FACTOR_INVENTORY.md").read_text(encoding="utf-8")
    old = (ROOT / "reports" / "QSF_1_1_FACTOR_MAPPING.md").read_text(encoding="utf-8")
    assert "이 문서는 2026-11-11까지의 옛 기록입니다" in old.split("## ")[0] and "QSF_FACTOR_INVENTORY.md" in old.split("## ")[0]
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "`US_SWING_V2`, `US_LONG_TERM_V2`" in readme and "`KR_SWING_V3`, `KR_LONG_TERM_V2`" in readme and "US_SWING_V1" not in readme
    assert "같은 날 R-2로 바뀜" in (ROOT / "reports" / "QSF_FORMULA_FREEZE_2026_11_25.md").read_text(encoding="utf-8")
    errata = (ROOT / "reports" / "QSF_BACKTEST_CURRENT_ERRATA.md").read_text(encoding="utf-8")
    assert "| 10 |" in errata and "| 11 |" in errata and "틀린 것을 찾지 못했습니다" in errata
