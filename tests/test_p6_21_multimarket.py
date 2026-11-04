"""P6-21: market-scoped architecture, identity, configuration, storage isolation, frozen-core integrity."""
import hashlib
import json
import tarfile
from pathlib import Path

import pytest

from markets.config import market_config
from markets.identity import Market, SecurityId, kr_security, us_security
from markets import storage
from pipeline.run_recorder import RunRecorder
from pipeline import prospective_ledger

ROOT = Path(__file__).resolve().parents[1]
FROZEN = json.loads((ROOT / "tests/fixtures/frozen_source_sha256_p6_19.json").read_text())


def test_frozen_core_hashes_unchanged():
    files = FROZEN["sha256"]
    assert files, "frozen manifest empty"
    for rel, h in files.items():
        assert hashlib.sha256((ROOT / rel).read_bytes()).hexdigest() == h, rel


def test_kr_package_never_imports_frozen_core():
    for p in (ROOT / "markets").rglob("*.py"):
        src = p.read_text(encoding="utf-8")
        for mod in ("core.factor_engine", "core.scoring_engine", "core.ranking_engine", "core.decision_engine",
                    "from core import"):
            assert mod not in src, f"{p} imports frozen US module {mod}"


def test_market_parse_rejects_unknown():
    assert Market.parse("kr") is Market.KR and Market.parse(Market.US) is Market.US
    with pytest.raises(ValueError):
        Market.parse("JP")


def test_identity_is_composite_not_ticker_format():
    a = kr_security("005930", "KOSPI")
    b = us_security("005930")              # a numeric US-style symbol must not become Korean
    assert a.key == "KR:KOSPI:005930" and a.currency == "KRW"
    assert b.market == "US" and b.currency == "USD" and a.key != b.key
    assert SecurityId.from_dict(a.to_dict()) == a
    assert kr_security("0126Z0", "KOSDAQ").identifiers["yahoo"] == "0126Z0.KQ"


def test_configs_are_separate_and_read_only():
    us, kr = market_config("US"), market_config("KR")
    assert us["currency"] == "USD" and kr["currency"] == "KRW"
    assert us["model"]["status"] == "FROZEN" and kr["model"]["status"] == "EXPERIMENTAL"
    assert us["timezone"] != kr["timezone"]
    with pytest.raises(TypeError):
        kr["currency"] = "USD"
    with pytest.raises(TypeError):
        us["model"]["status"] = "X"


def test_storage_paths_are_market_scoped(tmp_path):
    assert storage.runs_dir("US", tmp_path) == tmp_path / "runs"
    assert storage.runs_dir("KR", tmp_path) == tmp_path / "runs" / "KR"
    assert storage.tracking_dir("US", tmp_path) == tmp_path / "tracking"
    assert storage.tracking_dir("KR", tmp_path) == tmp_path / "tracking" / "kr"
    assert storage.data_dir("KR", tmp_path) == tmp_path / "data" / "kr"


def test_migration_is_additive_idempotent_and_backs_up(tmp_path):
    base = tmp_path / "proj"
    (base / "tracking" / "ledger").mkdir(parents=True)
    led = base / "tracking" / "ledger" / "observations.jsonl"
    led.write_text('{"x":1}\n')
    before = led.read_bytes()
    r1 = storage.migrate(base)
    assert led.read_bytes() == before                          # US ledger untouched
    assert (base / "runs" / "KR").is_dir() and (base / "tracking" / "kr" / "ledger").is_dir()
    backups = list((base.parent / "qse-backups").glob("*.tar.gz"))
    assert backups and "tracking/ledger/observations.jsonl" in " ".join(tarfile.open(backups[0]).getnames())
    assert storage.read_schema(base)["schema_version"] == 2
    r2 = storage.migrate(base)
    assert r1["status"] == "MIGRATED" and r2["status"] == "ALREADY_CURRENT"
    assert len(list((base.parent / "qse-backups").glob("*.tar.gz"))) == 1


def test_run_recorder_market_field_and_us_default(tmp_path):
    us = RunRecorder("market_scan", {}, runs_dir=str(tmp_path / "us"))
    man = json.loads((us.dir / "run_manifest.json").read_text())
    assert man["market"] == "US" and "frozen_source_sha256" in man
    kr = RunRecorder("kr_market_scan", {}, runs_dir=str(tmp_path / "kr"), market="KR",
                     stages=("RUN_STARTED", "X"), manifest_extra={"model_version": "KR-EXP-0.1"})
    km = json.loads((kr.dir / "run_manifest.json").read_text())
    assert km["market"] == "KR" and "frozen_source_sha256" not in km and km["model_version"] == "KR-EXP-0.1"
    with pytest.raises(Exception):
        kr.checkpoint("NOT_A_STAGE")


def test_us_ledger_rejects_kr_manifest(tmp_path):
    rd = tmp_path / "r"
    rd.mkdir()
    (rd / "run_manifest.json").write_text(json.dumps({"market": "KR", "mode": "market_scan"}))
    e = prospective_ledger.eligibility_of_run(rd)
    assert not e["eligible"] and "NOT_A_US_MARKET_RUN" in e["reasons"]


def test_us_sync_skips_kr_runs_directory(tmp_path):
    from tests import kr_fakes as F
    from markets.kr.pipeline import KRContext, run_kr_scan
    ctx = KRContext(fetch_kind=F.fake_kind(), provider_factory=F.provider_factory(F.FakeDownload()), now=F.NOW,
                    base_dir=tmp_path)
    run_kr_scan(10_000_000, ctx=ctx)
    out = prospective_ledger.sync_runs(str(tmp_path / "runs"), str(tmp_path / "tracking"))
    assert out["recorded_runs"] == [] and "KR" not in out["skipped"]
    # even pointed straight at a KR run, the US ledger refuses it
    kr_run = next(p for p in (tmp_path / "runs" / "KR").iterdir() if p.is_dir())
    assert "NOT_A_US_MARKET_RUN" in prospective_ledger.eligibility_of_run(kr_run)["reasons"]
    assert not (tmp_path / "tracking" / "ledger" / "observations.jsonl").exists() or \
        all(r.get("market", "US") == "US" for r in prospective_ledger.read_jsonl(
            tmp_path / "tracking" / "ledger" / "observations.jsonl"))
