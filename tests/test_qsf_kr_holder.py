"""Korean largest-holder test: the table read correctly, usable the day after receipt, no holder name kept, the key not written, one run.  No network."""
import json
from datetime import date, timedelta

import numpy as np
import pytest

from terminal.qsf import research_kr as kr, research_kr_fund as kf, research_kr_holder as kh
from tests.test_qsf_kr_events import small_prices

KEY = "not-a-real-key-789"
RC = "20250321000557"


def row(kind, name, end, begin, rc=RC):
    return {"rcept_no": rc, "stock_knd": kind, "nm": name, "relate": "특수관계인", "trmend_posesn_stock_qota_rt": end, "bsis_posesn_stock_qota_rt": begin}


def test_the_total_row_of_common_stock_is_read():
    table = [row("보통주", "홍길동", "19.20", "19.20"), row("보통주", "이순신", "0.80", "1.00"), row("보통주", "계", "20.00", "20.20"), row("우선주", "계", "55.00", "55.00")]
    assert kh.parse_table(table) == (RC, 20.0, 20.2)


def test_without_a_total_row_the_rows_are_summed():
    assert kh.parse_table([row("보통주식", "가", "10.5", "9"), row("보통주식", "나", "2.5", "1")]) == (RC, 13.0, 10.0)


def test_a_missing_part_leaves_the_sum_empty():
    assert kh.parse_table([row("보통주", "가", "10.5", "-"), row("보통주", "나", "2.5", "1")]) == (RC, 13.0, None)


@pytest.mark.parametrize("table", [[], None, [row("우선주", "계", "10", "10")], [row("-", "계", "-", "-")]])
def test_no_common_stock_is_empty_not_zero(table):
    assert kh.parse_table(table)[1:] == (None, None)


def test_an_impossible_share_is_left_empty():
    assert kh.parse_table([row("보통주", "계", "130.0", "20")])[1:] == (None, 20.0)
    assert kh.parse_table([row("보통주", "합계", "1,020.0", "-1")])[1:] == (None, None)


class Reply:
    def __init__(self, body):
        self.body = body

    def json(self):
        return self.body


def good(url, params=None, timeout=None):
    return Reply({"status": "000", "list": [row("보통주", "비밀 주주", "30", "28", rc=params["bsns_year"] + "0321000001"), row("보통주", "계", "30", "28", rc=params["bsns_year"] + "0321000001")]})


TODO = [("C1", "000010", 2024), ("C1", "000010", 2023), ("C2", "000020", 2024)]


def test_download_keeps_values_only_and_resumes(tmp_path):
    asked = []

    def get(url, params=None, timeout=None):
        asked.append((params["corp_code"], params["bsns_year"], params["reprt_code"]))
        assert "hyslrSttus" in url
        return good(url, params)
    res = kh.download(tmp_path, TODO, log=lambda m: None, get=get, sleep=lambda s: None, key=KEY)
    assert res == {"status": "DONE", "calls": 3} and asked[0] == ("C1", "2024", "11011")
    text = "".join(p.read_text(encoding="utf-8") for p in (tmp_path / kh.DATA).glob("*.jsonl"))
    assert "비밀" not in text and KEY not in text
    assert json.loads((tmp_path / kh.DATA / "2023.jsonl").read_text(encoding="utf-8").splitlines()[0]) == ["000010", 2023, "20230321000001", 30.0, 28.0]
    assert kh.download(tmp_path, TODO, log=lambda m: None, get=get, sleep=lambda s: None, key=KEY) == {"status": "DONE", "calls": 0}


def test_no_data_is_written_once_so_it_is_not_asked_forever(tmp_path):
    get = lambda url, params=None, timeout=None: Reply({"status": "013"})      # noqa: E731
    kh.download(tmp_path, TODO[:1], log=lambda m: None, get=get, sleep=lambda s: None, key=KEY)
    assert kh.download(tmp_path, TODO[:1], log=lambda m: None, get=get, sleep=lambda s: None, key=KEY)["calls"] == 0
    assert kh.load_reports(tmp_path / kh.DATA) == {}


def test_download_pauses_at_its_own_cap_and_resumes(tmp_path):
    got = kh.download(tmp_path, TODO, log=lambda m: None, get=good, sleep=lambda s: None, key=KEY, max_calls=2)
    assert got == {"status": "PAUSED", "stopped": "CALL_CAP", "calls": 2, "left": 1}
    assert kh.download(tmp_path, TODO, log=lambda m: None, get=good, sleep=lambda s: None, key=KEY)["calls"] == 1


@pytest.mark.parametrize("state", ["020", "010", "011", "012", "901"])
def test_download_stops_on_the_limit_or_a_key_problem(tmp_path, state):
    get = lambda url, params=None, timeout=None: Reply({"status": state})      # noqa: E731
    assert kh.download(tmp_path, TODO, log=lambda m: None, get=get, sleep=lambda s: None, key=KEY) == {"status": "STOPPED", "stopped": f"DART_{state}", "calls": 1}


def test_an_error_never_carries_the_address(tmp_path):
    logs = []

    def get(url, params=None, timeout=None):
        raise RuntimeError(f"failed {url}?crtfc_key={params['crtfc_key']}")
    res = kh.download(tmp_path, TODO * 5, log=logs.append, get=get, sleep=lambda s: None, key=KEY)
    assert res["stopped"] == "TOO_MANY_FAILURES" and logs and all(KEY not in x for x in logs)


def test_no_key_does_nothing(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENDART_API_KEY", raising=False)
    assert kh.download(tmp_path, TODO) == {"status": "NO_KEY"} and not (tmp_path / kh.DATA).exists()


def reports_file(tmp_path, lines):
    root = tmp_path / kh.DATA
    root.mkdir(parents=True, exist_ok=True)
    with open(root / "2020.jsonl", "a", encoding="utf-8") as fh:
        for x in lines:
            fh.write(json.dumps(x) + "\n")
    return root


def test_reports_load_in_receipt_order_with_the_change(tmp_path):
    root = reports_file(tmp_path, [["000010", 2021, "20220330000001", 41.0, 40.0], ["000010", 2020, "20210330000001", 40.0, None], ["000020", 2020, None, None, None]])
    assert kh.load_reports(root) == {"000010": (["2021-03-30", "2022-03-30"], [(40.0, None), (41.0, 1.0)])}


def test_a_report_is_not_usable_on_its_receipt_day_and_goes_stale():
    px = small_prices(start=date(2019, 1, 1), sessions=800)
    i = 700
    on = px.dates[i]
    code = px.symbols[0]
    got = lambda days: kh.build_features(px, [i], {code: (days, [(40.0, 1.0)] * len(days))}, log=lambda m: None)[0, 0]      # noqa: E731
    assert np.isnan(got([on])).all()
    assert got([px.dates[i - 1]]).tolist() == [40.0, 1.0]
    old = (date.fromisoformat(on) - timedelta(days=kf.STALE_DAYS + 1)).isoformat()
    assert np.isnan(got([old])).all()


def test_an_ineligible_stock_stays_empty_and_a_missing_change_stays_empty():
    px = small_prices(start=date(2019, 1, 1), sessions=800)
    i = 700
    px.data["volume"][i, 1] = 0
    day = px.dates[i - 5]
    got = kh.build_features(px, [i], {px.symbols[0]: ([day], [(40.0, None)]), px.symbols[1]: ([day], [(50.0, 2.0)])}, log=lambda m: None)[0]
    assert got[0, 0] == 40.0 and np.isnan(got[0, 1]) and np.isnan(got[1]).all() and np.isnan(got[2]).all()


def test_targets_cover_two_years_before_first_qualifying_and_stop_at_the_last():
    px = small_prices(start=date(2020, 6, 1), sessions=400)
    rows = list(range(260, 400, 5))
    corp = {px.symbols[0]: "C0"}
    got = kh.targets(px, rows, corp)
    first_year = int(px.dates[260][:4])
    assert {t[0] for t in got} == {"C0"} and min(t[2] for t in got) == first_year - 2 and max(t[2] for t in got) == int(px.dates[395][:4])
    assert [t[2] for t in got] == sorted((t[2] for t in got), reverse=True)


def test_a_score_needs_both_signals():
    t = np.full((1, 60, 2), np.nan, dtype=np.float32)
    t[0, :50, 0] = np.arange(50)
    t[0, :49, 1] = np.arange(49)
    s = kh.score_of(t)[0]
    assert np.isfinite(s[:49]).all() and np.isnan(s[49:]).all() and s[48] > s[0]


def money(top, no_bottom, every, market):
    return {"top": {"annual_net": top}, "no_bottom": {"annual_net": no_bottom}, "all_equal": {"annual_net": every}, "cap_weighted_market": {"annual": market}}


def test_money_conditions_need_both_periods():
    good_ = money(0.2, 0.1, 0.05, 0.1)
    assert kh.money_conditions({"2022_2023": good_, "2024_on": good_}) == {"b1_top_beats_market": True, "b2_avoiding_bottom_helps": True}
    bad = money(0.05, 0.01, 0.05, 0.1)
    assert kh.money_conditions({"2022_2023": good_, "2024_on": bad}) == {"b1_top_beats_market": False, "b2_avoiding_bottom_helps": False}


@pytest.mark.parametrize("v20,v252,b1,b2,want", [
    ("WEAK_POSITIVE_EVIDENCE", "WEAK_POSITIVE_EVIDENCE", True, True, "A_AND_B1"),
    ("WEAK_POSITIVE_EVIDENCE", "WEAK_POSITIVE_EVIDENCE", False, True, "A_AND_B2"),
    ("WEAK_POSITIVE_EVIDENCE", "WEAK_POSITIVE_EVIDENCE", False, False, "A_ONLY"),
    ("NO_EVIDENCE", "WEAK_POSITIVE_EVIDENCE", True, True, "NO_EVIDENCE"),
])
def test_the_reading_is_fixed(v20, v252, b1, b2, want):
    assert kh.reading({"SWING_20": {"verdict": v20}, "LONG_252": {"verdict": v252}}, {"b1_top_beats_market": b1, "b2_avoiding_bottom_helps": b2}) == want


def panel(tmp_path, monkeypatch, edge):
    """A known effect: the holder score's two inputs rank stocks by a fixed order and returns follow it by ``edge`` a session.  No real data."""
    rng = np.random.default_rng(11)
    sessions, stocks = 2300, 60
    px = small_prices(stocks=stocks, sessions=sessions)
    order = np.arange(stocks) / (stocks - 1)
    daily = rng.normal(0.0004, 0.02, (sessions, stocks + 1)) + rng.normal(0, 0.008, (sessions, 1))
    daily[:, :stocks] += edge * (order - 0.5)
    path = 100 * np.exp(np.cumsum(daily, axis=0))
    px.data["adj_close"], px.data["close"], px.data["open"] = path, path, path
    rows = list(range(260, sessions - 1, kr.STEP))
    tensor = np.full((len(rows), stocks + 1, 2), np.nan, dtype=np.float32)
    tensor[:, :stocks, 0], tensor[:, :stocks, 1] = order * 60, order * 4 - 2
    (tmp_path / kh.DATA).mkdir(parents=True)
    np.savez_compressed(tmp_path / kh.FEATURES, tensor=tensor)
    fund = rng.normal(size=(len(rows), stocks + 1, len(kf.SIGNALS))).astype(np.float32)
    fund[:, stocks] = np.nan
    (tmp_path / kf.FEATURES).parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(tmp_path / kf.FEATURES, tensor=fund)
    monkeypatch.setattr(kh, "_inputs", lambda base: (px, rows, np.ones((len(rows), stocks + 1), dtype=bool)))


def test_the_whole_run_finds_a_planted_effect_and_refuses_a_second_time(tmp_path, monkeypatch):
    panel(tmp_path, monkeypatch, 0.004)
    out = kh.run_once(tmp_path, log=lambda m: None)
    assert out["reading"] in ("A_AND_B1", "A_AND_B2") and out["conditions"]["b2_avoiding_bottom_helps"]
    for s in kh.HORIZONS:
        assert out["scores"]["HOLDER"][s]["ic"] > 0.02 and set(out["scores"]["HOLDER"][s]["subsets"]) == {"kospi", "kosdaq", "top300"}
    assert set(out["scores"]) == {"HOLDER", "STAKE", "CHANGE", "FUND_ONLY", "FUND_WITH_HOLDER"} and set(out["money_20d"]) == set(kh.PORTFOLIO_PERIODS)
    assert out["money_20d"]["2022_on"]["top"]["mean_holdings"] == 12 and out["money_20d"]["2022_on"]["no_bottom"]["mean_holdings"] == 48
    with pytest.raises(RuntimeError):
        kh.run_once(tmp_path, log=lambda m: None)


def test_the_whole_run_finds_nothing_when_nothing_is_planted(tmp_path, monkeypatch):
    panel(tmp_path, monkeypatch, 0.0)
    assert kh.run_once(tmp_path, log=lambda m: None)["reading"] == "NO_EVIDENCE"
