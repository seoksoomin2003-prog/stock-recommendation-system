"""The rank rules beside the paper book, and the reading that decides on them.  Rules: reports/QSF_RANK_RULES_PROTOCOL.md.

A made-up account (RK-1) that forks from the paper book's state and follows the same rules plus two: an entry candidate must be inside
the top 20% of the day's scores of its market and strategy, and a long position is sold when its rank leaves the top 50% (in place of
the under-40 rule).  Whatever the paper book itself uses (the turnover rules once they are adopted) this book uses too, so the two
always differ by the rank rules alone.  Nothing of this book's value or return is shown before the reading.

At 240 recorded sessions the program reads once, by itself: ADOPT only when the mean daily return difference is above zero and
distinct (Newey-West t of 2.0 or more), KEEP otherwise.  ``QSF_RANK_RULES`` in ``.env`` (auto / on / off) lets the user overrule it.
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from terminal.qsf import kr_forward as kf, paper_book, turnover_book as tb, validate

PROTOCOL = "reports/QSF_RANK_RULES_PROTOCOL.md"
VERSION = "RK-1"
RULES = {"entry_top": 0.2, "long_exit_top": 0.5}
FOLDERS = {"KR": Path("research_data") / "rank_book_kr", "US": Path("research_data") / "rank_book_us"}
REPORTS = {m: Path("reports") / "qsf" / f"QSF_RANK_RULES_{m}.json" for m in ("KR", "US")}
FIRST = "2026-11-16"               # the comparison book's first session; it starts from the paper book's state of the session before
READ_AT = 240
LAG = 20
MIN_T = 2.0
ENV = "QSF_RANK_RULES"
PAPER_VERSIONS = {(True, False): tb.ADOPTED_VERSION, (False, True): "PB-4", (True, True): "PB-5"}     # (turnover rules, rank rules) in force
DECISION_KO = {"ADOPT": "적용", "KEEP": "유지"}
RULE_KO = {"RANK_ENTRY": "순위 규칙 때문에 빠진 주문(종목·날)", "RANK_EXIT": "순위로 정한 장기 매도"}
NotDue = tb.NotDue


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------- which rules are in force
def mode() -> str:
    got = (os.getenv(ENV) or "auto").strip().lower()
    return got if got in ("auto", "on", "off") else "auto"


def report(base: Path, market: str) -> Optional[Dict[str, Any]]:
    p = Path(base) / REPORTS[market]
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def active_rules(base: Path, market: str) -> Optional[Dict[str, Any]]:
    """The rank rules when they are in force for the paper book, the real order plan and the holding reading of ``market``."""
    m = mode()
    if m == "off":
        return None
    if m == "on":
        return dict(RULES)
    rep = report(base, market)
    return dict(RULES) if rep and rep.get("decision") == "ADOPT" else None


def paper_rules(base: Path, market: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """What the paper book itself runs under: the adopted rule sets together, and the version its records carry (None: PB-2 as it is)."""
    turn, rank = tb.active_rules(base, market), active_rules(base, market)
    if not turn and not rank:
        return None, None
    return {**(turn or {}), **(rank or {})}, PAPER_VERSIONS[(bool(turn), bool(rank))]


# ---------------------------------------------------------------------- the daily record
def record(base: Path, market: str, loader: Callable[[str], Sequence[Dict[str, Any]]], info: Callable[[], Dict[str, Dict[str, Any]]] = lambda: {},
           bench: Optional[Callable[[], Sequence[Dict[str, Any]]]] = None, now: Callable[[], datetime] = _utcnow, first: Optional[str] = None) -> Dict[str, Any]:
    """The comparison book up to the newest ledger session.  DONE once the reading exists: nothing is written after it."""
    if (Path(base) / REPORTS[market]).exists():
        return {"status": "DONE", "market": market, "written": []}
    first = first or FIRST
    rules = {**(tb.active_rules(base, market) or {}), **RULES}        # what the paper book uses, plus the rank rules
    return paper_book.record(base, market, loader, info=info, bench=bench, now=now, first=first, store=FOLDERS[market], rules=rules, version=VERSION,
                             seed=lambda: tb._seed(base, market, first))


# ---------------------------------------------------------------------- figures and the decision
def rule_counts(docs: List[Dict[str, Any]]) -> Dict[str, int]:
    out = {k: 0 for k in RULE_KO}
    for d in docs:
        for e in d.get("rule_events") or []:
            if e["rule"] in out:
                out[e["rule"]] += 1
    return out


def decide(base_fig: Dict[str, Any], rule_fig: Dict[str, Any], mean_diff: float, t: Optional[float]) -> Dict[str, Any]:
    """The protocol's decision.  ADOPT only on a distinct, positive mean daily return difference."""
    distinct = t is not None and abs(t) >= MIN_T
    decision = "ADOPT" if t is not None and mean_diff > 0 and t >= MIN_T else "KEEP"
    t_txt = "계산할 수 없음(두 장부의 수익률이 같음)" if t is None else f"{t:+.2f}"
    why = [f"하루 수익률 차이(순위 규칙 − 기존)의 평균: {mean_diff * 1e4:+.2f}bp, t {t_txt} (적용 기준: 평균이 0보다 크고 t가 {MIN_T:g} 이상).",
           f"기간 수익률: 순위 규칙 {rule_fig['return_pct']:+.2f}%, 기존 {base_fig['return_pct']:+.2f}%. 최대 낙폭: {rule_fig['max_drawdown_pct']:.2f}%, {base_fig['max_drawdown_pct']:.2f}%.",
           f"비용(수수료·세금 + 슬리피지 추정 ÷ 평균 평가액): 순위 규칙 {rule_fig['cost_pct']:.2f}%, 기존 {base_fig['cost_pct']:.2f}%."]
    if decision == "ADOPT":
        why.append("수익 차이가 0보다 크고 통계로 구분되어 순위 규칙을 적용합니다.")
    elif distinct:
        why.append("수익 차이가 통계로 구분되지만 순위 규칙 쪽이 낮아 기존 규칙을 유지합니다.")
    else:
        why.append("수익 차이가 통계로 구분되지 않아 기존 규칙을 유지합니다. 순위 규칙이 나쁘다는 뜻이 아니라 낫다는 근거가 없었다는 뜻입니다.")
    return {"decision": decision, "evidence": "DISTINCT" if distinct else "NOT_DISTINCT", "why": why}


def measure(base_docs: List[Dict[str, Any]], rule_docs: List[Dict[str, Any]], seed: Dict[str, Any]) -> Dict[str, Any]:
    start = {"equity": seed["equity"], "fees": seed["state"]["fees"], "slippage": seed["state"]["slippage"]}
    b, r = tb.figures(base_docs, start), tb.figures(rule_docs, start)
    diff = [x - y for x, y in zip(r.pop("log_returns"), b.pop("log_returns"))]
    mean_diff = sum(diff) / len(diff)
    t = validate.newey_west_t(diff, LAG)
    return {"paper_book": b, "rules_book": r, "difference": {"mean_daily": mean_diff, "t": t, "days": len(diff)}, "rule_counts": rule_counts(rule_docs), **decide(b, r, mean_diff, t)}


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
    seed = tb._seed(base, market, sessions[0])
    if seed is None:
        raise RuntimeError("갈라진 지점의 기존 장부 기록이 없어 읽지 않습니다.")
    rule_docs = [kf._read_day(base / FOLDERS[market], s) for s in sessions]
    base_docs = [kf._read_day(base / paper_book.FOLDERS[market], s) for s in sessions]
    res = {"status": "REAL", "protocol": PROTOCOL, "version": VERSION, "market": market, "first": sessions[0], "last": sessions[-1], "seed_session": seed["session"],
           "read_at": now().isoformat(), "rules": dict(RULES), **measure(base_docs, rule_docs, seed),
           "note": "계좌 하나의 경로를 나란히 본 비교입니다. 점수가 맞는지의 근거가 아니며 투자 자문이 아닙니다. .env의 QSF_RANK_RULES(auto/on/off)로 이 결정을 뒤집을 수 있습니다."}
    res["consequence"] = ("이 뒤의 기록부터 기존 모의 장부, 실제 계좌의 주문 계획, 보유 종목 판단이 순위 규칙을 씁니다." if res["decision"] == "ADOPT"
                          else "아무것도 바뀌지 않습니다. 비교 장부는 더 적지 않습니다.")
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".tmp")
    tmp.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(target)
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
        return f"[순위 규칙 판정 · {name}] 읽지 못했습니다: {rep.get('reason')} 기록을 확인해야 합니다. 규칙: {PROTOCOL}"
    lines = [f"[순위 규칙 판정 · {name}] 결정: {DECISION_KO[rep['decision']]}", f"구간 {rep['first']} ~ {rep['last']} ({rep['difference']['days']}거래일)"]
    lines += [f"- {w}" for w in rep["why"]]
    lines += [rep["consequence"], "터미널 점수 탭의 모의 장부에서 수치를 볼 수 있습니다. 뒤집으려면 .env의 QSF_RANK_RULES를 on 또는 off로 두세요."]
    return "\n".join(lines)


def short(rep: Dict[str, Any]) -> str:
    return f"{tb.MARKET_KO.get(rep.get('market'), '')}: {DECISION_KO.get(rep.get('decision'), '읽지 못함')}"


# ---------------------------------------------------------------------- what the screen shows
def status(base: Path, market: str) -> Dict[str, Any]:
    """Progress of the comparison, what the rules did so far, and the decision once made.  Nothing of the comparison book's value,
    return or cost is given before the reading."""
    base = Path(base)
    index = kf.read_index(base, FOLDERS[market])
    rep = report(base, market)
    out: Dict[str, Any] = {"status": "DECIDED" if rep else "RECORDING" if index else "NO_RECORD", "market": market, "protocol": PROTOCOL, "version": VERSION, "rules": dict(RULES),
                           "read_at": READ_AT, "first": FIRST, "mode": mode(), "active": active_rules(base, market) is not None, "paper_version": paper_rules(base, market)[1],
                           "rule_labels": RULE_KO, "records": len(index), "left": max(READ_AT - len(index), 0),
                           "started": index[0]["session"] if index else None, "last": index[-1]["session"] if index else None,
                           "note": "판정 전에는 비교 장부의 평가액·수익률·비용을 보여 주지 않습니다. 240거래일이 되면 프로그램이 스스로 읽고 정합니다."}
    if index:
        out["rule_counts"] = rule_counts([kf._read_day(base / FOLDERS[market], r["session"]) for r in index])
    if rep:
        out["decision"] = {k: rep.get(k) for k in ("decision", "evidence", "why", "consequence", "first", "last", "read_at", "paper_book", "rules_book", "difference", "rule_counts", "note")}
    return out
