"""The turnover rules beside the paper book, and the reading that decides on them.  Rules: reports/QSF_TURNOVER_RULES_PROTOCOL.md.

A second made-up account (TO-1) that forks from the paper book's state and follows the same rules plus two: a stock sold at its stop
is not planned again for 20 sessions, and a swing position at its 30th session stays while its swing score is 55 or more (60 sessions
at most).  Both books are written every session; nothing of the comparison book's value or return is shown before the reading.

At 240 recorded sessions the program reads once, by itself, and decides: ADOPT when the comparison book paid less in costs and its
mean daily return was not below the paper book's, KEEP otherwise.  An ADOPT makes the paper book, the real account's order plan and
the holding reading use the rules from then on.  ``QSF_TURNOVER_RULES`` in ``.env`` (auto / on / off) lets the user overrule it.
"""
import json
import math
import os
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from terminal.qsf import calibrate
from terminal.qsf import kr_forward as kf, paper_book, validate
from utils import durable

PROTOCOL = "reports/QSF_TURNOVER_RULES_PROTOCOL.md"
VERSION = "TO-1"
ADOPTED_VERSION = "PB-3"        # what the paper book writes in its records once the rules are in force
RULES = {"reentry_wait": 20, "hold_score": 55.0, "hold_cap": 60}
FOLDERS = {"KR": Path("research_data") / "turnover_book_kr", "US": Path("research_data") / "turnover_book_us"}
REPORTS = {m: Path("reports") / "qsf" / f"QSF_TURNOVER_{m}.json" for m in ("KR", "US")}
FIRST = "2026-11-16"            # the comparison book's first session; it starts from the paper book's state of the session before
READ_AT = 240                   # recorded sessions at the single reading
LAG = 20
MIN_T = 2.0
ENV = "QSF_TURNOVER_RULES"
MARKET_KO = {"KR": "한국", "US": "미국"}
DECISION_KO = {"ADOPT": "적용 조건 충족(자동 적용 안 함)", "KEEP": "유지"}
RULE_KO = {"REENTRY_WAIT": "재진입을 막은 후보(종목·날)", "HOLD_EXTENDED": "보유 연장(종목·날)", "HOLD_NO_SCORE": "점수가 없어 넘긴 날"}


class NotDue(Exception):
    """The reading's day has not come: fewer than ``READ_AT`` records, or the paper book lacks one of the sessions."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------- which rules are in force
SWITCH_WORDS = {"": "auto", "auto": "auto", "on": "on", "off": "off", "1": "on", "true": "on", "yes": "on", "0": "off", "false": "off", "no": "off"}


def switch_of(env: str) -> Dict[str, Any]:
    """The .env switch as typed: {"mode": auto|on|off, "unknown": the text when it is none of the words}.  A value that is not
    understood means auto, as before, but it is shown as not understood: someone who typed it meant something by it."""
    raw = (os.getenv(env) or "").split("#")[0].strip().strip("'\"").lower()
    return {"mode": SWITCH_WORDS.get(raw, "auto"), "unknown": None if raw in SWITCH_WORDS else raw}


SWITCH_FILE = Path("data") / "qsf" / "turnover_switch.json"          # the screen's button, one entry per market


def stored_switch(base: Path, market: str) -> Optional[str]:
    """What the screen's button was last set to for ``market``: "on", "off" or None (never pressed, or the file cannot be read)."""
    try:
        got = (json.loads((Path(base) / SWITCH_FILE).read_text(encoding="utf-8")).get(market) or {}).get("mode")
    except (OSError, ValueError, AttributeError):
        return None
    return got if got in ("on", "off") else None


def mode(base: Optional[Path] = None, market: Optional[str] = None) -> str:
    """auto, on or off.  ``.env`` decides when it says on or off (it is the same on every screen and survives a lost file); without
    it the screen's button for that market does; without either, auto: the rules are not in force."""
    env = switch_of(ENV)["mode"]
    if env != "auto" or base is None or market is None:
        return env
    return stored_switch(base, market) or "auto"


def set_switch(base: Path, market: str, on: bool, now: Callable[[], datetime] = _utcnow) -> Dict[str, Any]:
    """The screen's button (user decision 2026-11-22: a button, not a line in a file).  Turning the rules on is refused until the
    market's reading exists: before it, the paper book would run under the rules it is being compared with, and the comparison
    would measure nothing.  Turning them off is always allowed."""
    if market not in REPORTS:
        raise ValueError(market)
    rep = report(base, market)
    if on and (not rep or rep.get("status") == "DAMAGED"):
        return {"status": "REFUSED", "market": market, "reason": "240거래일 판정이 나온 뒤에 켤 수 있습니다. 그 전에 켜면 비교하려는 두 장부가 같은 규칙을 쓰게 되어 비교가 뜻을 잃습니다."}
    path = Path(base) / SWITCH_FILE
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        doc = doc if isinstance(doc, dict) else {}
    except (OSError, ValueError):
        doc = {}
    doc[market] = {"mode": "on" if on else "off", "at": now().isoformat()}
    path.parent.mkdir(parents=True, exist_ok=True)
    durable.write_text(path, json.dumps(doc, ensure_ascii=False, indent=1))
    env = switch_of(ENV)["mode"]
    return {"status": "OK", "market": market, "mode": doc[market]["mode"], "active": active_rules(base, market) is not None, "env": env,
            "note": f".env의 {ENV}={env} 가 이 버튼보다 먼저 읽힙니다. 버튼대로 하려면 .env의 그 줄을 지우세요." if env != "auto" else None}


def read_report(path: Path, market: str) -> Optional[Dict[str, Any]]:
    """None when the reading has not been made.  A file that is there but is not a verdict (cut short, emptied, edited by hand)
    is ``{"status": "DAMAGED", ...}``: it must not pass for "not read" (the reading would refuse, the file exists) nor for a
    verdict.  The rules are not in force on a damaged file, and the user is told until it is restored from the backup."""
    if not path.exists():
        return None
    try:
        got = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        got = None
    if isinstance(got, dict) and got.get("decision"):
        return got
    name = "/".join(path.parts[-3:])
    return {"status": "DAMAGED", "market": market, "file": name,
            "reason": f"결과 파일 {name} 을 읽을 수 없습니다. 백업 폴더의 같은 파일로 바꿔야 하며, 그때까지 이 규칙은 적용되지 않습니다."}


def report(base: Path, market: str) -> Optional[Dict[str, Any]]:
    return read_report(Path(base) / REPORTS[market], market)


def active_rules(base: Path, market: str) -> Optional[Dict[str, Any]]:
    """The rules when they are in force for the paper book, the real order plan and the holding reading of ``market``."""
    m = mode(base, market)
    if m == "off":
        return None
    if m == "on":
        return dict(RULES)
    # "auto": the reading no longer switches the rules on (user decision 2026-11-22).  Its two conditions (cheaper, and a mean
    # difference of zero or more) are met about half the time when the rules change nothing (audit QNT-02), so the reading
    # reports and the user decides: the button on the screen (``set_switch``) or QSF_TURNOVER_RULES=on puts the rules in force.
    return None


# ---------------------------------------------------------------------- the daily record
def _seed(base: Path, market: str, first: str) -> Optional[Dict[str, Any]]:
    """The paper book's record of its last session before ``first``: the state both books start from."""
    before = [r["session"] for r in kf.read_index(base, paper_book.FOLDERS[market]) if r["session"] < first]
    return kf._read_day(Path(base) / paper_book.FOLDERS[market], before[-1]) if before else None


def record(base: Path, market: str, loader: Callable[[str], Sequence[Dict[str, Any]]], info: Callable[[], Dict[str, Dict[str, Any]]] = lambda: {},
           bench: Optional[Callable[[], Sequence[Dict[str, Any]]]] = None, now: Callable[[], datetime] = _utcnow, first: str = FIRST) -> Dict[str, Any]:
    """The comparison book up to the newest ledger session.  DONE once the reading exists: nothing is written after it."""
    if (Path(base) / REPORTS[market]).exists():
        return {"status": "DONE", "market": market, "written": []}
    return paper_book.record(base, market, loader, info=info, bench=bench, now=now, first=first, store=FOLDERS[market], rules=dict(RULES), version=VERSION,
                             seed=lambda: _seed(base, market, first))


# ---------------------------------------------------------------------- figures
def figures(docs: List[Dict[str, Any]], start: Dict[str, float]) -> Dict[str, Any]:
    """What one book did over ``docs``.  ``start``: equity, fees and slippage of the state the first of them was built on."""
    equity = [float(start["equity"])] + [float(d["equity"]) for d in docs]
    last = docs[-1]["state"]
    mean_equity = sum(equity[1:]) / len(docs)
    cost = (last["fees"] + last["slippage"]) - (start["fees"] + start["slippage"])
    fills = [(i, f) for i, d in enumerate(docs) for f in d["fills"]]
    exits = [(i, e) for i, d in enumerate(docs) for e in d["exits"]]
    traded = sum(f["qty"] * f["price"] for _, f in fills) + sum(e["qty"] * e["exit"] for _, e in exits)
    by_reason: Dict[str, int] = {}
    for _, e in exits:
        by_reason[e["reason"]] = by_reason.get(e["reason"], 0) + 1
    rebuys = sum(1 for i, e in exits if e["reason"] == "STOP" and any(f["ticker"] == e["ticker"] and i <= j <= i + RULES["reentry_wait"] for j, f in fills))
    peak, worst = equity[0], 0.0
    for v in equity:
        peak = max(peak, v)
        worst = min(worst, v / peak - 1)
    return {"sessions": len(docs), "return_pct": (equity[-1] / equity[0] - 1) * 100, "cost": cost, "cost_pct": cost / mean_equity * 100 if mean_equity else None,
            "traded_pct": traded / mean_equity * 100 if mean_equity else None, "fills": len(fills), "exits": len(exits), "exit_counts": by_reason,
            "rebuys_after_stop": rebuys, "max_drawdown_pct": worst * 100, "mean_cash_pct": sum(d["cash"] / d["equity"] for d in docs if d["equity"]) / len(docs) * 100,
            "log_returns": [math.log(b / a) for a, b in zip(equity, equity[1:])]}


def rule_counts(docs: List[Dict[str, Any]]) -> Dict[str, int]:
    out = {k: 0 for k in RULE_KO}
    for d in docs:
        for e in d.get("rule_events") or []:
            out[e["rule"]] = out.get(e["rule"], 0) + 1
    out["STOPS"] = sum(1 for d in docs for e in d["exits"] if e["reason"] == "STOP")
    return out


def decide(base_fig: Dict[str, Any], rule_fig: Dict[str, Any], mean_diff: float, t: Optional[float], bar: Optional[float] = None) -> Dict[str, Any]:
    """The protocol's reading.  ADOPT: the comparison book paid less and its mean daily return was not below the paper book's.
    Since 2026-11-22 the word is a finding, not a switch: nothing is applied by it (see ``active_rules``).  ``bar``: the t bar
    for the sample's own design (terminal/qsf/calibrate.py); MIN_T without it."""
    bar = bar or MIN_T
    cheaper = rule_fig["cost_pct"] < base_fig["cost_pct"]
    decision = "ADOPT" if cheaper and mean_diff >= 0 else "KEEP"
    distinct = t is not None and abs(t) >= bar
    t_txt = "계산할 수 없음(두 장부의 수익률이 같음)" if t is None else f"{t:+.2f}"
    why = [f"비용(수수료·세금 + 슬리피지 추정 ÷ 평균 평가액): 규칙 적용 {rule_fig['cost_pct']:.2f}%, 기존 {base_fig['cost_pct']:.2f}%. " + ("규칙 쪽이 낮습니다." if cheaper else "규칙 쪽이 낮지 않습니다."),
           f"하루 수익률 차이(규칙 − 기존)의 평균: {mean_diff * 1e4:+.2f}bp, t {t_txt} (기준 ±{bar:g}). " + ("0 이상입니다." if mean_diff >= 0 else "0보다 작습니다."),
           f"기간 수익률: 규칙 적용 {rule_fig['return_pct']:+.2f}%, 기존 {base_fig['return_pct']:+.2f}%. 최대 낙폭: {rule_fig['max_drawdown_pct']:.2f}%, {base_fig['max_drawdown_pct']:.2f}%."]
    if decision == "ADOPT":
        why.append("두 조건(비용이 낮음, 수익 차이의 평균이 0 이상)을 모두 채웠습니다. 프로그램이 스스로 적용하지는 않습니다." + ("" if distinct else " 다만 수익 차이는 통계로 구분되지 않아, 비용 절감과 점 추정에 기댄 약한 결정입니다."))
    else:
        why.append("두 조건(비용이 낮음, 수익 차이의 평균이 0 이상) 중 채우지 못한 것이 있어 기존 규칙을 유지합니다." + ("" if distinct else " 수익 차이는 통계로 구분되지 않았습니다."))
    return {"decision": decision, "evidence": "DISTINCT" if distinct else "NOT_DISTINCT", "cheaper": cheaper, "why": why}


def measure(base_docs: List[Dict[str, Any]], rule_docs: List[Dict[str, Any]], seed: Dict[str, Any]) -> Dict[str, Any]:
    start = {"equity": seed["equity"], "fees": seed["state"]["fees"], "slippage": seed["state"]["slippage"]}
    b, r = figures(base_docs, start), figures(rule_docs, start)
    diff = [x - y for x, y in zip(r.pop("log_returns"), b.pop("log_returns"))]
    mean_diff = sum(diff) / len(diff)
    t = validate.newey_west_t(diff, LAG)
    return {"paper_book": b, "rules_book": r, "difference": {"mean_daily": mean_diff, "t": t, "days": len(diff)}, "rule_counts": rule_counts(rule_docs),
            **decide(b, r, mean_diff, t, calibrate.bar(MIN_T, len(diff), 1, 1, LAG))}


# ---------------------------------------------------------------------- the single reading
def evaluate_once(base: Path, market: str, now: Callable[[], datetime] = _utcnow) -> Dict[str, Any]:
    """The protocol's one reading.  NotDue before its day; RuntimeError when a chain is broken or a report already exists."""
    base = Path(base)
    target = base / REPORTS[market]
    if target.exists():
        raise RuntimeError("이미 읽었습니다. 규칙상 다시 읽지 않습니다.")
    index = kf.read_index(base, FOLDERS[market])
    if len(index) < READ_AT:
        raise NotDue(f"{len(index)}/{READ_AT}")
    for store in (FOLDERS[market], paper_book.FOLDERS[market]):
        if kf.verify(base, store)["status"] != "OK":
            raise RuntimeError("기록 검증에 실패해 읽지 않습니다.")
    sessions = [r["session"] for r in index[:READ_AT]]
    have = {r["session"] for r in kf.read_index(base, paper_book.FOLDERS[market])}
    if not set(sessions) <= have:
        raise NotDue("PAPER_BOOK_BEHIND")
    seed = _seed(base, market, sessions[0])
    if seed is None:
        raise RuntimeError("갈라진 지점의 기존 장부 기록이 없어 읽지 않습니다.")
    rule_docs = [kf._read_day(base / FOLDERS[market], s) for s in sessions]
    base_docs = [kf._read_day(base / paper_book.FOLDERS[market], s) for s in sessions]
    res = {"status": "REAL", "protocol": PROTOCOL, "version": VERSION, "market": market, "first": sessions[0], "last": sessions[-1], "seed_session": seed["session"],
           "read_at": now().isoformat(), "rules": dict(RULES), **measure(base_docs, rule_docs, seed),
           "note": "계좌 하나의 경로를 나란히 본 비교입니다. 점수가 맞는지의 근거가 아니며 투자 자문이 아닙니다. 규칙은 화면의 '이 규칙 쓰기' 버튼을 누르거나 .env의 QSF_TURNOVER_RULES=on 일 때만 쓰입니다."}
    res["consequence"] = ("자동으로 바뀌는 것은 없습니다(2026-11-22 결정). 이 두 조건은 규칙에 효과가 없어도 절반쯤은 채워지므로, 위의 t가 기준을 넘었는지를 함께 보고 정하세요. "
                          "규칙을 쓰려면 점수 탭 모의 장부의 회전율 규칙 칸에서 '이 규칙 쓰기'를 누릅니다(.env의 QSF_TURNOVER_RULES=on 도 같습니다). 그러면 모의 장부, 실제 계좌의 주문 계획, 보유 종목 판단이 두 규칙을 씁니다." if res["decision"] == "ADOPT"
                          else "아무것도 바뀌지 않습니다. 비교 장부는 더 적지 않습니다.")
    res["applies_itself"] = False
    target.parent.mkdir(parents=True, exist_ok=True)
    durable.write_text(target, json.dumps(res, ensure_ascii=False, indent=1))        # whole and on the disk: this file switches rules on
    return res


def read_when_due(base: Path, market: str, now: Callable[[], datetime] = _utcnow) -> Optional[Dict[str, Any]]:
    """The reading's report: the stored one, or a new one on the day it falls due.  None while it is not due.
    A broken record gives ``{"status": "NO_READING", ...}`` and writes nothing."""
    got = report(base, market)
    if got:
        return got
    try:
        return evaluate_once(base, market, now)
    except NotDue:
        return None
    except RuntimeError as exc:
        return {"status": "NO_READING", "market": market, "reason": str(exc)}


def text(rep: Dict[str, Any]) -> str:
    """The notice sent once when the reading is made."""
    name = MARKET_KO.get(rep.get("market"), rep.get("market"))
    if rep.get("status") != "REAL":
        return f"[회전율 규칙 판정 · {name}] 읽지 못했습니다: {rep.get('reason')} 기록을 확인해야 합니다. 규칙: {PROTOCOL}"
    lines = [f"[회전율 규칙 판정 · {name}] 결정: {DECISION_KO[rep['decision']]}", f"구간 {rep['first']} ~ {rep['last']} ({rep['difference']['days']}거래일)"]
    lines += [f"- {w}" for w in rep["why"]]
    lines += [rep["consequence"], "터미널 점수 탭의 모의 장부에서 수치를 볼 수 있습니다."]
    return "\n".join(lines)


def short(rep: Dict[str, Any]) -> str:
    return f"{MARKET_KO.get(rep.get('market'), '')}: {DECISION_KO.get(rep.get('decision'), '읽지 못함')}"


# ---------------------------------------------------------------------- what the screen shows
def status(base: Path, market: str) -> Dict[str, Any]:
    """Progress of the comparison, what the rules did so far, the paper book's own turnover, and the decision once made.
    Nothing of the comparison book's value, return or cost is given before the reading."""
    base = Path(base)
    index = kf.read_index(base, FOLDERS[market])
    rep = report(base, market)
    head = {"market": market, "protocol": PROTOCOL, "version": VERSION, "rules": dict(RULES), "read_at": READ_AT, "first": FIRST, "mode": mode(),
            "switch_unknown": switch_of(ENV)["unknown"], "damaged": rep.get("reason") if rep and rep.get("status") == "DAMAGED" else None,
            "switch": stored_switch(base, market), "can_switch": bool(rep and rep.get("status") != "DAMAGED") and mode() == "auto",
            "active": active_rules(base, market) is not None, "adopted_version": ADOPTED_VERSION, "rule_labels": RULE_KO,
            "note": "판정 전에는 비교 장부의 평가액·수익률·비용을 보여 주지 않습니다. 240거래일이 되면 프로그램이 스스로 읽고 알립니다. 규칙을 스스로 바꾸지는 않습니다(2026-11-22 결정)."}
    if head["damaged"]:
        rep = None
    out: Dict[str, Any] = {"status": "DAMAGED" if head["damaged"] else "DECIDED" if rep else "RECORDING" if index else "NO_RECORD", **head, "records": len(index), "left": max(READ_AT - len(index), 0),
                           "started": index[0]["session"] if index else None, "last": index[-1]["session"] if index else None}
    if index:
        out["rule_counts"] = rule_counts([kf._read_day(base / FOLDERS[market], r["session"]) for r in index])
    book = kf.read_index(base, paper_book.FOLDERS[market])
    if book:
        docs = [kf._read_day(base / paper_book.FOLDERS[market], r["session"]) for r in book]
        fig = figures(docs, {"equity": paper_book.START_CASH[market], "fees": 0.0, "slippage": 0.0})
        fig.pop("log_returns")
        out["paper_book"] = fig
    if rep:
        out["decision"] = {k: rep.get(k) for k in ("decision", "evidence", "why", "consequence", "first", "last", "read_at", "paper_book", "rules_book", "difference", "rule_counts", "note")}
    return out


def loss_sales(closed: Sequence[Dict[str, Any]], market: str, session: str, step: Callable[[date], date], wait: int) -> Dict[str, str]:
    """The real journal has no 'stop' mark: a stock sold at a loss within the last ``wait`` sessions is the one that waits.
    ``closed``: the journal's closed trades (date, ticker, pnl).  Returns {ticker: the day it was sold}."""
    from terminal.qsf import holding
    today, out = date.fromisoformat(session), {}
    for c in closed:
        if (c.get("pnl") or 0) < 0 and holding.add_sessions(date.fromisoformat(c["date"]), wait, step) > today:
            out[c["ticker"]] = max(c["date"], out.get(c["ticker"], ""))
    return out
