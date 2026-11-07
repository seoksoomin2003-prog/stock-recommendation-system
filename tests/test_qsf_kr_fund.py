"""Korean statements: figures wait for their receipt date, bases never mix, the key is not written.  No network."""
import gzip
import io
import json
import math
import zipfile

import numpy as np
import pytest

from terminal.qsf import dart_history as dh, research_kr_fund as kf


def row(stock, basis, name, amt, add="", rcept="20200401000001", dt=""):
    return [rcept, "C" + stock, stock, basis, "IS", name, dt, amt, add]


def put(root, year, report, rows):
    p = dh.path_of(root, year, report, 0)
    p.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(p, "wt", encoding="utf-8") as fh:
        json.dump(rows, fh, ensure_ascii=False)


def test_receipt_day_commas_and_the_first_row_of_an_account(tmp_path):
    put(tmp_path, 2020, "FY", [row("000010", "CFS", "당기순이익(손실)", "1,000"), row("000010", "CFS", "당기순이익(손실)", "900"), row("000010", "CFS", "어떤계정", "5")])
    r = kf.load_reports(tmp_path)["000010"][(2020, "FY")]["CFS"]
    assert r["rcept"] == "2020-04-01" and r["ni"] == (1000.0, None) and len(r) == 2


def reports():
    def rep(rcept, assets, ni, ytd=None):
        return {"CFS": {"rcept": rcept, "assets": (assets, None), "equity": (assets / 2, None), "liab": (assets / 2, None), "ni": (ni, ytd), "op": (ni * 2, None if ytd is None else ytd * 2), "sales": (ni * 10, None if ytd is None else ytd * 10), "ca": (10.0, None), "cl": (5.0, None)}}
    return {(2019, "FY"): rep("2020-03-20", 100.0, 40.0), (2019, "H1"): rep("2019-08-14", 90.0, 8.0, 18.0), (2020, "H1"): rep("2020-08-14", 110.0, 12.0, 30.0)}


def test_four_quarters_come_from_last_year_plus_this_year_less_the_same_stretch():
    assert kf.ttm(reports(), 2020, "H1", "CFS", "ni") == 40 + 30 - 18
    assert kf.ttm(reports(), 2019, "FY", "CFS", "ni") == 40
    assert kf.ttm(reports(), 2019, "H1", "CFS", "ni") is None      # no 2018 year behind it


def test_bases_do_not_mix():
    r = reports()
    r[(2020, "H1")] = {"OFS": r[(2020, "H1")]["CFS"]}
    assert kf.ttm(r, 2020, "H1", "OFS", "ni") is None


def test_a_report_counts_only_after_its_receipt_day():
    days, m = kf.timeline(reports())
    assert days == ["2019-08-14", "2020-03-20", "2020-08-14"] and m.shape == (3, len(kf.REPORT_FIELDS))
    assert kf.latest(days, "2020-08-14") == 1 and kf.latest(days, "2020-08-15") == 2 and kf.latest(days, "2019-01-01") is None


def test_an_amended_old_report_does_not_replace_a_newer_period():
    r = {(2020, "FY"): {"CFS": {"rcept": "2021-03-20", "assets": (10.0, None)}}, (2020, "Q3"): {"CFS": {"rcept": "2021-06-01", "assets": (7.0, None)}}, (2021, "FY"): {"CFS": {"rcept": "2022-03-20", "assets": (20.0, None)}}}
    days, m = kf.timeline(r)
    a = kf.REPORT_FIELDS.index("assets")
    assert days == ["2021-03-20", "2021-06-01", "2022-03-20"] and list(m[:, a]) == [10, 10, 20]


def test_an_amended_input_holds_back_the_report_that_uses_it():
    r = {(2019, "FY"): {"CFS": {"rcept": "2021-09-01", "assets": (5.0, None), "ni": (1.0, None)}}, (2020, "FY"): {"CFS": {"rcept": "2021-03-20", "assets": (10.0, None), "ni": (2.0, None)}}}
    days, _ = kf.timeline(r)
    assert days == ["2021-09-01", "2021-09-01"]


def test_a_company_that_stopped_reporting_goes_blank():
    assert kf.latest(["2020-01-01"], "2021-06-01") is None and kf.latest(["2020-01-01"], "2021-01-01") == 0


def test_separate_statements_are_used_only_without_consolidated():
    r = {(2020, "FY"): {"OFS": {"rcept": "2021-03-01", "assets": (5.0, None)}, "CFS": {"rcept": "2021-03-01", "assets": (9.0, None)}}, (2021, "FY"): {"OFS": {"rcept": "2022-03-01", "assets": (6.0, None)}}}
    _, m = kf.timeline(r)
    a = kf.REPORT_FIELDS.index("assets")
    assert m[0, a] == 9 and m[1, a] == 6


def test_signals_and_empty_stay_empty():
    days, m = kf.timeline(reports())
    s = kf.signals(m[2], 200.0, 0.1)
    assert s["bm"] == pytest.approx(55 / 200) and s["ep"] == pytest.approx(52 / 200) and s["low_leverage"] == pytest.approx(0.5) and s["current"] == pytest.approx(2)
    assert s["asset_growth"] == pytest.approx(110 / 90 - 1) and s["issuance"] == 0.1
    assert math.isnan(s["ni_change"])      # the year-earlier four quarters are not there
    neg = dict(zip(kf.REPORT_FIELDS, m[2]))
    neg["equity"] = -5.0
    assert math.isnan(kf.signals([neg[k] for k in kf.REPORT_FIELDS], 200.0, 0.0)["roe"])


def test_directions_are_fixed():
    assert not kf.GOOD_HIGH["asset_growth"] and not kf.GOOD_HIGH["issuance"] and kf.GOOD_HIGH["ep"] and len(kf.SIGNALS) == 12


def test_the_second_test_is_refused(tmp_path):
    p = tmp_path / kf.REPORT
    p.parent.mkdir(parents=True)
    p.write_text("{}")
    with pytest.raises(RuntimeError):
        kf.run_once(tmp_path)


def test_company_list_keeps_only_stock_codes():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("CORPCODE.xml", "<result><list><corp_code>1</corp_code><stock_code> </stock_code></list><list><corp_code>2</corp_code><stock_code>000010</stock_code></list></result>")
    assert dh.parse_corp_list(buf.getvalue()) == {"000010": "2"}


class Resp:
    def __init__(self, body):
        self.body = body

    def json(self):
        return self.body


def test_download_keeps_going_and_stops_on_the_limit_and_never_writes_the_key(tmp_path):
    calls = []

    def get(url, params, timeout):
        calls.append(params["reprt_code"])
        return Resp({"status": "000", "list": [{"rcept_no": "20200101000001", "corp_code": "1", "crtfc_key": params["crtfc_key"]}]})
    res = dh.download(tmp_path, "SECRET", get, ["1", "2"], [2020], sleep=lambda s: None, log=lambda m: None)
    assert res["status"] == "DONE" and len(calls) == 4
    assert dh.download(tmp_path, "SECRET", get, ["1", "2"], [2020], sleep=lambda s: None, log=lambda m: None)["calls"] == 0
    assert all(b"SECRET" not in gzip.open(p).read() for p in tmp_path.rglob("*.gz"))
    stop = dh.download(tmp_path, "SECRET", lambda *a, **k: Resp({"status": "020"}), ["1"], [2021], sleep=lambda s: None, log=lambda m: None)
    assert stop["stopped"] == "DART_020"


def test_an_exception_message_cannot_carry_the_key(tmp_path):
    logged = []

    def get(url, params, timeout):
        raise ConnectionError(f"failed {params['crtfc_key']}")
    res = dh.download(tmp_path, "SECRET", get, ["1"], [2020], sleep=lambda s: None, log=logged.append)
    assert res["status"] == "INCOMPLETE" and res["missed"] == 4 and logged and not any("SECRET" in m for m in logged)


def test_no_data_is_stored_so_it_is_not_asked_again(tmp_path):
    res = dh.download(tmp_path, "K", lambda *a, **k: Resp({"status": "013"}), ["1"], [2015], sleep=lambda s: None, log=lambda m: None)
    assert res["status"] == "DONE" and res["stored"] == 4
    assert np.array(json.loads(gzip.open(dh.path_of(tmp_path, 2015, "FY", 0), "rt").read())).size == 0


def test_refresh_asks_again_only_what_it_is_told(tmp_path):
    asked = []

    def get(url, params, timeout):
        asked.append((params["bsns_year"], params["reprt_code"]))
        return Resp({"status": "000", "list": []})
    dh.download(tmp_path, "K", get, ["1"], [2025, 2026], sleep=lambda s: None, log=lambda m: None)
    asked.clear()
    dh.download(tmp_path, "K", get, ["1"], [2025, 2026], sleep=lambda s: None, log=lambda m: None, refresh=lambda y, r: y == 2026 or (y == 2025 and r == "FY"))
    assert sorted(asked) == sorted([(2025, "11011"), (2026, "11013"), (2026, "11012"), (2026, "11014"), (2026, "11011")])
