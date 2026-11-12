"""Paper trades kept by hand: the broker's fee is worked out for each fill, a sale shows what it left after fees, and the paper
journal is a separate file from the real account's.  Offline: fake sources and a tmp base directory."""
import json
from datetime import date
from pathlib import Path

import pytest

from terminal import paper_trade as pt, portfolio as pf
from terminal.services import Terminal, clean_ticker
from tests.test_terminal_1 import AFTER, fake_src
from tests.test_terminal_1 import _loopback_only  # noqa: F401  (autouse: these tests may reach 127.0.0.1 only)

TODAY = date(2026, 11, 4)


def test_the_fee_is_the_brokers_schedule_with_its_own_rounding():
    assert pt.toss_fee("KR", 1_000_000, "BUY") == {"commission": 150.0, "tax": 0.0, "exchange_fee": 0.0, "total": 150.0, "auto": True}
    assert pt.toss_fee("KR", 1_000_000, "SELL")["total"] == 150.0 + 2000.0 and pt.toss_fee("KR", 1_000_000, "SELL")["tax"] == 2000.0
    odd = pt.toss_fee("KR", 12_345, "SELL")                         # 1.85 won of commission and 24.69 won of tax: anything under one won is dropped
    assert (odd["commission"], odd["tax"], odd["total"]) == (1.0, 24.0, 25.0)
    assert pt.toss_fee("US", 1_000, "BUY")["total"] == 1.0 and pt.toss_fee("US", 1_234.56, "BUY")["commission"] == 1.23
    sell = pt.toss_fee("US", 1_000, "SELL")
    assert (sell["commission"], sell["exchange_fee"], sell["total"]) == (1.0, 0.02, 1.02)
    small = pt.toss_fee("US", 10, "SELL")                           # ten dollars or less: no commission; the SEC fee is at least a cent
    assert (small["commission"], small["exchange_fee"], small["total"]) == (0.0, 0.01, 0.01) and pt.toss_fee("US", 10, "BUY")["total"] == 0.0


def test_an_entry_without_a_typed_fee_gets_the_fee_with_its_parts_and_a_typed_fee_is_kept():
    auto = pt.prepare({"kind": "buy", "ticker": "005930", "qty": "10", "price": "70000", "date": "2026-11-03"}, TODAY, clean_ticker)
    assert auto["fee"] == 105.0 and auto["fee_auto"] is True and auto["fee_parts"] == {"commission": 105.0, "tax": 0.0, "exchange_fee": 0.0} and auto["market"] == "KR" and auto["fee_checked"]
    typed = pt.prepare({"kind": "SELL", "ticker": "AAPL", "qty": 3, "price": 200, "fee": "2.5", "date": "2026-11-04"}, TODAY, clean_ticker)
    assert typed["fee"] == 2.5 and typed["fee_auto"] is False and "fee_parts" not in typed and "market" not in typed
    dep = pt.prepare({"kind": "DEPOSIT", "amount": "10000000", "market": "KR", "date": "2026-11-04"}, TODAY, clean_ticker)
    assert dep == {"kind": "DEPOSIT", "date": "2026-11-04", "amount": 10_000_000.0, "market": "KR"}
    for bad in ("DIVIDEND", "PLAN", "STYLE", "FEE", ""):
        with pytest.raises(pf.JournalError, match="모의 매매에서는"):
            pt.prepare({"kind": bad, "ticker": "AAPL", "date": "2026-11-04"}, TODAY, clean_ticker)
    with pytest.raises(pf.JournalError, match="미래 날짜"):
        pt.prepare({"kind": "BUY", "ticker": "AAPL", "qty": 1, "price": 1, "date": "2026-11-05"}, TODAY, clean_ticker)
    with pytest.raises(pf.JournalError):
        pt.prepare({"kind": "BUY", "ticker": "AAPL", "qty": 0, "price": 1, "date": "2026-11-04"}, TODAY, clean_ticker)


def terminal(tmp_path):
    return Terminal(tmp_path, src=fake_src(), now=lambda: AFTER)


def add(t, **raw):
    return t.paper_add({"date": "2026-11-04", **raw})["entry"]


def test_a_round_trip_shows_what_went_in_what_came_out_and_what_the_fees_took(tmp_path):
    t = terminal(tmp_path)
    t._kr_name = lambda ticker: "삼성전자" if ticker == "005930" else None      # no listed-company file in a tmp folder; the lookup would go to the network
    assert t.paper_trades("KR")["records"] == 0 and t.paper_trades("KR")["start_hint"] == 10_000_000.0
    with pytest.raises(ValueError, match="현금이 부족"):            # a buy dated before the money was there
        add(t, kind="BUY", ticker="005930", qty=10, price=70_000, date="2026-11-02")
    add(t, kind="DEPOSIT", amount=10_000_000, market="KR", date="2026-11-02")
    add(t, kind="BUY", ticker="005930", qty=10, price=70_000, date="2026-11-02")
    sold = add(t, kind="SELL", ticker="005930", qty=10, price=77_000, note="목표 도달")
    assert sold["fee"] == 115.0 + 1540.0 and sold["fee_parts"] == {"commission": 115.0, "tax": 1540.0, "exchange_fee": 0.0}
    v = t.paper_trades("KR")
    c = v["closed"][0]
    assert (c["paid"], c["proceeds"], c["gross"], c["fee_buy"], c["fee_sell"], c["fees"], c["net"]) == (700_000.0, 770_000.0, 70_000.0, 105.0, 1655.0, 1760.0, 68_240.0)
    assert c["name"] == "삼성전자" and v["journal"][0]["name"] == "삼성전자"
    assert c["net_pct"] == pytest.approx(68_240 / 700_105 * 100) and c["received"] == 768_345.0 and c["hold_days"] == 2 and c["buy_price"] == 70_000.0 and c["note"] == "목표 도달"
    assert v["cash"] == pytest.approx(10_068_240.0) and v["equity"] == pytest.approx(10_068_240.0) and v["total_pnl"] == pytest.approx(68_240.0) and v["realized"] == pytest.approx(68_240.0)
    assert v["fees"] == pytest.approx(1760.0) and v["positions"] == [] and v["net_deposits"] == 10_000_000.0 and v["return_pct"] == pytest.approx(0.6824)
    assert v["stats"] == {"count": 1, "wins": 1, "win_rate_pct": 100.0, "net": 68_240.0, "gross": 70_000.0, "fees": 1760.0, "mean_net_pct": pytest.approx(68_240 / 700_105 * 100)}
    assert [r["kind"] for r in v["journal"]] == ["SELL", "BUY", "DEPOSIT"] and v["journal"][0]["fee_auto"] is True and v["status"] == "REAL" and "주문을 보내지" in v["note"]
    assert t.paper_trades("US")["records"] == 0                     # the dollar account is its own


def test_a_holding_is_valued_at_the_newest_close_and_a_part_sale_carries_its_share_of_the_buy_fee(tmp_path):
    t = terminal(tmp_path)
    add(t, kind="DEPOSIT", amount=10_000, market="US")
    add(t, kind="BUY", ticker="AAPL", qty=10, price=150)                      # fee 1.50
    v = t.paper_trades("US")
    p = v["positions"][0]
    assert p["avg"] == pytest.approx(150.15) and p["close"] == 159.0 and p["value"] == 1590.0 and p["unrealized"] == pytest.approx(88.5) and p["exit_fee"] == pytest.approx(1.59 + 0.03)
    assert v["equity"] == pytest.approx(10_000 - 1501.5 + 1590.0) and v["total_pnl"] == pytest.approx(88.5) and v["closed"] == []
    add(t, kind="SELL", ticker="AAPL", qty=4, price=160)                      # 640: commission 0.64, SEC fee 0.01
    v = t.paper_trades("US")
    c = v["closed"][0]
    assert c["fee_buy"] == pytest.approx(0.6) and c["fee_sell"] == pytest.approx(0.65) and c["net"] == pytest.approx(640 - 600 - 0.6 - 0.65) and v["positions"][0]["qty"] == 6.0
    assert v["positions"][0]["cost"] == pytest.approx(6 * 150.15) and v["realized"] == pytest.approx(c["net"])


def test_the_account_refuses_what_it_could_not_have_done_and_a_cancelled_record_is_kept_but_not_counted(tmp_path):
    t = terminal(tmp_path)
    with pytest.raises(ValueError, match="현금이 부족"):
        add(t, kind="BUY", ticker="AAPL", qty=1, price=100)
    add(t, kind="DEPOSIT", amount=1_000, market="US")
    buy = add(t, kind="BUY", ticker="AAPL", qty=5, price=100)
    with pytest.raises(ValueError, match="매도 수량이 보유 수량보다"):
        add(t, kind="SELL", ticker="AAPL", qty=6, price=100)
    with pytest.raises(ValueError, match="현금이 부족"):
        add(t, kind="BUY", ticker="MSFT", qty=5, price=100)                   # 499.50 left, the order with its fee needs 500.50
    sell = add(t, kind="SELL", ticker="AAPL", qty=5, price=110)
    t.paper_void(sell["id"])
    v = t.paper_trades("US")
    assert v["closed"] == [] and v["positions"][0]["qty"] == 5.0 and v["records"] == 4 and [r["voided"] for r in v["journal"] if r["kind"] == "SELL"] == [True]
    with pytest.raises(ValueError, match="이미 취소된"):
        t.paper_void(sell["id"])
    assert buy["fee"] == 0.5 and t.paper.read()[1]["status"] == "OK"


def test_paper_trades_never_touch_the_real_account(tmp_path):
    t = terminal(tmp_path)
    add(t, kind="DEPOSIT", amount=10_000, market="US")
    add(t, kind="BUY", ticker="AAPL", qty=10, price=150)
    assert t.journal.read() == ([], {"status": "OK", "records": 0}) and not (tmp_path / "data" / "terminal" / "journal.jsonl").exists()
    assert (tmp_path / pt.FILE).exists() and t.portfolio("US")["journal"] == [] and t.portfolio("US")["summary"]["cash"] == 0
    lines = [json.loads(x) for x in (tmp_path / pt.FILE).read_text(encoding="utf-8").splitlines()]
    assert lines[1]["fee_auto"] is True and lines[1]["prev_hash"] == lines[0]["hash"]


def test_the_fee_preview_records_nothing_and_a_broken_file_is_said_plainly(tmp_path):
    t = terminal(tmp_path)
    got = t.paper_fee({"market": "KR", "side": "sell", "qty": "10", "price": "77000"})
    assert got["total"] == 1655.0 and got["value"] == 770_000.0 and not (tmp_path / pt.FILE).exists()
    with pytest.raises(ValueError):
        t.paper_fee({"market": "KR", "side": "HOLD", "qty": 1, "price": 1})
    add(t, kind="DEPOSIT", amount=1_000, market="US")
    p = tmp_path / pt.FILE
    p.write_text(p.read_text(encoding="utf-8").replace("1000", "9000"), encoding="utf-8")
    assert t.paper_trades("US")["status"] == "BROKEN"
    with pytest.raises(ValueError, match="무결성"):
        add(t, kind="DEPOSIT", amount=1, market="US")


def test_the_tab_the_routes_and_the_backup_are_in_place():
    from terminal import automation
    root = Path(__file__).resolve().parents[1]
    server = (root / "terminal" / "server.py").read_text(encoding="utf-8")
    assert all(f'"{r}"' in server for r in ("/api/paper-trade", "/api/paper-trade/fee", "/api/paper-trade/add", "/api/paper-trade/void"))
    html = (root / "terminal" / "static" / "index.html").read_text(encoding="utf-8")
    assert 'data-tab="paper"' in html and 'id="tab-paper"' in html and html.index("portfolio.js") < html.index("paper.js")
    js = (root / "terminal" / "static" / "paper.js").read_text(encoding="utf-8")
    assert all(w in js for w in ("RENDER.paper = renderPaper", "주문을 보내지 않습니다", "가상의 계좌", "나가는 돈", "들어오는 돈", "순손익", "/api/paper-trade/fee"))
    assert "data/terminal/paper_journal.jsonl" in automation.BACKUP_GLOBS and '"paper"' in (root / "terminal" / "static" / "app.js").read_text(encoding="utf-8")
