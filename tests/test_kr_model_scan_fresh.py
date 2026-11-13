"""The Korean model scan never reuses a download that does not reach the session it scores, and a session is recorded once."""
import pandas as pd

from markets.kr import acquisition, tracking as kt
from markets.kr.pipeline import KRContext, run_kr_scan
from markets.storage import runs_dir, tracking_dir
from tests import kr_fakes as F


def ctx(tmp_path):
    return KRContext(fetch_kind=F.fake_kind(), provider_factory=F.provider_factory(F.FakeDownload()), now=F.NOW, base_dir=tmp_path)


def test_both_downloads_are_asked_to_reach_the_session_being_scored(tmp_path, monkeypatch):
    seen = []
    real = acquisition.bars

    def bars(provider, securities, start, end, now, cache_dir, tag, fresh_at=None):
        seen.append((tag, fresh_at))
        return real(provider, securities, start, end, now, cache_dir, tag, fresh_at=fresh_at)
    monkeypatch.setattr(acquisition, "bars", bars)
    v = run_kr_scan(10_000_000, ctx=ctx(tmp_path))
    latest = pd.Timestamp(v["latest_session"])
    assert [t for t, _ in seen] == ["universe", "history"] and all(f == latest for _, f in seen)


def test_a_stored_download_from_before_the_close_is_fetched_again(tmp_path):
    first = run_kr_scan(10_000_000, ctx=ctx(tmp_path))
    assert first["recommendation_status"] == "REAL RECOMMENDATION"
    cache = tmp_path / "data" / "kr" / "cache"
    files = sorted(cache.glob("universe_*.csv.gz"))
    assert len(files) == 1
    df = pd.read_csv(files[0], dtype={"ticker": str}, parse_dates=["date"])
    df[df["date"] < df["date"].max()].to_csv(files[0], index=False, compression="gzip")          # as if stored before the last session was out
    again = run_kr_scan(10_000_000, ctx=ctx(tmp_path))
    assert again["recommendation_status"] == "REAL RECOMMENDATION" and again["scored"] == first["scored"] and again["latest_session"] == first["latest_session"]
    assert pd.read_csv(files[0], parse_dates=["date"])["date"].max() == pd.Timestamp(first["latest_session"])


def test_a_second_scan_of_a_session_already_recorded_adds_no_observations(tmp_path):
    first = run_kr_scan(10_000_000, ctx=ctx(tmp_path))
    td, rd = tracking_dir("KR", tmp_path), runs_dir("KR", tmp_path)
    assert first["tracking"]["recorded_observations"] == 10 and kt.recorded_sessions(td) == {first["latest_session"]: first["run_id"]}
    second = run_kr_scan(10_000_000, ctx=ctx(tmp_path))
    assert second["run_id"] != first["run_id"] and second["latest_session"] == first["latest_session"]
    assert second["tracking"] == {"recorded_observations": 0, "eligible": False, "reasons": ["SESSION_ALREADY_RECORDED"], "recorded_run": first["run_id"]}
    assert len(kt.observations(td)) == 10 and len(kt.runs(td)) == 1
    synced = kt.sync_runs(rd, td)
    assert synced["recorded"] == [] and synced["skipped"][second["run_id"]] == ["SESSION_ALREADY_RECORDED"] and len(kt.observations(td)) == 10
    assert kt.record_run(rd / first["run_id"], td)["already_recorded"] is True               # the recorded run itself still reads as recorded


def test_the_calendar_also_follows_a_large_stock_when_the_index_series_ends_a_session_behind(tmp_path):
    """Yahoo's KOSPI index can lack the newest session in the morning while every stock has it: the scan must score that session."""
    whole = run_kr_scan(10_000_000, ctx=ctx(tmp_path / "whole"))
    behind = F.FakeDownload(mutate={"^KS11": lambda df: df.iloc[:-1], "^KQ11": lambda df: df.iloc[:-1]})
    lagging = KRContext(fetch_kind=F.fake_kind(), provider_factory=F.provider_factory(behind), now=F.NOW, base_dir=tmp_path / "lag")
    got = run_kr_scan(10_000_000, ctx=lagging)
    assert got["latest_session"] == whole["latest_session"] and got["scored"] == whole["scored"] and got["recommendation_status"] == "REAL RECOMMENDATION"
    assert [r["ticker"] for r in got["recommendations"]] == [r["ticker"] for r in whole["recommendations"]]
    no_anchor = F.FakeDownload(drop={"005930.KS"}, mutate={"^KS11": lambda df: df.iloc[:-1], "^KQ11": lambda df: df.iloc[:-1]})
    alone = run_kr_scan(10_000_000, ctx=KRContext(fetch_kind=F.fake_kind(), provider_factory=F.provider_factory(no_anchor), now=F.NOW, base_dir=tmp_path / "alone"))
    assert alone["latest_session"] < whole["latest_session"]            # without the stock the index alone decides, as before


def test_the_model_tab_keeps_the_last_list_when_a_newer_scan_scored_nothing(tmp_path):
    import json
    from terminal.services import Terminal
    from tests.test_terminal_1 import AFTER, fake_src
    root = tmp_path / "runs" / "KR"
    for name, status, session, recs in (("20261112T000000Z_kr_market_scan_good", "REAL RECOMMENDATION", "2026-11-11", [{"rank": 1, "ticker": "001820", "company_name": "삼화콘덴서공업"}]),
                                        ("20261113T000000Z_kr_market_scan_empty", "NO VALID RECOMMENDATION", "2026-11-13", [])):
        (root / name).mkdir(parents=True)
        (root / name / "validation_result.json").write_text(json.dumps({"run_id": name, "validation_scope": "full", "recommendation_status": status, "latest_session": session,
                                                                         "executed_at": name[:8], "recommendations": recs}), encoding="utf-8")
    b = Terminal(tmp_path, src=fake_src(), now=lambda: AFTER).model("KR")["baseline"]
    assert b["run_id"].endswith("_good") and b["latest_session"] == "2026-11-11" and [r["ticker"] for r in b["top5"]] == ["001820"]
    assert b["newer_empty_scan"] == {"executed_at": "20261113", "latest_session": "2026-11-13"}
