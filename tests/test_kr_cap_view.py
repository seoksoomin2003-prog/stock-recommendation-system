"""The screen's second Korean list: the newest day of the market-value universe record, read only."""
import gzip
import json
from datetime import datetime, timezone
from pathlib import Path

from terminal.qsf import kr_cap_view as cv, kr_forward as kf

AT = datetime(2026, 11, 10, 23, 0, tzinfo=timezone.utc)


def doc(session, n=40):
    rows = [{"ticker": f"{k:06d}", "cap_rank": k + 1, "cap": 1e12 / (k + 1), "in_live": k % 3 != 0, "swing": None if k == 5 else 30.0 + k, "long": 90.0 - k,
             "swing_actionability": "BLOCKED" if k == 39 else "ACTIONABLE", "long_actionability": "ACTIONABLE"} for k in range(n)]
    return {"session": session, "protocol": cv.PROTOCOL, "size": 300, "members": 300, "entry_session": "2026-11-11", "model_version": "QSF-1.2.0", "live_only": ["900001", "900002"], "rows": rows}


def write(base, session):
    assert kf.write_record(base, session, AT, False, store=cv.FOLDER, scorer=lambda b, d: doc(d))


def test_no_record_is_unavailable_and_the_newest_day_is_shown(tmp_path):
    assert cv.view(tmp_path)["status"] == "UNAVAILABLE"
    write(tmp_path, "2026-11-10")
    write(tmp_path, "2026-11-11")
    got = cv.view(tmp_path, "SWING", name_of=lambda c: f"회사{c}", top=10)
    assert got["status"] == "REAL" and got["session"] == "2026-11-11" and got["records"] == 2 and got["model_version"] == "QSF-1.2.0"
    assert [r["ticker"] for r in got["rows"][:2]] == ["000039", "000038"] and got["rows"][0] == {"rank": 1, "ticker": "000039", "name": "회사000039", "cap_rank": 40, "score": 69.0, "in_live": False, "actionability": "BLOCKED"}
    assert got["scored"] == 39 and len(got["rows"]) == 10                       # the stock without a swing score is left out, not shown as zero
    assert got["in_both"] == 26 and got["cap_only"] == 14 and got["live_only"] == 2 and got["buy_band"] == 0 and len(got["notes"]) == 4


def test_the_long_view_sorts_by_the_long_score_and_nothing_is_written(tmp_path):
    write(tmp_path, "2026-11-10")
    before = sorted((p.name, p.read_bytes()) for p in (tmp_path / cv.FOLDER).iterdir())
    got = cv.view(tmp_path, "LONG_TERM")
    assert got["strategy"] == "LONG_TERM" and got["rows"][0]["ticker"] == "000000" and got["rows"][0]["score"] == 90.0 and got["buy_band"] == 21 and got["rows"][0]["name"] is None
    assert cv.view(tmp_path, "NONSENSE")["strategy"] == "SWING"
    assert sorted((p.name, p.read_bytes()) for p in (tmp_path / cv.FOLDER).iterdir()) == before and kf.verify(tmp_path, cv.FOLDER)["status"] == "OK"


def test_the_view_shares_the_records_folder_and_plan_and_never_imports_the_evaluation():
    root = Path(__file__).resolve().parents[1]
    src = (root / "terminal" / "qsf" / "kr_cap_view.py").read_text(encoding="utf-8")
    assert "import kr_cap_universe" not in src and "forward(" not in src and "evaluate" not in src
    from terminal.qsf import kr_cap_universe as cu
    assert cv.FOLDER == cu.FOLDER and cv.PROTOCOL == cu.PROTOCOL
    assert "/api/qsf/cap-universe" in (root / "terminal" / "server.py").read_text(encoding="utf-8")
    js = (root / "terminal" / "static" / "qsf.js").read_text(encoding="utf-8")
    assert "qsfCap();" in js and 'id="qsfcap"' in js and "비교용" in js
