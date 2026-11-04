"""Summarise a pytest JUnit XML into reports/P6-19_TEST_RESULTS.json (P6-19 Phase E)."""
import json
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main(xml_path="reports/P6-19_pytest_junit.xml", out="reports/P6-19_TEST_RESULTS.json", extra=None):
    tree = ET.parse(ROOT / xml_path)
    suite = tree.getroot().find("testsuite") if tree.getroot().tag == "testsuites" else tree.getroot()
    per_file = defaultdict(lambda: defaultdict(int))
    details = defaultdict(list)
    for case in suite.iter("testcase"):
        mod = case.get("classname", "").split(".")
        fname = "/".join(mod[:2]) + ".py" if len(mod) >= 2 else case.get("file", "?")
        outcome = "passed"
        for child in case:
            if child.tag == "skipped":
                outcome = "xfailed" if child.get("type") == "pytest.xfail" else "skipped"
                details[outcome].append({"test": f"{case.get('classname')}::{case.get('name')}",
                                         "reason": (child.get("message") or "")[:300]})
            elif child.tag in ("failure", "error"):
                outcome = "failed" if child.tag == "failure" else "error"
                details[outcome].append({"test": f"{case.get('classname')}::{case.get('name')}",
                                         "message": (child.get("message") or "")[:300]})
        per_file[fname][outcome] += 1
        per_file[fname]["seconds"] = round(per_file[fname]["seconds"] + float(case.get("time", 0)), 2)
    test_files = sorted(str(p.relative_to(ROOT)) for p in (ROOT / "tests").glob("test_*.py"))
    totals = defaultdict(int)
    for f in per_file.values():
        for k in ("passed", "failed", "error", "skipped", "xfailed"):
            totals[k] += f.get(k, 0)
    payload = {
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "runner": "pytest 8.4.2 + pytest-timeout (180 s per test), offline sandbox (tests/conftest.py)",
        "command": ".venv/bin/python -m pytest tests -q",
        "total_test_files": len(test_files),
        "test_files_with_collected_tests": len(per_file),
        "test_files_without_tests": [f for f in test_files if f not in per_file],
        "total_collected": int(suite.get("tests", 0)),
        "passed": totals["passed"], "failed": totals["failed"], "errors": totals["error"],
        "skipped": totals["skipped"], "xfailed_strict_isolated": totals["xfailed"], "deselected": 0,
        "collection_errors": 0,
        "suite_seconds": float(suite.get("time", 0)),
        "skipped_detail": details["skipped"], "xfailed_detail": details["xfailed"],
        "failed_detail": details["failed"], "error_detail": details["error"],
        "per_file": {k: dict(v) for k, v in sorted(per_file.items())},
        **(extra or {}),
    }
    (ROOT / out).write_text(json.dumps(payload, indent=2))
    print(json.dumps({k: payload[k] for k in ("total_test_files", "test_files_with_collected_tests",
                                              "test_files_without_tests", "total_collected", "passed", "failed",
                                              "errors", "skipped", "xfailed_strict_isolated", "suite_seconds")},
                     indent=1))


if __name__ == "__main__":
    main(*sys.argv[1:])
