"""Korean live-score replay: the price panel, the universe rule, the statement download and the one-run guards.  All offline."""
import gzip
import json
from datetime import date, timedelta

import numpy as np
import pytest

from terminal.qsf import research_kr_live as rl


def days(n, start=date(2024, 1, 2)):
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def snap(code, name, close, rate, vol, shares, o=None, h=None, lo=None):
    o, h, lo = o or close, h or close, lo or close
    return [code, name, "", str(o), str(h), str(lo), str(close), f"{rate:.2f}", str(vol), str(int(vol * close)), str(int(close * shares)), str(shares)]


def write_days(root, by_day):
    for day, boards in by_day.items():
        for board in ("KOSPI", "KOSDAQ"):
            p = root / board / f"{day}.json.gz"
            p.parent.mkdir(parents=True, exist_ok=True)
            with gzip.open(p, "wt", encoding="utf-8") as fh:
                json.dump(boards.get(board, []), fh)


def market(root, n=60, split_at=40):
    """A: steady KOSPI stock that splits 1:5 on day ``split_at``; B: KOSDAQ stock; C: thin; D: stops trading; a SPAC to be ignored."""
    ds = days(n)
    by = {}
    a, b = 10000.0, 500.0
    for k, d in enumerate(ds):
        ra, rb = (1.0 if k else 0.0), (-0.5 if k else 0.0)
        a *= 1 + ra / 100
        b *= 1 + rb / 100
        split = k >= split_at
        raw_a = round(a / 5) if split else round(a)
        rows_k = [snap("000010", "가", raw_a, ra, 1000 * (5 if split else 1), 1_000_000 * (5 if split else 1)), snap("000030", "다", 100, 0.0, 10, 1000)]
        rows_q = [snap("000020", "나", round(b), rb, 2000, 500_000), snap("000040", "라", 200, 0.0, 0 if k >= n - 3 else 50, 1000), snap("000050", "한국스팩", 2000, 0.0, 5000, 1000)]
        by[d] = {"KOSPI": rows_k, "KOSDAQ": rows_q}
    write_days(root, by)
    return ds


@pytest.fixture
def panel(tmp_path):
    ds = market(tmp_path / rl.KRX)
    return rl.Panel(rl.build_panel(tmp_path / rl.KRX, log=lambda m: None)), ds


def test_panel_keeps_raw_prices_and_chains_a_split(panel):
    px, ds = panel
    assert px.symbols[:4] == ["000010", "000020", "000030", "000040"] and "000050" not in px.col            # the SPAC is not a common operating stock
    j = px.col["000010"]
    level, raw = px.data["close"][:, j].astype(float), px.data["raw"][:, j].astype(float)
    assert raw[39] / raw[40] == pytest.approx(5.0, rel=0.02) and level[40] / level[39] == pytest.approx(1.01, rel=1e-4)     # raw falls by five, the level does not
    bars = px.bars(j, len(ds) - 1)
    assert bars[-1]["close"] == pytest.approx(raw[-1]) and bars[-1]["date"] == ds[-1] and len(bars) == len(ds)
    assert bars[10]["close"] == pytest.approx(raw[10] / 5, rel=0.02) and bars[10]["volume"] == pytest.approx(5000, rel=0.02)   # old days on today's basis
    assert bars[50]["volume"] == pytest.approx(5000, rel=1e-3) and bars[-1]["adj_close"] == bars[-1]["close"]
    early = px.bars(j, 20)
    assert early[-1]["close"] == pytest.approx(raw[20]) and early[-1]["volume"] == pytest.approx(1000)        # before the split nothing is rescaled


def test_board_and_market_indexes_follow_their_members(panel):
    px, ds = panel
    kospi, kosdaq, allm = (px.data["close"][:, px.col[s]].astype(float) for s in ("IDX_KOSPI", "IDX_KOSDAQ", rl.MARKET))
    assert kospi[-1] > kospi[0] and kosdaq[-1] < kosdaq[0] and kosdaq[-1] < allm[-1] < kospi[-1]
    assert px.market_return(10, 5) == pytest.approx(allm[15] / allm[10] - 1) and np.isnan(px.market_return(len(ds) - 2, 5))
    fwd = px.forward(10, 5)
    assert np.isnan(fwd[px.col["IDX_KOSPI"]]) and fwd[px.col["000010"]] == pytest.approx(1.01 ** 4 - 1, rel=0.02)       # in at the next open, which here is that day's close


def test_a_stock_gone_before_the_exit_closes_at_its_last_trade(tmp_path):
    ds = days(30)
    by = {d: {"KOSPI": [snap("000010", "가", 1000 + 10 * k, 1.0, 100, 1000)] + ([snap("000020", "나", 500 - 5 * k, -1.0, 100, 1000)] if k < 15 else []), "KOSDAQ": []} for k, d in enumerate(ds)}
    write_days(tmp_path, by)
    px = rl.Panel(rl.build_panel(tmp_path, log=lambda m: None))
    j = px.col["000020"]
    lvl = px.data["close"][:, j].astype(float)
    assert px.forward(10, 10)[j] == pytest.approx(lvl[14] / px.data["open"][11, j] - 1)             # held to its last trade, not dropped
    assert np.isnan(px.forward(20, 5)[j])                                                          # already gone on the entry day


def test_a_holiday_the_exchange_answers_with_nothing_is_not_a_session(tmp_path):
    ds = days(12)
    by = {d: {"KOSPI": [] if k == 5 else [snap("000010", "가", 1000 + k, 0.1, 100, 1000)], "KOSDAQ": []} for k, d in enumerate(ds)}
    write_days(tmp_path, by)
    px = rl.Panel(rl.build_panel(tmp_path, log=lambda m: None))
    assert len(px.dates) == 11 and ds[5] not in px.dates and np.isfinite(px.data["close"][:, px.col["000010"]]).all()


def test_universe_ranks_by_traded_value_and_drops_halted_and_short_stocks(panel):
    px, ds = panel
    got = [px.symbols[j] for j in rl.universe(px, len(ds) - 1)]
    assert got == ["000010", "000020", "000030"]                              # 000040 traded nothing for three sessions
    assert [px.symbols[j] for j in rl.universe(px, len(ds) - 1, size=1)] == ["000010"]
    assert len(rl.universe(px, 10)) == 0                                      # fewer than twenty valid sessions so far
    assert [px.symbols[j] for j in rl.universe(px, 30)] == ["000010", "000020", "000040", "000030"]


def test_needs_are_the_four_years_before_each_day(panel):
    px, ds = panel
    got = rl.needs(px, [30, len(ds) - 1])
    assert got["000010"] == [2020, 2021, 2022, 2023] and set(got) == {"000010", "000020", "000030", "000040"}


def test_statement_download_asks_once_with_a_hint_and_falls_back_without(tmp_path):
    asked = []

    def fetch(corp, year, fs):
        asked.append((corp, year, fs))
        if corp == "C1":
            return {"status": "000", "list": [{"rcept_no": "20230315000001", "sj_div": "BS", "account_id": "ifrs-full_Assets", "account_nm": "자산총계", "thstrm_amount": "100"}]}
        if corp == "C2" and fs == "OFS":
            return {"status": "000", "list": [{"rcept_no": "20230320000002", "sj_div": "BS", "account_id": "ifrs-full_Assets", "account_nm": "자산총계", "thstrm_amount": "7"}]}
        return {"status": "013"}
    res = rl.download_statements(tmp_path, {"000010": [2022], "000020": [2022], "000030": [2022], "000099": [2022]}, {"000010": "C1", "000020": "C2", "000030": "C3"},
                                 {("000010", 2022): "CFS"}, fetch, log=lambda m: None)
    assert asked == [("C1", 2022, "CFS"), ("C2", 2022, "CFS"), ("C2", 2022, "OFS"), ("C3", 2022, "CFS"), ("C3", 2022, "OFS")]
    assert res["status"] == "OK" and res["calls"] == 5 and res["stored"] == 3 and res["empty"] == 1
    with gzip.open(rl.statement_path(tmp_path, "C2", 2022), "rt", encoding="utf-8") as fh:
        rec = json.load(fh)
    assert rec["fs_div"] == "OFS" and rec["rows"][0][rl.ROW_FIELDS.index("thstrm_amount")] == "7"
    asked.clear()
    assert rl.download_statements(tmp_path, {"000010": [2022], "000030": [2022]}, {"000010": "C1", "000030": "C3"}, {}, fetch, log=lambda m: None)["calls"] == 0 and not asked


def test_statement_download_stops_at_the_cap_and_at_darts_limit_and_keeps_failures_for_later(tmp_path):
    def limit(corp, year, fs):
        return {"status": "020"}
    assert rl.download_statements(tmp_path / "a", {"000010": [2022]}, {"000010": "C1"}, {}, limit, log=lambda m: None)["stopped"] == "DART_020"
    ok = lambda corp, year, fs: {"status": "000", "list": [{"rcept_no": "20230315000001", "sj_div": "BS", "account_id": "x", "account_nm": "y", "thstrm_amount": "1"}]}      # noqa: E731
    res = rl.download_statements(tmp_path / "b", {"000010": [2021, 2022, 2023]}, {"000010": "C1"}, {}, ok, cap=2, log=lambda m: None)
    assert res["stopped"] == "DAILY_CAP" and res["stored"] == 2 and res["left"] == 1

    def broken(corp, year, fs):
        raise ConnectionError("down")
    import time
    real, time.sleep = time.sleep, lambda s: None
    try:
        res = rl.download_statements(tmp_path / "c", {"000010": [2022]}, {"000010": "C1"}, {}, broken, log=lambda m: None)
    finally:
        time.sleep = real
    assert res["stored"] == 0 and not rl.statement_path(tmp_path / "c", "C1", 2022).exists()


def test_basis_hint_prefers_consolidated(tmp_path):
    from terminal.qsf import dart_history as dh
    f = {name: n for n, name in enumerate(dh.FIELDS)}

    def row(stock, fs):
        r = [None] * len(dh.FIELDS)
        r[f["stock_code"]], r[f["fs_div"]] = stock, fs
        return r
    p = tmp_path / "2022_FY" / "000.json.gz"
    p.parent.mkdir(parents=True)
    with gzip.open(p, "wt", encoding="utf-8") as fh:
        json.dump([row("000010", "OFS"), row("000010", "CFS"), row("000010", "OFS"), row("000020", "OFS")], fh)
    assert rl.basis_hint(tmp_path) == {("000010", 2022): "CFS", ("000020", 2022): "OFS"}


def test_eligibility_follows_the_live_master_rules():
    ok = rl.eligible_stock
    assert ok("005930", "삼성전자", "") and ok("0126Z0", "삼성에피스홀딩스", "")                    # codes issued since 2024 carry letters
    assert not ok("00593K", "삼성전자우", "") and not ok("0099X0", "IBKS제25호스팩", "") and not ok("0030R0", "대신밸류리츠", "")
    assert not ok("900140", "엘브이엠씨홀딩스", "") and not ok("123450", "어떤기업인수목적", "") and not ok(None, "x", "")


def test_fund_vehicles_leave_the_universe_once_their_class_is_known(panel):
    px, ds = panel
    st = rl.Statements(px and "none", {}, {"000010": "TRUST_AND_COLLECTIVE_INVESTMENT"})
    got = [px.symbols[j] for j in rl.universe(px, len(ds) - 1, exclude=st.not_operating(px))]
    assert got == ["000020", "000030"]


def test_industry_class_from_the_dart_code():
    assert rl.ksic_class("64110") == "BANK" and rl.ksic_class("661") == "SECURITIES_AND_FINANCIAL_SERVICES" and rl.ksic_class("64992") == "HOLDING_OR_OTHER_FINANCIAL"
    assert rl.ksic_class("26110") == "NON_FINANCIAL" and rl.ksic_class(None) == "NON_FINANCIAL"


def stored(root, corp, year, rcept, revenue, income, assets, equity):
    def r(sj, acc, name, val):
        return [rcept, sj, acc, name, None, str(val), None, "KRW"]
    rows = [r("IS", "ifrs-full_Revenue", "매출액", revenue), r("IS", "ifrs-full_ProfitLossAttributableToOwnersOfParent", "지배기업 소유주지분 순이익", income),
            r("BS", "ifrs-full_Assets", "자산총계", assets), r("BS", "ifrs-full_EquityAttributableToOwnersOfParent", "지배기업 소유주지분", equity)]
    p = rl.statement_path(root, corp, year)
    p.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(p, "wt", encoding="utf-8") as fh:
        json.dump({"corp": corp, "year": year, "fs_div": "CFS", "rows": rows}, fh)


def test_fundamentals_use_the_live_mapping_and_only_filed_reports(tmp_path):
    for year, rev in ((2020, 800), (2021, 900), (2022, 1000)):
        stored(tmp_path, "C1", year, f"{year + 1}0320000001", rev * 1e8, rev * 1e7, rev * 2e8, rev * 1e8)
    st = rl.Statements(tmp_path, {"000010": "C1"}, {})
    late = st.fund("000010", "2023-06-01", 10000.0, 1_000_000.0)
    assert late["status"] in ("REAL", "STALE") and late["pe"] == pytest.approx(10000.0 * 1_000_000 / (1000 * 1e7))
    early = st.fund("000010", "2023-03-01", 10000.0, 1_000_000.0)             # the 2022 report is not filed yet: the 2021 figures stand
    assert early["pe"] == pytest.approx(10000.0 * 1_000_000 / (900 * 1e7))
    assert st.fund("000099", "2023-06-01", 100.0, 10.0)["status"] == "UNAVAILABLE"


def test_statements_in_the_older_dart_spelling_are_read_the_same(tmp_path):
    for year, rev in ((2016, 800), (2017, 900)):
        stored(tmp_path, "C1", year, f"{year + 1}0320000001", rev * 1e8, rev * 1e7, rev * 2e8, rev * 1e8)
        p = rl.statement_path(tmp_path, "C1", year)
        with gzip.open(p, "rt", encoding="utf-8") as fh:
            rec = json.load(fh)
        k = rl.ROW_FIELDS.index("account_id")
        for r in rec["rows"]:
            r[k] = r[k].replace("ifrs-full_", "ifrs_")
        with gzip.open(p, "wt", encoding="utf-8") as fh:
            json.dump(rec, fh)
    got = rl.Statements(tmp_path, {"000010": "C1"}, {}).fund("000010", "2018-06-01", 10000.0, 1_000_000.0)
    assert got["status"] in ("REAL", "STALE") and got["pe"] == pytest.approx(10000.0 * 1_000_000 / (900 * 1e7)) and got["rev_growth"] == pytest.approx(0.125)


def test_a_day_is_scored_by_the_live_engine_without_reading_a_return(tmp_path):
    ds = days(260)
    rng = np.random.default_rng(5)
    by, price = {}, {c: 5000.0 + 100 * n for n, c in enumerate(f"{k:05d}0" for k in range(1, 41))}
    for k, d in enumerate(ds):
        rows = []
        for c in price:
            r = float(rng.normal(0.05, 1.5)) if k else 0.0
            price[c] *= 1 + r / 100
            rows.append(snap(c, "종목" + c, round(price[c]), r, 2_000_000, 10_000_000, h=round(price[c] * 1.01), lo=round(price[c] * 0.99)))
        by[d] = {"KOSPI": rows[:20], "KOSDAQ": rows[20:]}
    write_days(tmp_path / rl.KRX, by)
    px = rl.Panel(rl.build_panel(tmp_path / rl.KRX, log=lambda m: None))
    recs = rl.score_day(px, len(ds) - 1, rl.Statements(tmp_path / "none", {}, {}))
    assert len(recs) == 40 and all(r["i"] == len(ds) - 1 and r["fund_status"] == "UNAVAILABLE" for r in recs)
    assert all(r.get("SWING") is not None and 0 <= r["SWING"] <= 100 and r["SWING|TECHNICAL"] is not None for r in recs)       # swing needs no fundamentals
    assert all("LONG_TERM" not in r and "SHORT_FUNDAMENTAL" in r["LONG_TERM|WHY"] for r in recs)                             # the long score does, as live
    assert len({round(r["SWING"], 3) for r in recs}) > 20


def test_rank_correlation_and_readings():
    assert rl.rank_corr(list(range(30)), [2 * x + 1 for x in range(30)]) == pytest.approx(1.0) and rl.rank_corr([1, 2], [1, 2]) is None
    assert rl.reading(True, True) == "RANK_AND_MONEY" and rl.reading(True, False) == "RANK_ONLY" and rl.reading(False, True) == "NO_EVIDENCE"


def test_the_return_test_needs_a_passed_fidelity_check_and_runs_once(tmp_path):
    with pytest.raises(RuntimeError, match="정확도"):
        rl.run_once(tmp_path)
    (tmp_path / rl.FIDELITY).parent.mkdir(parents=True)
    (tmp_path / rl.FIDELITY).write_text(json.dumps({"passed": False}))
    with pytest.raises(RuntimeError, match="정확도"):
        rl.run_once(tmp_path)
    (tmp_path / rl.REPORT).write_text("{}")
    with pytest.raises(RuntimeError, match="한 번만"):
        rl.run_once(tmp_path)
