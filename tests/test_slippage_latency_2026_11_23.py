"""Review of slippage and latency, fixes 1-3 (user decision 2026-11-23): the order price sits on the exchange's price step, the plan
says when to place orders, and a short Korean message goes out the moment the Korean score is recorded.  All offline."""
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

from terminal import automation
from terminal.automation import Daily
from terminal.qsf import order_plan as op
from tests.test_order_plan_paper_book import snap
from tests.test_terminal_1 import _loopback_only  # noqa: F401  (autouse: these tests may reach 127.0.0.1 only)
from tests.test_terminal_4 import TUE_NIGHT, FakeTerminal, clean_env, ledger  # noqa: F401  (clean_env is an autouse fixture)

ROOT = Path(__file__).resolve().parents[1]
KST = timezone(timedelta(hours=9))


# ---------------------------------------------------------------------- 1. the price step
def test_the_korean_price_step_follows_the_2023_band_table_and_us_steps_are_cents():
    assert [op.tick_size("KR", p) for p in (1_999, 2_000, 4_999, 5_000, 19_999, 20_000, 49_999, 50_000, 199_999, 200_000, 499_999, 500_000, 2_000_000)] == \
        [1, 5, 5, 10, 10, 50, 50, 100, 100, 500, 500, 1_000, 1_000]
    assert op.tick_size("US", 1.0) == 0.01 and op.tick_size("US", 0.99) == 0.0001


def test_the_order_price_is_the_cap_rounded_down_to_a_step():
    assert op.order_price("KR", 71_234.56) == 71_200 and op.order_price("KR", 20_030.0) == 20_000 and op.order_price("KR", 19_995.0) == 19_990
    assert op.order_price("KR", 512_345.0) == 512_000 and op.order_price("KR", 1_999.7) == 1_999 and op.order_price("KR", 71_200.0) == 71_200
    assert op.order_price("US", 123.456) == 123.45 and op.order_price("US", 0.56789) == 0.5678 and op.order_price("US", 10.0) == 10.0
    assert op.order_price("KR", None) is None and op.order_price("US", 0) is None
    rnd = random.Random(7)
    for _ in range(5_000):
        cap = rnd.uniform(500, 900_000)
        got = op.order_price("KR", cap)
        assert got <= cap + 1e-9 and got % op.tick_size("KR", got) == 0 and cap - got < op.tick_size("KR", cap) + 1e-6
        usd = rnd.uniform(1, 3_000)
        got = op.order_price("US", usd)
        assert got <= usd + 1e-9 and abs(round(got * 100) - got * 100) < 1e-6


def test_the_plan_itself_is_unchanged_so_the_paper_book_reads_the_same_limit():
    plan = op.build([op.candidates([snap("A", price=71_234.0, atr=1_500.0)], "2026-11-12")[0]], {"equity": 1e8, "cash": 1e8, "positions": {}}, "KR")
    o = plan["orders"][0]
    assert o["limit"] == 71_234.0 + op.LIMIT_ATR * 1_500.0 and "limit_order" not in o


def test_the_real_account_plan_carries_the_order_price_and_the_timing_note():
    src = (ROOT / "terminal" / "services.py").read_text(encoding="utf-8")
    assert 'o["limit_order"] = op.order_price(market, o["limit"])' in src and src.count('"timing_note": op.TIMING_NOTE[market]') == 2
    js = (ROOT / "terminal" / "static" / "qsf.js").read_text(encoding="utf-8")
    assert "isNum(o.limit_order) ? o.limit_order : o.limit" in js and js.count("d.timing_note") == 4 and "호가 단위로 내린 가격입니다" in js
    book = (ROOT / "terminal" / "qsf" / "paper_book.py").read_text(encoding="utf-8")
    assert "limit_order" not in book and "order_price" not in book


# ---------------------------------------------------------------------- 2. when to place the orders
def test_the_timing_note_names_the_opening_auction_and_the_us_regular_open():
    assert all(w in op.TIMING_NOTE["KR"] for w in ("08:30~08:59", "동시호가", "09:00", "NXT", "08:00~08:50"))
    assert all(w in op.TIMING_NOTE["US"] for w in ("23:30", "22:30", "프리마켓", "주간거래"))


def test_the_message_line_follows_the_korean_clock():
    at = lambda d, h, m: datetime(2026, 11, d, h, m, tzinfo=KST)        # noqa: E731  (2026-11-23 is a Monday)
    assert op.kr_timing_now(at(23, 7, 50)).startswith("오늘이 거래일이면 08:30~08:59")
    assert op.kr_timing_now(at(23, 8, 40)).startswith("지금이 동시호가 시간")
    assert op.kr_timing_now(at(23, 10, 1)).startswith("오늘 장은 이미 열렸습니다")
    assert op.kr_timing_now(at(23, 16, 0)).startswith("오늘 장은 끝났습니다")
    assert op.kr_timing_now(at(21, 8, 1)).startswith("다음 거래일")             # a Saturday run records Friday for Monday's open


# ---------------------------------------------------------------------- 3. the early Korean message
class PlanTerminal(FakeTerminal):
    def __init__(self, plan, calls=None):
        super().__init__()
        self.plan, self.calls = plan, calls

    def order_plan(self, market="US"):
        assert market == "KR"
        return dict(self.plan)


REAL = {"status": "REAL", "session": "2026-11-03", "candidates": 12, "orders": [
    {"ticker": "005930", "name": "삼성전자", "style": "SWING", "shares": 3, "limit": 71_234.5, "limit_order": 71_200.0, "band_label": "매수 후보"},
    {"ticker": "000660", "name": "SK하이닉스", "style": "LONG", "shares": 1, "limit": 201_234.0, "limit_order": 201_000.0}]}


def job(tmp_path, plan, terminal=None):
    clock, calls, sent = {"now": TUE_NIGHT}, [], []

    def runner(name, argv):
        calls.append(name)
        clock["now"] += timedelta(minutes=5)
        if name == "LAB":
            ledger(tmp_path, d.now().date().isoformat())
        return 0

    def telegram(text):
        sent.append(text)
        calls.append("TELEGRAM")
        return {"status": "SENT"}
    d = Daily(tmp_path, now=lambda: clock["now"], runner=runner, telegram=telegram, macos=lambda t, b: {"status": "SENT"},
              terminal=terminal or PlanTerminal(plan), backup_dir=tmp_path / "bk")
    return d, calls, sent


def test_the_korean_message_goes_out_right_after_the_korean_score_and_before_the_rest_of_the_chain(tmp_path):
    d, calls, sent = job(tmp_path, REAL)
    d.run()
    assert calls.index("QSF_KR") < calls.index("TELEGRAM") < calls.index("NEWS_KR") and calls.count("TELEGRAM") == 2      # early one, then the summary
    early = sent[0]
    assert early.startswith("🇰🇷 한국 점수 기록 완료 (기준 거래일 2026-11-03") and "삼성전자(005930) 스윙 3주, 지정가 71,200원 · 매수 후보" in early
    assert "SK하이닉스(000660) 장기 1주, 지정가 201,000원" in early and "71,234" not in early and "매매 지시가 아닙니다" in early
    assert "08:30~08:59" in early and d.state()["kr_early"]["session"] == "2026-11-03"


def test_the_message_is_sent_once_per_korean_session(tmp_path):
    d, calls, sent = job(tmp_path, REAL)
    d.run()
    st = d.state()
    st["kr_day"] = None                                    # the Korean steps run again, as on the next hourly firing of a new weekday
    d._save(st)
    d.run(resend=True)
    assert sum(t.startswith("🇰🇷") for t in sent) == 1


def test_no_account_lists_the_candidates_and_a_plan_that_cannot_be_read_sends_nothing(tmp_path):
    plan = {"status": "NO_ACCOUNT", "session": "2026-11-03", "candidates": 5, "candidates_by": {"SWING": {"all": 3, "buy": 1}, "LONG": {"all": 2, "buy": 0}}}
    text = Daily.compose_kr_early(plan, datetime(2026, 11, 4, 7, 50, tzinfo=KST))
    assert "진입 가능 후보 5종목: 스윙 3(매수 구간 1), 장기 2(매수 구간 0)." in text and "07:50 KST" in text and "수량은 계산하지 않았습니다" in text
    d, calls, sent = job(tmp_path, None, terminal=FakeTerminal())       # no order_plan at all: the run goes on, one summary as before
    res = d.run()
    assert calls.count("TELEGRAM") == 1 and res["status"] == "DONE" and "kr_early" not in d.state()
    d2, calls2, sent2 = job(tmp_path / "b", {"status": "NO_SCAN"})
    d2.run()
    assert calls2.count("TELEGRAM") == 1


def test_a_long_plan_shows_eight_rows_and_says_how_many_more():
    orders = [{"ticker": f"{k:06d}", "name": f"종목{k}", "style": "SWING", "shares": 1, "limit": 10_005.0, "limit_order": 10_000.0} for k in range(11)]
    text = Daily.compose_kr_early({"status": "REAL", "session": "2026-11-03", "candidates": 20, "orders": orders}, datetime(2026, 11, 4, 8, 5, tzinfo=KST))
    assert text.count("· 종목") == 8 and "· 외 3종목은 화면의 주문 계획에서" in text and "내 계좌 기준 주문 계획 11종목 (진입 후보 20종목)" in text


def test_the_early_message_is_wired_after_both_tries_of_the_korean_step():
    src = (ROOT / "terminal" / "automation.py").read_text(encoding="utf-8")
    assert src.count('if name == "QSF_KR":\n                self._kr_early(st, steps)') == 1 and src.count('if name == "QSF_KR":\n                    self._kr_early(st, steps)') == 1
    assert automation.STEP_NAMES and list(automation.STEP_NAMES).index("QSF_KR") < list(automation.STEP_NAMES).index("NEWS_KR")
