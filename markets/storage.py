"""Market-aware storage layout and the P6-21 additive storage migration (§3.4).

Layout after migration (schema 2):

    runs/                      US run artifacts (unchanged; pre-P6-21 runs are US by construction)
    runs/KR/                   KR run artifacts (own LATEST)
    tracking/ledger/ ...       US P6-20 ledger, prices, outcomes, reports (unchanged, never rewritten)
    tracking/kr/ledger/ ...    KR ledger, prices, outcomes, reports
    data/kr/                   KR security-master and universe snapshots, KR market-data cache
    tracking/STORAGE_SCHEMA.json   schema version + market partition map + migration history

The migration is additive and idempotent: it only creates directories and the schema file, it never
modifies, moves or deletes an existing file.  A tar.gz backup of ``tracking/`` (and runs/ manifests) is
written first.  Rollback = delete ``tracking/STORAGE_SCHEMA.json``, ``tracking/kr`` and ``runs/KR``
(both empty until a KR run exists); US data is untouched either way.
"""
import json
import os
import tarfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from markets.identity import Market

STORAGE_SCHEMA_VERSION = 2          # 1 = implicit pre-P6-21 layout (US only)
SCHEMA_FILE = "STORAGE_SCHEMA.json"


def root() -> Path:
    return Path(os.getenv("QPP_PROJECT_ROOT", "."))


def runs_dir(market, base: Optional[Path] = None) -> Path:
    base = Path(base) if base else root()
    runs = Path(os.getenv("QPP_RUNS_DIR", str(base / "runs")))
    return runs if Market.parse(market) is Market.US else runs / "KR"


def tracking_dir(market, base: Optional[Path] = None) -> Path:
    base = Path(base) if base else root()
    tr = Path(os.getenv("QPP_TRACKING_DIR", str(base / "tracking")))
    return tr if Market.parse(market) is Market.US else tr / "kr"


def data_dir(market, base: Optional[Path] = None) -> Path:
    base = Path(base) if base else root()
    if Market.parse(market) is Market.US:
        return base / "data"
    return Path(os.getenv("QPP_KR_DATA_DIR", str(base / "data" / "kr")))


def read_schema(base: Optional[Path] = None) -> Dict[str, Any]:
    path = Path(os.getenv("QPP_TRACKING_DIR", str((Path(base) if base else root()) / "tracking"))) / SCHEMA_FILE
    if not path.exists():
        return {"schema_version": 1, "implicit": True,
                "note": "pre-P6-21 layout: every run and ledger record is US by construction"}
    return json.loads(path.read_text(encoding="utf-8"))


def migrate(base: Optional[Path] = None, backup_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Idempotent additive migration to schema 2.  Returns what was done."""
    base = (Path(base) if base else root()).resolve()
    tracking = base / "tracking"
    schema_path = tracking / SCHEMA_FILE
    current = read_schema(base) if schema_path.exists() else {"schema_version": 1}
    if current.get("schema_version", 1) >= STORAGE_SCHEMA_VERSION:
        return {"status": "ALREADY_CURRENT", "schema_version": current["schema_version"], "created": []}
    now = datetime.now(timezone.utc)
    backup = None
    if tracking.exists():
        bdir = Path(backup_dir) if backup_dir else base.parent / "qse-backups"
        bdir.mkdir(parents=True, exist_ok=True)
        backup = bdir / f"tracking_before_storage_v2_{now:%Y%m%dT%H%M%SZ}.tar.gz"
        with tarfile.open(backup, "w:gz") as tar:
            tar.add(tracking, arcname="tracking")
    created = []
    for d in (base / "runs" / "KR", tracking / "kr" / "ledger", base / "data" / "kr"):
        if not d.exists():
            d.mkdir(parents=True)
            created.append(str(d.relative_to(base)))
    tracking.mkdir(parents=True, exist_ok=True)
    schema = {
        "schema_version": STORAGE_SCHEMA_VERSION,
        "markets": {
            "US": {"runs": "runs/", "tracking": "tracking/ (ledger/, prices/, outcomes/, reports/)",
                   "note": "unchanged; records without a 'market' field are US by construction"},
            "KR": {"runs": "runs/KR/", "tracking": "tracking/kr/", "data": "data/kr/"}},
        "history": [{"from": 1, "to": 2, "at": now.isoformat(), "kind": "additive (directories + this file)",
                     "backup": str(backup) if backup else None,
                     "rollback": "delete tracking/STORAGE_SCHEMA.json, tracking/kr/, runs/KR/ (US unaffected)"}],
    }
    tmp = schema_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(schema, indent=1), encoding="utf-8")
    os.replace(tmp, schema_path)
    return {"status": "MIGRATED", "schema_version": STORAGE_SCHEMA_VERSION, "created": created,
            "backup": str(backup) if backup else None}
