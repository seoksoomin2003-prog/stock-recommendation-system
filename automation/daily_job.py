"""Daily automated market scan (P6-18): thin wrapper over the canonical service.

Runs the same Automated Market Scan as ``python app.py scan`` and also writes
the legacy ``reports/daily/RECOMMENDATION_<date>.md`` summary (copied from the
run's ``report.md``).  ``TEST_MODE=1`` bounds the scan to 3 constituents and is
labelled ``validation_scope=bounded`` in the artifacts.
"""
import os
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from utils import runtime_config

runtime_config.load_local_env()

from pipeline.service import run_market_scan  # noqa: E402
from utils.logger import setup_logger  # noqa: E402

logger = setup_logger("DailyJob")


def run_daily_job(**scan_kwargs):
    logger.info("Starting Daily Autonomous Job...")
    start = time.time()
    limit = 3 if os.environ.get("TEST_MODE") == "1" else None
    # P6-19: capital must be configured explicitly (QPP_CAPITAL); there is no default amount.
    capital = scan_kwargs.pop("capital", None)
    capital, source = runtime_config.resolve_capital(capital)
    result = run_market_scan(capital=capital, limit=limit, capital_source=source, **scan_kwargs)
    report_dir = Path(os.getenv("QPP_DAILY_REPORT_DIR", "reports/daily"))
    report_dir.mkdir(parents=True, exist_ok=True)
    src = Path(result.get("artifact_dir", "")) / "report.md"
    if src.exists():
        dst = report_dir / f"RECOMMENDATION_{datetime.now():%Y-%m-%d}.md"
        shutil.copyfile(src, dst)
        logger.info(f"Daily report: {dst}")
    logger.info(f"Daily job finished in {time.time() - start:.1f}s: {result.get('display_status')} "
                f"(run {result.get('run_id')})")
    return result


if __name__ == "__main__":
    os.chdir(PROJECT_ROOT)  # P6-19: at run time only; importing this module has no side effects
    run_daily_job()
