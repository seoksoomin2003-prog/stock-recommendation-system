"""QSF-1.3.0: the live Korean scan on the market-value top 300, and the record that still scores the former universe.  All offline."""
import gzip
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest

from terminal.qsf import config, kr_cap_universe as cu, kr_forward as kf, kr_traded_universe as tu, krx_history as kh, research_kr_live, service
from terminal.qsf.service import QSF

NOW = datetime(2026, 11, 11, 22, 30, tzinfo=timezone.utc)


def krx_day(base, day, n=320, empty=False):
    """One KRX day on file for both boards: ``n`` ordinary stocks, the larger the code the smaller the company."""
    for board in kh.BOARDS:
        rows = []
        if not empty:
            for k in range(n // 2):
                code = f"{(k * 2 + (board == 'KOSDAQ')):05d}0"            # ordinary shares end in 0
                row = {name: "" for name in kh.FIELDS}
                row.update(ISU_CD=code, ISU_NM=f"회사{code}", SECT_TP_NM="", TDD_OPNPRC="100", TDD_HGPRC="101", TDD_LWPRC="99", TDD_CLSPRC="100", FLUC_RT="0", ACC_TRDVOL="1000", ACC_TRDVAL="100000",
                           MKTCAP=str(10 ** 12 - int(code) * 10 ** 5), LIST_SHRS="1000")
                rows.append([row[name] for name in kh.FIELDS])
        p = kh.path_of(Path(base) / cu.KRX, board, day)
        p.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(p, "wt", encoding="utf-8") as fh:
            json.dump(rows, fh)


def days_on_file(base, last_day=10, count=25, **kw):
    for d in range(count):
        krx_day(base, f"2026-10-{d + 1:02d}" if d < count - last_day else f"2026-11-{d - (count - last_day) + 1:02d}", **kw)


@pytest.fixture
def no_master(monkeypatch):
    monkeypatch.setattr(research_kr_live, "_klass_from_master", lambda base: {})


def test_the_live_rule_is_market_value_and_the_former_rule_is_still_there():
    assert config.KR_UNIVERSE == "MARKET_CAP" and config.MODEL_VERSION == "QSF-1.6.0"
    src = (Path(__file__).resolve().parents[1] / "terminal" / "qsf" / "service.py").read_text(encoding="utf-8")
    assert 'elif config.KR_UNIVERSE == "MARKET_CAP":' in src and "self.kr_traded_value_universe(master, sessions, latest, now)" in src
    assert "universe.build(elig, ub[\"bars\"]" in src                 # the former rule's own code, unchanged


def test_the_universe_is_the_300_largest_on_the_newest_krx_day(tmp_path, no_master):
    days_on_file(tmp_path)
    q = QSF(tmp_path, src=object(), now=lambda: NOW)
    codes, info = q.kr_market_cap_universe("2026-11-10")
    assert len(codes) == 300 and codes[:3] == ["000000", "000010", "000020"] and codes[-1] == "002990" and "003190" not in codes
    assert info == {"rule": "MARKET_CAP", "krx_day": "2026-11-10", "members": 300, "size": 300, "same_day": True}
    assert codes == [m["code"] for m in cu.members(tmp_path / cu.KRX, "2026-11-10", {})]            # the market-value record's own rule
    later, info = q.kr_market_cap_universe("2026-11-11")                                            # the session's day is not on file yet: the day before stands in
    assert later == codes and info["krx_day"] == "2026-11-10" and info["same_day"] is False


def test_a_holiday_file_is_skipped_and_old_data_is_no_universe(tmp_path, no_master):
    days_on_file(tmp_path)
    krx_day(tmp_path, "2026-11-11", empty=True)
    q = QSF(tmp_path, src=object(), now=lambda: NOW)
    assert q.kr_market_cap_universe("2026-11-11")[1]["krx_day"] == "2026-11-10"
    with pytest.raises(RuntimeError, match="KRX daily data unavailable"):
        q.kr_market_cap_universe("2026-11-25")                                                      # fifteen days after the newest day on file
    with pytest.raises(RuntimeError, match="KRX daily data unavailable"):
        QSF(tmp_path / "empty", src=object(), now=lambda: NOW).kr_market_cap_universe("2026-11-10")


def test_the_scan_never_asks_krx_with_a_test_source_or_without_a_key(tmp_path, monkeypatch):
    called = []
    monkeypatch.setattr(kh, "download", lambda *a, **k: called.append(a))
    monkeypatch.setenv("KRX_API_KEY", "x")
    QSF(tmp_path, src=object(), now=lambda: NOW)._refresh_krx_days("2026-11-10")
    monkeypatch.delenv("KRX_API_KEY")
    QSF(tmp_path, now=lambda: NOW)._refresh_krx_days("2026-11-10")
    assert called == []
    monkeypatch.setenv("KRX_API_KEY", "x")
    monkeypatch.setattr(kh, "download", lambda *a, **k: (_ for _ in ()).throw(OSError("down")))
    QSF(tmp_path, now=lambda: NOW)._refresh_krx_days("2026-11-10")                                  # a failure leaves what is on file and raises nothing


# ---------------------------------------------------------------------- the record of the former universe
def scan_rows(codes, session="2026-11-11"):
    rows = []
    for n, c in enumerate(codes):
        for st, score in (("SWING", 30.0 + n % 40), ("LONG_TERM", 80.0 - n % 50)):
            rows.append({"ticker": c, "strategy": st, "score": score, "actionability": "ACTIONABLE", "data_date": session})
    return {"session": session, "model_version": "QSF-1.3.0", "rows": rows}


class Service:
    def __init__(self, codes, session="2026-11-11", fail=False):
        self.codes, self.session, self.fail, self.scans = codes, session, fail, []

    def regime(self, market):
        return {"session": self.session}

    def kr_former_universe_codes(self):
        if self.fail:
            raise RuntimeError("no bars")
        return self.codes

    def scan(self, market, tickers=None, record=True, side_files=True):
        self.scans.append((market, len(tickers), record, side_files))
        return scan_rows(tickers, self.session)

    def _entry_date(self, market, session):
        return datetime(2026, 11, 12).date()


FORMER = [f"{k:06d}" for k in range(100, 400)]          # 300 codes; the live universe below is 000000..000299


def test_the_doc_has_the_market_value_records_shape_with_the_roles_swapped():
    live = [f"{k:06d}" for k in range(300)]
    doc = tu.build_doc("2026-11-11", FORMER, scan_rows(FORMER), live, "2026-11-12")
    assert doc["universe"] == "TRADED_VALUE" and doc["protocol"] == tu.PROTOCOL and len(doc["rows"]) == 300 and doc["entry_session"] == "2026-11-12"
    first = doc["rows"][0]
    assert first == {"ticker": "000100", "in_live": True, "swing": 30.0, "long": 80.0, "swing_actionability": "ACTIONABLE", "long_actionability": "ACTIONABLE", "traded_rank": 1}
    assert sum(r["in_live"] for r in doc["rows"]) == 200 and doc["live_only"] == [f"{k:06d}" for k in range(100)]
    with pytest.raises(ValueError, match="TOO_FEW_STOCKS"):
        tu.build_doc("2026-11-11", FORMER, scan_rows(FORMER[:50]), live, "2026-11-12")


def test_record_waits_for_the_live_record_and_is_written_once_without_touching_live_files(tmp_path, monkeypatch):
    live = [f"{k:06d}" for k in range(300)]
    monkeypatch.setattr(cu, "live_tickers", lambda led, session: [])
    svc = Service(FORMER)
    assert tu.record(tmp_path, svc, now=lambda: NOW) == {"status": "WAITING", "reason": "LIVE_NOT_RECORDED", "session": "2026-11-11"} and svc.scans == []
    monkeypatch.setattr(cu, "live_tickers", lambda led, session: live)
    assert tu.record(tmp_path, Service(FORMER, fail=True), now=lambda: NOW)["reason"] == "UNIVERSE_NOT_BUILT"
    assert tu.record(tmp_path, Service(FORMER[:50]), now=lambda: NOW)["reason"] == "TOO_FEW_MEMBERS"
    assert tu.record(tmp_path, Service(FORMER, session="2026-11-10"), now=lambda: NOW)["reason"] == "BEFORE_FIRST"
    got = tu.record(tmp_path, svc, now=lambda: NOW)
    assert got == {"status": "OK", "written": ["2026-11-11"], "stocks": 300, "overlap": 200} and svc.scans == [("KR", 300, False, False)]
    assert tu.record(tmp_path, svc, now=lambda: NOW) == {"status": "OK", "written": [], "last": "2026-11-11"} and len(svc.scans) == 1
    assert kf.verify(tmp_path, tu.FOLDER)["status"] == "OK" and tu.status(tmp_path)["records"] == 1 and not (tmp_path / cu.FOLDER).exists()


def test_the_reading_tells_the_universes_apart_only_with_both_halves_and_a_clear_lead():
    rng = np.random.default_rng(3)
    def days(lead):
        return [{"live_net": lead + float(x), "universe_net": 0.0} for x in rng.normal(0, 0.01, 240)]
    assert tu.universe_reading(days(0.02))["reading"] == "SWITCH_SUPPORTED"
    assert tu.universe_reading(days(-0.02))["reading"] == "FORMER_BETTER"
    assert tu.universe_reading(days(0.0))["reading"] in ("NOT_DISTINGUISHED", "SAME_DIRECTION_NOT_SIGNIFICANT")
    split = [{"live_net": 0.02, "universe_net": 0.0}] * 120 + [{"live_net": -0.02, "universe_net": 0.0}] * 120
    assert tu.universe_reading(split)["reading"] == "NOT_DISTINGUISHED"


def test_evaluation_is_refused_before_240_matured_days_and_runs_once(tmp_path, monkeypatch):
    monkeypatch.setattr(cu, "live_tickers", lambda led, session: [f"{k:06d}" for k in range(300)])
    tu.record(tmp_path, Service(FORMER), now=lambda: NOW)

    class Panel:
        dates = ["2026-11-11", "2026-11-12"] + [f"d{k}" for k in range(30)]
    with pytest.raises(RuntimeError, match="240개"):
        tu.evaluate_once(tmp_path, panel=Panel())
    (tmp_path / tu.REPORT).parent.mkdir(parents=True)
    (tmp_path / tu.REPORT).write_text(json.dumps({}))
    with pytest.raises(RuntimeError, match="한 번만"):
        tu.evaluate_once(tmp_path, panel=Panel())


def test_the_plan_is_written_and_the_record_is_backed_up_and_wired_into_the_daily_step():
    root = Path(__file__).resolve().parents[1]
    text = (root / tu.PROTOCOL).read_text(encoding="utf-8")
    assert all(w in text for w in ("SWITCH_SUPPORTED", "FORMER_BETTER", "NOT_DISTINGUISHED", "240개"))
    from terminal import automation
    assert "kr_traded_universe" in automation.FORWARD_STORES and any("kr_traded_universe/index.jsonl" in g for g in automation.BACKUP_GLOBS)
    app = (root / "app.py").read_text(encoding="utf-8")
    assert 'res["traded_universe"] = kr_traded_universe.record(PROJECT_ROOT, QSF(PROJECT_ROOT))' in app and '"kr-traded-universe-evaluate"' in app


# ---------------------------------------------------------------------- what the screen says
def test_the_notice_names_the_live_universe_its_weak_evidence_and_the_new_swing_composition():
    root = Path(__file__).resolve().parents[1]
    n = config.VALIDATION_NOTICE
    assert "시가총액 상위 300" in n and "기준에 못 미쳤" in n and "거래대금 상위 300" in n and "차트 항목을 뺀" in n and "상위와 하위 묶음의 수익이 같았" in n
    assert n.split("근거를 찾지 못했습니다. ", 1)[1] in (root / "terminal" / "static" / "qsf.js").read_text(encoding="utf-8")
    assert "시가총액 상위 300" in service.QSF._kr_scan_input.__code__.co_consts or "시가총액 상위 300 (스캔 대상)" in (root / "terminal" / "qsf" / "service.py").read_text(encoding="utf-8")
