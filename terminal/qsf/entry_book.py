"""The entry comparison book: buying a new-high swing candidate at once instead of waiting for a pullback.
Rules: reports/QSF_ENTRY_RULES_PROTOCOL.md (EN-1, user decision 2026-11-25 "그대로 + 비교 기록").

The live rule stays as it is.  A made-up account (EN-1) forks from the paper book's state and follows the same rules plus one: a
swing card in the buy band that waits for a pullback only because no resistance stands above it (``order_plan.breakout_wait``) is
an entry candidate too.  Whatever the paper book itself uses this book uses too, so the two differ by that rule alone.  Nothing
of this book's value or return is shown before the reading.

At 240 recorded sessions the program reads once, by itself, and tells the result.  The reading changes nothing: it says whether
the two books' daily returns were distinct and which way.  Changing the entry rule afterwards is the user's decision.
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from terminal.qsf import calibrate
from terminal.qsf import kr_forward as kf, paper_book, turnover_book as tb, validate
from utils import durable

PROTOCOL = "reports/QSF_ENTRY_RULES_PROTOCOL.md"
VERSION = "EN-1"
RULES = {"breakout_entry": True}
FOLDERS = {"KR": Path("research_data") / "entry_book_kr", "US": Path("research_data") / "entry_book_us"}
REPORTS = {m: Path("reports") / "qsf" / f"QSF_ENTRY_RULES_{m}.json" for m in ("KR", "US")}
FIRST = "2026-11-25"               # the comparison book's first session; it starts from the paper book's state of the session before
READ_AT = 240
LAG = 20
MIN_T = 2.0
DECISION_KO = {"BREAKOUT_BETTER": "바로 진입 쪽이 나았음(통계로 구분됨)", "PULLBACK_BETTER": "지금 규칙(눌림 대기) 쪽이 나았음(통계로 구분됨)", "NOT_DISTINCT": "구분되지 않음"}
RULE_KO = {"BREAKOUT_ENTRY": "이 규칙으로만 생긴 주문(종목·날)"}
NotDue = tb.NotDue


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def report(base: Path, market: str) -> Optional[Dict[str, Any]]:
    return tb.read_report(Path(base) / REPORTS[market], market)        # None, the verdict, or DAMAGED (never taken for either)


# ---------------------------------------------------------------------- the daily record
def record(base: Path, market: str, loader: Callable[[str], Sequence[Dict[str, Any]]], info: Callable[[], Dict[str, Dict[str, Any]]] = lambda: {},
           bench: Optional[Callable[[], Sequence[Dict[str, Any]]]] = None, now: Callable[[], datetime] = _utcnow, first: Optional[str] = None) -> Dict[str, Any]:
    """The comparison book up to the newest ledger session.  DONE once the reading exists: nothing is written after it."""
    if (Path(base) / REPORTS[market]).exists():
        return {"status": "DONE", "market": market, "written": []}
    from terminal.qsf import rank_book
    first = first or FIRST
    rules = {**(rank_book.paper_rules(base, market)[0] or {}), **RULES}        # what the paper book uses, plus the one entry rule
    return paper_book.record(base, market, loader, info=info, bench=bench, now=now, first=first, store=FOLDERS[market], rules=rules, version=VERSION,
                             seed=lambda: tb._seed(base, market, first))


# ---------------------------------------------------------------------- figures and the reading
def rule_counts(docs: List[Dict[str, Any]]) -> Dict[str, int]:
    out = {k: 0 for k in RULE_KO}
    for d in docs:
        for e in d.get("rule_events") or []:
            if e["rule"] in out:
                out[e["rule"]] += 1
    return out


def decide(base_fig: Dict[str, Any], rule_fig: Dict[str, Any], mean_diff: float, t: Optional[float], bar: Optional[float] = None) -> Dict[str, Any]:
    """The protocol's reading: which book's daily returns were higher, and whether the difference is distinct.  It adopts nothing."""
    bar = bar or MIN_T
    distinct = t is not None and abs(t) >= bar
    decision = "NOT_DISTINCT" if not distinct else "BREAKOUT_BETTER" if mean_diff > 0 else "PULLBACK_BETTER"
    t_txt = "계산할 수 없음(두 장부의 수익률이 같음)" if t is None else f"{t:+.2f}"
    why = [f"하루 수익률 차이(바로 진입 − 지금 규칙)의 평균: {mean_diff * 1e4:+.2f}bp, t {t_txt} (구분 기준: |t|가 {bar:g} 이상).",
           f"기간 수익률: 바로 진입 {rule_fig['return_pct']:+.2f}%, 지금 규칙 {base_fig['return_pct']:+.2f}%. 최대 낙폭: {rule_fig['max_drawdown_pct']:.2f}%, {base_fig['max_drawdown_pct']:.2f}%.",
           f"비용(수수료·세금 + 슬리피지 추정 ÷ 평균 평가액): 바로 진입 {rule_fig['cost_pct']:.2f}%, 지금 규칙 {base_fig['cost_pct']:.2f}%."]
    why.append({"BREAKOUT_BETTER": "신고가 근처에서 바로 진입한 장부의 수익이 더 높았고 통계로 구분됩니다.",
                "PULLBACK_BETTER": "눌림을 기다리는 지금 규칙의 장부 수익이 더 높았고 통계로 구분됩니다.",
                "NOT_DISTINCT": "두 장부의 수익 차이가 통계로 구분되지 않습니다. 어느 쪽이 낫다는 근거가 없다는 뜻입니다."}[decision])
    return {"decision": decision, "evidence": "DISTINCT" if distinct else "NOT_DISTINCT", "why": why, "t_bar": bar}


def measure(base_docs: List[Dict[str, Any]], rule_docs: List[Dict[str, Any]], seed: Dict[str, Any]) -> Dict[str, Any]:
    start = {"equity": seed["equity"], "fees": seed["state"]["fees"], "slippage": seed["state"]["slippage"]}
    b, r = tb.figures(base_docs, start), tb.figures(rule_docs, start)
    diff = [x - y for x, y in zip(r.pop("log_returns"), b.pop("log_returns"))]
    mean_diff = sum(diff) / len(diff)
    t = validate.newey_west_t(diff, LAG)
    return {"paper_book": b, "rules_book": r, "difference": {"mean_daily": mean_diff, "t": t, "days": len(diff)}, "rule_counts": rule_counts(rule_docs),
            **decide(b, r, mean_diff, t, calibrate.bar(MIN_T, len(diff), 1, 1, LAG))}


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
    seed = tb._seed(base, market, sessions[0])
    if seed is None:
        raise RuntimeError("갈라진 지점의 기존 장부 기록이 없어 읽지 않습니다.")
    rule_docs = [kf._read_day(base / FOLDERS[market], s) for s in sessions]
    base_docs = [kf._read_day(base / paper_book.FOLDERS[market], s) for s in sessions]
    res = {"status": "REAL", "protocol": PROTOCOL, "version": VERSION, "market": market, "first": sessions[0], "last": sessions[-1], "seed_session": seed["session"],
           "read_at": now().isoformat(), "rules": dict(RULES), **measure(base_docs, rule_docs, seed),
           "note": "계좌 하나의 경로를 나란히 본 비교입니다. 점수가 맞는지의 근거가 아니며 투자 자문이 아닙니다. 두 장부는 투자 비중이 달라서, 시장이 오르거나 내린 구간이면 "
                   "규칙에 실력이 없어도 차이가 날 수 있습니다. 평균 현금 비중과 구간의 지수 수익을 함께 보세요."}
    res["consequence"] = "아무것도 바뀌지 않습니다. 진입 규칙을 바꿀지는 이 결과를 보고 직접 정합니다. 비교 장부는 더 적지 않습니다."
    res["applies_itself"] = False
    target.parent.mkdir(parents=True, exist_ok=True)
    durable.write_text(target, json.dumps(res, ensure_ascii=False, indent=1))
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
    name = tb.MARKET_KO.get(rep.get("market"), rep.get("market"))
    if rep.get("status") != "REAL":
        return f"[진입 규칙 비교 · {name}] 읽지 못했습니다: {rep.get('reason')} 기록을 확인해야 합니다. 규칙: {PROTOCOL}"
    lines = [f"[진입 규칙 비교 · {name}] 결과: {DECISION_KO[rep['decision']]}", f"구간 {rep['first']} ~ {rep['last']} ({rep['difference']['days']}거래일)"]
    lines += [f"- {w}" for w in rep["why"]]
    lines += [rep["consequence"], "터미널 순위·카드 탭의 판정 일정에서 볼 수 있습니다."]
    return "\n".join(lines)


def short(rep: Dict[str, Any]) -> str:
    return f"{tb.MARKET_KO.get(rep.get('market'), '')}: {DECISION_KO.get(rep.get('decision'), '읽지 못함')}"


# ---------------------------------------------------------------------- what the screen shows
def status(base: Path, market: str) -> Dict[str, Any]:
    """Progress of the comparison, how often the rule made an order so far, and the result once read.  Nothing of the comparison
    book's value, return or cost is given before the reading."""
    base = Path(base)
    index = kf.read_index(base, FOLDERS[market])
    rep = report(base, market)
    damaged = rep.get("reason") if rep and rep.get("status") == "DAMAGED" else None
    rep = None if damaged else rep
    out: Dict[str, Any] = {"status": "DAMAGED" if damaged else "DECIDED" if rep else "RECORDING" if index else "NO_RECORD", "market": market, "protocol": PROTOCOL, "version": VERSION,
                           "rules": dict(RULES), "damaged": damaged, "read_at": READ_AT, "first": FIRST, "rule_labels": RULE_KO, "records": len(index), "left": max(READ_AT - len(index), 0),
                           "started": index[0]["session"] if index else None, "last": index[-1]["session"] if index else None,
                           "note": "판정 전에는 비교 장부의 평가액·수익률·비용을 보여 주지 않습니다. 240거래일이 되면 프로그램이 스스로 읽고 알립니다. 결과가 무엇이든 진입 규칙은 스스로 바뀌지 않습니다."}
    if index:
        out["rule_counts"] = rule_counts([kf._read_day(base / FOLDERS[market], r["session"]) for r in index])
    if rep:
        out["decision"] = {k: rep.get(k) for k in ("decision", "evidence", "why", "consequence", "first", "last", "read_at", "paper_book", "rules_book", "difference", "rule_counts", "note")}
    return out
