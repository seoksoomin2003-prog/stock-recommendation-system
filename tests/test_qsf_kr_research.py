"""Korean price test: delisted names stay in, nothing leaks, the key is not written.  No network."""
import gzip
import json

import numpy as np
import pytest

from terminal.qsf import krx_history as kh, research_kr as kr


def row(code, name="회사", section="중견기업부", o=100, h=110, l=90, c=100, chg=0, vol=1000, val=5_000_000_000, cap=1e12):
    return [code, name, section, str(o), str(h), str(l), str(c), str(chg), str(vol), str(val), str(cap), "100"]


def write_day(root, board, day, rows):
    p = kh.path_of(root, board, day)
    p.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(p, "wt", encoding="utf-8") as fh:
        json.dump(rows, fh)


def test_numbers_with_commas_and_blanks():
    assert kr.num("1,234.5") == 1234.5 and kr.num("-") is None and kr.num(None) is None


def test_preferred_stock_and_spacs_are_left_out():
    assert kr.common_stock("005930", "삼성전자", "")
    assert not kr.common_stock("005935", "삼성전자우", "")
    assert not kr.common_stock("03481K", "우B", "")
    assert not kr.common_stock("123450", "IBKS제24호스팩", "")
    assert not kr.common_stock("123450", "어떤회사", "SPAC(소속부없음)")


def test_adjusted_price_follows_the_change_not_the_quote_across_a_split(tmp_path):
    write_day(tmp_path, "KOSPI", "2020-01-02", [row("000010", c=1000, o=1000, h=1000, l=1000)])
    write_day(tmp_path, "KOSPI", "2020-01-03", [row("000010", c=110, o=100, h=110, l=100, chg=10)])     # 1:10 split, then +10%
    d = kr.build_prices(tmp_path, log=lambda m: None)
    j = list(d["symbols"]).index("000010")
    assert d["adj_close"][1, j] == pytest.approx(1100)
    assert d["open"][1, j] == pytest.approx(1000) and d["close"][1, j] == pytest.approx(1100)


def test_a_delisted_name_is_in_the_sample_and_a_watch_listing_is_marked(tmp_path):
    write_day(tmp_path, "KOSDAQ", "2020-01-02", [row("000020", section="관리종목(소속부없음)"), row("000030")])
    write_day(tmp_path, "KOSDAQ", "2020-01-03", [row("000030")])
    d = kr.build_prices(tmp_path, log=lambda m: None)
    s = list(d["symbols"])
    assert "000020" in s and d["watch"][0, s.index("000020")] and not d["watch"][0, s.index("000030")]
    assert not d["kospi"][s.index("000030")]


def test_zero_prices_stay_empty(tmp_path):
    write_day(tmp_path, "KOSPI", "2020-01-02", [row("000010", o=0, h=0, l=0, vol=0)])
    d = kr.build_prices(tmp_path, log=lambda m: None)
    j = list(d["symbols"]).index("000010")
    assert np.isnan(d["open"][0, j]) and d["close"][0, j] == 100


def prices(adj, opens):
    adj, opens = np.array(adj, dtype=np.float32), np.array(opens, dtype=np.float32)
    D = adj.shape[0]
    z = {"dates": np.array([f"2020-01-{i + 1:02d}" for i in range(D)]), "symbols": np.array(["A", "B", "C", kr.MARKET]), "kospi": np.ones(4, bool), "adj_close": adj, "open": opens}
    return kr.KrPrices(z)


def test_a_stock_gone_before_exit_closes_at_its_last_price_and_no_entry_means_no_return():
    n = np.nan
    px = prices([[100, 100, 100, 1], [100, 50, 100, 1], [110, 10, 100, 1], [120, n, 100, 1]],
                [[100, 100, 100, 1], [100, 50, n, 1], [100, 10, 100, 1], [100, n, 100, 1]])
    r = px.forward(0, 3)
    assert r[0] == pytest.approx(0.2) and r[1] == pytest.approx(10 / 50 - 1) and np.isnan(r[2])


def test_forward_past_the_end_is_empty():
    assert np.isnan(prices([[1, 1, 1, 1]] * 2, [[1, 1, 1, 1]] * 2).forward(1, 1)).all()


def test_market_weights_on_the_previous_day_and_ignores_itself():
    d = {x: np.full((2, 3), np.nan, dtype=np.float32) for x in ("open", "high", "low", "close", "adj_close", "volume", "cap")}
    d["adj_close"][:, 0], d["adj_close"][:, 1] = [100, 110], [100, 100]
    d["cap"][0, :2] = [3, 1]
    d["cap"][1, :2] = [1000, 1000]
    kr.add_market(d, 2)
    assert d["adj_close"][1, 2] == pytest.approx(1000 * (1 + 0.1 * 3 / 4))
    assert d["open"][1, 2] == pytest.approx(1000)


def elig_data(n=250):
    d = {x: np.full((n, 2), 1.0, dtype=np.float32) for x in ("close", "volume")}
    d["value"] = np.full((n, 2), 2e9, dtype=np.float32)
    d["watch"] = np.zeros((n, 2), dtype=bool)
    d["symbols"] = np.array(["A", kr.MARKET])
    return d


def test_eligible_requires_liquidity_history_and_no_watch_listing():
    d = elig_data()
    assert kr.eligible(d, 249).tolist() == [True, False]
    low = {**d, "value": np.full((250, 2), 1e8, dtype=np.float32)}
    assert not kr.eligible(low, 249)[0]
    assert not kr.eligible(d, 150)[0]
    w = {**d, "watch": np.ones((250, 2), dtype=bool)}
    assert not kr.eligible(w, 249)[0]
    v = {**d, "volume": np.zeros((250, 2), dtype=np.float32)}
    assert not kr.eligible(v, 249)[0]


def test_eligible_reads_nothing_after_its_day():
    d = elig_data()
    later = {k: v.copy() for k, v in d.items()}
    later["close"][201:] = np.nan
    later["value"][201:] = 0
    assert kr.eligible(d, 200).tolist() == kr.eligible(later, 200).tolist()


class Resp:
    def __init__(self, code, rows=None):
        self.status_code, self._rows = code, rows

    def json(self):
        return {"OutBlock_1": self._rows or []}


def test_download_skips_kept_days_stops_on_refusal_and_never_writes_the_key(tmp_path):
    calls = []

    def get(url, params, headers, timeout):
        calls.append(params["basDd"])
        assert headers["AUTH_KEY"] == "SECRET"
        return Resp(200, [{"ISU_CD": "000010", "ISU_NM": "회사"}])
    res = kh.download(tmp_path, "SECRET", get, "2020-01-02", "2020-01-02", sleep=lambda s: None, log=lambda m: None)
    assert res["status"] == "DONE" and res["stored"] == 2 and len(calls) == 2
    assert kh.download(tmp_path, "SECRET", get, "2020-01-02", "2020-01-02", sleep=lambda s: None, log=lambda m: None)["calls"] == 0
    assert all(b"SECRET" not in gzip.open(p).read() for p in tmp_path.rglob("*.gz"))
    stop = kh.download(tmp_path, "SECRET", lambda *a, **k: Resp(429), "2020-01-03", "2020-01-03", sleep=lambda s: None, log=lambda m: None)
    assert stop["stopped"] == "REFUSED_429"


def test_a_day_without_trading_is_kept_and_not_asked_again(tmp_path):
    res = kh.download(tmp_path, "K", lambda *a, **k: Resp(200, []), "2020-01-01", "2020-01-01", sleep=lambda s: None, log=lambda m: None)
    assert res["empty"] == 2 and kh.path_of(tmp_path, "KOSPI", "2020-01-01").exists()


def test_the_daily_cap_stops_the_run(tmp_path):
    res = kh.download(tmp_path, "K", lambda *a, **k: Resp(200, []), "2020-01-01", "2020-01-31", sleep=lambda s: None, cap=3, log=lambda m: None)
    assert res["stopped"] == "DAILY_CAP" and res["calls"] == 3


def test_the_second_test_is_refused(tmp_path):
    p = tmp_path / kr.REPORT
    p.parent.mkdir(parents=True)
    p.write_text("{}")
    with pytest.raises(RuntimeError):
        kr.run_once(tmp_path)
