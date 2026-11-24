"""2026-11-24 user report: a DART filing of 16:37 missing from the stock screen (현대자동차 자기주식처분결과보고서), the Korean news
record cut at the same place every day, and the account form's total.  No network."""
import json
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from terminal import news
from terminal.cache import FileCache
from terminal.qsf.service import QSF, TTL

ROOT = Path(__file__).resolve().parents[1]


class _Reply:
    def __init__(self, body):
        self.body = body

    def json(self):
        return self.body


class _Dart:
    def __init__(self):
        self.asked = []

    def _get(self, endpoint, **params):
        self.asked.append(params["end_de"])
        return _Reply({"status": "000", "total_page": 1, "list": [{"rcept_dt": params["end_de"], "report_nm": f"공시 {len(self.asked)}"}]})


def _qsf(tmp_path, clock):
    q = object.__new__(QSF)
    q.cache, q._dart = FileCache(tmp_path, clock=clock), _Dart()
    return q


def test_a_stored_list_that_ends_before_the_asked_day_is_fetched_again(tmp_path):
    now = [datetime(2026, 11, 24, 0, 28, tzinfo=ZoneInfo("Asia/Seoul")).timestamp()]
    q = _qsf(tmp_path, lambda: now[0])
    first = q._kr_filing_list("00164742", date(2026, 11, 23), TTL["subm"])
    assert first["data"]["end"] == "20261123"
    now[0] += 16 * 3600                                                    # 16:28 the same day, inside the old 20-hour life
    again = q._kr_filing_list("00164742", date(2026, 11, 24), TTL["kr_list_screen"])
    assert again["data"]["end"] == "20261124" and q._dart.asked == ["20261123", "20261124"]
    now[0] += 30 * 60
    q._kr_filing_list("00164742", date(2026, 11, 24), TTL["kr_list_screen"])          # within the hour: the stored list
    assert len(q._dart.asked) == 2
    now[0] += 31 * 60
    q._kr_filing_list("00164742", date(2026, 11, 24), TTL["kr_list_screen"])          # past the hour: asked again
    assert len(q._dart.asked) == 3 and TTL["kr_list_screen"] == 3600


def test_the_scan_reads_a_list_fetched_after_its_session_day(tmp_path):
    seoul = ZoneInfo("Asia/Seoul")
    now = [datetime(2026, 11, 24, 15, 0, tzinfo=seoul).timestamp()]
    q = _qsf(tmp_path, lambda: now[0])
    q._kr_filing_list("1", date(2026, 11, 24), TTL["kr_list_screen"])                 # the screen, mid-afternoon
    now[0] = datetime(2026, 11, 25, 7, 30, tzinfo=seoul).timestamp()               # next morning's scan of session 11-24
    q._kr_filing_list("1", date(2026, 11, 24), TTL["subm"], whole_day=True)
    assert len(q._dart.asked) == 2                                                  # the afternoon list missed the evening
    q._kr_filing_list("1", date(2026, 11, 24), TTL["subm"], whole_day=True)
    assert len(q._dart.asked) == 2                                                  # fetched after the day: kept


def _universe(base, n):
    folder = base / "data" / "qsf"
    folder.mkdir(parents=True)
    (folder / "latest_KR.json").write_text(json.dumps({"rows": [{"ticker": f"{i:06d}", "name": f"회사{i}"} for i in range(n)]}), encoding="utf-8")


def test_the_news_record_resumes_where_the_provider_refused(tmp_path, monkeypatch):
    _universe(tmp_path, 10)
    asked, refuse_after = [], [4]

    def fake_fetch(ticker, market, name, client):
        if len(asked) >= refuse_after[0]:
            raise news.FeedRefused("429")
        asked.append(ticker)
        return {"items": []}
    monkeypatch.setattr(news, "fetch", fake_fetch)
    first = news.record(tmp_path, "KR", http=object(), sleep=lambda s: None)
    assert asked == ["000000", "000001", "000002", "000003"] and first["next_start"] == 4 and first["start"] == 0
    asked.clear()
    second = news.record(tmp_path, "KR", http=object(), sleep=lambda s: None)
    assert asked == ["000004", "000005", "000006", "000007"] and second["start"] == 4 and second["next_start"] == 8
    asked.clear(); refuse_after[0] = 99
    third = news.record(tmp_path, "KR", http=object(), sleep=lambda s: None)
    assert asked[:3] == ["000008", "000009", "000000"] and len(asked) == 10 and third["status"] == "OK" and third["next_start"] == 8


def test_resume_point_is_read_safely():
    assert news.resume_at(Path("/nonexistent"), 300) == 0


def test_the_account_form_shows_quantity_times_price():
    acct = (ROOT / "terminal" / "static" / "account.js").read_text(encoding="utf-8")
    assert 'id="accttotal"' in acct and "${qtyFmt(q)}${unit} × ${acctPrice(p, cur)}" in acct and "1주당" in acct
    assert "(${qty}주 × ${money(price)})" in (ROOT / "terminal" / "static" / "paper.js").read_text(encoding="utf-8")
