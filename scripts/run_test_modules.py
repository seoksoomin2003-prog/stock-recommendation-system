"""Run every tests/test_*.py module in its own subprocess with a timeout (P6-18).

Classifies each module as PASSED / FAILED / ERROR / TIMEOUT and records counts,
so a single hanging legacy test cannot hide the results of the others.
Writes reports/P6-18_TEST_RESULTS.json.
"""
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TIMEOUT = int(sys.argv[1]) if len(sys.argv) > 1 else 180


def main():
    results = []
    for path in sorted((ROOT / "tests").glob("test_*.py")):
        mod = f"tests.{path.stem}"
        t0 = time.time()
        try:
            out = subprocess.run([sys.executable, "-m", "unittest", mod], cwd=ROOT, capture_output=True, text=True,
                                 timeout=TIMEOUT, env={**__import__("os").environ, "QPP_LOG_LEVEL": "ERROR"})
            text = out.stdout + out.stderr
            ran = re.search(r"Ran (\d+) test", text)
            tail = re.search(r"\n(OK|FAILED)[^\n]*", text)
            status = "PASSED" if out.returncode == 0 else "FAILED"
            fails = re.findall(r"^(FAIL|ERROR): (\S+)", text, re.M)
            results.append({"module": mod, "status": status, "tests": int(ran.group(1)) if ran else 0,
                            "summary": tail.group(0).strip() if tail else text.strip().splitlines()[-1:],
                            "failures": [f"{k}: {n}" for k, n in fails], "seconds": round(time.time() - t0, 1)})
        except subprocess.TimeoutExpired:
            results.append({"module": mod, "status": "TIMEOUT", "tests": None, "seconds": TIMEOUT,
                            "summary": f"no result within {TIMEOUT}s"})
        r = results[-1]
        print(f"{r['status']:8} {r['seconds']:7.1f}s {mod} {r.get('summary')}", flush=True)
    payload = {"executed_at": datetime.now(timezone.utc).isoformat(), "python": sys.version.split()[0],
               "timeout_seconds": TIMEOUT, "modules": results,
               "totals": {s: sum(1 for r in results if r["status"] == s) for s in ("PASSED", "FAILED", "TIMEOUT")}}
    (ROOT / "reports" / "P6-18_TEST_RESULTS.json").write_text(json.dumps(payload, indent=2))
    print(payload["totals"])


if __name__ == "__main__":
    main()
