#!/bin/zsh
# A quick check before a commit (assessment 2026-11-26, P2-6): every Python file compiles, every screen script parses, and the
# fast guard tests pass.  About a minute.  It does not replace the full test run (about 20 minutes): python -m pytest -q
cd "$(dirname "$0")/.." || exit 1
PY=.venv/bin/python
echo "1/3 Python files compile"
$PY -m compileall -q app.py terminal markets pipeline utils core tests >/dev/null || { echo "FAILED: a Python file does not compile"; exit 1; }
echo "2/3 screen scripts parse"
for f in terminal/static/*.js; do node --check "$f" || { echo "FAILED: $f"; exit 1; }; done
echo "3/3 guard tests (frozen score, wording, error sentences, phone writes)"
$PY -m pytest -q -p no:cacheprovider tests/test_freeze_and_entry_book.py tests/test_rules_r2.py tests/test_maturity_fixes_2026_11_22.py tests/test_phone_view.py tests/test_audit10_p0_2026_11_26.py || { echo "FAILED: a guard test"; exit 1; }
echo "OK. Run the full suite before committing a change to code: $PY -m pytest -q"
