"""What the stored historical checks said about the live score, for the screen.  Read only: it reads report files already written
and computes no return.  Nothing here is new evidence; it puts the numbers of the one-run reports next to the score."""
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional

from terminal.qsf import live_forward, validate
from terminal.qsf.ledger import Ledger

# market -> report file, table key per strategy, and what kind of check it was
# market -> the rows to show: report file, strategy, table key (None: the report's ``primary`` block), and what kind of check it was
LIVE_KR, FORMER_KR = "시가총액 상위 300 (지금 대상)", "거래대금 상위 300 (이전 대상)"
SOURCES = {
    "KR": {"file": "reports/qsf/QSF_KR_UNIVERSE_TEST.json", "results": "reports/QSF_KR_UNIVERSE_TEST_RESULTS.md",
           "what": "라이브 점수 과거 재현 (상장폐지 종목 포함, 구간마다 한 번 실행; 시가총액 대상은 결과를 본 뒤의 탐색 시험)",
           "rows": [
               # the live universe since QSF-1.3.0: the one exploratory test of the same score on the market-value top 300
               {"file": "reports/qsf/QSF_KR_UNIVERSE_TEST.json", "strategy": "SWING", "table": "SWING|20", "universe": LIVE_KR, "superseded": True},
               {"file": "reports/qsf/QSF_KR_UNIVERSE_TEST.json", "strategy": "LONG_TERM", "table": "LONG_TERM|252", "universe": LIVE_KR},
               # the former live universe: the first replay and the second window checked once afterwards
               {"file": "reports/qsf/QSF_KR_LIVE_REPLAY.json", "strategy": "LONG_TERM", "table": "LONG_TERM|252", "universe": FORMER_KR, "former_universe": True,
                "results": "reports/QSF_KR_LIVE_REPLAY_RESULTS.md"},
               {"file": "reports/qsf/QSF_KR_LONG_EARLY.json", "strategy": "LONG_TERM", "table": None, "universe": FORMER_KR, "former_universe": True, "second_window": True,
                "results": "reports/QSF_KR_LONG_EARLY_RESULTS.md"}]},
    "US": {"file": "reports/qsf/QSF_CORRECTED_OPEN.json", "tables": {"SWING": "SWING|A|20", "LONG_TERM": "LONG_TERM|A|252"}, "results": "reports/QSF_CORRECTED_RECHECK_RESULTS.md",
           "what": "S&P 500 과거 검증 (라이브 방식 점수, 인수·파산 종목 일부 누락)"},
}
READINGS = {"WEAK_POSITIVE_EVIDENCE": "근거 있음(약함)", "RANK_ONLY": "순위만 설명", "NO_EVIDENCE": "시험했으나 기준 미달", "NOT_CONFIRMED": "확인 안 됨(같은 방향, 더 약함)"}
DOMAIN_NAMES = {"TECHNICAL": "차트", "FUNDAMENTAL": "재무", "RISK": "위험"}
BAND_NOTE = "점수 구간별 평균입니다(비용 0.2% 차감). 여러 날을 합친 수치라 판정에는 쓰지 않습니다."
EXPECTED = {"SWING": "2027년 12월쯤", "LONG_TERM": "2030년 초"}          # reports/QSF_LIVE_FORWARD_PROTOCOL.md
NOT_STORED = "미국 시험은 이 수치를 저장하지 않았습니다. 점수 구간별 성적은 판정 근거에 있습니다."
CAVEATS = {"KR": ["과거 구간의 결과입니다. 앞으로도 같다는 뜻이 아닙니다.", "시장 국면·공시 영역과 배당은 빠져 있습니다.",
                  "지금 대상(시가총액 상위 300)의 수치는 결과를 본 뒤 대상만 바꿔 한 번 해 본 탐색 시험입니다. 이 대상 안에서 점수는 기준에 못 미쳤습니다.",
                  "이전 대상(거래대금 상위 300)은 두 구간 모두 시장보다 크게 부진했습니다.",
                  "스윙 줄은 차트 항목이 점수에 들어가던 이전 구성의 성적입니다. 2026-11-11부터의 스윙 점수(차트 항목 제외)는 과거 구간에서 시험한 적이 없고 앞으로의 기록으로만 확인합니다."],
           "US": ["과거 한 구간의 결과입니다. 앞으로도 같다는 뜻이 아닙니다.", "2017년 이후 지수에서 빠진 종목 일부가 없어 수익이 실제보다 좋게 보일 수 있습니다."]}


def pair_win(ic: Optional[float]) -> Optional[float]:
    """Chance that the higher-scored of two random stocks did better, from the rank correlation (0.5 + IC / pi)."""
    return None if ic is None else 0.5 + ic / math.pi


def _pct(v: Optional[float], digits: int = 2) -> str:
    return "없음" if v is None else f"{v * 100:+.{digits}f}%"


def _num(v: Optional[float], digits: int = 3) -> str:
    return "없음" if v is None else f"{v:+.{digits}f}"


def _checks(t: Dict[str, Any], stored: Optional[Dict[str, bool]]) -> List[Dict[str, Any]]:
    """The five conditions every one of these tests was read by, with the measured value next to each.  The pass marks are the
    stored ones when the report kept them, else ``validate.verdict`` on the same stored numbers; nothing is measured again."""
    got = stored or validate.verdict(t)["checks"]
    early, late = t.get("early") or {}, t.get("late") or {}
    return [
        {"key": "ic", "label": "점수 순위와 수익 순위의 관계(IC)", "need": f"{validate.MIN_IC:.2f} 이상", "value": _num(t.get("ic")), "passed": bool(got.get("ic"))},
        {"key": "t", "label": "우연이 아닐 만큼 뚜렷한가(t값)", "need": f"{validate.MIN_T:.2f} 이상", "value": "없음" if t.get("t") is None else f"{t['t']:.2f}", "passed": bool(got.get("t"))},
        {"key": "ic_both_halves", "label": "전반·후반 모두 양의 관계", "need": "둘 다 0 초과", "value": f"{_num(early.get('ic'))} / {_num(late.get('ic'))}", "passed": bool(got.get("ic_both_halves"))},
        {"key": "spread_both_halves", "label": "상위 20% − 하위 20% 수익(비용 후), 전반·후반", "need": "둘 다 0 초과",
         "value": f"{_pct(early.get('spread_net'))} / {_pct(late.get('spread_net'))}", "passed": bool(got.get("spread_both_halves"))},
        {"key": "buy_band", "label": "70점 이상 종목의 평균 대비 수익", "need": "0 초과", "value": _pct(t.get("buy_excess")), "passed": bool(got.get("buy_band"))}]


def pair_win_range(ic: Optional[float], t: Optional[float]) -> Optional[List[float]]:
    """About a 95% range of the win share, from the mean rank correlation and its standard error (ic / t)."""
    if ic is None or not t or not ic:
        return None
    se = abs(ic / t)
    return [pair_win(ic - 1.96 * se), pair_win(ic + 1.96 * se)]


def _reason(t: Dict[str, Any], checks: List[Dict[str, Any]], reading: Optional[str], money_passed: Optional[bool]) -> List[str]:
    """Why the row reads as it does, in sentences built from the stored numbers."""
    ok = {c["key"]: c["passed"] for c in checks}
    win, rng = pair_win(t.get("ic")), pair_win_range(t.get("ic"), t.get("t"))
    win_txt = "" if win is None else f"높은 점수가 이긴 비율 {win * 100:.1f}%" + ("" if not rng else f", 오차 범위 {rng[0] * 100:.1f}~{rng[1] * 100:.1f}%")
    dates, lag, mean_n = t.get("dates"), t.get("lag"), t.get("mean_n")
    out = []
    if dates:
        size = f"평가일 {dates}개" + (f", 하루 평균 {mean_n:.0f}종목" if mean_n else "")
        indep = round(dates / lag) if lag and lag > 1 else None
        if indep is not None and indep < 30:
            out.append(f"{size}을 시험했습니다. 보유 기간이 겹쳐 서로 독립인 구간은 약 {indep}개입니다." + ("" if ok["t"] else " 그래서 작은 효과는 우연과 구별하기 어렵습니다."))
        elif all(ok.values()):
            out.append(f"{size}을 시험했습니다.")
        else:
            out.append(f"{size}을 시험했습니다. 자료가 모자라서가 아니라 시험 결과가 기준에 못 미쳐서 나온 판정입니다.")
    if all(ok.values()):
        out.append(f"사전에 정한 다섯 조건을 모두 충족했습니다({win_txt})." + (" 다만 상위 종목을 실제로 샀을 때 시장을 이기지는 못했습니다." if money_passed is False else ""))
    elif not ok["ic"] and not ok["t"]:
        out.append(f"점수 순위와 이후 수익의 관계가 0과 구별되지 않았습니다({win_txt}). 50%는 동전 던지기입니다.")
    elif not ok["t"]:
        out.append(f"점수가 높은 쪽이 조금 나았지만 우연과 구별될 만큼 뚜렷하지 않았습니다({win_txt}).")
    else:
        out.append(f"순위 관계는 확인됐지만({win_txt}), 상위 종목을 실제로 샀을 때의 수익 조건이 미달했습니다.")
    early, late = t.get("early") or {}, t.get("late") or {}
    if not ok["ic_both_halves"] and early.get("ic") is not None and late.get("ic") is not None:
        out.append(f"기간을 반으로 나누면 순위 관계가 전반 {_num(early['ic'])}, 후반 {_num(late['ic'])}로 한쪽에서만 맞았습니다.")
    if not ok["spread_both_halves"] and early.get("spread_net") is not None and late.get("spread_net") is not None:
        out.append(f"상위 20%에서 하위 20%를 뺀 수익(비용 후)은 전반 {_pct(early['spread_net'])}, 후반 {_pct(late['spread_net'])}로, 두 구간 모두 양이어야 하는 조건에 못 미쳤습니다.")
    if not ok["buy_band"] and t.get("buy_excess") is not None:
        out.append(f"70점 이상 종목은 같은 날 평균보다 {_pct(t['buy_excess'])}였습니다.")
    if reading == "NOT_CONFIRMED":
        out.append("첫 구간의 결과를 다른 구간에서 다시 본 시험이며, 같은 방향이지만 기준에는 못 미쳤습니다.")
    return out


def _domains(tables: Dict[str, Any], strategy: str, horizon: Optional[int]) -> List[Dict[str, Any]]:
    """How each score domain did alone in the same run, where the report kept it."""
    out = []
    for key, name in DOMAIN_NAMES.items():
        d = (tables or {}).get(f"{strategy}|{key}|{horizon}")
        if d and d.get("ic") is not None:
            out.append({"key": key, "name": name, "ic": d["ic"], "t": d.get("t"), "pair_win": pair_win(d["ic"]),
                        "early_ic": (d.get("early") or {}).get("ic"), "late_ic": (d.get("late") or {}).get("ic")})
    return out


def _bands(buckets: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [{"band": k, "n": v.get("n"), "vs_average": v.get("mean_vs_average"), "vs_index_net": v.get("mean_vs_bench_net"), "beat_average_rate": v.get("beat_average_rate")}
            for k, v in (buckets or {}).items() if v.get("n")]


def _row(strategy: str, t: Dict[str, Any], primary: Dict[str, Any], money: Dict[str, Any]) -> Dict[str, Any]:
    stored = (primary.get("condition_a") or {}).get("checks")
    reading = primary.get("reading") or (primary.get("condition_a") or {}).get("verdict") or ("NO_EVIDENCE" if t.get("t") is None or t["t"] < validate.MIN_T else None)
    checks = _checks(t, stored)
    passed = sum(c["passed"] for c in checks)
    label = READINGS.get(reading, READINGS["NO_EVIDENCE"])          # a row without a stored reading is never promoted to evidence here
    if label == READINGS["NO_EVIDENCE"]:
        label = f"{label} (조건 {passed}/5 충족)"
    return {"strategy": strategy, "horizon": int(str(primary.get("horizon") or 0)) or None, "dates": t.get("dates"), "first": t.get("first"), "last": t.get("last"),
            "ic": t.get("ic"), "t": t.get("t"), "pair_win": pair_win(t.get("ic")), "pair_win_range": pair_win_range(t.get("ic"), t.get("t")),
            "top_fifth_excess": t.get("top_fifth_excess"), "bottom_fifth_excess": t.get("bottom_fifth_excess"), "spread_net": t.get("spread_net"),
            "buy_excess": t.get("buy_excess"), "buy_trades": t.get("buy_trades"), "universe_return": t.get("average_return"), "market_return": t.get("market_return"),
            "mean_n": t.get("mean_n"), "split": t.get("split"), "checks": checks, "checks_passed": passed, "why": _reason(t, checks, reading, money.get("passed") if money else None),
            "reading": reading, "reading_label": label, "beats_market": money.get("passed") if money else None}


def forward(base: Path, market: str) -> Dict[str, Any]:
    """Where new evidence is being collected: counts of the write-once daily record, nothing is evaluated here."""
    out: Dict[str, Any] = {"first": live_forward.FIRST, "protocol": live_forward.PROTOCOL, "strategies": {}}
    try:
        days = sorted({r["session"] for r in Ledger(Path(base))._live_rows() if r.get("market") == market and r.get("session", "") >= live_forward.FIRST})
    except (OSError, ValueError, KeyError):
        days = []
    for strategy, h in live_forward.PRIMARY.items():
        out["strategies"][strategy] = {"horizon": h, "recorded": len(days), "needed": live_forward.NEED[strategy], "expected": EXPECTED.get(strategy)}
    return out


def _kr_rows(base: Path, specs) -> Dict[str, Any]:
    rows, more, docs = [], [], {}
    for spec in specs:
        if spec["file"] not in docs:
            try:
                docs[spec["file"]] = json.loads((Path(base) / spec["file"]).read_text(encoding="utf-8"))
            except (OSError, ValueError):
                docs[spec["file"]] = None
        doc = docs[spec["file"]]
        if not doc:
            continue
        strategy = spec["strategy"]
        if spec["table"] is None:                        # a report that holds one primary reading
            primary = doc.get("primary") or {}
            if primary.get("strategy") != strategy or primary.get("ic") is None:
                continue
            t = primary
        else:
            t = (doc.get("tables") or {}).get(spec["table"])
            if not t:
                continue
            primary = dict((doc.get("primary") or {}).get(strategy) or {})
            primary.setdefault("horizon", spec["table"].rsplit("|", 1)[-1])
        row = _row(strategy, t, primary, (doc.get("money") or {}).get(strategy) or {})
        row["domains"] = _domains(doc.get("domains") or {}, strategy, row["horizon"])
        row.update({k: spec[k] for k in ("universe", "superseded", "former_universe", "second_window") if spec.get(k)})
        rows.append(row)
        if spec.get("results") and spec["results"] not in more:
            more.append(spec["results"])
    return {"rows": rows, "more_sources": more}


def summary(base: Path, market: str) -> Dict[str, Any]:
    src = SOURCES.get(market)
    if not src:
        return {"status": "UNAVAILABLE", "market": market}
    if "rows" in src:
        got = _kr_rows(base, src["rows"])
        if not got["rows"]:
            return {"status": "UNAVAILABLE", "market": market}
        return {"status": "REAL", "market": market, "what": src["what"], "source": src["results"], **got, "caveats": CAVEATS[market], "forward": forward(base, market)}
    try:
        doc = json.loads((Path(base) / src["file"]).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"status": "UNAVAILABLE", "market": market}
    rows = []
    for strategy, key in src["tables"].items():
        t = (doc.get("tables") or {}).get(key)
        if not t:
            continue
        primary = {"horizon": key.rsplit("|", 1)[-1]}
        row = _row(strategy, t, primary, {})
        row["domains"] = _domains(doc.get("tables") or {}, strategy, row["horizon"])
        row["bands"], row["band_note"], row["not_stored_note"] = _bands((doc.get("buckets") or {}).get(key)), BAND_NOTE, NOT_STORED
        rows.append(row)
    if not rows:
        return {"status": "UNAVAILABLE", "market": market}
    return {"status": "REAL", "market": market, "what": src["what"], "source": src["results"], "more_sources": [], "rows": rows, "caveats": CAVEATS[market], "forward": forward(base, market)}
