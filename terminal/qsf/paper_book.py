"""The paper book: a made-up account that follows the program's own entry reading mechanically.  Rules: reports/PAPER_BOOK_RULES.md.

One account per market (won and dollars never mix), started with a fixed made-up amount.  Each session the book fills yesterday's
plan at the open, carries out the exits decided at yesterday's close, decides today's exits at the close, and writes the plan for
the next open (``order_plan``).  Every session is written once and chained by hash; a session builds on the state the session before
it wrote, never on a replay.  No order is sent anywhere, no real holding or journal record is read or written, and nothing here feeds
the live score.  The figures are a reference before any verdict: one account's path is not evidence about the score.
"""
import copy
import fcntl
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from terminal.qsf import config, kr_forward as kf, order_plan
from terminal.qsf.ledger import Ledger

RULES = "reports/PAPER_BOOK_RULES.md"
VERSION = "PB-2"            # PB-2 (2026-11-16): the plan reads the market state; on an adverse US day a new order is at most half its usual size
FOLDERS = {"KR": Path("research_data") / "paper_book_kr", "US": Path("research_data") / "paper_book_us"}
START_CASH = {"KR": 10_000_000.0, "US": 10_000.0}       # made-up amounts chosen by the user on 2026-11-12; not the real account
CURRENCY = {"KR": "원", "US": "달러"}
REFERENCE = {"KR": "005930", "US": "SPY"}                # whose bars give the market's trading days
FIRST = "2026-11-12"            # the first session that makes a plan; its fills come at the next session's open
SWING_TIME_STOP = config.SWING["time_stop"]             # sessions held after which a swing position is closed at the close
LONG_EXIT_SCORE = 40.0          # a long position leaves when its long-term score falls under this ('매도·회피 후보')
HALT_SESSIONS = 10              # sessions without a price after which a position is closed at its last close
RESTATED = 0.005                # a stored close this far from the price file's close for the same day means the file was restated
MIN_ROWS = 200                  # fewer scored stocks than this is a partial day: no plan is made from it
EXIT_LABELS = {"STOP": "손절", "TARGET": "목표 도달", "TIME": "시간 청산(30거래일)", "SCORE": "장기 점수 40점 미만", "RANK": "장기 점수 순위가 보유 기준 밖", "NO_PRICE": "가격 없음(거래정지·상장폐지)"}
UNFILLED_LABELS = {"NO_OPEN": "시가 없음", "ABOVE_LIMIT": "시가가 지정가보다 높음", "BELOW_STOP": "시가가 손절가 이하", "NO_CASH": "현금 부족"}


class NotReady(Exception):
    """A session that cannot be written yet and is asked again at the next run."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_state(market: str) -> Dict[str, Any]:
    return {"cash": START_CASH[market], "positions": {}, "pending_exits": [], "plan": [], "realized": 0.0, "fees": 0.0, "slippage": 0.0, "closed": 0, "wins": 0}


class Bars:
    """Day bars by ticker from a loader, read once per ticker.  ``at`` is a day's bar, ``close_on`` the file's close for a day."""

    def __init__(self, loader: Callable[[str], Sequence[Dict[str, Any]]]):
        self._loader, self._memo = loader, {}

    def _of(self, ticker: str) -> Dict[str, Dict[str, Any]]:
        if ticker not in self._memo:
            self._memo[ticker] = {b["date"]: b for b in (self._loader(ticker) or []) if b.get("date")}
        return self._memo[ticker]

    def at(self, ticker: str, day: str) -> Optional[Dict[str, Any]]:
        b = self._of(ticker).get(day)
        return b if b and b.get("close") else None

    def days(self, ticker: str) -> List[str]:
        return sorted(self._of(ticker))


def _sell(market: str, pos: Dict[str, Any], ref_price: float, day: str, reason: str, state: Dict[str, Any]) -> Dict[str, Any]:
    """Close a whole position at ``ref_price`` less the slippage estimate and the sale's fees; books the result into the state."""
    value = pos["qty"] * ref_price
    slip = order_plan.slippage_bps(market, value, pos.get("adv_value"), (pos.get("atr") or 0) / ref_price if ref_price else None)
    price = ref_price * (1 - slip["total"] / 1e4)
    proceeds = pos["qty"] * price
    fee = order_plan.fees(market, proceeds, "SELL")
    pnl = proceeds - fee - pos["cost"]
    state["cash"] += proceeds - fee
    state["realized"] += pnl
    state["fees"] += fee
    state["slippage"] += pos["qty"] * (ref_price - price)
    state["closed"] += 1
    state["wins"] += pnl > 0
    return {"ticker": pos["ticker"], "name": pos.get("name"), "style": pos["style"], "reason": reason, "label": EXIT_LABELS[reason], "session": day, "qty": pos["qty"],
            "entry": pos["entry"], "entry_session": pos["entry_session"], "exit": price, "ref_price": ref_price, "sessions": pos["sessions"], "fee": fee,
            "slippage_bps": slip["total"], "pnl": pnl, "net_pct": pnl / pos["cost"] * 100 if pos["cost"] else None}


def _stays(p: Dict[str, Any], snap: Optional[Dict[str, Any]], rules: Dict[str, Any]) -> Optional[str]:
    """The turnover rules' reading of a swing position at or past the time stop: the event code when it stays, None when it is sold.
    No swing score that day is not a low score: the position waits for the next session.  The cap sells whatever the score."""
    if p["sessions"] >= rules["hold_cap"]:
        return None
    if snap is None:
        return "HOLD_NO_SCORE"
    return "HOLD_EXTENDED" if snap["score"] >= rules["hold_score"] and snap.get("actionability") == "ACTIONABLE" else None


def step(prev: Optional[Dict[str, Any]], day: str, market: str, bars: Bars, snaps: Optional[List[Dict[str, Any]]], info: Optional[Dict[str, Dict[str, Any]]] = None,
         rules: Optional[Dict[str, Any]] = None, version: Optional[str] = None) -> Dict[str, Any]:
    """One session of the book.  ``prev``: the state the session before wrote (None on the first).  ``snaps``: the ledger snapshots
    of ``day`` (None or too few: no new plan, exits by price still run).  Reads no price after ``day``.
    ``rules``: the turnover rules (reports/QSF_TURNOVER_RULES_PROTOCOL.md) when they are in force: ``reentry_wait`` sessions without a
    new order after a stop, and a swing position past the time stop staying while its score is ``hold_score`` or more, up to
    ``hold_cap`` sessions.  The rank rules (reports/QSF_RANK_RULES_PROTOCOL.md) are two more keys: ``entry_top``, the share of the
    day's scores an entry candidate must be inside, and ``long_exit_top``, the looser share a long position must stay inside (it
    replaces the under-40 rule).  Each rule acts only when its keys are there.  None: the book as it always was, with not one key
    more in its record."""
    rules = rules or None
    waits, holds = bool(rules and rules.get("reentry_wait")), bool(rules and rules.get("hold_score") is not None)
    entry_top, exit_top = (rules or {}).get("entry_top"), (rules or {}).get("long_exit_top")
    breakout = bool((rules or {}).get("breakout_entry"))        # the entry comparison book's rule (reports/QSF_ENTRY_RULES_PROTOCOL.md)
    st = copy.deepcopy(prev) if prev else new_state(market)
    pos: Dict[str, Dict[str, Any]] = st["positions"]
    exits, fills, unfilled, adjusted = [], [], [], []
    events: List[Dict[str, Any]] = []
    wait: Dict[str, int] = dict(st.get("cooldown") or {}) if waits else {}       # ticker -> closes left without a new order
    # 1. a restated price file: the stored levels move with it, so a split is never read as a fall
    for t, p in pos.items():
        then = bars.at(t, p["last_bar"]) if p.get("last_bar") else None
        if then and p.get("last_close") and abs(then["close"] / p["last_close"] - 1) > RESTATED:
            g = then["close"] / p["last_close"]
            for k in ("entry", "stop", "target", "last_close", "atr"):
                if p.get(k) is not None:
                    p[k] *= g
            p["qty"] /= g
            adjusted.append({"ticker": t, "factor": g})
    # 2. the open: exits decided at the last close, then the plan made at the last close
    waiting = []
    for e in st["pending_exits"]:
        b, p = bars.at(e["ticker"], day), pos.get(e["ticker"])
        if p is None:
            continue
        if not b or not b.get("open"):
            waiting.append(e)
            continue
        exits.append(_sell(market, p, float(b["open"]), day, e["reason"], st))
        del pos[e["ticker"]]
        if waits and e["reason"] == "STOP":
            wait[e["ticker"]] = int(rules["reentry_wait"])
    st["pending_exits"] = waiting
    commission = config.COSTS[market]["commission_bps"] / 1e4
    for o in st["plan"]:
        b = bars.at(o["ticker"], day)
        reason = None
        if o["ticker"] in pos:
            continue
        if not b or not b.get("open"):
            reason = "NO_OPEN"
        elif b["open"] > o["limit"]:
            reason = "ABOVE_LIMIT"
        elif b["open"] <= o["stop"]:
            reason = "BELOW_STOP"
        if reason is None:
            op = float(b["open"])
            slip = order_plan.slippage_bps(market, o["shares"] * op, o.get("adv_value"), o["atr"] / op)
            price = op * (1 + slip["total"] / 1e4)
            shares = min(int(o["shares"]), int(st["cash"] / (price * (1 + commission)) + 1e-9))
            if shares < 1:
                reason = "NO_CASH"
        if reason:
            unfilled.append({"ticker": o["ticker"], "name": o.get("name"), "style": o["style"], "reason": reason, "label": UNFILLED_LABELS[reason], "limit": o["limit"],
                             "open": b.get("open") if b else None})
            continue
        fee = order_plan.fees(market, shares * price, "BUY")
        cost = shares * price + fee
        st["cash"] -= cost
        st["fees"] += fee
        st["slippage"] += shares * (price - op)
        pos[o["ticker"]] = {"ticker": o["ticker"], "name": o.get("name"), "sector": o.get("sector"), "style": o["style"], "qty": float(shares), "entry": price, "entry_session": day,
                            "stop": o["stop"], "target": o.get("target"), "atr": o["atr"], "adv_value": o.get("adv_value"), "score_at_plan": o.get("score"), "cost": cost,
                            "sessions": 0, "missing": 0, "last_close": op, "last_bar": None}
        fills.append({"ticker": o["ticker"], "name": o.get("name"), "style": o["style"], "session": day, "qty": shares, "open": op, "price": price, "fee": fee,
                      "slippage_bps": slip["total"], "planned_shares": o["shares"], "stop": o["stop"], "target": o.get("target")})
    st["plan"] = []
    # 3. the close: marks, then the exits this close decides
    long_score = {s["ticker"]: s["score"] for s in (snaps or []) if s.get("strategy") == "LONG_TERM" and s.get("data_date") == day and s.get("score") is not None}
    swing_snap = {s["ticker"]: s for s in (snaps or []) if s.get("strategy") == "SWING" and s.get("data_date") == day and s.get("score") is not None}
    ahead = order_plan.ahead_share(snaps or [], day) if entry_top is not None or exit_top is not None else {}
    decisions = []
    for t in sorted(pos):
        p, b = pos[t], bars.at(t, day)
        if not b:
            p["missing"] = p.get("missing", 0) + 1
            if p["missing"] >= HALT_SESSIONS:
                exits.append(_sell(market, p, p["last_close"], day, "NO_PRICE", st))
                del pos[t]
            continue
        close = float(b["close"])
        p.update(sessions=p["sessions"] + 1, last_close=close, last_bar=day, missing=0)
        if close <= p["stop"]:
            decisions.append({"ticker": t, "reason": "STOP"})
        elif p["style"] == "SWING" and p.get("target") and close >= p["target"]:
            decisions.append({"ticker": t, "reason": "TARGET"})
        elif p["style"] == "SWING" and p["sessions"] >= SWING_TIME_STOP:
            kept = _stays(p, swing_snap.get(t), rules) if holds else None
            if kept:
                events.append({"rule": kept, "ticker": t, "sessions": p["sessions"], "score": (swing_snap.get(t) or {}).get("score")})
            else:
                exits.append(_sell(market, p, close, day, "TIME", st))
                del pos[t]
        elif p["style"] == "LONG" and exit_top is not None:           # the rank rule replaces the under-40 rule; no long score today: not judged
            # A partial day ranks a stock among the few that were scored, so it says nothing about the top half.  The plan below has
            # the same guard.  Added 2026-11-17 by the user's decision, before the comparison book's first record.
            share = ahead.get((t, "LONG_TERM")) if len(long_score) >= MIN_ROWS else None
            if share is not None and share >= exit_top:
                decisions.append({"ticker": t, "reason": "RANK"})
                events.append({"rule": "RANK_EXIT", "ticker": t, "ahead_pct": round(share * 100, 1), "score": long_score.get(t)})
        elif p["style"] == "LONG" and t in long_score and long_score[t] < LONG_EXIT_SCORE:
            decisions.append({"ticker": t, "reason": "SCORE"})
    st["pending_exits"] += [d for d in decisions if d["ticker"] not in {e["ticker"] for e in st["pending_exits"]}]
    held_value = sum(p["qty"] * p["last_close"] for p in pos.values())
    equity = st["cash"] + held_value
    # 4. the plan for the next open, from today's scores and the account as it stands at this close
    scored = [s for s in (snaps or []) if s.get("data_date") == day and s.get("score") is not None]
    plan: Dict[str, Any] = {"orders": [], "skipped_counts": {}, "candidates": 0, "scored": False}
    if len({s["ticker"] for s in scored}) >= MIN_ROWS:
        cands = order_plan.candidates(scored, day, info, breakout=breakout)
        account = {"equity": equity, "cash": st["cash"], "positions": {t: {"style": p["style"], "value": p["qty"] * p["last_close"], "sector": p.get("sector")} for t, p in pos.items()}}
        mstate, outside = order_plan.state_for_plan(scored, market, day), order_plan.outside_top(cands, ahead, entry_top) if entry_top is not None else None
        built = order_plan.build(cands, account, market, state=mstate, blocked=wait if waits else None, outside=outside)
        if outside:             # what the rank rule cost today: orders the plan would have made without it (not every candidate it passed over)
            plain = order_plan.build(cands, account, market, state=mstate, blocked=wait if waits else None)
            events += [{"rule": "RANK_ENTRY", "ticker": o["ticker"], "style": o["style"], "score": o["score"]} for o in plain["orders"] if (o["ticker"], o["style"]) in outside]
        events += [{"rule": "REENTRY_WAIT", "ticker": s["ticker"], "style": s["style"], "left": wait[s["ticker"]]} for s in built["skipped"] if s["code"] == "REENTRY_WAIT"]
        if breakout:            # the orders this rule alone made today
            via = {(c["ticker"], c["style"]) for c in cands if c.get("via") == "BREAKOUT"}
            events += [{"rule": "BREAKOUT_ENTRY", "ticker": o["ticker"], "style": o["style"], "score": o["score"]} for o in built["orders"] if (o["ticker"], o["style"]) in via]
        plan = {"market_state": built["market_state"], "size_factor": built["size_factor"], "orders": built["orders"], "skipped_counts": built["skipped_counts"], "candidates": built["candidates"], "scored": True, "sleeve": built["sleeve"],
                "skipped_first": built["skipped"][:20]}
        st["plan"] = built["orders"]
    if waits:                   # a wait set at this open has now covered one close
        st["cooldown"] = {t: n - 1 for t, n in wait.items() if n > 1}
    bench = bars.at(REFERENCE[market], day) if market == "US" else None
    return {"session": day, "market": market, "rules": version or VERSION, "exits": exits, "fills": fills, "unfilled": unfilled, "adjusted": adjusted, "decisions": decisions, "plan": plan,
            "state": st, "equity": equity, "cash": st["cash"], "held_value": held_value, "positions": len(pos),
            "benchmark_close": float(bench["close"]) if bench else None, "rows": plan["orders"], **({"rule_events": events} if rules else {})}


# ---------------------------------------------------------------------- the daily record
def _session_snaps(led: Ledger, market: str, session: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for r in led._live_rows():
        if r["market"] == market and r["session"] == session:
            out += led._load(r)
    return out


def _last_doc(base: Path, market: str, store: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    where = store or FOLDERS[market]
    index = kf.read_index(base, where)
    return kf._read_day(Path(base) / where, index[-1]["session"]) if index else None


def record(base: Path, market: str, loader: Callable[[str], Sequence[Dict[str, Any]]], info: Callable[[], Dict[str, Dict[str, Any]]] = lambda: {},
           bench: Optional[Callable[[], Sequence[Dict[str, Any]]]] = None, now: Callable[[], datetime] = _utcnow, first: str = FIRST,
           store: Optional[Path] = None, rules: Optional[Dict[str, Any]] = None, version: Optional[str] = None,
           seed: Optional[Callable[[], Optional[Dict[str, Any]]]] = None) -> Dict[str, Any]:
    """Write every trading day from ``first`` up to the newest ledger session, in order.  One writer at a time: a second run that
    starts while this one works waits at the lock and then finds the days already written.
    ``store``, ``rules``, ``version``: another book under other rules (``turnover_book``).  ``seed``: the record whose state that
    book's first session builds on, in place of a new account."""
    where = store or FOLDERS[market]
    led = Ledger(Path(base))
    if led.verify()["status"] != "OK":
        return {"status": "FAILED", "reason": "LEDGER_BROKEN"}
    folder = Path(base) / where
    folder.mkdir(parents=True, exist_ok=True)
    with open(folder / "book.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if kf.verify(base, where)["status"] != "OK":
            return {"status": "FAILED", "reason": "BOOK_CHAIN_BROKEN"}
        scored = sorted({r["session"] for r in led._live_rows() if r["market"] == market and r["session"] >= first})
        if not scored:
            return {"status": "OK", "market": market, "written": [], "last": None, "sessions": len(kf.read_index(base, where))}
        bars = Bars(loader)
        done = [r["session"] for r in kf.read_index(base, where)]
        after = done[-1] if done else ""
        days = [d for d in bars.days(REFERENCE[market]) if first <= d <= scored[-1] and d > after]
        if not days and scored[-1] > after:
            return {"status": "WAITING", "market": market, "written": [], "waiting": {"session": scored[-1], "reason": "NO_PRICES_FOR_DAY"}, "last": after or None, "sessions": len(done)}
        at, wrote, extra = now(), [], None
        bench_close = {b["date"]: b.get("close") for b in (bench() if bench else [])} if days else {}
        for day in days:
            prev = _last_doc(base, market, where) or (seed() if seed else None)

            def scorer(b: Path, d: str) -> Dict[str, Any]:
                nonlocal extra
                extra = extra if extra is not None else info()
                doc = step(prev["state"] if prev else None, d, market, bars, _session_snaps(led, market, d) if d in scored else None, extra, rules=rules, version=version)
                if doc["benchmark_close"] is None and bench_close.get(d):
                    doc["benchmark_close"] = float(bench_close[d])
                return doc
            if kf.write_record(base, day, at, day != days[-1], store=where, scorer=scorer):
                wrote.append(day)
        return {"status": "OK", "market": market, "written": wrote, "last": (wrote or done or [None])[-1], "sessions": len(done) + len(wrote)}


# ---------------------------------------------------------------------- what the screen shows
def _drawdown(values: Sequence[float]) -> Optional[float]:
    peak, worst = None, 0.0
    for v in values:
        peak = v if peak is None or v > peak else peak
        worst = min(worst, v / peak - 1)
    return worst if values else None


def status(base: Path, market: str) -> Dict[str, Any]:
    """The account as the newest session left it, the plan for the next open, and what has happened so far.  Read only."""
    folder = Path(base) / FOLDERS[market]
    index = kf.read_index(base, FOLDERS[market])
    head = {"market": market, "rules": RULES, "version": VERSION, "start_cash": START_CASH[market], "currency": CURRENCY[market], "first": FIRST,
            "note": "판정 전 참고입니다. 가상의 금액으로 프로그램의 '지금 진입 가능' 안내를 기계적으로 따른 결과이고, 한 계좌의 경로는 점수의 근거가 아닙니다. 주문을 보내지 않으며 투자 자문이 아닙니다.",
            "exit_labels": EXIT_LABELS, "unfilled_labels": UNFILLED_LABELS, "binding_labels": order_plan.BINDING, "skip_labels": order_plan.REASONS,
            "cost_basis": config.COSTS[market]["basis"], "limit_atr": order_plan.LIMIT_ATR, "max_participation_pct": order_plan.MAX_PARTICIPATION * 100,
            "swing_time_stop": SWING_TIME_STOP, "long_exit_score": LONG_EXIT_SCORE}
    if not index:
        return {"status": "NO_RECORD", **head}
    docs = [kf._read_day(folder, r["session"]) for r in index]
    last = docs[-1]
    st = last["state"]
    equity = [d["equity"] for d in docs]
    bench = [(d["session"], d["benchmark_close"]) for d in docs if d.get("benchmark_close")]
    exits = [e for d in docs for e in d["exits"]]
    fills = [f for d in docs for f in d["fills"]]
    unfilled = [u for d in docs for u in d["unfilled"]]
    count = lambda rows, key: {k: sum(1 for r in rows if r[key] == k) for k in sorted({r[key] for r in rows})}      # noqa: E731
    positions = [{**{k: p.get(k) for k in ("ticker", "name", "sector", "style", "qty", "entry", "entry_session", "stop", "target", "sessions", "last_close", "last_bar")},
                  "value": p["qty"] * p["last_close"], "weight_pct": p["qty"] * p["last_close"] / last["equity"] * 100 if last["equity"] else None,
                  "unrealized_pct": (p["qty"] * p["last_close"] / p["cost"] - 1) * 100 if p.get("cost") else None,
                  "pending_exit": next((e["reason"] for e in st["pending_exits"] if e["ticker"] == p["ticker"]), None)} for p in sorted(st["positions"].values(), key=lambda p: p["ticker"])]
    net = [e["net_pct"] for e in exits if e.get("net_pct") is not None]
    return {"status": "REAL", **head, "version": last.get("rules") or VERSION, "sessions": len(docs), "started": docs[0]["session"], "last": last["session"], "integrity": kf.verify(base, FOLDERS[market])["status"],
            "equity": last["equity"], "cash": last["cash"], "held_value": last["held_value"], "return_pct": (last["equity"] / START_CASH[market] - 1) * 100,
            "max_drawdown_pct": (_drawdown(equity) or 0.0) * 100, "benchmark_return_pct": (bench[-1][1] / bench[0][1] - 1) * 100 if len(bench) >= 2 else None,
            "benchmark": "SPY" if market == "US" else "코스피", "realized": st["realized"], "fees": st["fees"], "slippage": st["slippage"],
            "closed": st["closed"], "wins": st["wins"], "win_rate_pct": st["wins"] / st["closed"] * 100 if st["closed"] else None, "mean_net_pct": sum(net) / len(net) if net else None,
            "exit_counts": count(exits, "reason"), "unfilled_counts": count(unfilled, "reason"), "fills": len(fills), "positions": positions,
            "plan": {**last["plan"], "for_session_after": last["session"]}, "pending_exits": st["pending_exits"],
            "recent": {"exits": exits[-15:][::-1], "fills": fills[-15:][::-1], "unfilled": unfilled[-10:][::-1]},
            "curve": [{"session": d["session"], "equity": d["equity"], "benchmark_close": d.get("benchmark_close")} for d in docs[-260:]]}
