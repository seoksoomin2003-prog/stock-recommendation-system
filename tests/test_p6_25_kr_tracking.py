"""P6-25: KR paper tracking: immutability, duplicates, entry timing, no look-ahead, KRW/cohort separation."""
import json
from datetime import datetime, timezone

import pandas as pd
import pytest

from tests import kr_fakes as F
from markets.kr import tracking as kt
from markets.kr.pipeline import KRContext, run_kr_scan
from markets.storage import runs_dir, tracking_dir
from pipeline.prospective_ledger import read_jsonl


@pytest.fixture()
def scanned(tmp_path):
    ctx = KRContext(fetch_kind=F.fake_kind(), provider_factory=F.provider_factory(F.FakeDownload()), now=F.NOW,
                    base_dir=tmp_path)
    v = run_kr_scan(10_000_000, ctx=ctx)
    return {"v": v, "td": tracking_dir("KR", tmp_path), "rd": runs_dir("KR", tmp_path), "base": tmp_path}


def _prov():
    return F.provider_factory(F.FakeDownload())()


def test_records_are_kr_krw_experimental_and_keyed(scanned):
    obs = kt.observations(scanned["td"])
    assert len(obs) == 10 and len(kt.runs(scanned["td"])) == 1
    for o in obs:
        assert o["market"] == "KR" and o["currency"] == "KRW" and o["cohort"] == "EXPERIMENTAL_PROSPECTIVE"
        assert o["key"] == f"OBS:KR:{o['run_id']}:{o['ticker']}" and o["model_version"].startswith("KR-EXP")
        assert o["benchmark"] in ("^KS11", "^KQ11") and o["horizon_sessions"] == 20
    r = kt.runs(scanned["td"])[0]
    assert r["universe"]["snapshot_sha256"] and r["signal"]["entry_not_before"]


def test_kr_ledger_is_separate_from_us(scanned):
    assert scanned["td"] == scanned["base"] / "tracking" / "kr"
    assert not (scanned["base"] / "tracking" / "ledger" / "observations.jsonl").exists()


def test_duplicate_recording_is_idempotent(scanned):
    rd = scanned["rd"] / scanned["v"]["run_id"]
    before = (scanned["td"] / "ledger" / "observations.jsonl").read_bytes()
    assert kt.record_run(rd, scanned["td"])["already_recorded"]
    assert kt.sync_runs(scanned["rd"], scanned["td"])["recorded"] == []
    assert (scanned["td"] / "ledger" / "observations.jsonl").read_bytes() == before


def test_ledger_tamper_detected(scanned):
    p = scanned["td"] / "ledger" / "observations.jsonl"
    lines = p.read_text().splitlines()
    rec = json.loads(lines[3])
    rec["shares"] += 1
    lines[3] = json.dumps(rec)
    p.write_text("\n".join(lines) + "\n")
    assert not kt.verify(scanned["td"], scanned["rd"])["ok"]


def test_artifact_change_detected(scanned):
    rd = scanned["rd"] / scanned["v"]["run_id"]
    (rd / "candidate_flow.json").write_text("{}")
    r = kt.verify(scanned["td"], scanned["rd"])
    assert not r["ok"] and r["runs"][0]["artifacts"] == "CHANGED"


def test_entry_never_before_entry_not_before_and_horizon(scanned):
    r = kt.update(scanned["td"], provider=_prov(), now=datetime(2026, 12, 20, 10, tzinfo=timezone.utc))
    out = json.loads(open(r["outcomes_file"]).read())
    obs = {o["observation_id"]: o for o in kt.observations(scanned["td"])}
    for oid, x in out["outcomes"].items():
        assert x["outcome_state"] == "COMPLETED_OUTCOME" and x["currency"] == "KRW"
        assert x["entry"]["session"] >= obs[oid]["entry_not_before"] and x["entry"]["basis"] == "open"
        assert x["sessions_held"] == 20 and x["exit"]["session"] > x["entry"]["session"]
        assert x["returns"]["benchmark"] == obs[oid]["benchmark"]
    s = out["summary"]
    assert s["sample_status"] == "INSUFFICIENT_SAMPLE" and "annual" not in json.dumps(s).lower()


def test_pending_states_before_data_exists(scanned):
    early = kt.update(scanned["td"], provider=_prov(), now=datetime(2026, 11, 4, 1, tzinfo=timezone.utc))
    assert set(early["states"]) <= {"PENDING_ENTRY", "PENDING_OUTCOME"}


def test_no_look_ahead_bars_after_now_are_ignored(scanned):
    now = datetime(2026, 11, 20, 10, tzinfo=timezone.utc)
    r = kt.update(scanned["td"], provider=_prov(), now=now)
    snap = pd.read_csv(scanned["td"] / "prices" / f"{r['update_id']}.csv.gz", parse_dates=["date"])
    assert snap["date"].max() <= pd.Timestamp("2026-11-20")
    out = json.loads(open(r["outcomes_file"]).read())
    assert all(x["outcome_state"] in ("PENDING_OUTCOME", "PENDING_ENTRY") for x in out["outcomes"].values())


def test_data_gap_is_incomplete_never_filled():
    sess = pd.bdate_range("2026-11-02", periods=25)
    obs = {"observation_id": "o", "ticker": "t", "entry_not_before": "2026-11-02", "benchmark": "^KS11"}
    bars = pd.DataFrame({"date": sess, "open": 100.0, "close": 101.0, "adj_close": 101.0, "quality_status": "REAL"})
    bench = pd.DataFrame({"Open": 1.0, "Close": 1.0}, index=sess)
    gap = bars.drop(index=5)
    assert kt.outcome(obs, gap, bench, sess)["outcome_state"] == "INCOMPLETE"
    assert kt.outcome(obs, gap, bench, sess)["reason"] == "DATA_GAP"
    invalid = bars.copy()
    invalid.loc[0, "quality_status"] = "INVALID"
    assert kt.outcome(obs, invalid, bench, sess)["reason"] == "ENTRY_BAR_MISSING"
    ok = kt.outcome(obs, bars, bench, sess)
    assert ok["outcome_state"] == "COMPLETED_OUTCOME" and ok["returns"]["price_return"] == pytest.approx(0.01)
    assert [c["cost_bps_per_side"] for c in ok["returns"]["cost_sensitivity"]] == list(kt.COST_BPS)


def test_replay_matches_and_report_written(scanned):
    r = kt.update(scanned["td"], provider=_prov(), now=datetime(2026, 12, 20, 10, tzinfo=timezone.utc))
    assert kt.replay(r["update_id"], scanned["td"])["match"]
    rep = kt.write_report(scanned["td"]).read_text(encoding="utf-8")
    assert "KRW" in rep and "EXPERIMENTAL" in rep and "USD" not in rep.replace("never combined with USD", "")
    assert (scanned["td"] / "reports" / "latest.html").exists()
    assert kt.verify(scanned["td"], scanned["rd"])["ok"]
    log = read_jsonl(scanned["td"] / "updates.jsonl")
    assert log[-1]["outcomes_sha256"]


def test_ineligible_runs_not_recorded(tmp_path):
    rd = tmp_path / "r"
    rd.mkdir()
    (rd / "run_manifest.json").write_text(json.dumps({"market": "US"}))
    e = kt.eligibility(rd)
    assert not e["eligible"] and "NOT_A_KR_RUN" in e["reasons"]
    assert kt.record_run(rd, tmp_path / "t")["recorded_observations"] == 0


# ----------------------------------------------------------------------------- an index bar without a close (2026-11-14)
def _half_last_bar(df):
    df = df.copy()
    df.loc[df.index[-1], ["High", "Low", "Close"]] = float("nan")
    return df


def test_whole_index_ends_before_the_first_bar_without_a_close():
    days = pd.bdate_range("2026-11-02", periods=5)
    df = pd.DataFrame({"Open": 1.0, "High": 1.0, "Low": 1.0, "Close": [1.0, 1.0, float("nan"), 1.0, 1.0]}, index=days)
    kept, held = kt.whole_index(df)
    assert list(kept.index) == list(days[:2])                       # the day is not skipped: the series stops before it
    assert held == ["2026-11-04", "2026-11-05", "2026-11-06"]
    whole = df.assign(Close=1.0)
    assert kt.whole_index(whole)[1] == [] and len(kt.whole_index(whole)[0]) == 5
    assert kt.whole_index(pd.DataFrame())[1] == []


def test_index_bar_without_close_is_not_a_session_and_leaves_no_nan(scanned):
    """The morning of 2026-11-14 the source's KOSPI bar of the last session had an open and no close: stocks were marked on that
    day and every comparison with the index became not-a-number.  Such a day waits for its close."""
    now = datetime(2026, 11, 20, 10, tzinfo=timezone.utc)           # 19:00 KST Friday: the day's bar counts as complete
    half = F.provider_factory(F.FakeDownload(mutate={"^KS11": _half_last_bar, "^KQ11": _half_last_bar}))()
    r = kt.update(scanned["td"], provider=half, now=now)
    assert r["index_bars_held_back"] == {"KOSPI": ["2026-11-20"], "KOSDAQ": ["2026-11-20"]}
    text = open(r["outcomes_file"]).read()
    assert "NaN" not in text
    out = json.loads(text)
    assert out["index_bars_held_back"]["KOSPI"] == ["2026-11-20"]
    marked = [x for x in out["outcomes"].values() if x.get("returns")]
    assert marked and all(x["mark"]["session"] == "2026-11-19" for x in marked)
    assert all(isinstance(x["returns"]["benchmark_price_return"], float) and isinstance(x["returns"]["excess_vs_benchmark"], float) for x in marked)
    snap = pd.read_csv(scanned["td"] / "prices" / f"{r['update_id']}.csv.gz", parse_dates=["date"])
    assert snap[snap["ticker"].isin(["^KS11", "^KQ11"])]["date"].max() == pd.Timestamp("2026-11-19")
    assert kt.replay(r["update_id"], scanned["td"])["match"]
    rep = kt.write_report(scanned["td"]).read_text(encoding="utf-8")
    assert "nan" not in rep.lower() and "held back" in rep

    later = kt.update(scanned["td"], provider=_prov(), now=datetime(2026, 11, 20, 12, tzinfo=timezone.utc))
    assert "index_bars_held_back" not in later
    out2 = json.loads(open(later["outcomes_file"]).read())
    assert all(x["mark"]["session"] == "2026-11-20" for x in out2["outcomes"].values() if x.get("returns"))


def test_report_reads_an_old_update_with_nan_as_empty():
    assert kt._pct(float("nan")) == "-" and kt._pct(None) == "-" and kt._pct(0.0123) == "1.23%"


# ----------------------------------------------------------------------------- a session recorded twice (before 2026-11-14)
def _recorded_twice(scanned):
    """The ledger as it was before ``record_run`` refused a second scan of a session: both scans recorded."""
    from pipeline.prospective_ledger import append_records
    ctx = KRContext(fetch_kind=F.fake_kind(), provider_factory=F.provider_factory(F.FakeDownload()), now=F.NOW,
                    base_dir=scanned["base"])
    second = run_kr_scan(10_000_000, ctx=ctx)
    assert second["tracking"]["reasons"] == ["SESSION_ALREADY_RECORDED"]
    append_records(scanned["td"] / "ledger" / "observations.jsonl", kt.build_records(scanned["rd"] / second["run_id"]), key="key")
    return scanned["v"]["run_id"], second["run_id"]


def test_a_later_scan_of_a_recorded_session_is_the_duplicate_and_only_it_can_be_excluded(scanned):
    first, second = _recorded_twice(scanned)
    td = scanned["td"]
    assert kt.duplicate_runs(td) == {second: {"session": scanned["v"]["latest_session"], "kept_run": first}}
    assert kt.exclude_run(first, td) == {"excluded": False, "reason": "NOT_A_DUPLICATE_SESSION", "run_id": first}
    assert kt.exclude_run("no_such_run", td)["reason"] == "UNKNOWN_RUN"
    assert not (td / "ledger" / kt.EVENTS_FILE).exists() and kt.excluded_runs(td) == {}
    before = (td / "ledger" / "observations.jsonl").read_bytes()
    r = kt.exclude_run(second, td)
    assert r["excluded"] and not r["already_excluded"] and r["kept_run"] == first
    assert kt.exclude_run(second, td)["already_excluded"] and len(read_jsonl(td / "ledger" / kt.EVENTS_FILE)) == 1
    assert (td / "ledger" / "observations.jsonl").read_bytes() == before          # the records themselves are untouched
    assert kt.counts(td) == {"runs": 2, "observations": 20, "excluded_runs": 1, "excluded_observations": 10,
                             "counted_runs": 1, "counted_observations": 10}


def test_figures_leave_the_excluded_run_out_and_its_outcomes_stay(scanned):
    first, second = _recorded_twice(scanned)
    td = scanned["td"]
    now = datetime(2026, 12, 20, 10, tzinfo=timezone.utc)
    both = json.loads(open(kt.update(td, provider=_prov(), now=now)["outcomes_file"], encoding="utf-8").read())
    assert both["summary"]["observations"] == 20 and both["summary"]["runs"] == 2 and both["summary"]["excluded_runs"] == 0
    assert both["summary"]["turnover_between_consecutive_runs"] == [0.0]          # the same ten stocks counted twice
    kt.exclude_run(second, td)
    waiting = kt.write_report(td).read_text(encoding="utf-8")                      # the stored update still counts both
    assert "Marked for exclusion after this update was computed" in waiting and second in waiting
    r = kt.update(td, provider=_prov(), now=now.replace(hour=11))
    one = json.loads(open(r["outcomes_file"], encoding="utf-8").read())
    s = one["summary"]
    assert s["observations"] == 10 and s["runs"] == 1 and s["excluded_runs"] == 1 and s["excluded_observations"] == 10
    assert s["turnover_between_consecutive_runs"] == [] and sum(s["outcome_states"].values()) == 10
    assert s["price_return"]["n"] == both["summary"]["price_return"]["n"] // 2
    assert len(one["outcomes"]) == 20 and one["outcomes"] == both["outcomes"]      # every observation keeps its outcome
    assert {q["run_id"]: q.get("excluded") for q in one["paper_portfolios"]} == {first: None, second: kt.DUPLICATE_SESSION}
    assert read_jsonl(td / "updates.jsonl")[-1]["states"] == s["outcome_states"]
    rep = kt.write_report(td).read_text(encoding="utf-8")
    assert f"run `{second}` (second scan of session" in rep and "· excluded" in rep and "Marked for exclusion after" not in rep
    assert rep.count("· excluded |") == 11                                         # ten observation rows and one portfolio row
    assert kt.replay(r["update_id"], td)["match"] and kt.verify(td, scanned["rd"])["ok"]


def test_verify_reports_an_exclusion_that_names_a_run_it_may_not_exclude(scanned):
    from pipeline.prospective_ledger import append_records
    first, second = _recorded_twice(scanned)
    td = scanned["td"]
    kt.exclude_run(second, td)
    assert kt.verify(td, scanned["rd"])["ok"] and len(kt.verify(td, scanned["rd"])["chains"]) == 3
    append_records(td / "ledger" / kt.EVENTS_FILE, [{"record_type": "EVENT", "event_id": "x", "kind": "EXCLUSION",
                                                     "category": kt.DUPLICATE_SESSION, "target": {"run_id": first}}], key="event_id")
    v = kt.verify(td, scanned["rd"])
    assert v["exclusions_not_allowed"] == [first] and not v["ok"]
    assert list(kt.excluded_runs(td)) == [second]                                  # and the figures ignore it
    lines = (td / "ledger" / kt.EVENTS_FILE).read_text().splitlines()
    (td / "ledger" / kt.EVENTS_FILE).write_text(lines[0].replace(second, second[:-1] + "0") + "\n")
    assert not kt.verify(td, scanned["rd"])["chains"][2]["ok"]                     # an edited event breaks its chain


def test_kr_exclusions_command_refuses_a_run_that_is_not_a_duplicate(scanned, monkeypatch, capsys):
    from types import SimpleNamespace
    from markets.kr import cli
    first, second = _recorded_twice(scanned)
    monkeypatch.setattr(kt, "_tracking_dir", lambda market="KR", base=None: scanned["td"])
    assert cli.cmd_tracking(SimpleNamespace(action="exclusions", add=first)) == 2
    assert kt.excluded_runs(scanned["td"]) == {}
    assert cli.cmd_tracking(SimpleNamespace(action="exclusions", add=second)) == 0
    assert cli.cmd_tracking(SimpleNamespace(action="exclusions", add=None)) == 0
    out = capsys.readouterr().out
    assert "NOT_A_DUPLICATE_SESSION" in out and "EXCLUDED from the figures" in out and list(kt.excluded_runs(scanned["td"])) == [second]
