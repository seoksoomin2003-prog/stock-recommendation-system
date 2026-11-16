"""The separate US challenger record: fixed bundles, written once, no early evaluation, the live ledger untouched.  No network."""
import gzip
import hashlib
import json
import zlib
from datetime import date, datetime, timezone

import numpy as np
import pytest

from terminal.qsf import config, kr_forward as kf, us_challenger as uc
from terminal.qsf.ledger import Ledger
from utils import nyse_calendar

MON = "2026-11-09"
TUE = "2026-11-10"
WED = "2026-11-11"


def all_factors(strategy):
    p = config.PROFILES[f"US_{strategy}_V2"]                 # QSF-1.4.0: the regime factors are reference rows, still on every card
    return [n for part in (p["domains"], p["reference"]) for d in part.values() for n in d]


def snap(ticker, strategy, session, seed, version="QSF-1.1.6", score=60.0, drop=()):
    rng = np.random.default_rng(seed)
    factors = [{"factor": n, "normalized": None if n in drop else float(rng.random())} for n in all_factors(strategy)]
    return {"market": "US", "ticker": ticker, "strategy": strategy, "data_date": session, "score": score, "model_version": version, "actionability": "ACTIONABLE", "factors": factors, "price": 100.0}


def write_shard(base, session, snaps):
    """A real ledger index, written directly so the test can put in any factor values."""
    led = Ledger(base)
    led.dir.mkdir(parents=True, exist_ok=True)
    idx = led.read_index()["rows"]
    seq = len(idx) + 1
    name = f"{session}_US_{seq:06d}.jsonl.gz"
    with gzip.open(led.dir / name, "wt", encoding="utf-8") as fh:
        fh.write("\n".join(json.dumps(s) for s in snaps) + "\n")
    row = {"seq": seq, "session": session, "market": "US", "file": name, "sha256": hashlib.sha256((led.dir / name).read_bytes()).hexdigest(), "records": len(snaps), "model_version": "QSF-1.1.6",
           "prev_hash": idx[-1]["hash"] if idx else "0" * 64}
    row["hash"] = hashlib.sha256(json.dumps(row, sort_keys=True).encode()).hexdigest()
    with open(led.index, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, sort_keys=True) + "\n")
    return name


def day_snaps(session, n=420):
    return [snap(f"T{i:03d}", s, session, zlib.crc32(f"{i}{s}{session}".encode())) for i in range(n) for s in ("SWING", "LONG_TERM")]


def at(session, hour=12):
    d = date.fromisoformat(session)
    return lambda: datetime(d.year, d.month, d.day, hour, tzinfo=timezone.utc)


def test_bundles_are_live_signals_and_leave_out_the_measured_ones():
    for strategy, bundles in uc.BUNDLES.items():
        names = [n for b in bundles for n in b]
        assert len(names) == len(set(names))
        assert set(names) <= set(all_factors(strategy))
        regime = set(config.PROFILES[f"US_{strategy}_V2"]["reference"]["REGIME"])
        assert not set(names) & regime
    assert "earnings_calendar" not in sum(uc.BUNDLES["SWING"], []) and "material_disclosures" not in sum(uc.BUNDLES["SWING"], [])
    assert not {"governance", "material_events"} & set(sum(uc.BUNDLES["LONG_TERM"], []))
    assert len(uc.BUNDLES["SWING"]) == 10 and len(uc.BUNDLES["LONG_TERM"]) == 9


def test_score_gives_each_bundle_the_same_weight():
    """Five signals in one bundle must not outweigh a bundle of one."""
    def row(t, big, small):
        s = {"ticker": t, "score": 50.0, "factors": []}
        for b in uc.BUNDLES["SWING"]:
            v = big if len(b) > 1 else small
            s["factors"] += [{"factor": n, "normalized": v} for n in b]
        return s
    rows = uc.score_strategy([row("A", 1.0, 0.0), row("B", 0.0, 1.0)], "SWING")
    by = {r["ticker"]: r["score"] for r in rows}
    assert by["A"] == pytest.approx(10.0) and by["B"] == pytest.approx(90.0)
    assert rows[0]["bundles"][0] == 100.0 and rows[1]["bundles"][0] == 0.0


def test_missing_stays_missing_and_too_many_empty_bundles_give_no_score():
    snaps = [snap(f"T{i}", "SWING", MON, i) for i in range(40)]
    none = [n for b in uc.BUNDLES["SWING"][5:] for n in b]
    snaps[0] = snap("T0", "SWING", MON, 0, drop=none)        # half the bundles are empty
    snaps[1] = snap("T1", "SWING", MON, 1, drop=("momentum",))
    rows = {r["ticker"]: r for r in uc.score_strategy(snaps, "SWING")}
    assert rows["T0"]["score"] is None
    assert rows["T1"]["score"] is not None and rows["T1"]["bundles"][1] is None


def test_a_bundle_needs_half_of_its_signals():
    drop = ("trend_structure", "relative_strength", "breakout_volume")
    rows = uc.score_strategy([snap(f"T{i}", "SWING", MON, i, drop=drop if i == 0 else ()) for i in range(40)], "SWING")
    assert rows[0]["bundles"][0] is None and rows[1]["bundles"][0] is not None


def test_score_depends_on_rank_only_within_the_day():
    snaps = [snap(f"T{i}", "LONG_TERM", MON, i) for i in range(40)]
    a = uc.score_strategy(snaps, "LONG_TERM")
    for s in snaps:
        for f in s["factors"]:
            f["normalized"] = f["normalized"] * 0.5 + 0.1
    assert a == uc.score_strategy(snaps, "LONG_TERM")


def test_record_is_written_once_chained_and_leaves_the_ledger_alone(tmp_path):
    name = write_shard(tmp_path, MON, day_snaps(MON))
    before = (Ledger(tmp_path).dir / name).read_bytes(), Ledger(tmp_path).index.read_bytes()
    res = uc.record(tmp_path, now=at(TUE))
    assert res["status"] == "OK" and res["written"] == [MON]
    assert before == ((Ledger(tmp_path).dir / name).read_bytes(), Ledger(tmp_path).index.read_bytes())
    file = tmp_path / uc.FOLDER / f"{MON}.json.gz"
    first = file.read_bytes()
    assert uc.record(tmp_path, now=at(TUE, 18))["written"] == [] and file.read_bytes() == first
    assert kf.verify(tmp_path, uc.FOLDER)["status"] == "OK"
    doc = kf._read_day(tmp_path / uc.FOLDER, MON)
    assert doc["model_versions"] == ["QSF-1.1.6"] and doc["bundles"] == uc.BUNDLES
    assert {"ticker", "score", "bundles", "live", "actionability"} == set(doc["strategies"]["SWING"][0])
    assert doc["strategies"]["SWING"][0]["live"] == 60.0
    assert "return" not in json.dumps(doc)


def test_an_edited_record_breaks_verification(tmp_path):
    write_shard(tmp_path, MON, day_snaps(MON))
    uc.record(tmp_path, now=at(TUE))
    file = tmp_path / uc.FOLDER / f"{MON}.json.gz"
    file.write_bytes(file.read_bytes() + b"x")
    assert kf.verify(tmp_path, uc.FOLDER)["status"] == "BROKEN"


def test_sessions_before_the_first_are_not_recorded(tmp_path):
    write_shard(tmp_path, "2026-11-06", day_snaps("2026-11-06"))
    res = uc.record(tmp_path, now=at("2026-11-07"))
    assert res["status"] == "OK" and res["written"] == [] and res["last"] is None
    assert kf.read_index(tmp_path, uc.FOLDER) == []


def test_waiting_until_the_ledger_has_the_session(tmp_path):
    write_shard(tmp_path, MON, day_snaps(MON))
    res = uc.record(tmp_path, now=at(WED))
    assert res["status"] == "WAITING" and res["written"] == [MON] and res["expected"] == TUE


def test_partial_day_is_not_written_and_is_asked_again(tmp_path):
    write_shard(tmp_path, MON, day_snaps(MON, n=100))
    res = uc.record(tmp_path, now=at(TUE))
    assert res["status"] == "WAITING" and res["partial"] == [MON] and res["written"] == []
    assert not (tmp_path / uc.FOLDER / f"{MON}.json.gz").exists()
    write_shard(tmp_path, MON, [snap(f"X{i:03d}", s, MON, i) for i in range(400) for s in ("SWING", "LONG_TERM")])
    assert uc.record(tmp_path, now=at(TUE))["written"] == [MON]


def test_stale_stocks_are_left_out(tmp_path):
    rows = day_snaps(MON) + [snap("OLD", "SWING", "2026-11-06", 7)]
    write_shard(tmp_path, MON, rows)
    uc.record(tmp_path, now=at(TUE))
    tickers = {r["ticker"] for r in kf._read_day(tmp_path / uc.FOLDER, MON)["strategies"]["SWING"]}
    assert "OLD" not in tickers


def test_voided_shard_is_not_read(tmp_path):
    name = write_shard(tmp_path, MON, day_snaps(MON))
    Ledger(tmp_path).void_shard(name, "test")
    assert uc.record(tmp_path, now=at(TUE))["written"] == []


def test_late_day_is_flagged_and_value_does_not_depend_on_when(tmp_path):
    other = tmp_path / "other"
    for base in (tmp_path, other):
        base.mkdir(exist_ok=True)
        write_shard(base, MON, day_snaps(MON))
    uc.record(other, now=at(TUE))
    write_shard(tmp_path, TUE, day_snaps(TUE))
    res = uc.record(tmp_path, now=at(WED))
    assert res["written"] == [MON, TUE] and res["status"] == "OK"
    late = kf._read_day(tmp_path / uc.FOLDER, MON)
    assert late["late"] is True and kf._read_day(tmp_path / uc.FOLDER, TUE)["late"] is False
    assert late["strategies"] == kf._read_day(other / uc.FOLDER, MON)["strategies"]


def test_broken_ledger_records_nothing(tmp_path):
    name = write_shard(tmp_path, MON, day_snaps(MON))
    (Ledger(tmp_path).dir / name).write_bytes(b"bad")
    res = uc.record(tmp_path, now=at(TUE))
    assert res["status"] == "FAILED" and not (tmp_path / uc.FOLDER / f"{MON}.json.gz").exists()


def test_before_next_open_uses_new_york_time():
    assert uc.next_open("2026-11-06") == datetime(2026, 11, 9, 14, 30, tzinfo=timezone.utc)


def test_status_counts_dates_and_never_reads_prices(tmp_path):
    write_shard(tmp_path, MON, day_snaps(MON))
    uc.record(tmp_path, now=at(TUE))
    cal = [d.isoformat() for d in nyse_calendar.sessions_between(date(2026, 11, 9), date(2026, 12, 31))]
    s = uc.status(tmp_path, cal)
    assert s["sessions"] == 1 and s["integrity"] == "OK" and s["target"] == config.MIN_INDEPENDENT and s["long_needed"] == 756
    assert "price_check" not in s and s["ready"] is False and not any("return" in k for k in s)


# ---------------------------------------------------------------------- evaluation
def calendar(n, first="2026-11-09"):
    out, d = [], date.fromisoformat(first)
    while len(out) < n:
        if nyse_calendar.is_session(d):
            out.append(d.isoformat())
        d = nyse_calendar.next_session(d)
    return out


def fake_market(sessions, tickers, seed=3, drift=None, stop=None):
    """Bars for every ticker.  ``drift`` makes a ticker's daily return follow its number, ``stop`` ends a ticker's bars early."""
    rng = np.random.default_rng(seed)
    bars = {}
    for k, t in enumerate(["SPY"] + list(tickers)):
        p = 100.0
        rows = []
        for d in sessions:
            p *= 1 + float(rng.normal(0, 0.01)) + (drift(k) if drift else 0.0)
            rows.append({"date": d, "open": p, "close": p, "adj_close": p})
        bars[t] = rows[:stop[t]] if stop and t in stop else rows
    return bars


def write_records(base, sessions, tickers, challenger, live, strategy="SWING"):
    folder = base / uc.FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    now = datetime(2026, 11, 7, tzinfo=timezone.utc)
    for day in sessions:
        rows = [{"ticker": t, "score": challenger(k, day), "bundles": [], "live": live(k, day), "actionability": "ACTIONABLE"} for k, t in enumerate(tickers)]
        doc = {"session": day, "strategies": {strategy: rows, ("LONG_TERM" if strategy == "SWING" else "SWING"): rows}, "recorded_at": now.isoformat(), "late": False, "before_next_open": True}
        with gzip.open(folder / f"{day}.json.gz", "wt", encoding="utf-8") as fh:
            json.dump(doc, fh)
        kf._append_index(folder, day, doc["recorded_at"], False, True, len(rows))


def test_evaluation_is_refused_until_enough_sessions_matured(tmp_path):
    cal = calendar(300)
    tickers = [f"T{i}" for i in range(40)]
    write_records(tmp_path, cal[:239], tickers, lambda k, d: float(k), lambda k, d: float(-k))
    market = fake_market(cal, tickers)
    with pytest.raises(RuntimeError, match="아직 평가할 수 없습니다"):
        uc.evaluate_once(tmp_path, "SWING", lambda t: market.get(t, []), cal)
    assert not (tmp_path / uc.REPORTS["SWING"]).exists()


def test_long_needs_its_own_longer_record(tmp_path):
    cal = calendar(400)
    tickers = [f"T{i}" for i in range(40)]
    write_records(tmp_path, cal[:300], tickers, lambda k, d: float(k), lambda k, d: float(k), "LONG_TERM")
    market = fake_market(cal, tickers)
    with pytest.raises(RuntimeError, match="기준 756개"):
        uc.evaluate_once(tmp_path, "LONG_TERM", lambda t: market.get(t, []), cal)


def test_evaluation_runs_once_and_prefers_the_score_that_ranks_better(tmp_path):
    cal = calendar(290)
    tickers = [f"T{i}" for i in range(60)]
    market = fake_market(cal, tickers, drift=lambda k: 0.0002 * k)
    write_records(tmp_path, cal[:260], tickers, lambda k, d: float(k), lambda k, d: float((k * 7 + zlib.crc32(d.encode())) % 60))
    res = uc.evaluate_once(tmp_path, "SWING", lambda t: market.get(t, []), cal)
    assert res["status"] == "EVALUATED" and res["dates"] == 52 and res["horizon"] == 20
    assert res["challenger"]["ic"] > res["live"]["ic"]
    assert res["paired_ic"]["mean"] > 0 and res["paired_ic"]["supports_challenger"] is True
    assert res["supports_challenger"] is True and res["live"]["verdict"] in ("NO_EVIDENCE", "WEAK_POSITIVE_EVIDENCE")
    assert set(res["challenger"]["top_vs_spy"]) >= {"top_fifth", "spy", "early", "late", "beats_spy_in_both_halves"}
    assert json.loads((tmp_path / uc.REPORTS["SWING"]).read_text(encoding="utf-8"))["status"] == "EVALUATED"
    with pytest.raises(RuntimeError, match="이미 평가"):
        uc.evaluate_once(tmp_path, "SWING", lambda t: market.get(t, []), cal)


def test_equal_scores_do_not_support_the_challenger(tmp_path):
    cal = calendar(290)
    tickers = [f"T{i}" for i in range(60)]
    market = fake_market(cal, tickers, drift=lambda k: 0.0002 * k)
    write_records(tmp_path, cal[:260], tickers, lambda k, d: float(k), lambda k, d: float(k))
    res = uc.evaluate_once(tmp_path, "SWING", lambda t: market.get(t, []), cal)
    assert res["paired_ic"]["mean"] == pytest.approx(0.0) and res["supports_challenger"] is False


def test_a_vanished_stock_exits_at_its_last_price():
    cal = calendar(30)
    market = fake_market(cal, ["A", "B"], stop={"A": 10})
    px = uc.build_panel(["A", "B"], lambda t: market.get(t, []), {})
    j = px.col["A"]
    last = market["A"][-1]["adj_close"]
    assert px.data["adj_close"][29, j] == last and np.isfinite(px.forward(5, 20)[j])
    assert px.forward(5, 20)[j] == pytest.approx(last / market["A"][6]["adj_close"] - 1)


def test_a_stock_without_quotes_uses_the_ledger_closes():
    cal = calendar(30)
    market = fake_market(cal, ["B"])
    px = uc.build_panel(["GONE", "B"], lambda t: market.get(t, []), {"GONE": {cal[3]: 50.0, cal[4]: 40.0}})
    j = px.col["GONE"]
    assert not np.isfinite(px.data["close"][2, j]) and px.data["close"][4, j] == 40.0 and px.data["adj_close"][20, j] == 40.0
    assert px.forward(3, 20)[j] == pytest.approx(40.0 / 40.0 - 1)
    assert px.forward(2, 20)[j] == pytest.approx(40.0 / 50.0 - 1)


def test_prices_before_a_listing_stay_empty():
    cal = calendar(30)
    market = fake_market(cal, ["B"])
    market["B"] = market["B"][10:]
    px = uc.build_panel(["B"], lambda t: market.get(t, []), {})
    assert not np.isfinite(px.data["close"][5, px.col["B"]])
    assert np.isnan(px.forward(1, 20)[px.col["B"]])
