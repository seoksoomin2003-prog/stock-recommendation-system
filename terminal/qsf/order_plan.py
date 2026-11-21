"""The order plan: which of today's entry candidates fit the account, in what size, at what limit, and at what expected cost.

No order is sent anywhere.  The plan answers the questions that come up when several candidates appear on one day: who goes first
(score), how much each may take (risk per trade, position weight, style sleeve, sector weight, cash, and a share of the stock's own
traded value), and what never gets a second order (a stock already held or already planned).  Costs are the broker's published fees
(``config.COSTS``); slippage is an ESTIMATE from the order's size against the stock's traded value and is labelled as one.

Pure functions: the same plan serves the paper book (``paper_book``) and the screen's plan for the real account.  Rules:
reports/PAPER_BOOK_RULES.md.
"""
import math
from bisect import bisect_right
from typing import Any, Dict, Iterable, List, Optional

from terminal import portfolio as pf
from terminal.qsf import config, engine

ENTRY_READY = "ENTRY_NOW"
LIMIT_ATR = 0.5                 # a buy is not chased beyond the reference close plus this many ATR
MAX_PARTICIPATION = 0.01        # an order takes at most this share of the stock's 20-session average traded value
MIN_WEIGHT_PCT = 1.0            # an order worth less than this share of the account is not placed: its fees and effort outweigh it
IMPACT_Y = 1.0                  # square-root impact: daily range share x sqrt(order value / traded value) x this
STYLE_OF = {"SWING": "SWING", "LONG_TERM": "LONG"}
STRATEGY_OF = {v: k for k, v in STYLE_OF.items()}
REASONS = {"RANK_OUT": "그날 점수 순위가 진입 기준 밖", "REENTRY_WAIT": "손절 뒤 재진입 대기", "ALREADY_HELD": "이미 보유 중", "ALREADY_PLANNED": "같은 날 이미 계획됨", "NO_STOP": "손절 기준(ATR) 없음", "NO_LIQUIDITY": "거래대금 자료 없음",
           "SLEEVE_FULL": "스타일 비중 한도 도달", "SECTOR_FULL": "섹터 한도 도달", "NO_CASH": "현금 부족", "TOO_SMALL": "주문이 계좌의 1% 미만이거나 한 주도 안 됨"}
BINDING = {"RISK": "거래당 위험 한도", "WEIGHT": "종목 비중 한도", "CASH": "현금", "SLEEVE": "스타일 비중 한도", "SECTOR": "섹터 한도", "LIQUIDITY": "거래대금 대비 주문 크기 한도"}


def slippage_bps(market: str, order_value: float, adv_value: Optional[float], atr_pct: Optional[float]) -> Dict[str, Optional[float]]:
    """One-way slippage estimate in basis points: the assumed spread part plus a square-root impact part that grows with order size.
    ``impact`` is None when the stock's traded value or range is unknown; the total then holds the spread part only."""
    spread = float(config.COSTS[market]["spread_slippage_bps"])
    impact = None
    if adv_value and adv_value > 0 and atr_pct and atr_pct > 0 and order_value > 0:
        impact = 1e4 * IMPACT_Y * atr_pct * math.sqrt(order_value / adv_value)
    return {"spread": spread, "impact": impact, "total": spread + (impact or 0.0)}


def fees(market: str, value: float, side: str) -> float:
    """The published part of one fill: commission, and on a sale the tax and exchange fee."""
    c = config.COSTS[market]
    bps = c["commission_bps"] + ((c["sell_tax_bps"] + c.get("sell_fee_bps", 0.0)) if side == "SELL" else 0.0)
    return value * bps / 1e4


def atr_of(snap: Dict[str, Any]) -> Optional[float]:
    """The ATR behind a snapshot's swing stop (price minus two ATR)."""
    price, stop = snap.get("price"), snap.get("stop")
    if not price or not stop or stop >= price:
        return None
    return (price - stop) / config.SWING["stop_atr"]


def _adv(snap: Dict[str, Any]) -> Optional[float]:
    for f in snap.get("factors") or []:
        if f.get("factor") == "liquidity" and (f.get("raw") or {}).get("adv_value"):
            return float(f["raw"]["adv_value"])
    return None


def session_snaps(led: Any, market: str, session: str) -> List[Dict[str, Any]]:
    """Every ledger snapshot of one market and session; the rest of the ledger is not opened."""
    out: List[Dict[str, Any]] = []
    for r in led._live_rows():
        if r["market"] == market and r["session"] == session:
            out += led._load(r)
    return out


def market_state(snaps: Iterable[Dict[str, Any]], market: str, session: str) -> Optional[Dict[str, Any]]:
    """The session's market state, read from its ledger snapshots: one scan scores every stock against one regime, so the first
    snapshot of the session that carries the regime factors has it.  None: no snapshot of the session carries them."""
    rows = [s for s in snaps if s.get("data_date") == session]
    for want in ("SWING", "LONG_TERM"):
        for s in rows:
            if s.get("strategy") == want and any(f.get("domain") == "REGIME" for f in s.get("factors") or []):
                return {**engine.market_state(s["factors"], market), "session": session}
    return None


def ahead_share(snaps: Iterable[Dict[str, Any]], session: str) -> Dict[Any, float]:
    """{(ticker, strategy): the share of the session's scored stocks of that strategy with a HIGHER score}.  0.0 is the top stock;
    under 0.2 is 'inside the top 20%'.  Ties share a rank.  A stock without a score that session is absent, never last."""
    out: Dict[Any, float] = {}
    rows = [s for s in snaps if s.get("data_date") == session and s.get("score") is not None]
    for strategy in STYLE_OF:
        mine = [(s["ticker"], float(s["score"])) for s in rows if s.get("strategy") == strategy]
        scores = sorted(v for _, v in mine)
        for t, v in mine:
            out[(t, strategy)] = (len(scores) - bisect_right(scores, v)) / len(scores)
    return out


def outside_top(cands: Iterable[Dict[str, Any]], ahead: Dict[Any, float], top: float) -> set:
    """(ticker, style) of the candidates that are not inside the top ``top`` share of their own strategy's scores that session."""
    return {(c["ticker"], c["style"]) for c in cands if ahead.get((c["ticker"], STRATEGY_OF[c["style"]]), 1.0) >= top}


def candidates(snaps: Iterable[Dict[str, Any]], session: str, info: Optional[Dict[str, Dict[str, Any]]] = None, settings: Optional[Dict[str, float]] = None) -> List[Dict[str, Any]]:
    """Ledger snapshots of ``session`` the program itself reads as enterable now: actionable, and entry status ENTRY_NOW.
    The long stop is the user's five ATR; the swing stop and target are the snapshot's own."""
    st = settings or pf.DEFAULT_SETTINGS
    info = info or {}
    out = []
    for s in snaps:
        if s.get("data_date") != session or s.get("actionability") != "ACTIONABLE" or s.get("entry_status") != ENTRY_READY or s.get("score") is None or not s.get("price"):
            continue
        style, atr, price = STYLE_OF.get(s.get("strategy")), atr_of(s), float(s["price"])
        if style is None:
            continue
        stop = None if atr is None else (float(s["stop"]) if style == "SWING" else price - st["stop_atr_long"] * atr)
        extra = info.get(s["ticker"]) or {}
        out.append({"ticker": s["ticker"], "name": extra.get("name"), "sector": extra.get("sector"), "style": style, "score": float(s["score"]), "close": price, "atr": atr,
                    "stop": stop if stop and stop > 0 else None, "target": float(s["target"]) if style == "SWING" and s.get("target") else None, "adv_value": _adv(s), "session": session})
    return sorted(out, key=lambda c: (-c["score"], c["ticker"], c["style"]))


def count_by(cands: List[Dict[str, Any]], buy: float = 70.0) -> Dict[str, Dict[str, int]]:
    """Per style, how many candidates there are and how many of them score inside the buy band.  Display only."""
    out: Dict[str, Dict[str, int]] = {}
    for c in cands:
        row = out.setdefault(c["style"], {"all": 0, "buy": 0})
        row["all"] += 1
        row["buy"] += c["score"] >= buy
    return out


def build(cands: List[Dict[str, Any]], account: Dict[str, Any], market: str, settings: Optional[Dict[str, float]] = None, state: Optional[Dict[str, Any]] = None,
          blocked: Optional[Any] = None, outside: Optional[set] = None) -> Dict[str, Any]:
    """``account``: ``equity``, ``cash``, ``positions`` {ticker: {style, value, sector}}.  Candidates are taken in score order; each
    order reserves cash at its limit price with the buy commission, so a fill at or under the limit never overdraws the account.
    ``state``: the session's market state.  On an adverse day in a market with a size factor (``config.ADVERSE_SIZE_FACTOR``) the risk
    per trade and the weight limit of every new order are multiplied by it; nothing else reads the state.
    ``blocked``: tickers that get no new order (the turnover rules' wait after a stop); None when the rules are not in force.
    ``outside``: (ticker, style) pairs outside the rank rules' entry share (``outside_top``); None when those rules are not in force."""
    st = settings or pf.DEFAULT_SETTINGS
    factor = float((state or {}).get("size_factor") or 1.0)
    equity, cash = float(account.get("equity") or 0.0), float(account.get("cash") or 0.0)
    held = dict(account.get("positions") or {})
    kr = "_kr" if market == "KR" else ""
    long_share = st[f"target_long{kr}_pct"] / 100
    sleeve_cap = {"LONG": equity * long_share, "SWING": equity * (1 - long_share)}
    sleeve = {s: sum(float(p.get("value") or 0.0) for p in held.values() if p.get("style") == s) for s in ("LONG", "SWING")}
    sector: Dict[str, float] = {}
    for p in held.values():
        if p.get("sector"):
            sector[p["sector"]] = sector.get(p["sector"], 0.0) + float(p.get("value") or 0.0)
    orders, skipped, planned = [], [], set()
    commission = config.COSTS[market]["commission_bps"] / 1e4

    def skip(c: Dict[str, Any], code: str) -> None:
        skipped.append({"ticker": c["ticker"], "name": c.get("name"), "style": c["style"], "score": c["score"], "code": code, "reason": REASONS[code]})
    for c in cands:
        t, style, close = c["ticker"], c["style"], c["close"]
        if t in held:
            skip(c, "ALREADY_HELD")
            continue
        if t in planned:
            skip(c, "ALREADY_PLANNED")
            continue
        if outside and (t, style) in outside:       # the rule sets come after: a stock already held is not counted as one they kept out
            skip(c, "RANK_OUT")
            continue
        if blocked and t in blocked:
            skip(c, "REENTRY_WAIT")
            continue
        if not c.get("stop") or not c.get("atr"):
            skip(c, "NO_STOP")
            continue
        if not c.get("adv_value"):
            skip(c, "NO_LIQUIDITY")
            continue
        limit = close + LIMIT_ATR * c["atr"]
        unit = limit * (1 + commission)                     # cash one share reserves
        lim = pf.limits_for(style, st, market)
        if factor != 1.0:
            lim = {**lim, "risk_per_trade_pct": lim["risk_per_trade_pct"] * factor, "max_position_pct": lim["max_position_pct"] * factor}
        size = pf.position_size(equity, cash, close, c["stop"], lim) if equity > 0 else None
        caps = dict(size["limits"]) if size else {"RISK": 0, "WEIGHT": 0, "CASH": 0}
        caps["CASH"] = math.floor(max(cash, 0.0) / unit + pf.EPS)
        caps["SLEEVE"] = math.floor(max(sleeve_cap[style] - sleeve[style], 0.0) / close + pf.EPS)
        if c.get("sector"):
            caps["SECTOR"] = math.floor(max(equity * st["max_sector_pct"] / 100 - sector.get(c["sector"], 0.0), 0.0) / close + pf.EPS)
        caps["LIQUIDITY"] = math.floor(MAX_PARTICIPATION * c["adv_value"] / close + pf.EPS)
        binding = min(caps, key=lambda k: (caps[k], list(BINDING).index(k)))
        shares = caps[binding]
        if shares < 1 or shares * close < equity * MIN_WEIGHT_PCT / 100:
            skip(c, {"CASH": "NO_CASH", "SLEEVE": "SLEEVE_FULL", "SECTOR": "SECTOR_FULL"}.get(binding, "TOO_SMALL"))
            continue
        value = shares * close
        slip = slippage_bps(market, value, c["adv_value"], c["atr"] / close)
        fee_buy, fee_sell = fees(market, value, "BUY"), fees(market, value, "SELL")
        orders.append({"ticker": t, "name": c.get("name"), "sector": c.get("sector"), "style": style, "score": round(c["score"], 2), "session": c.get("session"), "shares": int(shares),
                       "ref_close": close, "limit": limit, "stop": c["stop"], "target": c.get("target"), "atr": c["atr"], "notional": value,
                       "weight_pct": value / equity * 100, "risk_pct": shares * (close - c["stop"]) / equity * 100, "binding": binding, "binding_label": BINDING[binding],
                       "participation_pct": value / c["adv_value"] * 100, "slippage_bps": slip, "fee_buy": fee_buy, "fee_sell": fee_sell,
                       "est_round_trip_pct": (fee_buy + fee_sell) / value * 100 + 2 * slip["total"] / 100, "adv_value": c["adv_value"]})
        cash -= shares * unit
        sleeve[style] += value
        if c.get("sector"):
            sector[c["sector"]] = sector.get(c["sector"], 0.0) + value
        planned.add(t)
    by_code: Dict[str, int] = {}
    for s in skipped:
        by_code[s["code"]] = by_code.get(s["code"], 0) + 1
    shown = None if state is None else {k: state.get(k) for k in ("score_100", "state", "label", "mid", "size_factor", "note", "session", "coverage")}
    return {"market": market, "orders": orders, "skipped": skipped, "skipped_counts": by_code, "candidates": len(cands), "cash_after": cash, "market_state": shown, "size_factor": factor,
            "sleeve": {s: {"value": sleeve[s], "cap": sleeve_cap[s]} for s in sleeve},
            "assumptions": {"limit_atr": LIMIT_ATR, "min_weight_pct": MIN_WEIGHT_PCT, "max_participation_pct": MAX_PARTICIPATION * 100, "commission_bps": config.COSTS[market]["commission_bps"],
                            "sell_bps": config.COSTS[market]["sell_tax_bps"] + config.COSTS[market].get("sell_fee_bps", 0.0), "spread_bps": config.COSTS[market]["spread_slippage_bps"],
                            "cost_basis": config.COSTS[market]["basis"], "fees_checked": config.COSTS_CHECKED,
                            "slippage_note": "슬리피지는 추정입니다: 스프레드 가정값 + 주문 크기에 따른 충격(일간 변동폭 × √(주문금액 ÷ 20일 평균 거래대금))."}}
