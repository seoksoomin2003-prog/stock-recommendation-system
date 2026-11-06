"""Insider research: extraction rules, point-in-time windows, gaps kept apart from zeros, the rare-signal verdict and the one-shot test."""
import io
import json
import zipfile

import numpy as np
import pytest

from terminal.qsf import research_insider as ri, validate


def _tsv(rows):
    head = list(rows[0])
    return "\t".join(head) + "\n" + "".join("\t".join(str(r.get(h, "")) for h in head) + "\n" for r in rows)


def _zip(subs, owners, trans):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("SUBMISSION.tsv", _tsv(subs))
        z.writestr("REPORTINGOWNER.tsv", _tsv(owners))
        z.writestr("NONDERIV_TRANS.tsv", _tsv(trans))
    buf.seek(0)
    return zipfile.ZipFile(buf)


def _sub(acc, doc="4", issuer="0000000001", filed="15-MAR-2024"):
    return {"ACCESSION_NUMBER": acc, "FILING_DATE": filed, "DOCUMENT_TYPE": doc, "ISSUERCIK": issuer}


def _own(acc, cik="0000000009", role="Officer"):
    return {"ACCESSION_NUMBER": acc, "RPTOWNERCIK": cik, "RPTOWNER_RELATIONSHIP": role}


def _tr(acc, sk="1", code="P", ad="A", day="13-MAR-2024", shares="100", price="10"):
    return {"ACCESSION_NUMBER": acc, "NONDERIV_TRANS_SK": sk, "TRANS_CODE": code, "TRANS_ACQUIRED_DISP_CD": ad, "TRANS_DATE": day, "TRANS_SHARES": shares, "TRANS_PRICEPERSHARE": price}


def test_parse_date():
    assert ri.parse_date("31-JAN-2024") == "2024-01-31"
    assert ri.parse_date("") is None and ri.parse_date("2024-01-31") is None and ri.parse_date("31-XXX-2024") is None


def test_extract_keeps_only_open_market_trades_by_officers_and_directors():
    z = _zip([_sub("a"), _sub("amend", doc="4/A"), _sub("other", issuer="0000000002"), _sub("owner10"), _sub("gift")],
             [_own("a"), _own("amend"), _own("other"), _own("owner10", role="TenPercentOwner"), _own("gift", role="Director,TenPercentOwner")],
             [_tr("a"), _tr("a", sk="2", code="S", ad="D", shares="50", price="20"), _tr("a", sk="3", code="P", ad="D"), _tr("amend"), _tr("other"), _tr("owner10"), _tr("gift", code="G"), _tr("a", sk="4", code="M")])
    out = ri.extract(z, {1})
    assert out["last_filed"] == "2024-03-15"
    assert out["trades"][1] == [["2024-03-15", "2024-03-13", 9, "P", 1000.0], ["2024-03-15", "2024-03-13", 9, "S", 1000.0]]


def test_extract_counts_a_joint_filing_once_and_keeps_person_without_price():
    z = _zip([_sub("a")], [_own("a", cik="0000000030"), _own("a", cik="0000000020", role="Director"), _own("a", cik="0000000010", role="TenPercentOwner")],
             [_tr("a", price=""), _tr("a")])                # the second has the same key, a repeated row
    t = ri.extract(z, {1})["trades"][1]
    assert len(t) == 1 and t[0][2] == 20 and t[0][4] is None


def test_routine_needs_the_same_month_in_all_three_prior_years():
    rows = [["2021-03-20", "2021-03-10", 7, "S", 1.0], ["2022-03-20", "2022-03-10", 7, "S", 1.0], ["2023-03-20", "2023-03-10", 7, "S", 1.0], ["2024-03-20", "2024-03-10", 7, "P", 1.0],
            ["2024-04-20", "2024-04-10", 7, "P", 1.0], ["2024-03-20", "2024-03-10", 8, "P", 1.0]]
    out = {(r[2], r[1]): r[5] for r in ri.mark_routine(rows)}
    assert out[(7, "2024-03-10")] is True
    assert out[(7, "2024-04-10")] is False
    assert out[(7, "2021-03-10")] is False
    assert out[(8, "2024-03-10")] is False


def _rows():
    return ri.mark_routine([["2024-01-02", "2024-01-01", 1, "P", 100.0], ["2024-03-01", "2024-02-28", 2, "P", 300.0], ["2024-03-01", "2024-02-28", 3, "P", None],
                            ["2024-03-15", "2024-03-14", 4, "S", 200.0], ["2024-03-20", "2024-03-18", 5, "P", 50.0]])


def test_factors_read_only_filings_up_to_the_day():
    before = ri.factors_at(_rows(), "2024-03-19", 1000.0)
    after = ri.factors_at(_rows(), "2024-03-20", 1000.0)
    assert before["insider_buyers"] == 3 and after["insider_buyers"] == 4
    assert before["insider_buy_value"] == pytest.approx(0.4)


def test_window_edges_are_calendar_days_including_the_day():
    r = ri.mark_routine([["2024-01-02", "2024-01-01", 1, "P", 100.0]])
    assert ri.factors_at(r, "2024-04-01", 1.0)["insider_buyers"] == 1        # day 91 counting the day itself
    assert ri.factors_at(r, "2024-04-02", 1.0)["insider_buyers"] == 0


def test_cluster_and_net():
    f = ri.factors_at(_rows(), "2024-03-19", 1000.0)
    assert f["insider_cluster"] == 1
    assert f["insider_net"] == pytest.approx((400 - 200) / 600)
    assert ri.factors_at(_rows(), "2024-02-15", 1000.0)["insider_cluster"] == 0


def test_no_trades_is_zero_but_missing_adv_stays_empty():
    f = ri.factors_at([], "2024-03-19", 1000.0)
    assert f["insider_buyers"] == 0 and f["insider_net"] == 0
    assert np.isnan(ri.factors_at([], "2024-03-19", None)["insider_buy_value"])


def _panel(rows=340, cols=3):
    from datetime import date, timedelta
    dates = [(date(2010, 1, 1) + timedelta(days=k)).isoformat() for k in range(rows)]
    px = validate.Prices.__new__(validate.Prices)
    px.dates = dates
    px.symbols = ["AAA", "BBB", "SPY"][:cols]
    px.col = {s: j for j, s in enumerate(px.symbols)}
    n = len(dates)
    px.data = {k: np.full((n, cols), 50.0) for k in ("open", "high", "low", "close", "adj_close")}
    px.data["volume"] = np.full((n, cols), 1e6)
    return px


def test_a_gap_is_kept_apart_from_no_trades():
    px = _panel()
    day = px.dates[-1]
    old = ri.mark_routine([["2010-01-01", "2010-01-01", 7, "S", 5.0]])
    b = ri.build_features(px, lambda d: ["AAA", "BBB"], {"AAA": 1, "BBB": 2}, {1: old}, source_end=day)
    k = ri.FACTORS.index("insider_buyers")
    assert b["tensor"][-1, 0, k] == 0                     # linked, no trades
    assert np.isnan(b["tensor"][-1, 1, k])                # no filing of this kind anywhere
    gone = ri.build_features(px, lambda d: ["AAA"], {"AAA": 1}, {1: old}, source_end=px.dates[0])
    assert np.isnan(gone["tensor"][-1, 0, k])             # past the data


def test_earlier_company_numbers_join_the_current_one():
    merged = ri.merge_aliases({5: [["2015-01-01", "2015-01-01", 1, "P", 1.0]], 9: [["2020-01-01", "2020-01-01", 1, "P", 2.0]], 3: [["2020-01-01", "2020-01-01", 2, "S", 3.0]]}, {5: 9})
    assert sorted(merged) == [3, 9] and len(merged[9]) == 2


def test_alias_table_never_takes_a_current_number(tmp_path):
    target = tmp_path / ri.ALIASES
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps({"AAA": [2]}), encoding="utf-8")
    with pytest.raises(ValueError):
        ri.alias_map(tmp_path, {"AAA": 1, "BBB": 2})
    target.write_text(json.dumps({"AAA": [5]}), encoding="utf-8")
    assert ri.alias_map(tmp_path, {"AAA": 1, "BBB": 2}) == {5: 1}


def test_per_date_compares_signal_names_with_the_rest():
    s = np.zeros(40)
    s[:5] = 1.0
    r = np.zeros(40)
    r[:5] = 0.04
    d = ri.per_date(s, r, 0.002)
    assert d["signal_n"] == 5
    assert d["spread_net"] == pytest.approx(0.04 - 0.002)
    assert ri.per_date(np.zeros(40), r, 0.002) is None
    assert ri.per_date(s[:10], r[:10], 0.002) is None


def _summary(**kw):
    good = {"spread_net": 0.005, "t_spread": 2.5, "signal_excess": 0.004, "dates": 100, "mean_signal_n": 20, "early": {"spread_net": 0.004, "ic": 0.001}, "late": {"spread_net": 0.006, "ic": 0.002}}
    return {**good, **kw}


def test_verdict_needs_all_five():
    assert ri.verdict(_summary())["verdict"] == "WEAK_POSITIVE_EVIDENCE"
    for bad in ({"spread_net": -0.001}, {"t_spread": 2.0}, {"t_spread": None}, {"early": {"spread_net": -0.1, "ic": 0.1}}, {"late": {"spread_net": 0.1, "ic": -0.1}},
                {"signal_excess": -0.001}, {"dates": 59}, {"mean_signal_n": 4}):
        assert ri.verdict(_summary(**bad))["verdict"] == "NO_EVIDENCE", bad


def test_second_test_is_refused(tmp_path):
    target = tmp_path / ri.TEST_REPORT
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps({}), encoding="utf-8")
    with pytest.raises(RuntimeError):
        ri.test_once(tmp_path)
