"""P6-24: unified application: market selector, KR routing, US default unchanged, dashboard."""
import argparse

import pytest

import app
from markets import dashboard, storage
from markets.kr import cli as kr_cli


@pytest.fixture(autouse=True)
def _keep_sandbox_cwd(monkeypatch):
    """app.main() chdirs to the project root; restore the sandbox cwd so later tests stay sandboxed."""
    import os
    monkeypatch.chdir(os.getcwd())


def test_parser_market_selector_default_us():
    p = app.build_parser()
    assert p.parse_args(["scan"]).market == "US"
    assert p.parse_args(["--market", "KR", "scan", "--capital", "1"]).market == "KR"
    with pytest.raises(SystemExit):
        p.parse_args(["--market", "JP", "scan"])


def test_us_capital_error_unchanged(monkeypatch, capsys):
    monkeypatch.delenv("QPP_CAPITAL", raising=False)
    assert app.main(["scan"]) == 2
    assert "Capital is not configured" in capsys.readouterr().err


def test_kr_capital_never_reuses_usd_setting(monkeypatch):
    monkeypatch.setenv("QPP_CAPITAL", "50000")
    monkeypatch.delenv("QPP_CAPITAL_KRW", raising=False)
    with pytest.raises(kr_cli.KRCapitalNotConfigured):
        kr_cli.resolve_capital_krw(None)
    monkeypatch.setenv("QPP_CAPITAL_KRW", "10000000")
    assert kr_cli.resolve_capital_krw(None)[0] == 10_000_000


def test_kr_scan_routes_to_kr_engine(monkeypatch, capsys):
    monkeypatch.delenv("QPP_CAPITAL_KRW", raising=False)
    assert app.main(["--market", "KR", "scan"]) == 2
    assert "KRW" in capsys.readouterr().err
    called = {}
    import markets.kr.pipeline as kp

    def fake(cap, limit=None):
        called["cap"], called["limit"] = cap, limit
        return {"run_id": "r", "recommendation_status": "NO VALID RECOMMENDATION", "validation_scope": "bounded",
                "latest_session": "2026-10-30", "scored": 0, "recommendations": [], "tracking": {}}
    monkeypatch.setattr(kp, "run_kr_scan", fake)
    app.main(["--market", "KR", "scan", "--capital", "5000000", "--limit", "3"])
    assert called == {"cap": 5_000_000, "limit": 3}


def test_kr_unsupported_command_reports():
    assert kr_cli.dispatch(argparse.Namespace(command="doctor")) == 2


def test_dashboard_renders_both_markets_separately(tmp_path, monkeypatch):
    monkeypatch.setenv("QPP_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("QPP_TRACKING_DIR", str(tmp_path / "tracking"))
    d = dashboard.collect()
    assert set(d["markets"]) == {"US", "KR"}
    assert d["markets"]["US"]["currency"] == "USD" and d["markets"]["KR"]["currency"] == "KRW"
    assert d["markets"]["KR"]["model"]["status"] == "EXPERIMENTAL"
    html = dashboard.render(d)
    assert "prefers-color-scheme" in html and ">한국<" in html and ">미국<" in html and "lang='ko'" in html
    assert "실험 단계" in html and "KRW" in html and "USD" in html
    assert dashboard.write(tmp_path / "dash.html").exists()


def test_migrate_storage_is_idempotent_on_copy(tmp_path):
    (tmp_path / "tracking").mkdir()
    assert storage.migrate(tmp_path)["status"] == "MIGRATED"
    assert storage.migrate(tmp_path)["status"] == "ALREADY_CURRENT"
