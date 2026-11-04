"""Re-derive a run's TOP-5 from its own artifacts with the unmodified frozen DecisionEngine (P6-19 F3).

Thin wrapper around pipeline.replay. No network access.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.replay import replay  # noqa: E402

if __name__ == "__main__":
    out = replay(Path(sys.argv[1]))
    print(json.dumps(out, indent=1))
    sys.exit(0 if out["match"] else 1)
