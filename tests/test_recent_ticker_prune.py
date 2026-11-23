"""Stock shortcuts saved before the 2026-11-22 guard can hold a code that never existed (the user found 'APPL' among the chart tab's
shortcuts).  terminal/static/app.js drops such a shortcut once per page, only when the price source gave nothing for it while it gave
fresh prices for a known stock at the same time.  The JS is run in node with stand-ins for the server and the browser storage."""
import json
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "terminal" / "static" / "app.js").read_text(encoding="utf-8")


def block() -> str:
    i = APP.index("const PRUNE_PROBE")
    j = APP.index("\n}\n", APP.index("async function pruneRecentTickers(")) + 3
    return APP[i:j]


def run(stored, charts, exact=()):
    """charts: ticker -> the /api/chart answer (None: the request failed)."""
    js = """
let store = { recentTickers: JSON.stringify(%s) };
const localStorage = { getItem: (k) => store[k] ?? null, setItem: (k, v) => { store[k] = v; } };
const isNum = (v) => typeof v === "number" && isFinite(v);
const marketOf = (t) => (/^[0-9A-Z]{6}$/.test(t) && /[0-9]/.test(t) ? "KR" : "US");
function recentTickers() { return JSON.parse(localStorage.getItem("recentTickers") || "[]"); }
const CHARTS = %s, EXACT = new Set(%s);
async function api(url) {
  const q = new URL(url, "http://x").searchParams;
  if (url.startsWith("/api/symbols")) return { exact: EXACT.has(q.get("q")) ? { ticker: q.get("q") } : null, items: [] };
  const c = CHARTS[q.get("t")];
  if (c === undefined || c === null) throw new Error("offline");
  return c;
}
%s
pruneRecentTickers().then(() => console.log(store.recentTickers));
""" % (json.dumps(stored), json.dumps(charts), json.dumps(list(exact)), block())
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip())


# the shapes services.chart returns: its cache part is status, fetched_at and error only
at = lambda s: (datetime.now(timezone.utc) - timedelta(seconds=s)).isoformat()      # noqa: E731
EMPTY = {"status": "UNAVAILABLE", "bars": [], "cache": {"status": "UNAVAILABLE", "fetched_at": None, "error": "EMPTY_RESPONSE"}}
def FRESH():          # stamped when the test runs: the full suite reaches this file minutes after loading it
    return {"status": "REAL", "bars": [1], "cache": {"status": "REAL", "fetched_at": at(1), "error": None}}


def OLD():
    return {"status": "REAL", "bars": [1], "cache": {"status": "REAL", "fetched_at": at(600), "error": None}}

needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")


@needs_node
def test_a_code_with_no_prices_is_dropped_while_the_source_answers():
    got = run(["AAPL", "APPL", "QQQ", "^GSPC"], {"APPL": EMPTY, "QQQ": FRESH(), "SPY": FRESH()}, exact=["AAPL"])
    assert got == ["AAPL", "QQQ", "^GSPC"]


@needs_node
def test_nothing_is_dropped_when_the_source_cannot_be_shown_to_answer():
    assert run(["APPL"], {"APPL": EMPTY, "SPY": EMPTY}) == ["APPL"]                     # offline: the known stock is empty too
    assert run(["APPL"], {"APPL": EMPTY, "SPY": OLD()}) == ["APPL"]                       # only an old stored answer: not proof
    assert run(["APPL"], {"APPL": EMPTY}) == ["APPL"]                                   # the probe request failed
    failed = {**EMPTY, "cache": {**EMPTY["cache"], "error": "ConnectionError"}}
    assert run(["APPL"], {"APPL": failed, "SPY": FRESH()}) == ["APPL"]                    # a failed fetch is not 'no such code'


@needs_node
def test_a_korean_shortcut_is_checked_against_a_korean_stock():
    assert run(["123456", "005930"], {"123456": EMPTY, "005930": FRESH()}, exact=["005930"]) == ["005930"]


def test_the_check_reads_the_fields_the_chart_answer_has():
    src = (ROOT / "terminal" / "services.py").read_text(encoding="utf-8")
    assert '"cache": {k: res[k] for k in ("status", "fetched_at", "error")}' in src and "d.cache.fetched_at" in block() and "age_s" not in block()


def test_the_sweep_runs_once_after_the_first_screen():
    assert "setTimeout(() => pruneRecentTickers().catch(() => {}), 3000);" in APP and APP.count("pruneRecentTickers()") == 2      # the definition and the one call
    assert 'const PRUNE_PROBE = { US: "SPY", KR: "005930" };' in APP
