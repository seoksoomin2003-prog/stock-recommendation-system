"""The six reference readings of the third audit: expectations kept and recorded, merger filings, ex-dividend dates, moves
around results, valuation against the stock's own past, and the wording for financial companies.  None enters a score."""
import json

import pytest
from utils import durable
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

from terminal import analyst_more as am
from terminal import assistant as A
from terminal import sources, store_watch
from terminal.qsf import events, expectations, service, views

EX_DAY = datetime(2026, 12, 10, tzinfo=timezone.utc).timestamp()


def bars(n=400, start=100.0, step=0.0, first=date(2025, 1, 2)):
    out, d, px = [], first, start
    while len(out) < n:
        if d.weekday() < 5:
            out.append({"date": d.isoformat(), "close": round(px, 4)})
            px += step
        d += timedelta(days=1)
    return out


# ---------------------------------------------------------------------------------------------- the Yahoo record
def test_the_expectation_fields_are_kept_as_numbers_and_days_and_a_missing_one_stays_missing():
    raw = {"longName": "X", "forwardEps": "31.1", "targetMeanPrice": 376.5, "numberOfAnalystOpinions": 24, "recommendationKey": "hold", "exDividendDate": EX_DAY,
           "dateShortInterest": None, "sharesShort": "nan", "earningsTimestampStart": 0, "shortPercentOfFloat": 0.0245}
    out = sources.yahoo_info("X", fetch=lambda t: raw)
    assert out == {"longName": "X", "forwardEps": 31.1, "targetMeanPrice": 376.5, "numberOfAnalystOpinions": 24.0, "recommendationKey": "hold", "exDividendDate": "2026-12-10",
                   "shortPercentOfFloat": 0.0245}
    assert sources.yahoo_expectations({"recommendationKey": "none", "exDividendDate": "soon"}) == {}       # nothing is invented from an unreadable value
    assert set(sources.EXPECT_FIELDS).isdisjoint(sources.INFO_FIELDS)                                       # the fields the scores read are untouched


# ---------------------------------------------------------------------------------------------- the record
def test_a_stock_is_written_once_per_download_and_korean_records_are_found_by_either_suffix(tmp_path):
    store = {"info:AAA": {"stored_at": 1795000000.0, "data": {"targetMeanPrice": 120.0, "currentPrice": 100.0, "longName": "A"}},
             "info:BBB": {"stored_at": 1795000000.0, "data": {"longName": "B"}},                             # no expectation field: not a line
             "info:005930.KS": {"stored_at": 1795000000.0, "data": {"epsCurrentYear": 47679.5}}, "info:035720.KQ": {"stored_at": 1795000000.0, "data": {"targetMeanPrice": 5.0}}}
    got = expectations.record(tmp_path, "US", "2026-11-23", ["AAA", "BBB", "CCC"], store.get)
    assert got == {"status": "OK", "market": "US", "session": "2026-11-23", "written": 1, "with_expectations": 1}
    assert expectations.record(tmp_path, "US", "2026-11-24", ["AAA", "BBB"], store.get)["written"] == 0      # the same download is not written twice
    store["info:AAA"] = {"stored_at": 1795600000.0, "data": {"targetMeanPrice": 125.0, "currentPrice": 101.0}}
    assert expectations.record(tmp_path, "US", "2026-12-01", ["AAA"], store.get)["written"] == 1
    folder = tmp_path / "research_data" / "expectations_us"
    assert sorted(p.name for p in folder.glob("*.jsonl")) == ["2026-11.jsonl", "2026-12.jsonl"]
    assert durable.verify_chained(folder) == {"status": "OK", "lines": 2}                                # each line follows the one before (audit 2026-11-22)
    first = json.loads((folder / "2026-11.jsonl").read_text().splitlines()[0])
    assert first["ticker"] == "AAA" and first["targetMeanPrice"] == 120.0 and first["price"] == 100.0 and first["session"] == "2026-11-23" and first["fetched"].endswith("Z")
    with open(folder / "2026-12.jsonl", "a") as fh:
        fh.write('{"ticker": "AAA", "fetch')                                                               # a torn last line is skipped, not repaired
    st = expectations.status(tmp_path, "US")
    assert (st["market"], st["lines"], st["stocks"], st["first"]) == ("US", 2, 1, first["fetched"][:10]) and st["last"] > st["first"]
    store["info:AAA"] = {"stored_at": 1796000000.0, "data": {"targetMeanPrice": 130.0, "currentPrice": 102.0}}
    with pytest.raises(durable.TornFile):                                                                # and nothing is appended after it
        expectations.record(tmp_path, "US", "2026-12-02", ["AAA"], store.get)
    assert durable.verify_chained(folder)["status"] == "TORN" and store_watch.look(tmp_path, [])[0]["store"] == "expectations_us"
    assert expectations.record(tmp_path, "KR", "2026-11-23", ["005930", "035720", "000660"], store.get)["written"] == 2
    assert expectations.status(tmp_path, "KR")["stocks"] == 2 and expectations.status(tmp_path / "nothing", "US")["lines"] == 0


def test_the_note_states_the_stored_expectations_and_says_whose_numbers_they_are():
    info = {"numberOfAnalystOpinions": 24, "targetMeanPrice": 376.54, "targetLowPrice": 262.0, "targetHighPrice": 460.0, "epsCurrentYear": 36.8, "forwardEps": 31.11, "recommendationMean": 2.97,
            "recommendationKey": "hold", "sharesShort": 4460511, "sharesShortPriorMonth": 5893496, "shortPercentOfFloat": 0.0245, "shortRatio": 3.21, "dateShortInterest": "2026-10-30",
            "heldPercentInstitutions": 0.8906, "exDividendDate": "2026-12-10", "dividendRate": 5.0}
    got = expectations.lines(info, 393.24, "US", date(2026, 11, 20))
    assert got[0] == "목표주가: 증권사 24곳 평균 $376.54(지금 가격 대비 -4.2%), 범위 $262.00 ~ $460.00."
    assert got[1] == "예상 주당이익: 올해 $36.80, 다음 해 $31.11(-15.5%). 다음 해 예상 이익 기준 PER 12.6배."
    assert got[2] == "투자의견 평균 2.97(1 적극 매수 ~ 5 매도, '보유' 쪽)." and got[3] == "공매도 잔고: 2026-10-30 기준 유통주식의 2.5%, 한 달 전보다 -24%, 평균 거래량으로 3.2일치."
    assert got[4] == "기관 보유 비율 89%." and got[5] == "배당락일 2026-12-10(20일 뒤), 연 배당금 $5.00." and "공식 자료가 아닙니다" in got[6] and "점수에 들어가지 않습니다" in got[6]
    assert expectations.lines({}, 100.0, "US") == [] and expectations.lines(None, None, "KR") == []
    thin = expectations.lines({"numberOfAnalystOpinions": 2, "targetMeanPrice": 71000.0}, 70000.0, "KR")
    assert thin[0] == "목표주가: 증권사 2곳 평균 71,000원(지금 가격 대비 +1.4%). 의견이 2곳뿐이라 값이 크게 흔들릴 수 있습니다."


# ---------------------------------------------------------------------------------------------- merger filings
def test_merger_filings_are_kept_in_the_list_and_never_reach_the_event_score():
    plain = [{"form": "8-K", "date": "2026-10-05", "items": "2.02,9.01", "accession": "a", "doc": "d"}]
    deal = plain + [{"form": "DEFM14A", "date": "2026-08-20", "items": "", "accession": "b", "doc": "d"}, {"form": "PREM14A", "date": "2026-08-10", "items": "", "accession": "c", "doc": "d"},
                    {"form": "SC TO-T/A", "date": "2025-01-05", "items": "", "accession": "e", "doc": "d"}, {"form": "425", "date": "2026-09-01", "items": "", "accession": "f", "doc": "d"}]
    assert {"DEFM14A", "PREM14A", "SC TO-T", "SC 14D9/A"} <= events.KEPT_FORMS and "425" not in events.KEPT_FORMS and "S-4" not in events.KEPT_FORMS
    got = events.deal_filings(deal, "2026-11-20")
    assert got == [{"form": "DEFM14A", "date": "2026-08-20", "label": "합병 주주총회 위임장"}, {"form": "PREM14A", "date": "2026-08-10", "label": "합병 주주총회 예비 위임장"}]
    assert events.deal_filings(deal, "2026-01-01", days=400) == [{"form": "SC TO-T", "date": "2025-01-05", "label": "제3자의 공개매수 신고"}] and events.deal_filings(None, "2026-11-20") == []
    assert events.classify_us(deal, "2026-11-20") == events.classify_us(plain, "2026-11-20")              # the score's reading is the same with and without them


def test_the_mark_states_the_filing_and_reads_a_target_only_beside_a_pinned_price():
    rows = events.deal_filings([{"form": "DEFM14A", "date": "2026-08-20"}, {"form": "PREM14A", "date": "2026-08-10"}, {"form": "DEFM14A", "date": "2026-08-25"}], "2026-11-20")
    still = am.deal_line(rows, still=True)
    assert still.startswith("SEC에 인수·합병 절차 공시가 있습니다: 합병 주주총회 위임장(DEFM14A, 2026-08-25), 합병 주주총회 예비 위임장(PREM14A, 2026-08-10).") and "인수되는 쪽으로 읽힙니다" in still
    moving = am.deal_line(rows)
    assert "인수하는 쪽이 낼 때도 있으니" in moving and "인수되는 쪽으로" not in moving and moving.endswith("점수는 이 공시를 읽지 않습니다.") and am.deal_line([]) is None


def test_the_stored_list_is_read_without_a_request_and_the_pinned_note_states_the_filing():
    filings = [{"form": "DEFM14A", "date": "2026-08-20", "items": ""}]
    qsf = SimpleNamespace(cache=SimpleNamespace(read=lambda key: {"data": {"filings": filings}} if key == "submforms:0000842023" else None))
    assert service.QSF.stored_deals(qsf, "0000842023", "2026-11-20")[0]["form"] == "DEFM14A" and service.QSF.stored_deals(qsf, None, "2026-11-20") == [] and service.QSF.stored_deals(qsf, "1", "2026-11-20") == []
    term = SimpleNamespace(qsf=SimpleNamespace(stored_deals=lambda cik, day: events.deal_filings(filings, day)))
    pinned = {"market": "US", "cik": "0000842023", "data_date": "2026-11-20", "factors": [{"factor": "atr_risk", "raw": {"atr_pct": 0.002}}]}
    note = A.still_note(term, pinned)
    assert note.startswith("최근 하루 변동 폭이 가격의 0.2%로 거의 움직이지 않습니다. SEC에 인수·합병 절차 공시가 있습니다: 합병 주주총회 위임장(DEFM14A, 2026-08-20).") and "흔한 모습" not in note
    moving = dict(pinned, factors=[{"factor": "atr_risk", "raw": {"atr_pct": 0.03}}])
    assert A.still_note(term, moving).startswith("SEC에 인수·합병 절차 공시가 있습니다") and A.still_note(term, dict(moving, market="KR")) is None and A.still_note(term, None) is None
    broken = SimpleNamespace(qsf=SimpleNamespace())                                                       # no reader: the note falls back to the price alone
    assert A.still_note(broken, pinned) == A.pinned(pinned) and A.still_note(broken, moving) is None


# ---------------------------------------------------------------------------------------------- ex-dividend dates
def test_ex_dividend_dates_of_ones_own_stocks_come_from_the_stored_records_only():
    info = {"AAA": {"exDividendDate": "2026-11-24", "longName": "A Inc.", "dividendRate": 2.0}, "BBB": {"exDividendDate": "2026-12-30"}, "CCC": {"exDividendDate": "2026-11-19"}, "DDD": {}}
    fake = SimpleNamespace(now=lambda: datetime(2026, 11, 22, 3, 0, tzinfo=timezone.utc), stored_info=lambda t, m: info.get(t, {}),
                           terminal=SimpleNamespace(_book=lambda m: (None, None, {"positions": {"AAA": {}}}), watchlist=lambda: ["BBB", "CCC", "DDD", "005930"]))
    got = views.ScreenViews.dividends_upcoming(fake, "US", 14)
    assert [(i["ticker"], i["days_away"], i["held"], i["watched"]) for i in got["items"]] == [("AAA", 3, True, False)] and "공식 자료 아님" in got["source"]
    text = am.dividend_item_text(got["items"][0])
    assert text.startswith("보유 종목 A Inc.(AAA) 배당락일 2026-11-24(3일 뒤).") and "회사 공시와 다를 수 있습니다" in text
    assert am.dividend_item_text({"ticker": "BBB", "date": "2026-11-22", "days_away": 0, "held": False}).startswith("관심 종목 BBB(BBB) 배당락일 2026-11-22(오늘).")


# ---------------------------------------------------------------------------------------------- moves around results
def test_moves_around_past_results_use_the_close_before_and_the_close_of_the_session_after():
    b = bars(40)
    px = {x["date"]: x for x in b}
    days = [x["date"] for x in b]
    b[11]["close"] = 110.0                                 # the session after the announcement at index 10
    b[15]["close"] = 121.0                                 # the fifth session after
    weekend = (date.fromisoformat(days[19]) + timedelta(days=1)).isoformat()      # a Saturday: the next session is the first to react
    b[21]["close"] = 90.0
    got = am.reactions(b, [days[10], weekend, "2020-01-01", days[39]], bench=[dict(x, close=100.0) for x in b])
    assert [r["date"] for r in got] == [weekend, days[10]]                                                # newest first; no bar before, or none after: left out
    assert round(got[1]["move"], 4) == 0.10 and round(got[1]["five"], 4) == 0.21 and round(got[1]["rel"], 4) == 0.10 and round(got[0]["move"], 4) == -0.10
    assert am.reaction_lines(got) == [] and px[days[10]]["close"] == 100.0                                # fewer than three announcements: nothing is said
    rows = [{"date": "2026-10-20", "move": 0.031, "five": 0.05, "rel": 0.02}, {"date": "2026-07-21", "move": -0.052, "five": -0.01, "rel": -0.04}, {"date": "2026-04-21", "move": 0.012, "five": -0.02, "rel": 0.01}]
    lines = am.reaction_lines(rows, "SEC 8-K 실적 공시일(항목 2.02) 기준 추정")
    assert lines[0] == "지난 3번의 실적 발표 전후 움직임(발표 전날 종가 → 발표 다음 거래일 종가): 평균 크기 3.2%, 오른 적 2번, 내린 적 1번, 가장 큰 하락 -5.2%."
    assert lines[1] == "발표별: 26-10 +3.1%, 26-07 -5.2%, 26-04 +1.2%." and lines[2] == "발표 뒤 5거래일까지 같은 방향이 이어진 것은 3번 중 2번; 지수의 움직임을 뺀 평균 크기는 2.3%."
    assert "방향을 말하지 않습니다" in lines[3] and "SEC 8-K" in lines[3]


# ---------------------------------------------------------------------------------------------- valuation against its own past
def test_the_own_range_uses_the_annual_figure_filed_by_each_day_and_holds_the_share_count_still():
    b = bars(400, start=50.0, step=0.125)                                                                 # 50 -> 99.875
    filed_late = b[200]["date"]
    annual = {"net_income": [{"end": "2023-12-31", "val": 100.0, "filed": "2024-02-15"}, {"end": "2024-12-31", "val": 200.0, "filed": filed_late},
                             {"end": "2024-12-31", "val": 999.0, "filed": "2030-01-01"}],                    # a later restatement is not known yet
              "equity": [{"end": "2023-12-31", "val": 1000.0, "filed": "2024-02-15"}, {"end": "2024-12-31", "val": 1000.0, "filed": filed_late}]}
    assert am._known(annual["net_income"], b[199]["date"]) == 100.0 and am._known(annual["net_income"], filed_late) == 200.0 and am._known([], filed_late) is None
    h = am.valuation_history(b, annual, 20.0, 2.0, share_change=-0.015)
    assert h["status"] == "REAL" and h["from"] == b[0]["date"] and h["pe"]["n"] == 80 and h["pb"]["n"] == 80 and h["pe"]["now"] == 20.0
    oldest = 20.0 * (b[4]["close"] / b[-1]["close"]) * (200.0 / 100.0)                                    # the oldest weekly sample: price then, earnings known then
    assert abs(max(h["pe"]["high"], oldest) - h["pe"]["high"]) < 1e-9 and h["pb"]["high"] == 2.0 and h["pb"]["place"] == 1.0 and abs(h["pb"]["low"] - 2.0 * b[4]["close"] / b[-1]["close"]) < 1e-9
    lines = am.valuation_lines(h)
    assert lines[1].startswith("자기 이력 대비 PBR 2.0배: 2025-01부터의 범위 1.0~2.0배") and "가장 비싼 쪽" in lines[1] and lines[2].endswith("주식 수는 그대로였다고 본 참고값입니다.")
    assert am.valuation_lines(am.valuation_history(b, annual, 20.0, 2.0)) [-1].endswith("(주식 수 변화를 알 수 없는 종목입니다).")
    skipped = am.valuation_history(b, annual, 20.0, 2.0, share_change=0.12)
    assert skipped["status"] == "SKIPPED" and am.valuation_lines(skipped) == ["주식 수가 1년에 +12.0% 바뀌어, 주식 수를 그대로 두고 계산하는 자기 이력 범위를 내지 않았습니다."]
    loss = {"net_income": [{"end": "2023-12-31", "val": -5.0, "filed": "2024-02-15"}], "equity": []}
    assert am.valuation_history(b, loss, None, None)["status"] == "UNAVAILABLE" and am.valuation_history(b[:100], annual, 20.0, 2.0)["status"] == "UNAVAILABLE" and am.valuation_lines(None) == []
    only_pb = am.valuation_history(b, dict(annual, net_income=loss["net_income"]), 20.0, 2.0)
    assert "pe" not in only_pb and "pb" in only_pb                                                        # a loss year has no P/E and is not shown as one


def test_stored_statements_and_records_are_found_by_market():
    store = {"info:AAA": {"data": {"longName": "A"}}, "info:005930.KQ": {"data": {"longName": "삼성"}}, "annual5:0001": {"data": {"equity": []}}, "krfund3:005930": {"data": {"net_income": []}}}
    qsf = SimpleNamespace(cache=SimpleNamespace(read=store.get), _kr_identity_or_reason=lambda code: ({"fiscal_month": 12}, None) if code == "005930" else (None, None))
    assert service.QSF.stored_info(qsf, "AAA", "US") == {"longName": "A"} and service.QSF.stored_info(qsf, "005930", "KR") == {"longName": "삼성"} and service.QSF.stored_info(qsf, "ZZZ", "US") == {}
    assert service.QSF.stored_annual(qsf, "AAA", "US", "0001") == {"equity": []} and service.QSF.stored_annual(qsf, "AAA", "US") is None
    assert service.QSF.stored_annual(qsf, "005930", "KR") == {"net_income": []} and service.QSF.stored_annual(qsf, "000000", "KR") is None


# ---------------------------------------------------------------------------------------------- financial companies
def test_a_financial_company_reads_not_applicable_and_a_crowded_buy_list_is_said():
    assert am.is_financial("Financial Services") and am.is_financial("금융") and not am.is_financial("Technology") and not am.is_financial(None)
    line = "사업의 질 87/100: ROE 19.1%, 영업이익률 자료 없음, 매출총이익률 자료 없음, 흑자 연도 비율 100%."
    assert am.financial_wording(line) == "사업의 질 87/100: ROE 19.1%, 영업이익률 해당 없음(금융업), 매출총이익률 해당 없음(금융업), 흑자 연도 비율 100%."
    assert am.financial_wording("최근 매출 성장 자료 없음") == "최근 매출 성장 자료 없음"                    # only the items the business does not have
    rows = [{"score": 75.0, "sector": "Financial Services", "actionability": "ACTIONABLE"}] * 3 + [{"score": 72.0, "sector": "Technology", "actionability": "ACTIONABLE"}] * 7 \
        + [{"score": 50.0, "sector": "Technology", "actionability": "ACTIONABLE"}] * 20 + [{"score": 90.0, "sector": "Financial Services", "actionability": "BLOCKED"}, {"score": None, "sector": "금융"}]
    got = am.financial_share_line(rows)
    assert got.startswith("장기 상위 구간 10개 중 금융업이 3개(30%)입니다. 대상 전체에서 금융업은 13%입니다.") and "금융 비중이 큰 목록" in got
    assert am.financial_share_line(rows[2:]) is None and am.financial_share_line(rows[:6]) is None          # under a quarter, or too few candidates: nothing is said


def test_a_screener_row_opens_its_score_card_in_the_view_that_shows_it():
    """Found in the 2026-11-22 terminal review: the card was drawn into the rank view's panel while the screener view was on
    screen, so a click on a screener row showed nothing."""
    from pathlib import Path
    page = (Path(am.__file__).parent / "static" / "qsf.js").read_text(encoding="utf-8")
    click = next(line for line in page.splitlines() if 'body.querySelectorAll(".qs-open")' in line)      # the screener's rows (the change list's rows are already in the rank view)
    assert click.index('qsfSetView("rank")') < click.index("qsfEvaluate(b.dataset.t, mk)")
    rank_view = page[page.index('<div data-view="rank">'):page.index('<div id="qsfrank">')]
    assert '<form id="qsfform"' in rank_view
    # workstation stage 4: the card's panel sits in the right column outside every view host, so it shows in the rank and screener
    # views alike; a one-column screener still sends the click to the rank view (above), and two columns keep the screener (D2)
    right = page[page.index('<div class="ws-right"'):page.index('<div class="ws-lower">')]
    assert '<div id="qsfdetail" class="ws-first"></div>' in right and "data-view" not in right
    assert "if (qsfBeside()) return pickRow(b.dataset.t);" in click
