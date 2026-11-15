"""Korean market-value universe challenger: the membership rule, the write-once record, the refusals and the evaluation's readings.  All offline."""
from types import SimpleNamespace
import gzip
import json
from datetime import date, datetime, timedelta, timezone

import numpy as np
import pytest

from terminal.qsf import kr_cap_universe as cu, kr_forward as kf, krx_history as kh
from terminal.qsf.service import QSF

NOW = datetime(2026, 11, 11, 22, 30, tzinfo=timezone.utc)
S = "2026-11-11"
KLASS = {"777770": "TRUST_AND_COLLECTIVE_INVESTMENT"}


def weekdays_back(n, end=date(2026, 11, 11)):
    out, d = [], end
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d -= timedelta(days=1)
    return out


def row(code, name, close, vol, cap, section="중견기업부"):
    r = [None] * len(kh.FIELDS)
    for k, v in (("ISU_CD", code), ("ISU_NM", name), ("SECT_TP_NM", section), ("TDD_CLSPRC", close), ("ACC_TRDVOL", vol), ("MKTCAP", cap)):
        r[kh.FIELDS.index(k)] = v
    return r


def write_day(root, day, kospi, kosdaq):
    for board, rows in (("KOSPI", kospi), ("KOSDAQ", kosdaq)):
        p = kh.path_of(root, board, day)
        p.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(p, "wt", encoding="utf-8") as fh:
            json.dump(rows, fh)


def market(root, days=45, halted=(), young=None, holiday=None):
    """320 common stocks whose market value falls with the code, plus a SPAC, a foreign issuer, a preferred share and a fund vehicle."""
    for n, day in enumerate(weekdays_back(days)):
        if day == holiday:
            write_day(root, day, [], [])
            continue
        rows = [row(f"{k:05d}0", f"회사{k}", "1,000", 0 if (f"{k:05d}0" in halted and n < 5) else 500, str(10_000_000 - k * 1000)) for k in range(1, 321)
                if not (young and f"{k:05d}0" == young and n >= 10)]
        odd = [row("900010", "외국기업", 1000, 500, 9e12), row("400010", "미래스팩1호", 1000, 500, 9e12), row("000015", "회사우", 1000, 500, 9e12), row("777770", "맥쿼리펀드", 1000, 500, 9e12)]
        write_day(root, day, rows[:200] + odd, rows[200:])


def test_membership_is_the_largest_three_hundred_that_trade(tmp_path):
    root = tmp_path / cu.KRX
    market(root, halted=("000020",), young="000030", holiday=weekdays_back(3)[-1])
    mem = cu.members(root, S, KLASS)
    codes = [m["code"] for m in mem]
    assert len(mem) == 300 and codes[0] == "000010" and mem[0]["rank"] == 1 and mem[0]["cap"] == 9_999_000.0
    assert not {"900010", "400010", "000015", "777770", "000020", "000030"} & set(codes)      # foreign, SPAC, preferred, fund vehicle, halted, too new
    assert codes[-1] == "003020"                                                             # the two dropped names are replaced by the next two
    assert cu.members(root, "2026-11-12", {}) == []                                          # no snapshot of that day yet
    assert len(cu.recent_days(root, S)) == 40                                                # the holiday's empty files are not a day


def scan_rows(codes, session=S, stale=()):
    out = []
    for n, c in enumerate(codes):
        for strategy in ("SWING", "LONG_TERM"):
            out.append({"ticker": c, "strategy": strategy, "score": 40 + n % 50, "actionability": "ACTIONABLE", "data_date": "2026-11-10" if c in stale else session})
    return out


class FakeService:
    def __init__(self, session=S, scan_session=None, stale=()):
        self.session, self.scan_session, self.stale, self.calls = session, scan_session or session, stale, []

    def regime(self, market):
        return {"session": self.session}

    def scan(self, market, tickers=None, record=True, side_files=True):
        self.calls.append({"n": len(tickers), "record": record, "side_files": side_files})
        return {"status": "REAL", "session": self.scan_session, "model_version": "QSF-1.1.8", "rows": scan_rows(tickers, self.scan_session, self.stale)}

    def _entry_date(self, market, session):
        return date(2026, 11, 12)


class FakeLedger:
    n = 300

    def __init__(self, root):
        pass

    def _live_rows(self):
        return [{"market": "KR", "session": S}, {"market": "US", "session": S}]

    def _load(self, r):
        return [{"ticker": f"{k:05d}0", "strategy": "SWING", "score": 50.0, "data_date": S} for k in range(101, 101 + self.n)] if r["market"] == "KR" else []


@pytest.fixture
def world(tmp_path, monkeypatch):
    market(tmp_path / cu.KRX)
    monkeypatch.setattr(cu, "Ledger", FakeLedger)
    monkeypatch.setattr(FakeLedger, "n", 300)
    return tmp_path


def test_a_session_is_written_once_with_a_scan_that_writes_no_live_file(world):
    svc = FakeService()
    res = cu.record(world, svc, now=lambda: NOW, klass_of=KLASS)
    assert res == {"status": "OK", "written": [S], "stocks": 300, "overlap": 200} and svc.calls == [{"n": 300, "record": False, "side_files": False}]
    doc = kf._read_day(world / cu.FOLDER, S)
    assert doc["entry_session"] == "2026-11-12" and doc["rows"][0] == {"ticker": "000010", "cap_rank": 1, "cap": 9_999_000.0, "in_live": False, "swing": 40.0, "long": 40.0,
                                                                   "swing_actionability": "ACTIONABLE", "long_actionability": "ACTIONABLE"}
    assert len(doc["live_only"]) == 100 and doc["live_only"][0] == "003010" and kf.verify(world, cu.FOLDER)["status"] == "OK"
    again = cu.record(world, svc, now=lambda: NOW, klass_of=KLASS)
    assert again == {"status": "OK", "written": [], "last": S} and len(svc.calls) == 1        # no second scan, no second file
    assert cu.status(world)["records"] == 1


def test_it_waits_instead_of_writing_a_partial_or_wrong_day(world, monkeypatch):
    assert cu.record(world, FakeService(session="2026-11-12"), klass_of=KLASS) == {"status": "WAITING", "reason": "KRX_NOT_PUBLISHED", "session": "2026-11-12"}
    assert cu.record(world, FakeService(session="2026-11-09"), klass_of=KLASS)["reason"] == "BEFORE_FIRST"
    assert cu.record(world, FakeService(scan_session="2026-11-12"), klass_of=KLASS)["reason"] == "SESSION_MOVED"
    stale = tuple(f"{k:05d}0" for k in range(1, 150))
    assert cu.record(world, FakeService(stale=stale), klass_of=KLASS)["reason"] == "TOO_FEW_STOCKS"
    monkeypatch.setattr(FakeLedger, "n", 50)
    svc = FakeService()
    assert cu.record(world, svc, klass_of=KLASS)["reason"] == "LIVE_NOT_RECORDED" and not svc.calls
    assert cu.status(world)["records"] == 0


def test_a_recorded_scan_cannot_skip_its_side_files(tmp_path):
    with pytest.raises(ValueError):
        QSF.scan(SimpleNamespace(_regime={}, _regime_at={}, _regime_hold=False), "KR", record=True, side_files=False)      # a scan holds one regime (2026-11-15)


class FakePanel:
    """Returns by column: stock k earns ``gain[k]`` over any hold; the market earns ``index``."""

    def __init__(self, dates, symbols, gain, index=0.0):
        self.dates, self.symbols, self.col, self.gain, self.index = dates, symbols, {s: n for n, s in enumerate(symbols)}, gain, index

    def forward(self, i, h, cost=0.0):
        return self.gain(i) - cost

    def market_return(self, i, h):
        return self.index


def docs_and_panel(n_days=300, good_score=True, flip_from=None):
    dates = [d for d in reversed(weekdays_back(n_days + 40, end=date(2028, 3, 1)))]
    cap = [f"C{k:03d}" for k in range(120)]
    live_only = [f"L{k:03d}" for k in range(60)]
    symbols = cap + live_only
    rng = np.random.default_rng(7)

    def gain(i):
        g = np.concatenate([np.linspace(-0.02, 0.04, 120), np.full(60, -0.03)])
        if flip_from is not None and i >= flip_from:
            g = np.concatenate([np.full(120, -0.03), np.full(60, 0.02)])
        return g + 0.002 * rng.standard_normal(len(symbols))
    docs = []
    for n in range(n_days):
        rows = [{"ticker": c, "cap_rank": k + 1, "cap": 1.0, "in_live": k % 2 == 0, "swing": (30 + k * 0.4) if good_score else (80 - k * 0.4), "long": 50.0,
                 "swing_actionability": "ACTIONABLE", "long_actionability": "ACTIONABLE"} for k, c in enumerate(cap)]
        docs.append({"session": dates[n], "entry_session": dates[n + 1], "model_version": "QSF-1.1.8", "live_only": live_only, "rows": rows})
    return docs, FakePanel(dates, symbols, gain)


def write_docs(base, docs):
    for d in docs:
        kf.write_record(base, d["session"], NOW, False, store=cu.FOLDER, scorer=lambda b, day, d=d: d)


def test_the_evaluation_reads_the_universe_and_the_score_separately_and_once(tmp_path):
    docs, panel = docs_and_panel()
    write_docs(tmp_path, docs)
    res = cu.evaluate_once(tmp_path, panel=panel)
    assert res["sessions_used"] == 240 and res["universe"]["reading"] == "UNIVERSE_BETTER" and res["universe"]["mean"] > 0.02
    assert res["swing"]["verdict"] == "WEAK_POSITIVE_EVIDENCE" and res["swing"]["summary"]["all"]["score_effect"] > 0 and res["mean_overlap"] == 60
    with pytest.raises(RuntimeError, match="한 번만"):
        cu.evaluate_once(tmp_path, panel=panel)


def test_a_universe_that_wins_only_early_is_not_supported_and_too_few_days_are_refused(tmp_path):
    docs, panel = docs_and_panel(flip_from=150)
    write_docs(tmp_path / "a", docs)
    res = cu.evaluate_once(tmp_path / "a", panel=panel)
    assert res["universe"]["reading"] == "NOT_SUPPORTED" and res["universe"]["early"] > 0 > res["universe"]["late"]
    few, panel2 = docs_and_panel(n_days=200)
    write_docs(tmp_path / "b", few)
    with pytest.raises(RuntimeError, match="240개가 되기 전"):
        cu.evaluate_once(tmp_path / "b", panel=panel2)
    assert not (tmp_path / "b" / cu.REPORT).exists()
