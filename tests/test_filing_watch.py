"""2026-11-24 user decision ("만들어"): new filings of held and watched stocks, checked during the day, told by Telegram and on
the 오늘 screen, never scored.  No network."""
import json
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from terminal import assistant, filing_watch as fw

ROOT = Path(__file__).resolve().parents[1]
SEOUL, NY = ZoneInfo("Asia/Seoul"), ZoneInfo("America/New_York")


class _Reply:
    def __init__(self, body):
        self.body = body

    def json(self):
        return self.body


class _Dart:
    configured = True

    def __init__(self):
        self.rows, self.asked = [], 0

    def _get(self, endpoint, **params):
        self.asked += 1
        if not self.rows:
            return _Reply({"status": "013"})
        return _Reply({"status": "000", "total_page": 1, "list": list(self.rows)})


class _Qsf:
    def __init__(self):
        self.dart = _Dart()

    def _corp_code(self, code):
        return "00164742" if code == "005380" else None

    def latest(self, market):
        return {"rows": [{"ticker": "TECH", "name": "Bio-Techne"}]}


class _Src:
    def __init__(self):
        self.subm, self.asked = {"filings": {"recent": {}}}, 0

    def sec_submissions(self, cik):
        self.asked += 1
        return self.subm


class _Terminal:
    def __init__(self, base, us=("TECH",), kr=("005380",), watch=()):
        self.base, self.qsf, self.src = base, _Qsf(), _Src()
        self.books = {"US": {t: {} for t in us}, "KR": {t: {} for t in kr}}
        self.watch = list(watch)

    def _book(self, market):
        return [], {}, {"positions": self.books[market]}

    def watchlist(self):
        return self.watch

    def _cik(self, ticker):
        return "0000842023" if ticker == "TECH" else None

    def _kr_name(self, ticker):
        return "현대차"


def _subm(*rows):
    cols = {"form": [], "filingDate": [], "items": [], "accessionNumber": [], "primaryDocument": []}
    for form, day, items, acc in rows:
        for k, v in zip(cols, (form, day, items, acc, "x.htm")):
            cols[k].append(v)
    return {"filings": {"recent": cols}}


KR_OPEN = datetime(2026, 11, 24, 16, 50, tzinfo=SEOUL)
US_OPEN = datetime(2026, 11, 24, 10, 0, tzinfo=NY)


def test_hours_are_weekday_filing_hours_of_each_market():
    assert fw.open_now("KR", KR_OPEN) and not fw.open_now("KR", datetime(2026, 11, 24, 21, 0, tzinfo=SEOUL))
    assert not fw.open_now("KR", datetime(2026, 11, 22, 12, 0, tzinfo=SEOUL))           # Sunday
    assert fw.open_now("US", US_OPEN) and not fw.open_now("US", datetime(2026, 11, 24, 23, 0, tzinfo=NY))
    assert fw.EVERY_S == 1800


def test_labels_take_the_scored_lists_and_what_a_holder_wants_the_same_day():
    assert fw.kr_label("자기주식처분결과보고서") == "자사주 처분"
    assert fw.kr_label("주요사항보고서(유상증자결정)") == "유상증자"
    assert fw.kr_label("연결재무제표기준영업(잠정)실적(공정공시)") == "잠정 실적"
    assert fw.kr_label("임원ㆍ주요주주특정증권등소유상황보고서") is None
    assert fw.us_label("8-K", "2.02,9.01") == "실적 발표 (8-K 2.02)"
    assert fw.us_label("8-K", "9.01") is None and fw.us_label("10-Q", "") is None
    assert fw.us_label("SC TO-T", "") == "제3자의 공개매수 신고" and fw.us_label("10-K/A", "") == "연차보고서 정정 (10-K/A)"


def test_the_first_look_records_without_telling_then_only_new_important_filings_are_told(tmp_path):
    t = _Terminal(tmp_path)
    t.qsf.dart.rows = [{"rcept_no": "20261124000001", "report_nm": "분기보고서 (2026.09)"}]
    sent = []
    first = fw.check(t, KR_OPEN, ("KR",), send=sent.append, pause=lambda s: None)
    assert first["asked"] == 1 and first["new"] == [] and sent == []
    t.qsf.dart.rows.append({"rcept_no": "20261124000777", "report_nm": "자기주식처분결과보고서"})
    t.qsf.dart.rows.append({"rcept_no": "20261124000778", "report_nm": "기업설명회(IR)개최"})          # not on the lists: kept quiet
    got = fw.check(t, KR_OPEN, ("KR",), send=sent.append, pause=lambda s: None)
    assert [a["title"] for a in got["new"]] == ["자기주식처분결과보고서"] and got["new"][0]["name"] == "현대차"
    assert "rcpNo=20261124000777" in got["new"][0]["url"]
    assert len(sent) == 1 and "자사주 처분" in sent[0] and "점수와 판단은 바뀌지 않았습니다" in sent[0]
    again = fw.check(t, KR_OPEN, ("KR",), send=sent.append, pause=lambda s: None)
    assert again["new"] == [] and len(sent) == 1                                         # never told twice
    lines = (tmp_path / fw.ALERTS).read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1 and json.loads(lines[0])["ticker"] == "005380"


def test_us_filings_of_today_and_yesterday_only(tmp_path):
    t = _Terminal(tmp_path, kr=())
    t.src.subm = _subm(("8-K", "2026-11-20", "2.02", "0001-26-1"))
    fw.check(t, US_OPEN, ("US",), send=lambda x: None, pause=lambda s: None)
    t.src.subm = _subm(("8-K", "2026-11-24", "5.02", "0001-26-3"), ("8-K", "2026-11-20", "2.02", "0001-26-1"), ("4", "2026-11-24", "", "0001-26-4"))
    got = fw.check(t, US_OPEN, ("US",), send=lambda x: None, pause=lambda s: None)
    assert [a["label"] for a in got["new"]] == ["임원·이사 변경 (8-K 5.02)"] and got["new"][0]["name"] == "Bio-Techne"
    assert got["new"][0]["url"] == "https://www.sec.gov/Archives/edgar/data/842023/0001263/x.htm"


def test_closed_hours_ask_nothing_and_a_failed_request_is_named_by_type(tmp_path):
    t = _Terminal(tmp_path)
    assert fw.check(t, datetime(2026, 11, 22, 12, 0, tzinfo=SEOUL), send=lambda x: None, pause=lambda s: None)["asked"] == 0
    assert t.qsf.dart.asked == 0 and t.src.asked == 0

    def boom(cik):
        raise ConnectionError("https://example.invalid/?key=secret")
    t.src.sec_submissions = boom
    got = fw.check(t, US_OPEN, ("US",), send=lambda x: None, pause=lambda s: None)
    assert got["failed"] == [{"market": "US", "ticker": "TECH", "error": "ConnectionError"}] and "secret" not in json.dumps(got)


def test_targets_are_holdings_then_watch_list_per_market(tmp_path):
    t = _Terminal(tmp_path, us=("TECH",), kr=("005380",), watch=["AAPL", "005930", "TECH", "^GSPC"])
    got = fw.targets(t)
    assert got["US"] == ["TECH", "AAPL"] and got["KR"] == ["005380", "005930"]


def test_today_screen_lists_recent_alerts_of_its_market(tmp_path):
    (tmp_path / "data" / "terminal").mkdir(parents=True)
    rows = [{"at": "2026-11-24T07:40:00+00:00", "market": "KR", "ticker": "005380", "name": "현대차", "date": "2026-11-24",
             "title": "자기주식처분결과보고서", "label": "자사주 처분", "url": None},
            {"at": "2026-11-10T07:40:00+00:00", "market": "KR", "ticker": "005380", "name": "현대차", "date": "2026-11-10",
             "title": "주요사항보고서(유상증자결정)", "label": "유상증자", "url": None}]
    (tmp_path / fw.ALERTS).write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    now = datetime(2026, 11, 24, 18, 0, tzinfo=SEOUL)
    got = assistant.filing_items(tmp_path, now, "KR")
    assert len(got) == 1 and got[0]["kind"] == "NEW_FILING" and "현대차(005380)" in got[0]["text"] and got[0]["level"] == "DUE"
    assert assistant.filing_items(tmp_path, now, "US") == []
    assert "filings" in assistant.PART_KO


def test_the_watch_runs_only_in_the_real_server_and_feeds_no_score():
    server = (ROOT / "terminal" / "server.py").read_text(encoding="utf-8")
    assert "filing_watch.start(t)" in server and server.index("if warm_up:") < server.index("filing_watch.start(t)")
    for path in (ROOT / "terminal" / "qsf").glob("*.py"):
        assert "filing_watch" not in path.read_text(encoding="utf-8"), path.name


def test_days_without_a_turn_are_asked_again_and_a_missing_key_is_said(tmp_path):
    t = _Terminal(tmp_path, us=())
    asked = []
    get = t.qsf.dart._get

    def spy(endpoint, **params):
        asked.append((params["bgn_de"], params["end_de"]))
        return get(endpoint, **params)
    t.qsf.dart._get = spy
    fw.check(t, datetime(2026, 11, 19, 10, 0, tzinfo=SEOUL), ("KR",), send=lambda x: None, pause=lambda s: None)       # Thursday
    t.qsf.dart.rows = [{"rcept_no": "20261120000009", "rcept_dt": "20261120", "report_nm": "주요사항보고서(유상증자결정)"}]
    sent = []
    got = fw.check(t, datetime(2026, 11, 24, 10, 0, tzinfo=SEOUL), ("KR",), send=sent.append, pause=lambda s: None)   # the Mac slept until Tuesday
    assert asked == [("20261119", "20261119"), ("20261119", "20261124")]
    assert [a["date"] for a in got["new"]] == ["2026-11-20"] and len(sent) == 1                                      # the filing's own day, told once
    far = fw.check(t, datetime(2026, 12, 21, 10, 0, tzinfo=SEOUL), ("KR",), send=sent.append, pause=lambda s: None)
    assert asked[-1] == ("20261214", "20261221") and far["new"] == [] and fw.CATCH_UP_DAYS == 7                      # never further back than a week
    t.qsf.dart.configured = False
    none = fw.check(t, datetime(2026, 12, 22, 10, 0, tzinfo=SEOUL), ("KR",), send=sent.append, pause=lambda s: None)
    assert none["failed"] == [{"market": "KR", "ticker": "*", "error": "NO_DART_KEY"}] and none["asked"] == 0


def test_the_watch_stores_the_us_list_where_the_card_reads_it(tmp_path):
    t = _Terminal(tmp_path, kr=())
    stored = []

    def refresh(cik):
        stored.append(cik)
        return {"filings": [{"form": "8-K", "date": "2026-11-24", "items": "5.02", "accession": "0001-26-3", "doc": "x.htm"}]}
    t.qsf.refresh_us_filings = refresh
    fw.check(t, US_OPEN, ("US",), send=lambda x: None, pause=lambda s: None)
    assert stored == ["0000842023"] and t.src.asked == 0                         # one request, through the shared store
    s = (ROOT / "terminal" / "qsf" / "service.py").read_text(encoding="utf-8")
    assert 'res = self._us_subm_res(cik, ttl=0)' in s and 'TTL["subm"] if ttl is None else ttl' in s
