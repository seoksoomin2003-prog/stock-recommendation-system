"""P6-22: KR security master, OHLCV validation, KRX/DART adapters, account mapping, universe (offline)."""
import io
import json
import zipfile

import numpy as np
import pandas as pd
import pytest

from tests import kr_fakes as F
from markets.kr import account_mapping, dart, security_master, universe
from markets.kr import calendar as krcal
from markets.kr.market_data import (KRXOpenAPIProvider, YahooKRProvider, parse_krx_daily, select_provider,
                                    series_checks, validate_rows)


# ---------------------------------------------------------------- security master
def _master(extra=None):
    f = F.fake_kind(5, 4, extra)
    return security_master.build_master({m: f(m) for m in ("KOSPI", "KOSDAQ")}, verified_at="2026-11-04T00:00:00Z")


def test_kind_parse_preserves_leading_zero_and_alnum_codes():
    extra = {"KOSDAQ": [["알파뉴메릭", "코스닥", "0126Z0", "반도체 제조업", "", "2025-01-02", "12월", "", "", "경기도"],
                        ["제로", "코스닥", "000250", "의약품 제조업", "", "2001-01-02", "12월", "", "", "경기도"]]}
    m = _master(extra).set_index("canonical_ticker")
    assert "000250" in m.index and m.loc["000250", "security_key"] == "KR:KOSDAQ:000250"
    assert m.loc["0126Z0", "yahoo_symbol"] == "0126Z0.KQ" and bool(m.loc["0126Z0", "eligible"])


def test_kind_classification_exclusions_and_financial_classes():
    row = lambda name, ind, region="서울특별시", code="300001": [name, "유가", code, ind, "", "2020-01-01", "12월", "", "", region]
    extra = {"KOSPI": [row("가나스팩1호", "금융 지원 서비스업", code="300001"),
                       row("다라리츠", "부동산 임대 및 공급업", code="300002"),
                       row("마바펀드", "신탁업 및 집합투자업", code="300003"),
                       row("외국기업", "반도체 제조업", region="미국", code="300004"),
                       row("가나은행지주", "기타 금융업", code="300005"),
                       row("가나은행", "은행 및 저축기관", code="300006"),
                       row("가나보험", "보험업", code="300007")]}
    m = _master(extra).set_index("canonical_ticker")
    assert m.loc["300001", "exclusion_reason"] == "SPAC_EXCLUDED"
    assert m.loc["300002", "exclusion_reason"] == "REIT_EXCLUDED_SEPARATE_TREATMENT"
    assert m.loc["300003", "exclusion_reason"] == "COLLECTIVE_INVESTMENT_VEHICLE_EXCLUDED"
    assert m.loc["300004", "exclusion_reason"] == "FOREIGN_ISSUER_EXCLUDED_INITIAL_MODEL"
    assert m.loc["300005", "industry_class"] == "HOLDING_OR_OTHER_FINANCIAL" and bool(m.loc["300005", "eligible"])
    assert m.loc["300006", "industry_class"] == "BANK" and m.loc["300007", "industry_class"] == "INSURANCE"


def test_market_label_mismatch_and_duplicates_are_flagged():
    dup = [["중복", "유가", "100000", "반도체 제조업", "", "2020-01-01", "12월", "", "", "서울특별시"]]
    wrong = [["잘못", "코스닥", "399999", "반도체 제조업", "", "2020-01-01", "12월", "", "", "서울특별시"]]
    m = _master({"KOSPI": dup + wrong})
    assert (m["exclusion_reason"] == "DUPLICATE_SECURITY_KEY").sum() == 1
    # a KOSDAQ-labelled row inside the KOSPI download keeps its own (KOSDAQ) identity, flagged
    assert m.set_index("canonical_ticker").loc["399999", "exclusion_reason"] == "MARKET_LABEL_MISMATCH"


def test_kind_layout_change_raises():
    with pytest.raises(ValueError):
        security_master.parse_kind("<table><tr><th>a</th></tr><tr><td>1</td></tr></table>".encode("euc-kr"))


def test_master_snapshot_and_cache(tmp_path):
    f = F.fake_kind(5, 4)
    a = security_master.load_master(tmp_path, fetch=f, now=F.NOW)
    assert a["meta"]["status"] == "REAL" and len(a["meta"]["source_sha256"]) == 2
    b = security_master.load_master(tmp_path, fetch=lambda m: (_ for _ in ()).throw(AssertionError("refetch")),
                                    now=F.NOW + pd.Timedelta(hours=2))
    assert b["meta"]["cache_hit"] and b["master"]["canonical_ticker"].str.len().eq(6).all()


def test_master_fetch_failure_is_not_fabricated(tmp_path):
    def boom(m):
        raise RuntimeError("KIND download failed")
    with pytest.raises(RuntimeError):
        security_master.load_master(tmp_path, fetch=boom, now=F.NOW)


# ---------------------------------------------------------------- OHLCV validation
def _rows(**over):
    base = {"date": pd.Timestamp("2026-10-30"), "market": "KOSPI", "ticker": "005930", "open": 100.0, "high": 110.0,
            "low": 90.0, "close": 105.0, "adj_close": 105.0, "volume": 1000.0, "traded_value": 105000.0,
            "traded_value_basis": "PROXY_CLOSE_X_VOLUME", "provider": "test", "retrieved_at": "", "observation_ts": "",
            "adjustment": ""}
    base.update(over)
    return pd.DataFrame([base])


@pytest.mark.parametrize("over,flag", [({"close": 0.0}, "NON_POSITIVE_PRICE"), ({"high": 80.0}, "HIGH_BELOW_LOW"),
                                       ({"open": 200.0}, "OPEN_OUTSIDE_RANGE"), ({"volume": -1.0}, "NEGATIVE_VOLUME"),
                                       ({"close": np.nan}, "MISSING_PRICE"), ({"volume": np.nan}, "MISSING_VOLUME")])
def test_invalid_rows_are_flagged_and_nulled_never_zeroed(over, flag):
    v = validate_rows(_rows(**over))
    assert v.loc[0, "quality_status"] == "INVALID" and flag in v.loc[0, "quality_flags"]
    assert pd.isna(v.loc[0, "close"])            # missing stays missing, never 0


def test_valid_row_and_duplicate_dates():
    v = validate_rows(pd.concat([_rows(), _rows()], ignore_index=True))
    assert "DUPLICATE_DATE" in " ".join(v["quality_flags"].astype(str))
    assert validate_rows(_rows()).loc[0, "quality_status"] == "REAL"


def test_series_checks_stale_halt_corporate_action():
    sess = pd.bdate_range("2026-09-01", "2026-10-30")
    good = validate_rows(pd.concat([_rows(date=d) for d in sess], ignore_index=True))
    assert series_checks(good, sess, sess[-1])["status"] == "REAL"
    stale = good[good["date"] < sess[-3]]
    assert series_checks(stale, sess, sess[-1])["status"] == "STALE"
    halted = good.copy()
    halted.loc[halted.index[-3:], "volume"] = 0.0
    assert series_checks(halted, sess, sess[-1])["status"] == "HALTED"
    ca = good.copy()
    ca.loc[ca.index[:20], "adj_close"] = 50.0
    assert "CORPORATE_ACTION_SUSPECTED" in series_checks(ca, sess, sess[-1])["flags"]


def test_yahoo_provider_traded_value_is_labelled_proxy_and_missing_symbols_absent():
    dl = F.FakeDownload(drop={"100001.KS"})
    sec = pd.DataFrame({"canonical_ticker": ["100000", "100001"], "market": ["KOSPI", "KOSPI"],
                        "yahoo_symbol": ["100000.KS", "100001.KS"]})
    b = YahooKRProvider(download=dl, sleep=lambda s: None).fetch(sec, "2026-10-01", "2026-10-31")
    assert set(b["ticker"]) == {"100000"}
    assert (b["traded_value_basis"] == "PROXY_CLOSE_X_VOLUME").all()
    assert np.allclose(b["traded_value"], b["close"] * b["volume"])


def test_yahoo_provider_chunk_failure_recorded_not_fabricated():
    def fail(*a):
        raise ConnectionError("x")
    p = YahooKRProvider(download=fail, sleep=lambda s: None)
    sec = pd.DataFrame({"canonical_ticker": ["100000"], "market": ["KOSPI"], "yahoo_symbol": ["100000.KS"]})
    assert p.fetch(sec, "2026-10-01", "2026-10-31").empty and p.events[0]["kind"] == "chunk_failed"


# ---------------------------------------------------------------- KRX Open API adapter
KRX_PAYLOAD = {"OutBlock_1": [{"BAS_DD": "20261030", "ISU_CD": "005930", "ISU_NM": "삼성전자", "TDD_OPNPRC": "60,000",
                               "TDD_HGPRC": "61,000", "TDD_LWPRC": "59,000", "TDD_CLSPRC": "60,500",
                               "ACC_TRDVOL": "10,000,000", "ACC_TRDVAL": "605,000,000,000", "MKTCAP": "1",
                               "LIST_SHRS": "1"}]}


def test_krx_parse_uses_official_traded_value():
    df = parse_krx_daily(KRX_PAYLOAD, "KOSPI", "now")
    assert df.loc[0, "traded_value"] == 605e9 and df.loc[0, "traded_value_basis"] == "KRX_ACC_TRDVAL"
    assert df.loc[0, "ticker"] == "005930" and pd.isna(df.loc[0, "adj_close"])


def test_krx_layout_change_raises():
    with pytest.raises(ValueError):
        parse_krx_daily({"output": []}, "KOSPI", "now")
    with pytest.raises(ValueError):
        parse_krx_daily({"OutBlock_1": [{"BAS_DD": "1"}]}, "KOSPI", "now")


def test_krx_key_never_in_error_and_header_only():
    class R:
        status_code = 401

    class H:
        def get(self, url, params, headers, timeout):
            self.seen = (url, params, headers)
            return R()
    h = H()
    p = KRXOpenAPIProvider(api_key="SECRET-KEY-123", http=h, sleep=lambda s: None)
    with pytest.raises(RuntimeError) as e:
        p.daily("KOSPI", "20261030")
    assert "SECRET" not in str(e.value) and "SECRET" not in h.seen[0] and "SECRET" not in json.dumps(h.seen[1])
    assert h.seen[2]["AUTH_KEY"] == "SECRET-KEY-123"
    assert KRXOpenAPIProvider(api_key="").configured is False


def test_select_provider_by_key_presence():
    assert select_provider({})["provider"] == "yfinance"
    assert select_provider({"KRX_API_KEY": "x"})["provider"] == "krx_openapi"


# ---------------------------------------------------------------- OpenDART
def test_dart_missing_key_raises_unavailable():
    with pytest.raises(dart.DartUnavailable) as e:
        dart.OpenDartClient(api_key="").statements("00126380", 2025, "11011", "CFS")
    assert str(e.value) == "OPENDART_API_KEY_MISSING"


def test_dart_status_codes_and_key_not_leaked():
    class R:
        status_code = 200

        def __init__(self, p):
            self.p = p

        def json(self):
            return self.p

    class H:
        def __init__(self, p):
            self.p = p

        def get(self, url, params, timeout):
            return R(self.p)
    c = lambda p: dart.OpenDartClient(api_key="SECRET", http=H(p), sleep=lambda s: None)
    assert c({"status": "013"}).statements("1", 2025, "11011", "CFS")["status"] == "UNAVAILABLE"
    with pytest.raises(dart.DartUnavailable) as e:
        c({"status": "020"}).statements("1", 2025, "11011", "CFS")
    assert "LIMIT" in str(e.value) and "SECRET" not in str(e.value)
    with pytest.raises(dart.DartUnavailable) as e:
        c({"status": "010"}).statements("1", 2025, "11011", "CFS")
    assert "SECRET" not in str(e.value)


def test_parse_corp_codes_keeps_listed_only():
    xml = ("<result><list><corp_code>00126380</corp_code><corp_name>삼성전자</corp_name><stock_code>005930"
           "</stock_code><modify_date>20250101</modify_date></list><list><corp_code>1</corp_code><corp_name>비상장"
           "</corp_name><stock_code> </stock_code><modify_date>1</modify_date></list></result>")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("CORPCODE.xml", xml)
    df = dart.parse_corp_codes(buf.getvalue())
    assert list(df["stock_code"]) == ["005930"] and df.loc[0, "corp_code"] == "00126380"


def _row(sj, acc, amt, add=None, rcept="20260315000123", nm="x"):
    return {"rcept_no": rcept, "sj_div": sj, "account_id": acc, "account_nm": nm, "thstrm_amount": amt,
            "thstrm_add_amount": add, "currency": "KRW"}


def test_normalize_annual_quarterly_and_balance_sheet():
    annual = dart.normalize_statements([_row("IS", "ifrs-full_Revenue", "1,000"), _row("BS", "ifrs-full_Assets", "5,000")],
                                       corp_code="c", ticker="t", year=2025, reprt_code="11011", fs_div="CFS")
    assert {(o["statement"], o["amount_type"]) for o in annual} == {("IS", "FY"), ("BS", "INSTANT")}
    assert annual[0]["receipt_date"] == "2026-03-15" and annual[0]["basis"] == "CONSOLIDATED"
    q = dart.normalize_statements([_row("IS", "ifrs-full_Revenue", "300", "900"), _row("CF", "ifrs-full_CashFlowsFromUsedInOperatingActivities", "50")],
                                  corp_code="c", ticker="t", year=2025, reprt_code="11014", fs_div="OFS")
    kinds = {(o["statement"], o["amount_type"], o["value"]) for o in q}
    assert ("IS", "QUARTER_3M", 300.0) in kinds and ("IS", "YTD", 900.0) in kinds and ("CF", "YTD", 50.0) in kinds
    assert all(o["basis"] == "SEPARATE" for o in q)
    p = dart.fiscal_period(2025, "11014", 12)
    assert p["period_end"] == "2025-09-30" and p["quarter_start"] == "2025-07-01"
    p3 = dart.fiscal_period(2025, "11011", 3)
    assert p3["period_end"] == "2025-03-31" and p3["fy_start"] == "2024-04-01"


def _obs(rows, fs="CFS", rc="11011"):
    return dart.normalize_statements(rows, corp_code="c", ticker="t", year=2025, reprt_code=rc, fs_div=fs)


def test_extract_concepts_real_missing_not_applicable():
    o = _obs([_row("IS", "ifrs-full_Revenue", "1000"), _row("IS", "ifrs-full_ProfitLoss", ""),
              _row("IS", "-표준계정코드 미사용-", "77", nm="영업수익")])
    c = dart.extract_concepts(o, "NON_FINANCIAL")
    assert c["revenue"]["status"] == "REAL" and c["revenue"]["value"] == 1000.0 and c["revenue"]["basis"] == "CONSOLIDATED"
    assert c["net_income"] == {"status": "UNAVAILABLE", "reason": "VALUE_MISSING"}     # never 0
    assert c["total_assets"]["reason"] == "NOT_REPORTED_UNDER_STANDARD_ACCOUNT"
    bank = dart.extract_concepts(o, "BANK")
    assert bank["revenue"]["status"] == "NOT_APPLICABLE"


def test_extract_concepts_never_mixes_bases():
    with pytest.raises(ValueError):
        dart.extract_concepts(_obs([_row("IS", "ifrs-full_Revenue", "1")], "CFS") +
                              _obs([_row("IS", "ifrs-full_Revenue", "2")], "OFS"), "NON_FINANCIAL")


def test_receipt_date_point_in_time_rule():
    o = _obs([_row("IS", "ifrs-full_Revenue", "1000", rcept="20260315000001")])
    assert dart.extract_concepts(o, "NON_FINANCIAL", as_of_date="2026-03-15")["revenue"]["reason"] == \
        "RECEIVED_ON_OR_AFTER_AS_OF"
    assert dart.extract_concepts(o, "NON_FINANCIAL", as_of_date="2026-03-16")["revenue"]["status"] == "REAL"


def test_ambiguous_duplicate_rows_unavailable():
    o = _obs([_row("IS", "ifrs-full_Revenue", "1"), _row("IS", "ifrs-full_Revenue", "2")])
    assert dart.extract_concepts(o, "NON_FINANCIAL")["revenue"]["reason"] == "AMBIGUOUS_DUPLICATE_ACCOUNT_ROWS"


def test_choose_basis_prefers_consolidated_never_combines():
    assert dart.choose_basis({"CFS": {"status": "REAL", "list": [1]}, "OFS": {"status": "REAL", "list": [2]}})["fs_div"] == "CFS"
    s = dart.choose_basis({"CFS": {"status": "UNAVAILABLE", "list": []}, "OFS": {"status": "REAL", "list": [2]}})
    assert s["basis"] == "SEPARATE" and s["rows"] == [2] and "note" in s
    assert dart.choose_basis({})["status"] == "UNAVAILABLE"


def test_account_registry_is_xbrl_keyed_and_versioned():
    rows = account_mapping.spec_rows()
    assert len(rows) == len(account_mapping.REGISTRY) >= 15
    for c, d in account_mapping.REGISTRY.items():
        assert d["account_ids"] and all(a != account_mapping.NON_STANDARD_ACCOUNT for a in d["account_ids"])
        assert d["confidence"] and d["applicability"]


# ---------------------------------------------------------------- calendar
def test_bar_completion_and_signal_classification():
    assert not krcal.bar_is_complete("2026-10-30", pd.Timestamp("2026-10-30 08:00", tz="UTC"))   # 17:00 KST
    assert krcal.bar_is_complete("2026-10-30", pd.Timestamp("2026-10-30 09:01", tz="UTC"))       # 18:01 KST
    pre = krcal.classify_signal("2026-11-02T23:00:00+00:00")          # Tue 08:00 KST
    assert pre["classification"] == "PREMARKET" and pre["entry_not_before"] == "2026-11-03"
    after = krcal.classify_signal("2026-11-03T07:00:00+00:00")        # Tue 16:00 KST
    assert after["classification"] == "AFTER_CLOSE" and after["entry_not_before"] == "2026-11-04"
    reg = krcal.classify_signal("2026-11-03T02:00:00+00:00")          # Tue 11:00 KST
    assert reg["classification"] == "REGULAR_SESSION" and reg["entry_not_before"] == "2026-11-04"


# ---------------------------------------------------------------- universe
def _universe_inputs(n=12):
    sess = pd.bdate_range("2026-09-01", "2026-10-30")
    master = pd.DataFrame({"canonical_ticker": [f"{i:06d}" for i in range(n)],
                           "market": ["KOSPI" if i % 2 else "KOSDAQ" for i in range(n)],
                           "security_key": [f"KR:X:{i:06d}" for i in range(n)], "eligible": True,
                           "company_name": "x", "industry": "반도체 제조업", "industry_class": "NON_FINANCIAL"})
    rows = []
    for i in range(n):
        for d in sess:
            rows.append(_rows(date=d, ticker=f"{i:06d}", market=master.loc[i, "market"], volume=1000.0 * (i + 1),
                              traded_value=105000.0 * (i + 1)))
    return master, validate_rows(pd.concat(rows, ignore_index=True)), sess


def test_universe_ranks_by_adtv20_and_excludes_with_reasons():
    master, bars, sess = _universe_inputs()
    bars = bars[~((bars["ticker"] == "000011") & (bars["date"] > sess[-5]))]     # stale top name
    bars = bars[bars["ticker"] != "000010"]                                      # no data
    u = universe.build(master, bars, sess, sess[-1], size=5)
    t = u["table"].set_index("ticker")
    assert list(u["members"]["ticker"]) == ["000009", "000008", "000007", "000006", "000005"]
    assert t.loc["000011", "reason"] == "STALE_LAST_BAR" and t.loc["000010", "reason"] == "NO_MARKET_DATA"
    assert t.loc["000000", "status"] == "NOT_SELECTED"
    assert u["summary"]["traded_value_basis"] == ["PROXY_CLOSE_X_VOLUME"] and u["summary"]["members"] == 5


def test_universe_insufficient_observations_and_stability():
    master, bars, sess = _universe_inputs(6)
    bars = bars[~((bars["ticker"] == "000005") & (bars["date"] < sess[-10]))]
    u = universe.build(master, bars, sess, sess[-1], size=3)
    assert u["table"].set_index("ticker").loc["000005", "reason"] == "INSUFFICIENT_VALID_OBSERVATIONS"
    s = universe.stability(["a", "b", "c"], ["b", "c", "d"])
    assert s["jaccard"] == pytest.approx(0.5)
