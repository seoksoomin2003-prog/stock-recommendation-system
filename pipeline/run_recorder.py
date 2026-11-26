"""Durable run artifacts and stage checkpoints (P6-18 Phase C).

Every run gets a unique ``run_id`` and an artifact directory created before any
provider is contacted.  All JSON writes are atomic (temp file + ``os.replace``)
so an interrupted run never leaves a truncated artifact, and
``execution_status.json`` only says ``COMPLETED`` after ``RUN_COMPLETED`` was
actually checkpointed.
"""
import hashlib
import json
import os
import platform
try:
    import resource
except ImportError:          # Windows has no resource module: the peak is unknown there, never 0
    resource = None
import sys
import time
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

STAGES = (
    "RUN_STARTED",
    "UNIVERSE_BOOTSTRAP_COMPLETED",
    "MARKET_DATA_ACQUISITION_COMPLETED",
    "FINANCIAL_DATA_ACQUISITION_COMPLETED",
    "PROVENANCE_GATE_COMPLETED",
    "FACTOR_ENGINE_COMPLETED",
    "MODEL_RANK_E_COMPLETED",
    "LIQUIDITY_GATE_COMPLETED",
    "PORTFOLIO_GATE_COMPLETED",
    "FINAL_VALIDITY_GATE_COMPLETED",
    "RUN_COMPLETED",
)


def peak_rss_mb() -> float:
    if resource is None:
        return float("nan")
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # macOS reports bytes, Linux reports kilobytes.
    return usage / (1024 * 1024) if sys.platform == "darwin" else usage / 1024


def to_jsonable(obj: Any) -> Any:
    """Serialise numpy/pandas/dataclass values; NaN/inf become null (never a fake number)."""
    import math
    from dataclasses import asdict, is_dataclass
    from enum import Enum
    try:
        import numpy as np
        import pandas as pd
    except Exception:  # pragma: no cover
        np = pd = None
    if obj is None or isinstance(obj, (str, bool)):
        return obj
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, int):
        return obj
    if np is not None:
        if isinstance(obj, np.bool_):
            return bool(obj)
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            value = float(obj)
            return value if math.isfinite(value) else None
        if isinstance(obj, pd.Series):
            return {str(k): to_jsonable(v) for k, v in obj.items()}
        if isinstance(obj, pd.DataFrame):
            return {str(c): to_jsonable(obj[c]) for c in obj.columns}
        if isinstance(obj, pd.Timestamp):
            return obj.isoformat()
    if isinstance(obj, datetime):
        return obj.isoformat()
    if is_dataclass(obj):
        return to_jsonable(asdict(obj))
    if isinstance(obj, dict):
        return {str(k): to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [to_jsonable(v) for v in obj]
    return str(obj)


def atomic_write_json(path: Path, payload: Any):
    path = Path(path)
    tmp = path.with_suffix(path.suffix + f".tmp{os.getpid()}")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(to_jsonable(payload), fh, indent=2, ensure_ascii=False, allow_nan=False)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def frozen_config_fingerprint() -> Dict[str, Any]:
    from utils.config import DECISION_SETTINGS, DEFAULT_FACTOR_WEIGHTS, PORTFOLIO_SETTINGS
    frozen = {"DEFAULT_FACTOR_WEIGHTS": DEFAULT_FACTOR_WEIGHTS, "DECISION_SETTINGS": DECISION_SETTINGS,
              "PORTFOLIO_SETTINGS": PORTFOLIO_SETTINGS, "LIQUIDITY_MIN_VOLUME": 500000,
              "BEAR_ALPHA_PERCENTILE": 0.75}
    digest = hashlib.sha256(json.dumps(frozen, sort_keys=True).encode()).hexdigest()
    return {"values": frozen, "sha256": digest}


FROZEN_SOURCE_FILES = ("core/factor_engine.py", "core/scoring_engine.py", "core/ranking_engine.py",
                       "core/decision_engine.py", "contracts/decision.py")


def frozen_source_hashes() -> Dict[str, Optional[str]]:
    """sha256 of the frozen P6-11B engine sources (tests pin these; manifests record them)."""
    root = Path(__file__).resolve().parents[1]
    out: Dict[str, Optional[str]] = {}
    for rel in FROZEN_SOURCE_FILES:
        try:
            out[rel] = hashlib.sha256((root / rel).read_bytes()).hexdigest()
        except OSError:
            out[rel] = None
    return out


def _sec_status() -> str:
    from utils import runtime_config
    return runtime_config.sec_user_agent_status()["status"]  # never the value (contains a contact e-mail)


def _data_input_spec_version():
    from data.loader import DATA_INPUT_SPEC_VERSION
    return DATA_INPUT_SPEC_VERSION


class RunRecorder:
    def __init__(self, mode: str, params: Dict[str, Any], runs_dir: Optional[str] = None,
                 market: str = "US", stages=None, manifest_extra: Optional[Dict[str, Any]] = None):
        """``market`` (P6-21) is recorded explicitly in every manifest.  The US defaults are unchanged;
        another market supplies its own ``stages`` and ``manifest_extra`` (its own versions), and none
        of the US-specific fields (frozen fingerprints, SEC status, US data spec) are attached to it."""
        self.params = dict(params or {})
        self.market = market
        self.stages = tuple(stages) if stages else STAGES
        from utils import config as cfg
        self.started_monotonic = time.monotonic()
        self.started_at = datetime.now(timezone.utc)
        self.run_id = f"{self.started_at:%Y%m%dT%H%M%SZ}_{mode}_{uuid.uuid4().hex[:6]}"
        self.root = Path(runs_dir or cfg.RUNS_DIR)
        self.dir = self.root / self.run_id
        self.dir.mkdir(parents=True, exist_ok=False)
        self.mode = mode
        self.checkpoints = []
        self.state = "RUNNING"
        try:
            (self.root / "LATEST").write_text(self.run_id + "\n")
        except Exception:
            pass
        manifest = {
            "run_id": self.run_id, "mode": mode, "params": params, "market": market,
            "started_at": self.started_at.isoformat(), "cwd": os.getcwd(),
            "python": sys.version.split()[0], "platform": platform.platform(),
            "machine": platform.machine(), "pid": os.getpid(),
            "packages": self._package_versions(),
        }
        if market == "US":
            manifest.update({
                "market_config_version": "US-1",
                "frozen_core": frozen_config_fingerprint(),
                "frozen_source_sha256": frozen_source_hashes(),
                "sec_user_agent_status": _sec_status(),
                "data_input_spec_version": _data_input_spec_version(),
                "pipeline": "pipeline.canonical.CanonicalPipeline",
            })
        manifest.update(manifest_extra or {})
        self.write("run_manifest.json", manifest)
        self.checkpoint("RUN_STARTED")

    @staticmethod
    def _package_versions() -> Dict[str, Optional[str]]:
        from importlib.metadata import PackageNotFoundError, version
        out = {}
        for name in ("numpy", "pandas", "yfinance", "requests", "beautifulsoup4"):
            try:
                out[name] = version(name)
            except PackageNotFoundError:
                out[name] = None
        return out

    def elapsed(self) -> float:
        return round(time.monotonic() - self.started_monotonic, 3)

    def write(self, name: str, payload: Any):
        atomic_write_json(self.dir / name, payload)

    def write_text(self, name: str, text: str):
        path = self.dir / name
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)

    def _status_payload(self, **extra) -> Dict[str, Any]:
        return {"run_id": self.run_id, "mode": self.mode, "state": self.state,
                "last_checkpoint": self.checkpoints[-1]["stage"] if self.checkpoints else None,
                "elapsed_seconds": self.elapsed(), "peak_rss_mb": round(peak_rss_mb(), 1),
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "checkpoints": self.checkpoints, **extra}

    def checkpoint(self, stage: str, **details):
        if stage not in self.stages:
            raise ValueError(f"Unknown stage {stage}")
        entry = {"stage": stage, "at": datetime.now(timezone.utc).isoformat(),
                 "elapsed_seconds": self.elapsed(), "peak_rss_mb": round(peak_rss_mb(), 1),
                 **details}
        self.checkpoints.append(entry)
        with open(self.dir / "checkpoints.jsonl", "a", encoding="utf-8") as fh:
            fh.write(json.dumps(to_jsonable(entry), ensure_ascii=False) + "\n")
        self.write("execution_status.json", self._status_payload())

    def complete(self, **summary):
        self.checkpoint("RUN_COMPLETED", **summary)
        self.state = "COMPLETED"
        self.write("execution_status.json", self._status_payload(**summary))

    def fail(self, exc: BaseException, state: str = "FAILED"):
        self.state = state
        failure = {
            "run_id": self.run_id, "state": state,
            "failed_after_checkpoint": self.checkpoints[-1]["stage"] if self.checkpoints else None,
            "error_type": type(exc).__name__, "error": str(exc),
            "traceback": traceback.format_exception(type(exc), exc, exc.__traceback__),
            "at": datetime.now(timezone.utc).isoformat(), "elapsed_seconds": self.elapsed(),
            "peak_rss_mb": round(peak_rss_mb(), 1),
        }
        self.write("failure.json", failure)
        self.write("execution_status.json", self._status_payload(error_type=type(exc).__name__, error=str(exc)))
