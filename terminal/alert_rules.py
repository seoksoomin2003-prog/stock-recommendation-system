"""User alert rules: conditions the user sets on prices, score bands and earnings dates, checked on daily closes.

The rules live in ``data/terminal/alerts.json``; every alert that was actually delivered is appended to
``data/terminal/alerts_log.jsonl``.  Checking is pure: ``evaluate`` returns the alerts and each rule's next state, and the
state is written only after the message went out (``Store.commit``), so an alert lost to a failed send is raised again.

Only final daily closes are read (a delayed intraday bar is never a trigger).  A value that is missing is reported as
missing, never treated as a crossing.  Score bands are the live QSF output as recorded by the scan: a band change is a
reading to look at, not a trade instruction.
"""
from utils import fcntl_port as fcntl
import json
import uuid
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

TYPES = {
    "PRICE_ABOVE": "종가가 가격 이상",
    "PRICE_BELOW": "종가가 가격 이하",
    "MOVE": "하루 등락폭이 % 이상",
    "BAND_CHANGE": "QSF 점수 구간 변경",
    "EARNINGS_SOON": "실적 발표 임박",
}
ONE_SHOT = ("PRICE_ABOVE", "PRICE_BELOW")          # fires once, then waits until the user re-arms it
STRATEGIES = {"SWING": "스윙", "LONG_TERM": "장기"}
MAX_RULES = 200
BAND_LEVEL = {"BUY_CANDIDATE": "info", "HOLD_WATCH": "info", "WEAK_REDUCE": "warn", "SELL_AVOID": "warn"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def validate(rule: Dict[str, Any], market_of) -> Dict[str, Any]:
    """A clean rule from user input, or ValueError with a code the UI can show."""
    kind = str(rule.get("type") or "").upper()
    if kind not in TYPES:
        raise ValueError("BAD_TYPE")
    ticker = (str(rule.get("ticker") or "").strip().upper()) or None
    market = str(rule.get("market") or "US").upper()
    if market not in ("US", "KR"):
        raise ValueError("BAD_MARKET")
    if ticker:
        market = market_of(ticker)
    out = {"id": uuid.uuid4().hex[:10], "type": kind, "ticker": ticker, "market": market, "status": "ACTIVE", "created_at": _now(), "seen": {}}
    if kind in ONE_SHOT:
        if not ticker:
            raise ValueError("TICKER_REQUIRED")
        v = rule.get("value")
        if not isinstance(v, (int, float)) or isinstance(v, bool) or not v > 0:
            raise ValueError("BAD_VALUE")
        out["value"] = float(v)
    elif kind == "MOVE":
        v = rule.get("value")
        if not isinstance(v, (int, float)) or isinstance(v, bool) or not 0 < v <= 50:
            raise ValueError("BAD_VALUE")
        out["value"] = float(v)
    elif kind == "EARNINGS_SOON":
        v = rule.get("value")
        if not isinstance(v, int) or isinstance(v, bool) or not 1 <= v <= 30:
            raise ValueError("BAD_VALUE")
        out["value"] = v
    elif kind == "BAND_CHANGE":
        s = str(rule.get("strategy") or "SWING").upper()
        if s not in STRATEGIES:
            raise ValueError("BAD_STRATEGY")
        out["strategy"] = s
    return out


def describe(r: Dict[str, Any]) -> str:
    who = r["ticker"] or f"{'한국' if r['market'] == 'KR' else '미국'} 보유·관심 종목"
    if r["type"] == "PRICE_ABOVE":
        return f"{who} 종가 ≥ {_num(r['value'], r['market'])}"
    if r["type"] == "PRICE_BELOW":
        return f"{who} 종가 ≤ {_num(r['value'], r['market'])}"
    if r["type"] == "MOVE":
        return f"{who} 하루 등락 ±{r['value']:g}% 이상"
    if r["type"] == "EARNINGS_SOON":
        return f"{who} 실적 발표 {r['value']}일 전"
    return f"{who} {STRATEGIES[r['strategy']]} 점수 구간 변경"


def _num(v: float, market: str) -> str:
    return f"{v:,.0f}원" if market == "KR" else f"${v:,.2f}"


def evaluate(rules: List[Dict[str, Any]], ctx: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Dict[str, Dict[str, Any]], List[Dict[str, Any]]]:
    """Check every active rule against ``ctx``.

    ``ctx``: ``bars`` {ticker: {date, close, prev_close}} (final closes only; absent = no price), ``watched`` {market: [tickers]},
    ``bands`` {market: {"session", "by_ticker": {ticker: {strategy: {band, band_label, score}}}}}, ``earnings`` {ticker: [iso dates]},
    ``today`` iso date.  Returns (alerts, next state per rule id, notes on what could not be checked).
    """
    alerts, state, notes = [], {}, []
    today = date.fromisoformat(ctx["today"])
    for r in rules:
        if r.get("status") != "ACTIVE":
            continue
        tickers = [r["ticker"]] if r["ticker"] else list((ctx.get("watched") or {}).get(r["market"]) or [])
        seen = dict(r.get("seen") or {})
        nxt: Dict[str, Any] = {"seen": seen}
        name = describe(r)
        for t in tickers:
            if r["type"] in ONE_SHOT or r["type"] == "MOVE":
                b = (ctx.get("bars") or {}).get(t)
                if not b or not isinstance(b.get("close"), (int, float)):
                    notes.append({"rule_id": r["id"], "ticker": t, "reason": "NO_PRICE"})
                    continue
                c = b["close"]
                if r["type"] in ONE_SHOT:
                    hit = c >= r["value"] if r["type"] == "PRICE_ABOVE" else c <= r["value"]
                    if hit:
                        word = "이상" if r["type"] == "PRICE_ABOVE" else "이하"
                        alerts.append(_alert(r, t, "info", f"{t}: {b['date']} 종가 {_num(c, r['market'])}, 설정한 {_num(r['value'], r['market'])} {word}입니다."))
                        nxt.update(status="TRIGGERED", triggered_at=b["date"])
                    continue
                p = b.get("prev_close")
                if not isinstance(p, (int, float)) or p <= 0:
                    notes.append({"rule_id": r["id"], "ticker": t, "reason": "NO_PREVIOUS_CLOSE"})
                    continue
                ch = (c / p - 1) * 100
                if abs(ch) >= r["value"] and seen.get(t) != b["date"]:
                    alerts.append(_alert(r, t, "warn", f"{t}: {b['date']} 하루 {ch:+.1f}% (기준 ±{r['value']:g}%)."))
                    seen[t] = b["date"]
            elif r["type"] == "EARNINGS_SOON":
                days = (ctx.get("earnings") or {}).get(t)
                if days is None:
                    notes.append({"rule_id": r["id"], "ticker": t, "reason": "NO_EARNINGS_DATE"})
                    continue
                nd = next((d for d in sorted(days) if d >= ctx["today"]), None)
                if not nd:
                    continue
                left = (date.fromisoformat(nd) - today).days
                if left <= r["value"] and seen.get(t) != nd:
                    alerts.append(_alert(r, t, "info", f"{t}: 실적 발표 예정일 {nd} ({left}일 남음, Yahoo 일정은 회사 확정 전 추정치일 수 있음)."))
                    seen[t] = nd
            else:
                book = ((ctx.get("bands") or {}).get(r["market"]) or {})
                cur = ((book.get("by_ticker") or {}).get(t) or {}).get(r["strategy"])
                if not cur or not cur.get("band"):
                    notes.append({"rule_id": r["id"], "ticker": t, "reason": "NOT_SCANNED"})
                    continue
                old = seen.get(t)
                if old and old.get("band") != cur["band"]:
                    score = cur.get("score")
                    alerts.append(_alert(r, t, BAND_LEVEL.get(cur["band"], "info"),
                                         f"{t}: {STRATEGIES[r['strategy']]} 점수 구간 {old.get('label') or old['band']} → {cur.get('band_label') or cur['band']}"
                                         + (f" (점수 {score:.1f}, 스캔 {book.get('session')})" if isinstance(score, (int, float)) else "") + "."))
                seen[t] = {"band": cur["band"], "label": cur.get("band_label"), "session": book.get("session")}
        nxt["name"] = name
        state[r["id"]] = nxt
    return alerts, state, notes


def _alert(r: Dict[str, Any], ticker: str, level: str, text: str) -> Dict[str, Any]:
    return {"level": level, "code": f"RULE_{r['type']}", "ticker": ticker, "rule_id": r["id"], "market": r["market"], "text": text}


class Store:
    def __init__(self, folder: Path):
        self.folder = Path(folder)
        self.file = self.folder / "alerts.json"
        self.log_file = self.folder / "alerts_log.jsonl"

    @contextmanager
    def _lock(self):
        self.folder.mkdir(parents=True, exist_ok=True)
        with open(self.folder / ".alerts.lock", "w") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            yield

    def rules(self) -> List[Dict[str, Any]]:
        try:
            return json.loads(self.file.read_text(encoding="utf-8"))["rules"]
        except (OSError, ValueError, KeyError):
            return []

    def _write(self, rules: List[Dict[str, Any]]) -> None:
        tmp = self.file.with_suffix(".tmp")
        tmp.write_text(json.dumps({"rules": rules}, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.file)

    def add(self, rule: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock():
            rules = self.rules()
            if len(rules) >= MAX_RULES:
                raise ValueError("TOO_MANY_RULES")
            same = next((x for x in rules if x["status"] == "ACTIVE" and all(x.get(k) == rule.get(k) for k in ("type", "ticker", "market", "value", "strategy"))), None)
            if same:
                return same
            rules.append(rule)
            self._write(rules)
            return rule

    def remove(self, rule_id: str) -> bool:
        with self._lock():
            rules = self.rules()
            keep = [x for x in rules if x["id"] != rule_id]
            if len(keep) == len(rules):
                return False
            self._write(keep)
            return True

    def rearm(self, rule_id: str) -> bool:
        with self._lock():
            rules = self.rules()
            for x in rules:
                if x["id"] == rule_id and x["status"] == "TRIGGERED":
                    x["status"], x["triggered_at"] = "ACTIVE", None
                    self._write(rules)
                    return True
            return False

    def commit(self, state: Dict[str, Dict[str, Any]], delivered: List[Dict[str, Any]], at: Optional[str] = None) -> None:
        """After a send succeeded: store each rule's next state (rules removed meanwhile stay removed) and log the alerts."""
        with self._lock():
            rules = self.rules()
            for x in rules:
                s = state.get(x["id"])
                if not s or x["status"] != "ACTIVE":
                    continue
                x["seen"] = s["seen"]
                if s.get("status"):
                    x["status"], x["triggered_at"] = s["status"], s.get("triggered_at")
            self._write(rules)
            if delivered:
                stamp = at or _now()
                with open(self.log_file, "a", encoding="utf-8") as fh:
                    for a in delivered:
                        fh.write(json.dumps({"at": stamp, **a}, ensure_ascii=False) + "\n")

    def log(self, limit: int = 100) -> List[Dict[str, Any]]:
        try:
            lines = self.log_file.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        out = []
        for line in reversed(lines):
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
            if len(out) >= limit:
                break
        return out
