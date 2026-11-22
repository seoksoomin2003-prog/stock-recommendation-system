"""Five well-known investing approaches read as fixed checklists over the figures the scan already stores.

User request (2026-11-22): a team of five views (Buffett, Munger, Graham, Lynch, Druckenmiller) that gives an opinion on each
stock, one or two lines per view, and a team list.  Decisions the same day: each view says how many of its criteria are met
and whether the stock "meets", "partly meets" or "does not meet" them (never buy or sell); the team list is the stocks at
least three of the five views find to meet their criteria, most agreement first, at most ten, equal weight; the list is
recorded every day and no verdict is defined for it.

What this is not.  It is not what these people think about any stock: it is this program's reading of principles known from
their books, letters and interviews, reduced to thresholds on stored annual figures and daily prices.  The thresholds are
this program's choice.  None of it has been tested on returns, and none of it enters a score.  No network is asked.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

MEETS, PARTLY, FAILS, UNKNOWN = "MEETS", "PARTLY", "FAILS", "UNKNOWN"
VERDICT_KO = {MEETS: "기준에 맞음", PARTLY: "일부 맞음", FAILS: "맞지 않음", UNKNOWN: "자료 부족"}
MEET_SHARE, PART_SHARE, MIN_KNOWN = 0.70, 0.45, 4
AGREE, TEAM_SIZE = 3, 10
FOLDERS = {"KR": "five_views_kr", "US": "five_views_us"}
FINANCIAL = ("Financial Services", "금융")
NOTE = ("실존 투자자의 실제 의견이 아닙니다. 책과 주주서한 등으로 알려진 원칙을 이 프로그램이 기준값으로 옮긴 것이고, 기준값은 프로그램이 정했습니다. "
        "수익으로 검증하지 않았고 점수에 들어가지 않습니다.")
Check = Tuple[str, Optional[bool], str]          # what is asked, whether it holds (None: no figure), the figure as shown


# ---------------------------------------------------------------------------------------------- the figures
# which factor's stored figure answers each name; the first factor that has it wins.  Named one by one because two factors can
# use the same key for different things (a stock's relative-strength percentile, the credit spread's percentile).
SOURCES = {"pe": ("valuation",), "pb": ("valuation",), "roe": ("business_quality", "profitability"), "op_margin": ("business_quality", "profitability"),
           "gross_margin": ("business_quality",), "roe_years_positive": ("business_quality",), "eps_cagr3": ("growth_quality",), "rev_growth": ("growth_quality", "earnings_revenue_quality"),
           "eps_growth": ("earnings_revenue_quality",), "fcf_margin": ("free_cash_flow", "cash_flow_quality"), "fcf_years_positive": ("free_cash_flow",),
           "debt_equity": ("balance_dilution", "leverage", "balance_sheet"), "share_change": ("balance_dilution", "capital_allocation"),
           "current_ratio": ("financial_resilience", "balance_sheet"), "returns_capital": ("capital_allocation",), "ma200": ("long_trend", "trend_structure"),
           "ma200_slope": ("long_trend", "trend_structure"), "percentile": ("relative_strength",), "ret_12_1": ("momentum_persistence",),
           "max_drawdown_252": ("downside_drawdown", "drawdown_gap"), "negative": ("material_events", "material_disclosures")}


def figures(long_snap: Optional[Dict[str, Any]], swing_snap: Optional[Dict[str, Any]] = None, info: Optional[Dict[str, Any]] = None,
            marks: Iterable[str] = ()) -> Dict[str, Any]:
    """The stored figures the checklists read, by plain name.  A missing figure stays None: it is never read as zero."""
    raws: Dict[str, Dict[str, Any]] = {}
    for snap in (long_snap, swing_snap):
        for f in (snap or {}).get("factors") or []:
            if isinstance(f.get("raw"), dict) and f.get("factor") not in raws:
                raws[f["factor"]] = f["raw"]
    out: Dict[str, Any] = {"marks": list(marks)}
    for name, factors in SOURCES.items():
        out[name] = next((raws[k][name] for k in factors if k in raws and raws[k].get(name) is not None), None)
    gov = raws.get("governance")
    out["governance_issues"] = None if gov is None else len(gov.get("issues") or [])
    for key in ("insider_ownership", "insider_activity"):
        raw = raws.get(key) or {}
        ins = raw.get("insider") if isinstance(raw.get("insider"), dict) else raw
        if ins.get("status") == "REAL" and out.get("insider_buy") is None:
            out["insider_buy"], out["insider_sell"] = ins.get("open_market_buy"), ins.get("open_market_sell")
    base = long_snap or swing_snap or {}
    out["price"] = base.get("price")
    # the market state the program shows everywhere else is the swing scan's (order_plan.market_state reads SWING first)
    regimes = [((s or {}).get("domains") or {}).get("REGIME") for s in (swing_snap, long_snap)]
    out["market_state"] = next((r["score_100"] for r in regimes if isinstance(r, dict) and r.get("score_100") is not None), None)
    d = info or {}
    out["eps_now"], out["eps_next"] = d.get("epsCurrentYear"), d.get("forwardEps")
    return out


def _pct(v: Optional[float], digits: int = 1) -> str:
    return "자료 없음" if v is None else f"{v * 100:.{digits}f}%"


def _x(v: Optional[float], digits: int = 1) -> str:
    return "자료 없음" if v is None else f"{v:.{digits}f}배"


NO_EQUITY = 99.0          # terminal/qsf/fundamentals.py stores this as debt over equity when equity is zero or negative


def _de(v: Optional[float]) -> str:
    return "부채/자본 자료 없음" if v is None else "자본이 0 이하라 부채/자본 계산 안 됨" if v == NO_EQUITY else f"부채/자본 {v:.2f}배"


def _at_most(v: Optional[float], limit: float) -> Optional[bool]:
    return None if v is None else v <= limit


def _at_least(v: Optional[float], limit: float) -> Optional[bool]:
    return None if v is None else v >= limit


def _pe_ok(pe: Optional[float], limit: float) -> Optional[bool]:
    return None if pe is None else 0 < pe <= limit       # a loss has no P/E: it does not pass as "cheap"


# ---------------------------------------------------------------------------------------------- the five checklists
def graham(f: Dict[str, Any]) -> List[Check]:
    pe, pb = f.get("pe"), f.get("pb")
    cheap_assets = None if pb is None else (pb <= 1.5 or (pe is not None and 0 < pe and pe * pb <= 22.5))
    return [("PER 15배 이하", _pe_ok(pe, 15), f"PER {_x(pe)}"),
            ("PBR 1.5배 이하이거나 PER×PBR 22.5 이하", cheap_assets, f"PBR {_x(pb, 2)}"),
            ("유동비율 2배 이상", _at_least(f.get("current_ratio"), 2.0), f"유동비율 {_x(f.get('current_ratio'), 2)}"),
            ("부채/자본 1배 이하", _at_most(f.get("debt_equity"), 1.0), _de(f.get("debt_equity"))),
            ("적자를 낸 해가 없음", _at_least(f.get("roe_years_positive"), 1.0), f"흑자 연도 {_pct(f.get('roe_years_positive'), 0)}"),
            ("배당이나 자사주로 돌려줌", f.get("returns_capital") if isinstance(f.get("returns_capital"), bool) else None, "주주 환원 " + ("있음" if f.get("returns_capital") else "없음" if f.get("returns_capital") is False else "자료 없음")),
            ("3년 주당이익이 늘었음", None if f.get("eps_cagr3") is None else f["eps_cagr3"] > 0, f"3년 주당이익 성장 연 {_pct(f.get('eps_cagr3'))}")]


def buffett(f: Dict[str, Any]) -> List[Check]:
    margin, years = f.get("fcf_margin"), f.get("fcf_years_positive")
    fcf = None if margin is None else False if margin < 0.05 else None if years is None else years >= 0.75
    return [("ROE 15% 이상", _at_least(f.get("roe"), 0.15), f"ROE {_pct(f.get('roe'))}"),
            ("영업이익률 15% 이상", _at_least(f.get("op_margin"), 0.15), f"영업이익률 {_pct(f.get('op_margin'))}"),
            ("부채/자본 0.8배 이하", _at_most(f.get("debt_equity"), 0.8), _de(f.get("debt_equity"))),
            ("적자를 낸 해가 없음", _at_least(f.get("roe_years_positive"), 1.0), f"흑자 연도 {_pct(f.get('roe_years_positive'), 0)}"),
            ("남는 현금이 매출의 5% 이상이고 꾸준함", fcf, f"잉여현금흐름 마진 {_pct(f.get('fcf_margin'))}"),
            ("주식 수를 늘리지 않음", _at_most(f.get("share_change"), 0.01), f"주식 수 변화 {_pct(f.get('share_change'))}"),
            ("PER 25배 이하", _pe_ok(f.get("pe"), 25), f"PER {_x(f.get('pe'))}")]


def munger(f: Dict[str, Any]) -> List[Check]:
    known = f.get("governance_issues") is not None or f.get("negative") is not None or bool(f.get("marks"))
    clean = None if not known else not ((f.get("governance_issues") or 0) > 0 or (f.get("negative") or 0) > 0 or f.get("marks"))
    gross, op = f.get("gross_margin"), f.get("op_margin")
    wide = (gross is not None and gross >= 0.40) or (op is not None and op >= 0.20)
    moat = True if wide else None if gross is None or op is None else False          # one margin missing and the other low: not known
    margins = ", ".join(x for x in (None if gross is None else f"매출총이익률 {_pct(gross)}", None if op is None else f"영업이익률 {_pct(op)}") if x) or "이익률 자료 없음"
    warn = ", ".join(f.get("marks") or []) or ("경고 공시 있음" if clean is False else "경고 공시 없음" if clean else "자료 없음")
    return [("경고 공시와 회피 표시가 없음", clean, warn),
            ("주식 수 희석 3% 이하", _at_most(f.get("share_change"), 0.03), f"주식 수 변화 {_pct(f.get('share_change'))}"),
            ("부채/자본 1배 이하", _at_most(f.get("debt_equity"), 1.0), _de(f.get("debt_equity"))),
            ("적자를 낸 해가 없음", _at_least(f.get("roe_years_positive"), 1.0), f"흑자 연도 {_pct(f.get('roe_years_positive'), 0)}"),
            ("ROE 15% 이상", _at_least(f.get("roe"), 0.15), f"ROE {_pct(f.get('roe'))}"),
            ("매출총이익률 40% 이상이거나 영업이익률 20% 이상", moat, margins),
            ("PER 30배 이하", _pe_ok(f.get("pe"), 30), f"PER {_x(f.get('pe'))}")]


def lynch(f: Dict[str, Any]) -> List[Check]:
    pe, g = f.get("pe"), f.get("eps_cagr3")
    peg = None if pe is None or g is None or pe <= 0 else (pe / (g * 100) if g > 0 else None)
    peg_ok = None if pe is None or g is None else (False if pe <= 0 or g <= 0 else peg <= 1.0)
    buys = None if f.get("insider_buy") is None or f.get("insider_sell") is None else f["insider_buy"] > f["insider_sell"]
    peg_shown = f"PEG {peg:.2f}" if peg is not None else "PEG 자료 없음" if peg_ok is None else "PEG 계산 안 됨(적자이거나 3년 이익이 줄었음)"
    return [("PEG(PER ÷ 이익 성장률) 1 이하", peg_ok, peg_shown),
            ("3년 주당이익 성장이 연 10~30%", None if g is None else 0.10 <= g <= 0.30, f"3년 주당이익 성장 연 {_pct(g)}"),
            ("최근 주당이익이 늘었음", None if f.get("eps_growth") is None else f["eps_growth"] > 0, f"최근 주당이익 성장 {_pct(f.get('eps_growth'))}"),
            ("최근 매출이 늘었음", None if f.get("rev_growth") is None else f["rev_growth"] > 0, f"최근 매출 성장 {_pct(f.get('rev_growth'))}"),
            ("부채/자본 0.8배 이하", _at_most(f.get("debt_equity"), 0.8), _de(f.get("debt_equity"))),
            ("내부자가 판 것보다 많이 삼", buys, "내부자 순매수 " + ("있음" if buys else "없음" if buys is False else "자료 없음")),
            ("PER 25배 이하", _pe_ok(pe, 25), f"PER {_x(pe)}")]


def druckenmiller(f: Dict[str, Any]) -> List[Check]:
    price, ma200 = f.get("price"), f.get("ma200")
    above = None if not price or not ma200 else price > ma200
    if f.get("eps_now") and f.get("eps_next") and f["eps_now"] > 0:
        earn, shown = f["eps_next"] > f["eps_now"], f"다음 해 예상 이익 {(f['eps_next'] / f['eps_now'] - 1) * 100:+.1f}%(야후 집계)"
    else:
        earn = None if f.get("eps_growth") is None else f["eps_growth"] > 0
        shown = f"최근 주당이익 성장 {_pct(f.get('eps_growth'))}"
    return [("시장 상태가 50 이상", _at_least(f.get("market_state"), 50.0), "시장 상태 " + ("자료 없음" if f.get("market_state") is None else f"{f['market_state']:.0f}/100")),
            ("가격이 200일선 위", above, "200일선 대비 " + ("자료 없음" if above is None else f"{(price / ma200 - 1) * 100:+.1f}%")),
            ("200일선이 오르는 중", None if f.get("ma200_slope") is None else f["ma200_slope"] > 0, f"200일선 기울기 {_pct(f.get('ma200_slope'))}"),
            ("상대 강도 상위 30%", _at_least(f.get("percentile"), 0.70), f"상대 강도 백분위 {_pct(f.get('percentile'), 0)}"),
            ("이익이 늘어나는 쪽", earn, shown),
            ("최근 1년 최대 낙폭이 30% 안쪽", _at_least(f.get("max_drawdown_252"), -0.30), f"최근 1년 최대 낙폭 {_pct(f.get('max_drawdown_252'))}"),
            ("12개월 수익이 양수", None if f.get("ret_12_1") is None else f["ret_12_1"] > 0, f"12개월 수익 {_pct(f.get('ret_12_1'))}")]


VIEWS: List[Tuple[str, str, str, Callable[[Dict[str, Any]], List[Check]]]] = [
    ("BUFFETT", "버핏식", "좋은 사업을 적정한 값에", buffett),
    ("MUNGER", "멍거식", "피할 것부터 걸러 내고 질을 본다", munger),
    ("GRAHAM", "그레이엄식", "안전마진, 싼 값과 튼튼한 재무", graham),
    ("LYNCH", "린치식", "이익 성장에 비해 싼가", lynch),
    ("DRUCKENMILLER", "드러켄밀러식", "큰 흐름과 추세의 편에 선다", druckenmiller),
]


# The criteria without which the approach is not itself (positions in each checklist).  A stock that misses one of them can at
# most "partly meet" that view however many other boxes it ticks: a stock at 40 times earnings is not a Graham stock because
# its balance sheet is clean, and a stock under its 200-day line is not a trend follower's because its earnings grew.  The same
# holds when a core figure is missing: a view cannot be "met" on the boxes around the one it is about (review 2026-11-22, before
# the first record: 9 US stocks met the Buffett view with no return on equity, 33 Korean stocks the Lynch view with no PEG).
CORE = {"BUFFETT": (0,), "MUNGER": (0,), "GRAHAM": (0, 1), "LYNCH": (0,), "DRUCKENMILLER": (1,)}


# ---------------------------------------------------------------------------------------------- one stock
def read_view(key: str, name: str, motto: str, checks: List[Check]) -> Dict[str, Any]:
    known = [c for c in checks if c[1] is not None]
    met = [c for c in known if c[1]]
    missed = [c for c in known if not c[1]]
    share = len(met) / len(known) if known else None
    verdict = UNKNOWN if len(known) < MIN_KNOWN else MEETS if share >= MEET_SHARE else PARTLY if share >= PART_SHARE else FAILS
    core = [checks[i] for i in CORE.get(key, ()) if i < len(checks)]
    core_missed, core_unknown = [c for c in core if c[1] is False], [c for c in core if c[1] is None]
    capped = verdict == MEETS and bool(core_missed or core_unknown)
    if capped:
        verdict = PARTLY
    why = " ".join(x for x in (f"핵심 기준({', '.join(c[0] for c in core_missed)})을 채우지 못해 '맞음'으로 보지 않습니다." if core_missed else "",
                               f"핵심 기준({', '.join(c[0] for c in core_unknown)})을 확인할 자료가 없어 '맞음'으로 보지 않습니다." if core_unknown else "") if x) if capped else ""
    line = f"{name}({motto}): 기준 {len(known)}개 중 {len(met)}개 충족, {VERDICT_KO[verdict]}." + (f" {why}" if why else "")
    if verdict == UNKNOWN:
        line = f"{name}({motto}): 확인할 수 있는 기준이 {len(known)}개뿐이라 판단하지 않았습니다."
    detail = []
    if met:
        detail.append("맞는 것: " + ", ".join(c[2] for c in met[:4]))
    if missed:
        detail.append("걸리는 것: " + ", ".join(f"{c[2]}(기준: {c[0]})" for c in missed[:3]))
    return {"key": key, "name": name, "motto": motto, "verdict": verdict, "verdict_label": VERDICT_KO[verdict], "met": len(met), "known": len(known), "share": share, "core_missed": [c[0] for c in core_missed],
            "core_unknown": [c[0] for c in core_unknown], "capped": why, "line": line, "detail": ". ".join(detail) + ("." if detail else ""), "checks": [{"ask": c[0], "met": c[1], "shown": c[2]} for c in checks]}


def opinions(long_snap: Optional[Dict[str, Any]], swing_snap: Optional[Dict[str, Any]] = None, info: Optional[Dict[str, Any]] = None, marks: Iterable[str] = ()) -> Dict[str, Any]:
    f = figures(long_snap, swing_snap, info, marks)
    views = [read_view(key, name, motto, fn(f)) for key, name, motto, fn in VIEWS]
    agree = [v["name"] for v in views if v["verdict"] == MEETS]
    judged = [v for v in views if v["verdict"] != UNKNOWN]
    return {"views": views, "agree": len(agree), "agree_names": agree, "judged": len(judged), "in_team": len(agree) >= AGREE,
            "mean_share": sum(v["share"] for v in judged) / len(judged) if judged else None}


def team_line(op: Dict[str, Any]) -> str:
    if not op["judged"]:
        return "다섯 관점 모두 자료가 모자라 판단하지 않았습니다."
    who = f"({', '.join(op['agree_names'])})" if op["agree_names"] else ""
    tail = "과반이 맞다고 봐 팀 목록에 듭니다." if op["in_team"] else f"팀 목록은 {AGREE}개 관점 이상이 맞다고 볼 때 듭니다."
    return f"다섯 관점 가운데 {op['agree']}개가 '기준에 맞음'{who}. {tail}"


def lines(op: Dict[str, Any], detail: bool = True) -> List[str]:
    """One or two lines per view, the team line, and what this is not."""
    out = []
    for v in op["views"]:
        out.append(v["line"] + (f" {v['detail']}" if detail and v["detail"] and v["verdict"] != UNKNOWN else ""))
    return out + [team_line(op), NOTE]


# ---------------------------------------------------------------------------------------------- the team list
def team(stocks: Iterable[Dict[str, Any]], size: int = TEAM_SIZE) -> Dict[str, Any]:
    """``stocks``: {ticker, name, long, swing, info, marks}.  The stocks at least ``AGREE`` views find to meet their criteria,
    most agreement first (then the mean share of criteria met), at most ``size``, equal weight.  It can be empty."""
    rows, tally, judged, verdicts = [], {key: 0 for key, *_ in VIEWS}, 0, {}
    for s in stocks:
        op = opinions(s.get("long"), s.get("swing"), s.get("info"), s.get("marks") or ())
        if not op["judged"]:
            continue
        judged += 1
        verdicts[s["ticker"]] = "".join(v["verdict"][0] for v in op["views"])          # M, P, F or U per view, in the order of VIEWS
        for v in op["views"]:
            tally[v["key"]] += v["verdict"] == MEETS
        if op["in_team"]:
            rows.append({"ticker": s["ticker"], "name": s.get("name") or s["ticker"], "sector": s.get("sector"), "agree": op["agree"], "agree_names": op["agree_names"],
                         "mean_share": round(op["mean_share"], 4)})
    rows.sort(key=lambda r: (-r["agree"], -r["mean_share"], r["ticker"]))
    picked = rows[:size]
    for r in picked:
        r["weight"] = round(1 / len(picked), 4)
    return {"picked": picked, "eligible": len(rows), "judged": judged, "meets_by_view": tally, "agree_needed": AGREE, "size": size, "verdicts": verdicts}


def team_lines(t: Dict[str, Any], market_ko: str) -> List[str]:
    names = {key: name for key, name, *_ in VIEWS}
    tally = ", ".join(f"{names[k]} {n}개" for k, n in t["meets_by_view"].items())
    if not t["picked"]:
        return [f"{market_ko} {t['judged']}종목 가운데 다섯 관점 중 {t['agree_needed']}개 이상이 '기준에 맞음'으로 본 종목이 없습니다. 목록을 억지로 채우지 않습니다.",
                f"관점별로 기준에 맞는 종목 수: {tally}.", NOTE]
    out = [f"{market_ko} {t['judged']}종목 가운데 {t['eligible']}종목이 과반 합의({t['agree_needed']}개 관점 이상)에 들었고, 합의가 많은 순으로 {len(t['picked'])}종목입니다. 비중은 같게 {t['picked'][0]['weight'] * 100:.0f}%씩입니다."]
    out += [f"{r['name']}({r['ticker']}): {r['agree']}개 관점({', '.join(r['agree_names'])}), 기준 충족 평균 {r['mean_share'] * 100:.0f}%." for r in t["picked"]]
    sectors: Dict[str, int] = {}
    for r in t["picked"]:
        if r.get("sector"):
            sectors[r["sector"]] = sectors.get(r["sector"], 0) + 1
    if sectors:
        top = sorted(sectors.items(), key=lambda kv: -kv[1])[:3]
        out.append("업종: " + ", ".join(f"{k} {n}" for k, n in top) + ". 한 업종에 몰려 있으면 종목 수만큼 분산된 것이 아닙니다.")
        if sum(n for k, n in sectors.items() if k in FINANCIAL) * 2 >= len(t["picked"]):
            out.append("금융업이 절반 이상입니다. 금융업은 영업이익률·현금흐름·유동비율 기준이 비어 더 적은 기준으로 판단되고 PER·PBR이 낮게 나오는 업종이라, 다섯 관점 모두에서 유리합니다.")
    out += [f"관점별로 기준에 맞는 종목 수: {tally}.", "주문을 내지 않는 참고 목록입니다. 수량과 손절은 계산하지 않습니다.", NOTE]
    return out


# ---------------------------------------------------------------------------------------------- the record
def record(base: Path, market: str, session: str, t: Dict[str, Any]) -> Dict[str, Any]:
    """One line per session, appended once: the picked stocks with their agreement, how many stocks each view accepted, and every
    judged stock's five verdicts as five letters (``views`` gives their order; M meets, P partly, F fails, U not judged), so that
    a later question about any view can be asked of the record and not of a reconstruction.
    A record only: no verdict is defined for it (user decision 2026-11-22)."""
    folder = Path(base) / "research_data" / FOLDERS[market]
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{session[:7]}.jsonl"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                if json.loads(line).get("session") == session:
                    return {"status": "ALREADY", "session": session}
            except ValueError:
                continue
    row = {"session": session, "market": market, "rules": "FV-1", "agree_needed": t["agree_needed"], "judged": t["judged"], "eligible": t["eligible"], "meets_by_view": t["meets_by_view"],
           "picked": [{k: r[k] for k in ("ticker", "agree", "agree_names", "mean_share", "weight")} for r in t["picked"]],
           "views": [key for key, *_ in VIEWS], "verdicts": t.get("verdicts") or {}}
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    return {"status": "OK", "session": session, "picked": len(t["picked"])}
