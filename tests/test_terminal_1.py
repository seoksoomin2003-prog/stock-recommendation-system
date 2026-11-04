"""TERMINAL-1 offline tests: cache honesty, missing != 0, intraday/STALE labels, fiscal-year table,
input validation, watchlist persistence, read-only model view, loopback-only server, no secret leaks.

Every test uses fake sources and a tmp base directory; nothing touches the network or the real data/."""
import json
import socket
import urllib.error
import urllib.request
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from terminal import server, services, sources
from terminal.cache import FileCache
from terminal.services import Terminal, annual_table, clean_ticker

# 2026-11-04 15:00 UTC = 10:00 ET (regular session open); 22:00 UTC = 17:00 ET (after close)
DURING = datetime(2026, 11, 4, 15, 0, tzinfo=timezone.utc)
AFTER = datetime(2026, 11, 4, 22, 0, tzinfo=timezone.utc)


def bars(n, last="2026-11-04", start=100.0):
    from datetime import date, timedelta
    end = date.fromisoformat(last)
    out = []
    for i in range(n):
        d = end - timedelta(days=n - 1 - i)
        c = start + i
        out.append({"date": d.isoformat(), "open": c - 0.5, "high": c + 1, "low": c - 1, "close": c,
                    "adj_close": c, "volume": 1000.0 + i})
    return out


def fact(val, end, start=None, form="10-K", filed=None):
    e = {"val": val, "end": end, "form": form, "filed": filed or end}
    if start:
        e["start"] = start
    return e


def companyfacts(bank=False):
    years = [("2023-01-01", "2023-12-31"), ("2024-01-01", "2024-12-31"), ("2025-01-01", "2025-12-31")]
    g = {
        "Revenues": {"units": {"USD": [fact(100.0 * (i + 1), e, s) for i, (s, e) in enumerate(years)]
                               + [fact(30.0, "2025-09-30", "2025-07-01", form="10-Q")]}},   # quarter ignored
        "NetIncomeLoss": {"units": {"USD": [fact(10.0 * (i + 1), e, s) for i, (s, e) in enumerate(years)]}},
        "Assets": {"units": {"USD": [fact(1000.0, e) for _, e in years]}},
        "Liabilities": {"units": {"USD": [fact(600.0, e) for _, e in years]}},
        "StockholdersEquity": {"units": {"USD": [fact(400.0, e) for _, e in years]}},
        "NetCashProvidedByUsedInOperatingActivities": {"units": {"USD": [fact(50.0, e, s) for s, e in years]}},
    }
    if not bank:
        g["OperatingIncomeLoss"] = {"units": {"USD": [fact(20.0, e, s) for s, e in years]
                                              + [fact(25.0, "2025-12-31", "2025-01-01", filed="2026-02-01")]}}
        g["PaymentsToAcquirePropertyPlantAndEquipment"] = {"units": {"USD": [fact(5.0, e, s) for s, e in years]}}
    return {"facts": {"us-gaap": g}}


class FakeSrc(SimpleNamespace):
    SEC_ARCHIVE = sources.SEC_ARCHIVE
    _num = staticmethod(sources._num)


def fake_src(**over):
    calls = {"history": 0}

    def history(symbols, period):
        calls["history"] += 1
        return {s: bars(60) for s in symbols}

    src = FakeSrc(
        yahoo_history=history,
        yahoo_info=lambda t: {"longName": "Test Co", "marketCap": 1e12},
        sec_cik=lambda t: "0000000001",
        sec_companyfacts=lambda cik: companyfacts(),
        sec_submissions=lambda cik: {"name": "TEST CO", "filings": {"recent": {
            "accessionNumber": ["0001-26-000001"], "form": ["10-K"], "filingDate": ["2026-11-03"],
            "acceptanceDateTime": ["2026-11-03T16:00:00.000Z"], "primaryDocument": ["a10k.htm"],
            "primaryDocDescription": ["10-K"]}}},
        fred_series=lambda sid, start: [["2024-11-01", 100.0], ["2025-10-01", 102.0], ["2025-11-01", 103.0],
                                        ["2026-10-01", None], ["2026-11-01", 104.0]],
        calls=calls)
    for k, v in over.items():
        setattr(src, k, v)
    return src


# ----------------------------------------------------------------------------- cache
def test_cache_real_then_stale_then_unavailable(tmp_path):
    t = [1000.0]
    c = FileCache(tmp_path, clock=lambda: t[0])
    r = c.cached("k", 60, lambda: {"a": 1})
    assert r["status"] == "REAL" and r["data"] == {"a": 1}
    t[0] += 10
    assert c.cached("k", 60, lambda: pytest.fail("fresh hit must not refetch"))["status"] == "REAL"
    t[0] += 100

    def boom():
        raise ConnectionError("down")
    r = c.cached("k", 60, boom)
    assert r["status"] == "STALE" and r["data"] == {"a": 1} and r["error"] == "ConnectionError"
    assert r["age_s"] == 110
    r = c.cached("k", 60, lambda: {})
    assert r["status"] == "STALE" and r["error"] == "EMPTY_RESPONSE"
    r = c.cached("other", 60, boom)
    assert r == {"status": "UNAVAILABLE", "data": None, "fetched_at": None, "age_s": None, "error": "ConnectionError"}
    assert c.read("other") is None                     # a failure is never stored as data


def test_cache_key_sanitised(tmp_path):
    p = FileCache(tmp_path)._path("../../etc/passwd:^GSPC")
    assert p.parent == tmp_path and "/" not in p.name


# ----------------------------------------------------------------------------- sources
def test_num_missing_is_none_not_zero():
    assert sources._num(None) is None and sources._num("x") is None and sources._num(float("nan")) is None
    assert sources._num(0) == 0.0 and sources._num("1.5") == 1.5


def test_fred_layout_guard_and_missing_dot():
    class R:
        status_code = 200
        text = "observation_date,DGS10\n2026-11-02,4.1\n2026-11-03,.\n"
    http = SimpleNamespace(get=lambda *a, **k: R())
    assert sources.fred_series("DGS10", "2026-01-01", http=http) == [["2026-11-02", 4.1], ["2026-11-03", None]]
    R.text = "<html>error</html>"
    with pytest.raises(ValueError):
        sources.fred_series("DGS10", "2026-01-01", http=http)


def test_sec_not_configured_and_error_never_leaks_identity(monkeypatch):
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)
    with pytest.raises(sources.SecNotConfigured):
        sources.sec_user_agent()
    ident = "Research Tool qse-tests@mailbox-test.net"
    monkeypatch.setenv("SEC_USER_AGENT", ident)
    seen = {}

    def get(url, headers, timeout):
        seen.update(headers)
        return SimpleNamespace(status_code=403)
    with pytest.raises(RuntimeError) as ei:
        sources.sec_companyfacts("1", http=SimpleNamespace(get=get))
    assert seen["User-Agent"] == ident
    assert "mailbox-test.net" not in str(ei.value) and "HTTP_403" in str(ei.value)


def test_yahoo_info_drops_missing_fields():
    out = sources.yahoo_info("X", fetch=lambda t: {"longName": "X", "trailingPE": None, "beta": "Infinity",
                                                    "marketCap": "nan", "forwardPE": 12})
    assert out == {"longName": "X", "forwardPE": 12.0}


# ----------------------------------------------------------------------------- services
def test_clean_ticker():
    assert clean_ticker(" aapl ") == "AAPL" and clean_ticker("BRK.B") == "BRK.B" and clean_ticker("^GSPC") == "^GSPC"
    for bad in ("", "../x", "A B", "<script>", "X" * 20):
        with pytest.raises(ValueError):
            clean_ticker(bad)


def test_pct_is_percent_units():
    assert services._pct(101.0, 100.0) == pytest.approx(1.0)
    assert services._pct(None, 1) is None and services._pct(1, 0) is None


def test_intraday_flag_and_stale_label(tmp_path):
    t = Terminal(tmp_path, src=fake_src(), now=lambda: DURING)
    assert t._intraday("2026-11-04") is True
    assert t._intraday("2026-11-03") is False
    assert Terminal(tmp_path, src=fake_src(), now=lambda: AFTER)._intraday("2026-11-04") is False
    assert t._bar_status("2026-11-01", "REAL") == "REAL"
    assert t._bar_status("2026-10-25", "REAL") == "STALE"            # > 5 calendar days old
    assert t._bar_status("2026-11-04", "STALE") == "STALE"
    assert t._bar_status(None, "REAL") == "UNAVAILABLE"


def test_overview_quotes_and_missing_symbol(tmp_path):
    def history(symbols, period):
        return {s: bars(60) for s in symbols if s != "^VIX"}
    t = Terminal(tmp_path, src=fake_src(yahoo_history=history), now=lambda: DURING)
    o = t.overview()
    items = {i["symbol"]: i for g in o["groups"] for i in g["items"]}
    spx = items["^GSPC"]
    assert spx["status"] == "REAL" and spx["intraday"] is True
    assert spx["change_pct"] == pytest.approx((159 / 158 - 1) * 100)
    vix = items["^VIX"]
    assert vix["status"] == "UNAVAILABLE" and vix["close"] is None and vix["change_pct"] is None   # never 0


def test_chart_sma_and_ranges(tmp_path):
    t = Terminal(tmp_path, src=fake_src(yahoo_history=lambda s, p: {s[0]: bars(300)}), now=lambda: AFTER)
    c = t.chart("aapl", "1y")
    assert c["ticker"] == "AAPL" and len(c["bars"]) == 252 and c["status"] == "REAL"
    assert c["bars"][-1]["sma20"] == pytest.approx(sum(100 + i for i in range(280, 300)) / 20)
    assert c["last"]["intraday"] is False
    short = Terminal(tmp_path / "b", src=fake_src(yahoo_history=lambda s, p: {s[0]: bars(30)}), now=lambda: AFTER)
    c = short.chart("AAPL", "3mo")
    assert c["bars"][-1]["sma200"] is None and c["last"]["vs_sma200_pct"] is None      # not enough history
    with pytest.raises(ValueError):
        t.chart("AAPL", "10y")
    empty = Terminal(tmp_path / "c", src=fake_src(yahoo_history=lambda s, p: {}), now=lambda: AFTER)
    assert empty.chart("ZZZZ")["status"] == "UNAVAILABLE"


def test_annual_table_fiscal_years_and_latest_filing():
    tab = annual_table(companyfacts())
    assert tab["years"] == ["2023-12-31", "2024-12-31", "2025-12-31"]
    rows = {r["key"]: r for r in tab["rows"]}
    assert rows["revenue"]["values"]["2025-12-31"] == 300.0                 # 10-Q quarter ignored
    assert rows["operating_income"]["values"]["2025-12-31"] == 25.0         # later filing wins
    assert rows["fcf"]["values"]["2024-12-31"] == 45.0
    assert rows["debt_ratio"]["values"]["2024-12-31"] == pytest.approx(1.5)
    assert rows["eps_diluted"]["values"]["2024-12-31"] is None


def test_annual_table_bank_rows_missing_not_zero():
    rows = {r["key"]: r for r in annual_table(companyfacts(bank=True))["rows"]}
    for k in ("operating_income", "capex", "fcf", "op_margin", "cash"):
        assert all(v is None for v in rows[k]["values"].values()), k
    assert rows["net_margin"]["values"]["2023-12-31"] == pytest.approx(0.1)


def test_company_fundamentals_unavailable_reasons(tmp_path):
    t = Terminal(tmp_path, src=fake_src(sec_cik=lambda x: None), now=lambda: AFTER)
    f = t.company("SPY")["fundamentals"]
    assert f["status"] == "UNAVAILABLE" and "CIK" in f["reason"]

    def nocfg(cik):
        raise sources.SecNotConfigured("x")
    t = Terminal(tmp_path / "b", src=fake_src(sec_companyfacts=nocfg), now=lambda: AFTER)
    f = t.company("AAPL")["fundamentals"]
    assert f["status"] == "UNAVAILABLE" and "SEC_USER_AGENT" in f["reason"]
    ok = Terminal(tmp_path / "c", src=fake_src(), now=lambda: AFTER).company("AAPL")
    assert ok["fundamentals"]["status"] == "REAL" and ok["profile"]["data"]["longName"] == "Test Co"


def test_filings_urls(tmp_path):
    f = Terminal(tmp_path, src=fake_src(), now=lambda: AFTER).filings("AAPL")
    assert f["status"] == "REAL" and f["items"][0]["form"] == "10-K"
    assert f["items"][0]["url"] == "https://www.sec.gov/Archives/edgar/data/1/000126000001/a10k.htm"


def test_macro_yoy_and_missing_points(tmp_path):
    m = {i["id"]: i for i in Terminal(tmp_path, src=fake_src(), now=lambda: AFTER).macro()["items"]}
    assert m["DGS10"]["value"] == 104.0 and m["DGS10"]["date"] == "2026-11-01"     # '.'/None skipped
    assert m["CPIAUCSL"]["value"] == pytest.approx((104 / 103 - 1) * 100)
    assert m["DGS10"]["value_1y_ago"] == 103.0


def test_macro_unavailable(tmp_path):
    def down(sid, start):
        raise ConnectionError()
    items = Terminal(tmp_path, src=fake_src(fred_series=down), now=lambda: AFTER).macro()["items"]
    assert all(i["status"] == "UNAVAILABLE" and i["value"] is None for i in items)


def test_watchlist_persistence(tmp_path):
    t = Terminal(tmp_path, src=fake_src(), now=lambda: AFTER)
    assert t.watchlist() == ["AAPL", "MSFT", "NVDA", "SPY"]
    assert t.watchlist_add("tsla")[-1] == "TSLA"
    assert t.watchlist_add("TSLA").count("TSLA") == 1
    t.watchlist_remove("AAPL")
    again = Terminal(tmp_path, src=fake_src(), now=lambda: AFTER)
    assert again.watchlist() == ["MSFT", "NVDA", "SPY", "TSLA"]
    assert (tmp_path / "data" / "terminal" / "watchlist.json").exists()
    with pytest.raises(ValueError):
        t.watchlist_add("bad ticker")
    q = again.watchlist_quotes()
    assert [i["symbol"] for i in q["items"]] == q["tickers"]


def _tree(p):
    return {str(f.relative_to(p)): f.stat().st_mtime_ns for f in p.rglob("*") if f.is_file()}


def test_model_view_is_read_only(tmp_path):
    run = tmp_path / "runs" / "20261104T000000Z_market_scan_x"
    run.mkdir(parents=True)
    (run / "validation_result.json").write_text(json.dumps({
        "run_id": "R1", "mode": "market_scan", "validation_scope": "full", "recommendation_status": "REAL RECOMMENDATION",
        "recommendations": [{"recommendation_rank": 1, "ticker": "CL", "alpha": 4.9, "secret_field": "x"}]}))
    (tmp_path / "runs" / "LATEST").write_text("R1")
    before = _tree(tmp_path)
    m = Terminal(tmp_path, src=fake_src(), now=lambda: AFTER).model()
    assert _tree(tmp_path) == before
    assert m["baseline"]["status"] == "FROZEN" and m["baseline"]["run_id"] == "R1"
    assert m["baseline"]["top5"][0]["ticker"] == "CL" and "secret_field" not in m["baseline"]["top5"][0]
    assert m["challengers"] == []


def test_health_reports_status_word_only(tmp_path, monkeypatch):
    monkeypatch.setenv("SEC_USER_AGENT", "Research Tool qse-tests@mailbox-test.net")
    h = Terminal(tmp_path, src=fake_src(), now=lambda: AFTER).health()
    assert "mailbox-test.net" not in json.dumps(h) and h["sec"] in ("CONFIGURED", "MISSING", "INVALID")


# ----------------------------------------------------------------------------- server
_ORIG_CREATE_CONNECTION = socket.create_connection     # captured at import, before the conftest guard


@pytest.fixture(autouse=True)
def _loopback_only(monkeypatch):
    """The conftest guard blocks every create_connection; these tests may reach 127.0.0.1 and nothing else."""
    def create_connection(address, *a, **k):
        if address[0] not in ("127.0.0.1", "localhost"):
            raise OSError(f"non-loopback connection blocked in tests ({address!r})")
        return _ORIG_CREATE_CONNECTION(address, *a, **k)
    monkeypatch.setattr(socket, "create_connection", create_connection)


@pytest.fixture
def live(tmp_path, monkeypatch):
    monkeypatch.setenv("SEC_USER_AGENT", "Research Tool qse-tests@mailbox-test.net")
    t = Terminal(tmp_path, src=fake_src(), now=lambda: AFTER)
    httpd = server.serve(port=0, terminal=t, background=True)
    yield f"http://127.0.0.1:{httpd.server_port}", httpd
    httpd.shutdown()
    httpd.server_close()


def _get(url):
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            return r.status, r.headers, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read()


def _post(url, body, origin=None):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", **({"Origin": origin} if origin else {})})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_server_binds_loopback_only(live):
    _, httpd = live
    assert httpd.server_address[0] == "127.0.0.1" and server.HOST == "127.0.0.1"


def test_api_endpoints_json(live):
    base, _ = live
    for path in ("/api/health", "/api/overview", "/api/chart?t=AAPL&range=3mo", "/api/company?t=AAPL",
                 "/api/filings?t=AAPL", "/api/macro", "/api/watchlist", "/api/model"):
        code, headers, body = _get(base + path)
        assert code == 200, path
        assert headers["Content-Type"].startswith("application/json")
        text = body.decode()
        assert "mailbox-test.net" not in text and "NaN" not in text, path
        json.loads(text)
    code, _, body = _get(base + "/api/chart?t=../etc&range=1y")
    assert code == 400 and json.loads(body)["error"] == "INVALID_TICKER"
    assert _get(base + "/api/nope")[0] == 404


def test_api_internal_error_hides_details(tmp_path):
    def boom(*a):
        raise RuntimeError("token=abc123 qse-tests@mailbox-test.net")
    t = Terminal(tmp_path, src=fake_src(yahoo_history=boom), now=lambda: AFTER)
    t.overview = lambda: (_ for _ in ()).throw(RuntimeError("qse-tests@mailbox-test.net"))
    httpd = server.serve(port=0, terminal=t, background=True)
    try:
        code, _, body = _get(f"http://127.0.0.1:{httpd.server_port}/api/overview")
    finally:
        httpd.shutdown()
        httpd.server_close()
    assert code == 500 and b"mailbox-test.net" not in body and json.loads(body)["error"] == "INTERNAL_ERROR"


def test_watchlist_api_and_origin_check(live):
    base, httpd = live
    code, body = _post(base + "/api/watchlist/add", {"ticker": "amd"}, origin=base)
    assert code == 200 and "AMD" in body["tickers"]
    code, body = _post(base + "/api/watchlist/add", {"ticker": "evil"}, origin="https://evil.example")
    assert code == 403 and body["error"] == "FORBIDDEN_ORIGIN"
    code, body = _post(base + "/api/watchlist/remove", {"ticker": "AMD"})
    assert code == 200 and "AMD" not in body["tickers"]
    code, body = _post(base + "/api/watchlist/add", {"ticker": "a b"}, origin=base)
    assert code == 400 and body["error"] == "INVALID_TICKER"


def test_static_files_and_traversal(live):
    base, _ = live
    code, headers, body = _get(base + "/")
    assert code == 200 and "text/html" in headers["Content-Type"] and "퀀트 터미널" in body.decode()
    assert _get(base + "/app.js")[0] == 200 and _get(base + "/style.css")[0] == 200
    assert _get(base + "/../services.py")[0] == 404
    assert _get(base + "/%2e%2e/services.py")[0] == 404


def test_finite_never_emits_nan():
    assert server._finite({"a": float("nan"), "b": [float("inf"), 1.0], "c": 0.0}) == {"a": None, "b": [None, 1.0], "c": 0.0}


def test_static_ui_has_no_external_resources():
    from pathlib import Path
    root = Path(server.STATIC)
    for f in ("index.html", "app.js", "style.css"):
        text = (root / f).read_text(encoding="utf-8")
        assert "http://" not in text.replace("http://127.0.0.1", "") and "https://" not in text, f
    assert "lang=\"ko\"" in (root / "index.html").read_text(encoding="utf-8")


def test_app_cli_has_terminal_command():
    import app
    args = app.build_parser().parse_args(["terminal", "--port", "9999"])
    assert args.command == "terminal" and args.port == 9999 and args.open is False
