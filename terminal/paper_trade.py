"""A paper account the user keeps by hand: pick a stock, record a buy and a sell at their own prices, and read what came out after
the broker's fees.

It is the portfolio journal's own machinery (append-only, hash-chained, replayed on every write) on a separate file, so a paper
trade can never mix with the real account.  The one thing added is the fee: a buy or a sell without a typed fee gets the broker's
published fee for that amount, stored on the record with its parts, so a later change of the fee schedule never rewrites a past
trade.  No order is sent anywhere and no price is assumed: the price is the one the user typed.

Not the automatic paper book (``terminal/qsf/paper_book.py``), which follows the program's own plan without the user.
"""
import math
from datetime import date
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from terminal import portfolio as pf
from terminal.qsf import config

FILE = Path("data") / "terminal" / "paper_journal.jsonl"
KINDS = ("DEPOSIT", "WITHDRAW", "BUY", "SELL", "VOID")
START_HINT = {"KR": 10_000_000.0, "US": 10_000.0}        # the amount the screen offers for the first paper deposit
US_FREE_UNDER = 10.0            # Toss: no commission on a US order of 10 dollars or less
SEC_MIN = 0.01                  # Toss: the SEC fee on a sale is at least one cent
NOTE = "가상의 계좌입니다. 주문을 보내지 않으며 실제 포트폴리오 기록과 섞이지 않습니다. 가격은 직접 입력한 값이고, 그 가격에 실제로 체결된다는 뜻이 아닙니다. 투자 자문이 아닙니다."


def toss_fee(market: str, value: float, side: str) -> Dict[str, Any]:
    """The broker's published fee for one fill of ``value``, by part.  Rates are ``config.COSTS`` (checked ``config.COSTS_CHECKED``);
    the rounding is the schedule's own: Korean amounts drop anything under one won, the US commission anything under one cent."""
    c = config.COSTS[market]
    sell = side == "SELL"
    if market == "KR":
        commission = float(math.floor(value * c["commission_bps"] / 1e4 + 1e-9))
        tax = float(math.floor(value * c["sell_tax_bps"] / 1e4 + 1e-9)) if sell else 0.0
        exchange = 0.0
    else:
        commission = 0.0 if value <= US_FREE_UNDER else math.floor(value * c["commission_bps"] / 1e4 * 100 + 1e-9) / 100
        tax = 0.0
        exchange = max(round(value * c.get("sell_fee_bps", 0.0) / 1e4, 2), SEC_MIN) if sell else 0.0
    return {"commission": commission, "tax": tax, "exchange_fee": exchange, "total": round(commission + tax + exchange, 2), "auto": True}


def prepare(raw: Dict[str, Any], today: date, clean_ticker: Callable[[str], str]) -> Dict[str, Any]:
    """One typed entry, checked and ready for the journal.  A buy or sell with an empty fee box gets the broker's fee."""
    raw = dict(raw or {})
    kind = str(raw.get("kind", "")).upper()
    if kind not in KINDS:
        raise pf.JournalError("모의 매매에서는 매수, 매도, 모의 자금 넣기·빼기만 기록합니다.")
    market = pf.market_of(str(raw.get("ticker") or "").strip().upper()) if raw.get("ticker") else str(raw.get("market") or "US").upper()
    raw["market"] = market
    parts = None
    if kind in ("BUY", "SELL") and raw.get("fee") in (None, ""):
        qty, price = pf._pos(raw.get("qty"), "수량"), pf._pos(raw.get("price"), "가격")
        parts = toss_fee(market, qty * price, kind)
        raw["fee"] = parts["total"]
    entry = pf.normalize(raw, today, clean_ticker)
    if kind in ("BUY", "SELL"):
        entry["fee_auto"] = parts is not None
        if parts:
            entry["fee_parts"] = {k: parts[k] for k in ("commission", "tax", "exchange_fee")}
            entry["fee_checked"] = config.COSTS_CHECKED
    return entry


def closed_rows(recs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Every sale with what it cost and what it left: the buy side's share of fees, the sale's own fees, and the result net of both.
    The net figure is the journal's own realized profit; this only shows its parts."""
    pos: Dict[str, Dict[str, Any]] = {}
    out = []
    for r in pf.effective(recs):
        if r["kind"] == "BUY":
            p = pos.setdefault(r["ticker"], {"qty": 0.0, "paid": 0.0, "fee": 0.0, "opened": r["date"]})
            p["qty"] += r["qty"]
            p["paid"] += r["qty"] * r["price"]
            p["fee"] += r["fee"]
        elif r["kind"] == "SELL" and r["ticker"] in pos:
            p = pos[r["ticker"]]
            share = min(1.0, r["qty"] / p["qty"])
            paid, fee_buy = p["paid"] * share, p["fee"] * share
            proceeds = r["qty"] * r["price"]
            net = proceeds - paid - fee_buy - r["fee"]
            out.append({"id": r["id"], "date": r["date"], "ticker": r["ticker"], "qty": r["qty"], "buy_price": paid / r["qty"], "price": r["price"], "paid": paid, "proceeds": proceeds,
                        "gross": proceeds - paid, "fee_buy": fee_buy, "fee_sell": r["fee"], "fees": fee_buy + r["fee"], "net": net,
                        "net_pct": net / (paid + fee_buy) * 100 if paid + fee_buy > 0 else None, "received": proceeds - r["fee"],
                        "opened": p["opened"], "hold_days": (date.fromisoformat(r["date"]) - date.fromisoformat(p["opened"])).days, "note": r.get("note")})
            p["qty"] -= r["qty"]
            p["paid"] -= paid
            p["fee"] -= fee_buy
            if p["qty"] <= pf.EPS:
                del pos[r["ticker"]]
    return out


def view(all_recs: List[Dict[str, Any]], integrity: Dict[str, Any], market: str, quote: Callable[[List[str]], Dict[str, Dict[str, Any]]],
         name: Callable[[str], Optional[str]] = lambda t: None, today: Optional[date] = None) -> Dict[str, Any]:
    """The paper account of one market.  ``quote`` gives the newest close of the held tickers; a holding without one leaves the
    account's value empty, never understated."""
    recs = pf.for_market(all_recs, market)
    head = {"market": market, "currency": "KRW" if market == "KR" else "USD", "note": NOTE, "start_hint": START_HINT[market], "today": today.isoformat() if today else None,
            "fee_basis": config.COSTS[market]["basis"].split(" + 스프레드")[0] + " (슬리피지는 넣지 않습니다. 가격은 입력한 값 그대로입니다)", "fees_checked": config.COSTS_CHECKED}
    try:
        state = pf.replay(recs)
    except pf.JournalError as exc:
        return {"status": "BROKEN", **head, "integrity": {"status": "BROKEN", "reason": str(exc)}}
    if integrity.get("status") != "OK":
        return {"status": "BROKEN", **head, "integrity": integrity}
    held = sorted(state["positions"])
    quotes = quote(held) if held else {}
    positions, value, missing = [], 0.0, False
    for t in held:
        p, q = state["positions"][t], quotes.get(t) or {}
        close = q.get("close")
        v = p["qty"] * close if close is not None else None
        missing = missing or v is None
        value += v or 0.0
        positions.append({"ticker": t, "name": name(t), "qty": p["qty"], "avg": p["avg"], "cost": p["cost"], "close": close, "date": q.get("date"), "value": v,
                          "unrealized": v - p["cost"] if v is not None else None, "unrealized_pct": (v / p["cost"] - 1) * 100 if v is not None and p["cost"] else None,
                          "opened": p["opened"], "exit_fee": toss_fee(market, v, "SELL")["total"] if v is not None else None})
    closed = closed_rows(recs)
    for c in closed:
        c["name"] = name(c["ticker"])
    net_in = state["deposits"] - state["withdrawals"]
    equity = None if missing else state["cash"] + value
    wins = [c for c in closed if c["net"] > 0]
    pcts = [c["net_pct"] for c in closed if c["net_pct"] is not None]
    gone = pf.voided_ids(recs)
    journal = [{**{k: r.get(k) for k in ("id", "seq", "kind", "date", "ticker", "qty", "price", "fee", "fee_auto", "fee_parts", "amount", "note", "ref")}, "voided": r["id"] in gone,
                "name": name(r["ticker"]) if r.get("ticker") else None} for r in sorted(recs, key=lambda r: (r.get("date") or r["recorded_at"][:10], r["seq"]), reverse=True)]
    return {"status": "REAL", **head, "integrity": integrity, "cash": state["cash"], "net_deposits": net_in, "held_value": None if missing else value, "equity": equity,
            "total_pnl": equity - net_in if equity is not None else None, "return_pct": (equity / net_in - 1) * 100 if equity is not None and net_in > 0 else None,
            "realized": state["realized"], "fees": state["fees"], "positions": positions, "closed": closed[::-1],
            "stats": {"count": len(closed), "wins": len(wins), "win_rate_pct": len(wins) / len(closed) * 100 if closed else None, "net": sum(c["net"] for c in closed),
                      "gross": sum(c["gross"] for c in closed), "fees": sum(c["fees"] for c in closed), "mean_net_pct": sum(pcts) / len(pcts) if pcts else None},
            "journal": journal, "records": len(journal)}
