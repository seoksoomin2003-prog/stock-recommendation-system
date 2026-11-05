"""TERMINAL-2 portfolio core: append-only, hash-chained trade journal and pure portfolio maths.

No orders are ever placed.  Holdings are derived only from what the user records.
Moving-average cost; realized P&L = (sell price - average cost) x qty - fee.
Missing prices are None (never 0); totals that depend on a missing price are flagged.
"""
import hashlib
import json
import math
import os
import re
import threading
import uuid
from bisect import bisect_left, bisect_right
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

KINDS = ("DEPOSIT", "WITHDRAW", "BUY", "SELL", "DIVIDEND", "FEE", "PLAN", "STYLE", "VOID")
STYLES = ("LONG", "SWING")
STYLE_KO = {"LONG": "장기", "SWING": "스윙"}
MARKETS = ("US", "KR")
KR_TICKER = re.compile(r"^[0-9][0-9A-Z]{5}$")      # 005930, 0035S0; a US ticker never has this shape


def market_of(ticker: str) -> str:
    return "KR" if KR_TICKER.match(ticker or "") else "US"


def for_market(recs: List[Dict[str, Any]], market: str) -> List[Dict[str, Any]]:
    """One journal, two accounts: dollars and won never mix.  A record without a market field is US."""
    return [r for r in recs if r.get("market", "US") == market]
GENESIS = "0" * 64
EPS = 1e-9
# risk_per_trade_pct and max_position_pct apply until a position is tagged.  Values chosen by the user on 2026-11-05.
DEFAULT_SETTINGS = {"risk_per_trade_pct": 1.0, "max_position_pct": 20.0, "max_sector_pct": 40.0,
                    "near_stop_pct": 3.0, "risk_long_pct": 2.0, "max_position_long_pct": 25.0,
                    "risk_swing_pct": 1.0, "max_position_swing_pct": 10.0, "target_long_pct": 70.0,
                    "style_drift_pct": 10.0, "stop_atr_long": 5.0, "stop_atr_swing": 2.0,
                    "risk_long_kr_pct": 1.0, "max_position_long_kr_pct": 20.0, "risk_swing_kr_pct": 0.5,
                    "max_position_swing_kr_pct": 10.0, "target_long_kr_pct": 70.0}
SETTING_BOUNDS = {"risk_per_trade_pct": (0.05, 10.0), "max_position_pct": (1.0, 100.0),
                  "max_sector_pct": (5.0, 100.0), "near_stop_pct": (0.5, 20.0),
                  "risk_long_pct": (0.05, 10.0), "max_position_long_pct": (1.0, 100.0),
                  "risk_swing_pct": (0.05, 10.0), "max_position_swing_pct": (1.0, 100.0),
                  "target_long_pct": (0.0, 100.0), "style_drift_pct": (1.0, 50.0),
                  "stop_atr_long": (0.5, 20.0), "stop_atr_swing": (0.5, 20.0),
                  "risk_long_kr_pct": (0.05, 10.0), "max_position_long_kr_pct": (1.0, 100.0),
                  "risk_swing_kr_pct": (0.05, 10.0), "max_position_swing_kr_pct": (1.0, 100.0),
                  "target_long_kr_pct": (0.0, 100.0)}


def limits_for(style: Optional[str], st: Dict[str, float], market: str = "US") -> Dict[str, float]:
    """Settings with the risk and weight limits of one style and market; an untagged position keeps the general ones."""
    if style not in STYLES:
        return dict(st)
    s, kr = style.lower(), "_kr" if market == "KR" else ""
    return {**st, "risk_per_trade_pct": st[f"risk_{s}{kr}_pct"], "max_position_pct": st[f"max_position_{s}{kr}_pct"]}


def _price(v: float, market: str) -> str:
    return f"{v:,.0f}원" if market == "KR" else f"{v:,.2f}"


def _style(v) -> Optional[str]:
    if v in (None, ""):
        return None
    s = str(v).upper()
    if s not in STYLES:
        raise JournalError("구분은 장기 또는 스윙이어야 합니다.")
    return s


class JournalError(ValueError):
    """Rejected entry; the message is a Korean, user-facing reason."""


def _pos(v, name) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        raise JournalError(f"{name} 값이 숫자가 아닙니다.")
    if not math.isfinite(f) or f <= 0:
        raise JournalError(f"{name} 값은 0보다 커야 합니다.")
    return f


def _opt_pos(v, name) -> Optional[float]:
    return None if v in (None, "") else _pos(v, name)


def _hash(rec: Dict[str, Any]) -> str:
    body = {k: v for k, v in rec.items() if k != "hash"}
    return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def normalize(raw: Dict[str, Any], today: date, clean_ticker) -> Dict[str, Any]:
    """Validate one user entry (shape only; account consistency is checked by replay)."""
    kind = str(raw.get("kind", "")).upper()
    if kind not in KINDS:
        raise JournalError("기록 종류가 올바르지 않습니다.")
    e: Dict[str, Any] = {"kind": kind}
    market = str(raw.get("market") or "US").upper()
    if market not in MARKETS:
        raise JournalError("시장 값이 올바르지 않습니다.")
    if kind != "VOID":
        try:
            d = date.fromisoformat(str(raw.get("date", "")))
        except ValueError:
            raise JournalError("날짜 형식은 YYYY-MM-DD 입니다.")
        if d > today:
            raise JournalError("미래 날짜는 기록할 수 없습니다.")
        e["date"] = d.isoformat()
    if kind in ("BUY", "SELL", "DIVIDEND", "PLAN", "STYLE"):
        try:
            e["ticker"] = clean_ticker(raw.get("ticker", ""))
        except ValueError:
            raise JournalError("종목 코드 형식이 올바르지 않습니다.")
        market = market_of(e["ticker"])
    if kind in ("BUY", "SELL"):
        e["qty"] = _pos(raw.get("qty"), "수량")
        e["price"] = _pos(raw.get("price"), "가격")
        fee = raw.get("fee") or 0
        try:
            e["fee"] = float(fee)
        except (TypeError, ValueError):
            raise JournalError("수수료 값이 숫자가 아닙니다.")
        if not math.isfinite(e["fee"]) or e["fee"] < 0:
            raise JournalError("수수료는 0 이상이어야 합니다.")
    if kind in ("DEPOSIT", "WITHDRAW", "DIVIDEND", "FEE"):
        e["amount"] = _pos(raw.get("amount"), "금액")
    if kind == "PLAN":
        e["stop"] = _opt_pos(raw.get("stop"), "손절가")
        e["target"] = _opt_pos(raw.get("target"), "목표가")
        if e["stop"] and e["target"] and e["target"] <= e["stop"]:
            raise JournalError("목표가는 손절가보다 높아야 합니다.")
    if kind == "STYLE":
        e["style"] = _style(raw.get("style"))
        if not e["style"]:
            raise JournalError("변경할 구분을 선택하세요.")
    if kind == "BUY":
        if _style(raw.get("style")):
            e["style"] = _style(raw.get("style"))
        e["stop"] = _opt_pos(raw.get("stop"), "손절가")
        e["target"] = _opt_pos(raw.get("target"), "목표가")
        if e["stop"] and e["stop"] >= e["price"]:
            raise JournalError("손절가는 매수가보다 낮아야 합니다.")
    if kind == "VOID":
        ref = str(raw.get("ref", ""))
        if not ref:
            raise JournalError("취소할 기록을 지정하세요.")
        e["ref"] = ref
    if market == "KR" and kind != "VOID":
        e["market"] = "KR"
    note = str(raw.get("note") or "").strip()
    if note:
        e["note"] = note[:500]
    return e


# ----------------------------------------------------------------------------- journal file
class Journal:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = threading.Lock()

    def read(self) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """(records, integrity).  Integrity is OK / BROKEN (with the first bad line)."""
        recs, prev = [], GENESIS
        if not self.path.exists():
            return [], {"status": "OK", "records": 0}
        for n, line in enumerate(self.path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except ValueError:
                return recs, {"status": "BROKEN", "line": n, "reason": "JSON 형식 오류"}
            if r.get("prev_hash") != prev or _hash(r) != r.get("hash"):
                return recs, {"status": "BROKEN", "line": n, "reason": "해시 체인 불일치"}
            recs.append(r)
            prev = r["hash"]
        return recs, {"status": "OK", "records": len(recs)}

    def append(self, entry: Dict[str, Any], now: datetime) -> Dict[str, Any]:
        """Validate against a full replay, then append atomically (one line, fsync)."""
        with self._lock:
            recs, integ = self.read()
            if integ["status"] != "OK":
                raise JournalError("거래 기록 파일의 무결성 오류로 새 기록을 추가할 수 없습니다.")
            if entry["kind"] == "VOID":
                target = next((r for r in recs if r["id"] == entry["ref"]), None)
                if not target:
                    raise JournalError("취소할 기록을 찾을 수 없습니다.")
                if target["kind"] == "VOID" or entry["ref"] in voided_ids(recs):
                    raise JournalError("이미 취소된 기록이거나 취소 기록입니다.")
                if target.get("market"):
                    entry = {**entry, "market": target["market"]}
            rec = {**entry, "id": uuid.uuid4().hex[:12], "seq": len(recs) + 1,
                   "recorded_at": now.astimezone(timezone.utc).isoformat(),
                   "prev_hash": recs[-1]["hash"] if recs else GENESIS}
            for market in MARKETS:                     # raises JournalError if an account becomes invalid
                replay(for_market(recs + [rec], market))
            rec["hash"] = _hash(rec)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")
                f.flush()
                os.fsync(f.fileno())
            return rec


def voided_ids(recs: List[Dict[str, Any]]) -> set:
    return {r["ref"] for r in recs if r["kind"] == "VOID"}


def effective(recs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Non-voided, non-VOID entries in account order (date, then recording sequence)."""
    gone = voided_ids(recs)
    return sorted((r for r in recs if r["kind"] != "VOID" and r["id"] not in gone),
                  key=lambda r: (r["date"], r["seq"]))


# ----------------------------------------------------------------------------- replay
def replay(recs: List[Dict[str, Any]], until: Optional[str] = None) -> Dict[str, Any]:
    """Account state after applying entries (optionally up to and including date ``until``)."""
    cash, pos, plans = 0.0, {}, {}
    realized, dividends, fees, deposits, withdrawals = 0.0, 0.0, 0.0, 0.0, 0.0
    closed, flows = [], []
    for r in effective(recs):
        if until and r["date"] > until:
            break
        k = r["kind"]
        if k == "DEPOSIT":
            cash += r["amount"]; deposits += r["amount"]; flows.append((r["date"], r["amount"]))
        elif k == "WITHDRAW":
            cash -= r["amount"]; withdrawals += r["amount"]; flows.append((r["date"], -r["amount"]))
        elif k == "FEE":
            cash -= r["amount"]; fees += r["amount"]
        elif k == "DIVIDEND":
            cash += r["amount"]; dividends += r["amount"]
            if r["ticker"] in pos:
                pos[r["ticker"]]["dividends"] += r["amount"]
        elif k == "BUY":
            cost = r["qty"] * r["price"] + r["fee"]
            cash -= cost; fees += r["fee"]
            p = pos.setdefault(r["ticker"], {"qty": 0.0, "cost": 0.0, "opened": r["date"], "dividends": 0.0,
                                             "realized": 0.0, "style": None, "style_since": r["date"]})
            if r.get("style"):
                if p["style"] and p["style"] != r["style"]:
                    raise JournalError(f"{r['ticker']}는 {STYLE_KO[p['style']]}으로 보유 중입니다. 한 종목은 한 구분으로만 보유하므로 구분 변경을 먼저 기록하세요.")
                p["style"] = r["style"]
            p["qty"] += r["qty"]; p["cost"] += cost
            if r.get("stop") or r.get("target"):
                plans[r["ticker"]] = {"stop": r.get("stop"), "target": r.get("target"), "date": r["date"]}
        elif k == "SELL":
            p = pos.get(r["ticker"])
            if not p or r["qty"] > p["qty"] + EPS:
                raise JournalError(f"{r['date']} {r['ticker']} 매도 수량이 보유 수량보다 많습니다.")
            avg = p["cost"] / p["qty"]
            pnl = (r["price"] - avg) * r["qty"] - r["fee"]
            cash += r["qty"] * r["price"] - r["fee"]; fees += r["fee"]; realized += pnl; p["realized"] += pnl
            closed.append({"date": r["date"], "ticker": r["ticker"], "qty": r["qty"], "price": r["price"],
                           "avg_cost": avg, "pnl": pnl, "return_pct": (r["price"] / avg - 1) * 100,
                           "opened": p["opened"], "style": p["style"], "hold_days": (date.fromisoformat(r["date"])
                                                                - date.fromisoformat(p["opened"])).days})
            p["qty"] -= r["qty"]; p["cost"] -= avg * r["qty"]
            if p["qty"] <= EPS:
                del pos[r["ticker"]]
                plans.pop(r["ticker"], None)
        elif k == "STYLE":
            if r["ticker"] not in pos:
                raise JournalError(f"{r['ticker']}는 {r['date']} 기준 보유 중이 아니어서 구분을 바꿀 수 없습니다.")
            if pos[r["ticker"]]["style"] != r["style"]:
                pos[r["ticker"]]["style"] = r["style"]
                pos[r["ticker"]]["style_since"] = r["date"]    # a swing's time limit counts from here
        elif k == "PLAN":
            if r["ticker"] not in pos:
                raise JournalError(f"{r['ticker']}는 {r['date']} 기준 보유 중이 아니어서 손절·목표를 설정할 수 없습니다.")
            plans[r["ticker"]] = {"stop": r.get("stop"), "target": r.get("target"), "date": r["date"]}
        if cash < -0.005:
            raise JournalError(f"{r['date']} 기준 현금이 부족합니다 (현금 {cash:,.2f}). 입금을 먼저 기록하세요.")
    for p in pos.values():
        p["avg"] = p["cost"] / p["qty"]
    return {"cash": cash, "positions": pos, "plans": plans, "realized": realized, "dividends": dividends,
            "fees": fees, "deposits": deposits, "withdrawals": withdrawals, "closed": closed, "flows": flows}


# ----------------------------------------------------------------------------- valuation
def valuation(state: Dict[str, Any], quotes: Dict[str, Dict[str, Any]], sectors: Dict[str, Optional[str]],
              settings: Dict[str, float], market: str = "US") -> Dict[str, Any]:
    rows, mv, missing = [], 0.0, []
    for t, p in sorted(state["positions"].items()):
        q = quotes.get(t) or {}
        close = q.get("close")
        val = p["qty"] * close if close is not None else None
        prev = close / (1 + q["change_pct"] / 100) if close is not None and q.get("change_pct") is not None else None
        plan = state["plans"].get(t) or {}
        row = {"ticker": t, "qty": p["qty"], "avg_cost": p["avg"], "cost": p["cost"], "close": close,
               "date": q.get("date"), "status": q.get("status", "UNAVAILABLE"), "intraday": bool(q.get("intraday")),
               "value": val, "unrealized": val - p["cost"] if val is not None else None,
               "unrealized_pct": (close / p["avg"] - 1) * 100 if close is not None else None,
               "day_pnl": (close - prev) * p["qty"] if prev is not None else None,
               "change_pct": q.get("change_pct"), "opened": p["opened"], "realized": p["realized"],
               "dividends": p["dividends"], "sector": sectors.get(t), "stop": plan.get("stop"),
               "target": plan.get("target"), "style": p.get("style"), "style_since": p.get("style_since")}
        if val is None:
            missing.append(t)
        else:
            mv += val
        rows.append(row)
    equity = state["cash"] + mv
    complete = not missing
    for r in rows:
        r["weight_pct"] = r["value"] / equity * 100 if r["value"] is not None and equity > 0 else None
        s, c = r["stop"], r["close"]
        r["stop_distance_pct"] = (c / s - 1) * 100 if s and c is not None else None
        r["risk_to_stop"] = max(0.0, (c - s) * r["qty"]) if s and c is not None else None
    sector_w: Dict[str, float] = {}
    for r in rows:
        if r["weight_pct"] is not None:
            key = r["sector"] or "미분류"
            sector_w[key] = sector_w.get(key, 0.0) + r["weight_pct"]
    risk_total = sum(r["risk_to_stop"] for r in rows if r["risk_to_stop"] is not None)
    summary = {"cash": state["cash"], "market_value": mv if complete else None,
               "market_value_known": mv, "equity": equity if complete else None, "equity_known": equity,
               "complete": complete, "missing_prices": missing,
               "cash_pct": state["cash"] / equity * 100 if complete and equity > 0 else None,
               "unrealized": sum(r["unrealized"] for r in rows if r["unrealized"] is not None),
               "day_pnl": sum(r["day_pnl"] for r in rows if r["day_pnl"] is not None),
               "realized": state["realized"], "dividends": state["dividends"], "fees": state["fees"],
               "net_deposits": state["deposits"] - state["withdrawals"],
               "risk_to_stops": risk_total,
               "risk_to_stops_pct": risk_total / equity * 100 if complete and equity > 0 else None,
               "unprotected": [r["ticker"] for r in rows if not r["stop"]]}
    summary["total_pnl"] = (equity - summary["net_deposits"]) if complete else None
    styles = style_summary(rows, equity if complete else None, settings, market)
    summary["styles"] = styles
    return {"summary": summary, "holdings": rows, "sectors": dict(sorted(sector_w.items(), key=lambda x: -x[1])),
            "alerts": alerts(rows, sector_w, settings, styles, market)}


def style_summary(rows: List[Dict[str, Any]], equity: Optional[float], st: Dict[str, float], market: str = "US") -> Dict[str, Any]:
    """Share of the tagged stock value in each style.  Cash is left out, so an account still mostly in cash is not 'off target'."""
    known = {s: [r for r in rows if r.get("style") == s] for s in STYLES}
    complete = all(r["value"] is not None for r in rows)
    tagged = sum(r["value"] or 0.0 for s in STYLES for r in known[s])
    target = st["target_long_kr_pct"] if market == "KR" else st["target_long_pct"]
    out: Dict[str, Any] = {"target_long_pct": target, "target_swing_pct": 100.0 - target, "complete": complete,
                           "untagged": [r["ticker"] for r in rows if not r.get("style")]}
    for s in STYLES:
        value = sum(r["value"] or 0.0 for r in known[s])
        cost = sum(r["cost"] for r in known[s] if r["value"] is not None)
        out[s] = {"count": len(known[s]), "value": value if complete else None, "unrealized": sum(r["unrealized"] or 0.0 for r in known[s]),
                  "unrealized_pct": (value / cost - 1) * 100 if cost > 0 else None,
                  "share_pct": value / tagged * 100 if complete and tagged > 0 else None,
                  "weight_pct": value / equity * 100 if complete and equity and equity > 0 else None}
    return out


def alerts(rows: List[Dict[str, Any]], sector_w: Dict[str, float], st: Dict[str, float], styles: Optional[Dict[str, Any]] = None, market: str = "US") -> List[Dict[str, Any]]:
    out = []
    share = ((styles or {}).get("LONG") or {}).get("share_pct")
    target = (styles or {}).get("target_long_pct")
    if share is not None and abs(share - target) > st["style_drift_pct"]:
        out.append({"level": "warn", "code": "STYLE_DRIFT", "ticker": None,
                    "text": f"주식 평가액 중 장기 비중 {share:.0f}%가 목표 {target:.0f}%에서 {st['style_drift_pct']:.0f}%p 넘게 벗어났습니다."})
    for r in rows:
        t, c, s, g = r["ticker"], r["close"], r["stop"], r["target"]
        if c is None:
            out.append({"level": "warn", "code": "NO_PRICE", "ticker": t, "text": f"{t}: 시세가 없어 평가할 수 없습니다."})
            continue
        if s and c <= s:
            out.append({"level": "bad", "code": "STOP_HIT", "ticker": t,
                        "text": f"{t}: 종가 {_price(c, market)}{'이' if market == 'KR' else '가'} 손절가 {_price(s, market)} 이하입니다."})
        elif s and (c / s - 1) * 100 <= st["near_stop_pct"]:
            out.append({"level": "warn", "code": "NEAR_STOP", "ticker": t,
                        "text": f"{t}: 손절가까지 {(c / s - 1) * 100:.1f}% 남았습니다."})
        if g and c >= g:
            out.append({"level": "info", "code": "TARGET_HIT", "ticker": t,
                        "text": f"{t}: 종가 {_price(c, market)}{'이' if market == 'KR' else '가'} 목표가 {_price(g, market)}에 도달했습니다."})
        if not s:
            out.append({"level": "warn", "code": "NO_STOP", "ticker": t, "text": f"{t}: 손절가가 설정되지 않았습니다."})
        limit = limits_for(r.get("style"), st, market)["max_position_pct"]
        if r["weight_pct"] is not None and r["weight_pct"] > limit:
            out.append({"level": "warn", "code": "OVERWEIGHT", "ticker": t,
                        "text": f"{t}: 비중 {r['weight_pct']:.1f}%가 종목 한도 {limit:.0f}%를 넘습니다."})
        if not r.get("style"):
            out.append({"level": "warn", "code": "NO_STYLE", "ticker": t, "text": f"{t}: 장기·스윙 구분이 없어 보유 판정을 계산하지 않습니다."})
    for sec, w in sector_w.items():
        if w > st["max_sector_pct"]:
            out.append({"level": "warn", "code": "SECTOR_OVER", "ticker": None,
                        "text": f"섹터 '{sec}' 비중 {w:.1f}%가 섹터 한도 {st['max_sector_pct']:.0f}%를 넘습니다."})
    order = {"bad": 0, "warn": 1, "info": 2}
    return sorted(out, key=lambda a: order[a["level"]])


def trade_stats(closed: List[Dict[str, Any]]) -> Dict[str, Any]:
    n = len(closed)
    wins = [c["pnl"] for c in closed if c["pnl"] > 0]
    losses = [c["pnl"] for c in closed if c["pnl"] <= 0]
    return {"count": n, "wins": len(wins), "losses": len(losses),
            "win_rate_pct": len(wins) / n * 100 if n else None,
            "avg_win": sum(wins) / len(wins) if wins else None,
            "avg_loss": sum(losses) / len(losses) if losses else None,
            "payoff": (sum(wins) / len(wins)) / abs(sum(losses) / len(losses))
            if wins and losses and sum(losses) != 0 else None,
            "total": sum(c["pnl"] for c in closed),
            "small_sample": n < 20}


# ----------------------------------------------------------------------------- equity curve
def equity_curve(recs: List[Dict[str, Any]], history: Dict[str, List[Dict[str, Any]]],
                 bench: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Daily account value on benchmark trading days since the first entry, time-weighted return
    (cash flows removed) and the benchmark's return over the same days.  A held ticker without a price on
    or before a day makes that day's value unknown (None), never a 0 contribution."""
    eff = effective(recs)
    if not eff or not bench:
        return {"points": [], "twr_pct": None, "bench_pct": None}
    first = eff[0]["date"]
    days = [b["date"] for b in bench if b["date"] >= first]
    if not days:
        return {"points": [], "twr_pct": None, "bench_pct": None}
    bclose = {b["date"]: b["close"] for b in bench}
    series = {t: sorted((b["date"], b["close"]) for b in bars) for t, bars in history.items()}
    sdates = {t: [x[0] for x in v] for t, v in series.items()}

    def px(t, d):
        i = bisect_right(sdates.get(t, []), d)
        return series[t][i - 1][1] if i else None

    flows_by_day: Dict[str, float] = {}
    for fd, a in replay(recs)["flows"]:              # a weekend/holiday flow counts on the next trading day
        i = bisect_left(days, fd)
        if i < len(days):
            flows_by_day[days[i]] = flows_by_day.get(days[i], 0.0) + a
    points, twr, prev_v, b0 = [], 1.0, None, None
    for d in days:
        st = replay(recs, until=d)
        v = st["cash"]
        for t, p in st["positions"].items():
            c = px(t, d)
            if c is None:
                v = None
                break
            v += p["qty"] * c
        f = flows_by_day.get(d, 0.0)
        if v is not None and prev_v and prev_v > 0:
            twr *= (v - f) / prev_v
        if v is not None and b0 is None and v > 0:
            b0 = bclose[d]
        points.append({"date": d, "value": v, "twr_pct": (twr - 1) * 100 if b0 else None,
                       "bench_pct": (bclose[d] / b0 - 1) * 100 if b0 else None})
        if v is not None:
            prev_v = v
    last = next((p for p in reversed(points) if p["value"] is not None), None)
    return {"points": points, "twr_pct": last["twr_pct"] if last else None,
            "bench_pct": last["bench_pct"] if last else None, "start": days[0]}


# ----------------------------------------------------------------------------- sizing
def atr(bars: List[Dict[str, Any]], n: int = 14) -> Optional[float]:
    trs = []
    for prev, b in zip(bars, bars[1:]):
        if None in (b.get("high"), b.get("low"), prev.get("close")):
            continue
        trs.append(max(b["high"] - b["low"], abs(b["high"] - prev["close"]), abs(b["low"] - prev["close"])))
    return sum(trs[-n:]) / n if len(trs) >= n else None


def position_size(equity: float, cash: float, entry: float, stop: float, st: Dict[str, float]) -> Dict[str, Any]:
    if not (entry > 0 and stop > 0):
        raise JournalError("진입가와 손절가는 0보다 커야 합니다.")
    if stop >= entry:
        raise JournalError("손절가는 진입가보다 낮아야 합니다 (매수 기준).")
    if not equity or equity <= 0:
        raise JournalError("계좌 평가액이 없습니다. '계좌 금액'을 입력하거나 포트폴리오에 입금·거래를 먼저 기록하세요.")
    risk_amt = equity * st["risk_per_trade_pct"] / 100
    per_share = entry - stop
    limits = {"RISK": risk_amt / per_share, "WEIGHT": equity * st["max_position_pct"] / 100 / entry,
              "CASH": max(cash, 0.0) / entry}
    binding = min(limits, key=limits.get)
    shares = math.floor(limits[binding] + EPS)
    return {"shares": shares, "binding": binding, "limits": {k: math.floor(v + EPS) for k, v in limits.items()},
            "notional": shares * entry, "weight_pct": shares * entry / equity * 100,
            "risk_amount": shares * per_share, "risk_pct": shares * per_share / equity * 100,
            "risk_budget": risk_amt, "stop_distance_pct": per_share / entry * 100, "entry": entry, "stop": stop}


def clean_settings(raw: Dict[str, Any], current: Dict[str, float]) -> Dict[str, float]:
    out = dict(current)
    for k, (lo, hi) in SETTING_BOUNDS.items():
        if k in raw and raw[k] not in (None, ""):
            try:
                v = float(raw[k])
            except (TypeError, ValueError):
                raise JournalError("설정 값이 숫자가 아닙니다.")
            if not (lo <= v <= hi):
                raise JournalError(f"설정 값이 허용 범위({lo}~{hi})를 벗어났습니다.")
            out[k] = v
    return out
