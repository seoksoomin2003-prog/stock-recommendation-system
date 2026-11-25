"""What a desk analyst adds beside a stored score, each from data already on disk and none of it a score.

    exposure        what a stock has moved with: the market, its own sector fund and a theme fund beyond the market, a rate or a currency
    concentration   whether the day's buy candidates are one bet: their sectors, how alike they move, how defensive they are
    liked_but_marked  stocks the score likes that carry an avoid mark (the side the Korean tests found evidence on)
    change_since    what changed in a stock's score since the records of a week and a month ago
    fund_age        how old the statements behind the score are, and the score fresher statements would give
    fund_gaps       stocks whose two scores (annual statements, trailing four quarters) are far apart
    newly_marked    avoid marks that are on the newest record and were not on the one before

Reference only.  Nothing here feeds the score, the order plan or any record, and none of it says where a price will go:
co-movement is what happened in the window, not a cause and not a forecast.
"""
import math
from datetime import date
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

DAYS = 120                  # sessions of daily returns read
MIN_DAYS = 60
FACTOR_TTL = 20 * 3600
CLEAR = 0.15                # a partial correlation under this is "no clear relation"
WATCH = 55.0                # the score from which the screen says "watch"
BUY = 70.0
ONE_SECTOR = 0.30           # a third of the candidates in one sector
ALIKE = 0.40                # mean pairwise correlation from which candidates are said to move together
DEFENSIVE = 0.80            # mean market beta under which they are said to be defensive
BACK = ((5, "1주 전"), (21, "1개월 전"))
OLD_DAYS = 270              # statements older than this are said to be old
# market: the index.  others: (symbol, name, kind).  RETURN: a price whose daily return is read.  YIELD: a yield in percent whose
# daily change in percentage points is read.
FACTORS = {"US": {"market": ("SPY", "S&P 500"), "others": [("SOXX", "반도체 지수(SOXX)", "RETURN"), ("^TNX", "미국 10년물 금리", "YIELD")]},
           "KR": {"market": ("^KS11", "코스피"), "others": [("091160.KS", "반도체(KODEX 반도체)", "RETURN"), ("KRW=X", "원/달러 환율", "RETURN")]}}
DOMAIN_KO = {"TECHNICAL": "기술", "FUNDAMENTAL": "재무", "RISK": "위험", "EVENTS": "이벤트", "EVENT": "이벤트", "REGIME": "시장 국면"}
CAVEAT = "최근 {n}거래일 동안 같이 움직인 정도입니다. 원인이 아니고, 앞으로도 그렇다는 뜻이 아닙니다."
GAP = 10.0                  # points between the two scores from which a stock is listed
KR_YIELD = ("KTB3Y", "국고채 3년 금리", "YIELD")
# Yahoo's sector names, as the US rotation funds are named on the market tab
SECTOR_KO = {"Technology": "기술", "Financial Services": "금융", "Healthcare": "헬스케어", "Consumer Cyclical": "경기소비재", "Consumer Defensive": "필수소비재", "Industrials": "산업재",
             "Basic Materials": "소재", "Energy": "에너지", "Utilities": "유틸리티", "Real Estate": "부동산", "Communication Services": "커뮤니케이션"}


def _closes(rows: Optional[Sequence[Dict[str, Any]]]) -> Dict[str, float]:
    out = {}
    for r in rows or []:
        v = r.get("adj_close") or r.get("close")
        if isinstance(v, (int, float)) and math.isfinite(v) and v > 0 and r.get("date"):
            out[r["date"]] = float(v)
    return out


def _moves(closes: Dict[str, float], kind: str = "RETURN") -> Dict[str, float]:
    days = sorted(closes)
    return {b: (closes[b] - closes[a] if kind == "YIELD" else closes[b] / closes[a] - 1) for a, b in zip(days, days[1:])}


def factor_data(terminal: Any, market: str) -> Dict[str, List[Dict[str, Any]]]:
    """A year of daily prices of the market's index and its reference series, kept for a day."""
    spec = FACTORS[market]
    syms = [spec["market"][0]] + [s for s, _, _ in spec["others"]]
    return terminal.cache.cached(f"exposure:{market}:1y", FACTOR_TTL, lambda: terminal.src.yahoo_history(syms, "1y"))["data"] or {}


def own_sector(terminal: Any, market: str, row: Optional[Dict[str, Any]]) -> Optional[Tuple[str, str, List[Dict[str, Any]]]]:
    """(symbol, name, daily prices) of the rotation fund the stock belongs to, from the prices the market tab already keeps."""
    from terminal import services
    from terminal.qsf import sector_picks
    if not row:
        return None
    bench, _, funds = terminal.ROTATION[market]
    hit = next(((sym, name) for sym, name in funds if sector_picks.member(market, sym, row)), None)
    if not hit:
        return None
    data = terminal.cache.cached(f"rotation:{market}:2y", services.TTL["chart"], lambda: terminal.src.yahoo_history([bench] + [f for f, _ in funds], "2y"))["data"] or {}
    return (hit[0], f"자기 업종({hit[1]} ETF)", data.get(hit[0]) or [])


def kr_yield(terminal: Any) -> List[Dict[str, Any]]:
    """The 3-year treasury yield the Korean market state already downloads from the Bank of Korea, as daily rows; [] when absent."""
    rec = terminal.qsf.cache.read("ecos:kr_credit_spread") or {}
    return [{"date": d, "close": v} for d, v in ((rec.get("data") or {}).get("treasury") or []) if v is not None]


def exposure(stock_rows: Sequence[Dict[str, Any]], data: Dict[str, List[Dict[str, Any]]], market: str, days: int = DAYS,
             extra: Sequence[Tuple[str, str, str]] = ()) -> Optional[Dict[str, Any]]:
    """The stock's market beta, and for each reference series what is left of their co-movement once the market is taken out:
    the coefficient of the series in a regression on the market and the series together, and the partial correlation.
    ``extra``: more (key, name, kind) series whose rows are in ``data``, read before the market's own list; a key seen twice is read once."""
    spec = FACTORS[market]
    y, m = _moves(_closes(stock_rows)), _moves(_closes(data.get(spec["market"][0])))
    both = sorted(set(y) & set(m))[-days:]
    if len(both) < MIN_DAYS:
        return None
    ys, ms = np.array([y[d] for d in both]), np.array([m[d] for d in both])
    if ms.var() <= 0:
        return None
    out = {"days": len(both), "from": both[0], "to": both[-1], "market": spec["market"][1], "beta": float(np.cov(ys, ms, ddof=1)[0, 1] / ms.var(ddof=1)), "others": []}
    seen = set()
    for sym, name, kind in list(extra) + list(spec["others"]):
        if sym in seen:
            continue
        seen.add(sym)
        x = _moves(_closes(data.get(sym)), kind)
        common = sorted(set(both) & set(x))
        if len(common) < MIN_DAYS:
            continue
        yy, mm, xx = (np.array([s[d] for d in common]) for s in (y, m, x))
        coef = np.linalg.lstsq(np.column_stack([np.ones(len(common)), mm, xx]), yy, rcond=None)[0]
        res = lambda v: v - np.polyval(np.polyfit(mm, v, 1), mm)      # noqa: E731
        ry, rx = res(yy), res(xx)
        corr = float(np.corrcoef(ry, rx)[0, 1]) if ry.std() > 0 and rx.std() > 0 else None
        out["others"].append({"symbol": sym, "name": name, "kind": kind, "coef": float(coef[2]), "partial_corr": corr, "days": len(common)})
    return out


def exposure_lines(e: Optional[Dict[str, Any]]) -> List[str]:
    if not e:
        return ["가격 이력이 모자라 계산하지 못했습니다(60거래일 필요)."]
    lines = [f"시장 베타 {e['beta']:.2f}: {e['market']} 지수가 1% 움직인 날 평균 {e['beta']:+.2f}% 움직였습니다."]
    for o in e["others"]:
        if o["partial_corr"] is None:
            continue
        if abs(o["partial_corr"]) < CLEAR:
            lines.append(f"{o['name']}: 시장 움직임을 빼고 나면 뚜렷한 관계가 없습니다(부분 상관 {o['partial_corr']:+.2f}).")
        elif o["kind"] == "YIELD":
            lines.append(f"{o['name']}: 금리가 0.10%p 오른 날 시장 대비 평균 {o['coef'] * 0.10 * 100:+.2f}% 움직였습니다(부분 상관 {o['partial_corr']:+.2f}).")
        else:
            lines.append(f"{o['name']}: 시장보다 1% 더 오른 날 이 종목은 시장 대비 평균 {o['coef']:+.2f}% 움직였습니다(부분 상관 {o['partial_corr']:+.2f}).")
    return lines + [CAVEAT.format(n=e["days"])]


# ---------------------------------------------------------------------- the day's candidates as a group
def concentration(tickers: Sequence[str], sector_of: Callable[[str], Optional[str]], loader: Callable[[str], Sequence[Dict[str, Any]]], bench: Sequence[Dict[str, Any]], days: int = DAYS) -> Dict[str, Any]:
    """Sectors of the candidates, their mean pairwise correlation and their mean market beta over the last ``days`` sessions."""
    sectors: Dict[str, int] = {}
    for t in tickers:
        s = sector_of(t) or "분류 없음"
        sectors[s] = sectors.get(s, 0) + 1
    out: Dict[str, Any] = {"n": len(tickers), "sectors": sorted(sectors.items(), key=lambda kv: (-kv[1], kv[0])), "mean_corr": None, "mean_beta": None, "measured": 0}
    m = _moves(_closes(bench))
    series = {t: _moves(_closes(loader(t))) for t in tickers}
    common = sorted(set(m).intersection(*[set(s) for s in series.values()]))[-days:] if series else []
    used = [t for t in tickers if series[t]]
    if len(used) >= 2 and len(common) >= MIN_DAYS:
        R = np.array([[series[t][d] for d in common] for t in used])
        ms = np.array([m[d] for d in common])
        ok = R.std(axis=1) > 0
        if ok.sum() >= 2 and ms.var() > 0:
            c = np.corrcoef(R[ok])
            n = int(ok.sum())
            out.update(mean_corr=float((c.sum() - n) / (n * (n - 1))), mean_beta=float(np.mean([np.cov(r, ms, ddof=1)[0, 1] / ms.var(ddof=1) for r in R[ok]])), measured=n, days=len(common))
    return out


def concentration_line(c: Dict[str, Any]) -> Optional[str]:
    """One sentence on the candidates as a group, or None when there are fewer than three."""
    if c["n"] < 3:
        return None
    top, count = c["sectors"][0]
    mix = ", ".join(f"{s} {n}" for s, n in c["sectors"][:4])
    said = [f"상위 구간 후보 {c['n']}개의 업종: {mix}" + (" 등" if len(c["sectors"]) > 4 else "") + "."]
    flags = []
    if count / c["n"] >= ONE_SECTOR:
        flags.append(f"{top} 한 업종이 {count / c['n'] * 100:.0f}%")
    if c["mean_corr"] is not None:
        said.append(f"서로의 평균 상관 {c['mean_corr']:.2f}, 평균 시장 베타 {c['mean_beta']:.2f}(최근 {c['days']}거래일).")
        if c["mean_corr"] >= ALIKE:
            flags.append("서로 같이 움직이는 편")
        if c["mean_beta"] < DEFENSIVE:
            flags.append("시장보다 덜 움직이는 방어주 쪽")
    if flags:
        said.append(f"{', '.join(flags)}입니다. {c['n']}개를 사도 {c['n']}개로 나뉜 분산이 아닙니다.")
    return " ".join(said)


# ---------------------------------------------------------------------- what a high score looks like (user decision 2026-11-25)
TILT_MIN = 30                   # scored stocks a day under which the line is not written
NEAR_HIGH = -0.05               # within five percent of the 52-week high


def _raw(snap: Dict[str, Any], fid: str, key: str) -> Optional[float]:
    v = next(((f.get("raw") or {}).get(key) for f in snap.get("factors") or [] if f.get("factor") == fid and isinstance(f.get("raw"), dict)), None)
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and np.isfinite(v) else None


def tilt(snaps: Sequence[Dict[str, Any]], strategy: str = "SWING") -> Optional[Dict[str, Any]]:
    """How the day's top fifth by score differs from every scored stock, from the recorded factor values alone: the median
    volatility and the share standing near the 52-week high.  No return is read.  The record of the current formula on used
    windows found one thing the top fifth had in all four scores, lower volatility, and no return edge (BT-1); this line shows
    the shape a high score picks, so the list is read as a style and not as "the better stocks"."""
    rows = [s for s in snaps if s.get("strategy") == strategy and s.get("score") is not None and s.get("actionability") == "ACTIONABLE"]
    if len(rows) < TILT_MIN:
        return None
    rows.sort(key=lambda s: -float(s["score"]))
    top = rows[:max(1, len(rows) // 5)]

    def med(group, fid, key):
        v = [x for x in (_raw(s, fid, key) for s in group) if x is not None]
        return float(np.median(v)) if len(v) >= max(3, len(group) // 2) else None

    def share(group):
        v = [x for x in (_raw(s, "breakout_volume", "dist_high") for s in group) if x is not None]
        return float(np.mean([x >= NEAR_HIGH for x in v])) if len(v) >= max(3, len(group) // 2) else None
    return {"strategy": strategy, "n": len(rows), "top_n": len(top), "vol_top": med(top, "atr_risk", "hist_vol"), "vol_all": med(rows, "atr_risk", "hist_vol"),
            "near_high_top": share(top), "near_high_all": share(rows)}


def tilt_line(t: Optional[Dict[str, Any]]) -> Optional[str]:
    if not t or (t["vol_top"] is None and t["near_high_top"] is None):
        return None
    parts = []
    if t["vol_top"] is not None and t["vol_all"] is not None:
        parts.append(f"최근 변동성(연 환산)의 중앙값 {t['vol_top'] * 100:.0f}%(스캔 전체 {t['vol_all'] * 100:.0f}%)")
    if t["near_high_top"] is not None and t["near_high_all"] is not None:
        parts.append(f"52주 고점에서 5% 안에 있는 종목 {t['near_high_top'] * 100:.0f}%(전체 {t['near_high_all'] * 100:.0f}%)")
    if not parts:
        return None
    return (f"스윙 점수 상위 5분의 1({t['top_n']}종목)의 모양: " + ", ".join(parts) + ". 높은 점수는 '더 오를 종목'이 아니라 이런 모양의 종목을 고른 것입니다. "
            "높은 점수가 더 오른다는 근거는 아직 확인되지 않았습니다.")


def tilt_long(snaps: Sequence[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """The same for the long-term score (score audit 2026-11-25, P2-4): the top fifth's median price-to-earnings ratio (companies
    with earnings only), return on equity and downside volatility beside the whole scan's.  Recorded factor values; no return."""
    rows = [s for s in snaps if s.get("strategy") == "LONG_TERM" and s.get("score") is not None and s.get("actionability") == "ACTIONABLE"]
    if len(rows) < TILT_MIN:
        return None
    rows.sort(key=lambda s: -float(s["score"]))
    top = rows[:max(1, len(rows) // 5)]

    def med(group, fid, key, positive=False):
        v = [x for x in (_raw(s, fid, key) for s in group) if x is not None and (x > 0 or not positive)]
        return float(np.median(v)) if len(v) >= max(3, len(group) // 2) else None
    out: Dict[str, Any] = {"n": len(rows), "top_n": len(top)}
    for name, fid, key, positive in (("pe", "valuation", "pe", True), ("roe", "business_quality", "roe", False), ("down_vol", "downside_drawdown", "downside_vol", False)):
        out[f"{name}_top"], out[f"{name}_all"] = med(top, fid, key, positive), med(rows, fid, key, positive)
    return out


def tilt_long_line(t: Optional[Dict[str, Any]]) -> Optional[str]:
    if not t:
        return None
    parts = []
    if t["pe_top"] is not None and t["pe_all"] is not None:
        parts.append(f"PER 중앙값 {t['pe_top']:.1f}배(스캔 전체 {t['pe_all']:.1f}배, 흑자 회사만)")
    if t["roe_top"] is not None and t["roe_all"] is not None:
        parts.append(f"ROE 중앙값 {t['roe_top'] * 100:.0f}%(전체 {t['roe_all'] * 100:.0f}%)")
    if t["down_vol_top"] is not None and t["down_vol_all"] is not None:
        parts.append(f"하방 변동성 중앙값 {t['down_vol_top'] * 100:.0f}%(전체 {t['down_vol_all'] * 100:.0f}%)")
    if not parts:
        return None
    return (f"장기 점수 상위 5분의 1({t['top_n']}종목)의 모양: " + ", ".join(parts) + ". 높은 점수는 이런 모양의 회사를 고른 것이고, 더 오른다는 근거는 아직 확인되지 않았습니다.")


# ---------------------------------------------------------------------- liked by the score, flagged by an avoid mark
def marks_of(row: Dict[str, Any]) -> List[str]:
    out = []
    if (row.get("filing_events") or {}).get("financing"):
        out.append("자금 조달 공시")
    if row.get("high_risk"):
        out.append("고위험")
    return out


def liked_but_marked(rows: Sequence[Dict[str, Any]], mine: Sequence[str] = ()) -> Dict[str, List[Dict[str, Any]]]:
    """``liked``: swing rows at or over the watch line that carry a mark, highest score first.  ``mine``: held or watched stocks
    that carry one, whatever their score."""
    marked = [{"ticker": r["ticker"], "name": r.get("name"), "score": r.get("score"), "marks": marks_of(r)} for r in rows if r.get("strategy") == "SWING" and marks_of(r)]
    return {"liked": sorted((r for r in marked if (r["score"] or 0) >= WATCH), key=lambda r: -(r["score"] or 0)), "mine": [r for r in marked if r["ticker"] in set(mine)]}


# ---------------------------------------------------------------------- what changed since the last notes
def change_since(ledger: Any, market: str, ticker: str, strategy: str, back: Sequence[Tuple[int, str]] = BACK) -> List[Dict[str, Any]]:
    """The stock's score and domain scores now and ``n`` recorded sessions ago, read from the ledger's light side files."""
    by_day: Dict[str, List[Dict[str, Any]]] = {}
    for r in ledger._rows():
        if r["market"] == market:
            by_day.setdefault(r["session"], []).append(r)
    days = sorted(by_day)

    def at(day: str) -> Optional[Dict[str, Any]]:
        for r in by_day[day]:
            got = (ledger.side(r).get(ticker) or {}).get(strategy)
            if got and got.get("data_date") == day and got.get("score") is not None:
                return got
        return None
    now = at(days[-1]) if days else None
    out = []
    for n, label in back:
        if now is None or len(days) <= n:
            continue
        then = at(days[-1 - n])
        if then is None:
            continue
        doms = {d: (now["domains"].get(d) or {}).get("score_100") - (then["domains"].get(d) or {}).get("score_100") for d in now.get("domains") or {}
                if (now["domains"].get(d) or {}).get("score_100") is not None and (then.get("domains") or {}).get(d, {}).get("score_100") is not None}
        out.append({"label": label, "session": days[-1 - n], "then": float(then["score"]), "now": float(now["score"]), "diff": float(now["score"]) - float(then["score"]), "domains": doms,
                    "band": (then.get("band"), now.get("band")), "versions": (then.get("model_version"), now.get("model_version"))})
    return out


def change_lines(changes: List[Dict[str, Any]], band_ko: Callable[[Optional[str]], str] = lambda b: str(b)) -> List[str]:
    lines = []
    for c in changes:
        moved = sorted(((d, v) for d, v in c["domains"].items() if abs(v) >= 3 and d != "REGIME"), key=lambda kv: -abs(kv[1]))[:3]
        parts = ", ".join(f"{DOMAIN_KO.get(d, d)} {v:+.0f}" for d, v in moved)
        line = f"{c['label']}({c['session']}) 기록 대비: 점수 {c['then']:.1f} → {c['now']:.1f}({c['diff']:+.1f})."
        line += f" 영역 점수 변화: {parts}." if parts else " 영역 점수는 3점 넘게 움직인 곳이 없습니다."
        if c["band"][0] != c["band"][1]:
            line += f" 구간이 '{band_ko(c['band'][0])}'에서 '{band_ko(c['band'][1])}'(으)로 바뀌었습니다."
        if c["versions"][0] != c["versions"][1]:
            line += f" 그 사이 공식 버전이 바뀌어({c['versions'][0]} → {c['versions'][1]}) 차이에 공식 변경이 섞여 있습니다."
        lines.append(line)
    return lines


# ---------------------------------------------------------------------- how old the statements are
def fund_age_lines(snap: Dict[str, Any], session: str) -> List[str]:
    """The age of the statements the score read, and what the other period's statements give (reports/QSF_FUND_PERIOD_PROTOCOL.md)."""
    fp = snap.get("fund_period") or {}
    live = fp.get((fp.get("live") or "ANNUAL").lower()) or {}
    end = live.get("fiscal_end")
    filed = live.get("filed") or (snap.get("provenance") or {}).get("fund_filed")
    age = lambda d: (date.fromisoformat(session) - date.fromisoformat(d)).days      # noqa: E731
    lines = []
    if end:
        kind = "연간 보고서" if fp.get("live") != "TRAILING" else "최근 4분기"
        lines.append(f"점수가 읽은 재무: {end}까지({kind}, 기준일에서 {age(end)}일 지남" + (f", 보고서 제출 {filed}" if filed else "") + ")." + (" 오래된 자료입니다." if age(end) > OLD_DAYS else ""))
    elif filed:
        lines.append(f"점수가 읽은 재무 보고서 제출일: {filed}({age(filed)}일 전).")
    other_key = "trailing" if fp.get("live") != "TRAILING" else "annual"
    other = fp.get(other_key) or {}
    if other.get("score") is not None and live.get("score") is not None and other_key == "trailing":
        if other.get("newer_quarter"):
            diff = other["score"] - live["score"]
            lines.append(f"최근 4분기 재무({other.get('fiscal_end')}까지)로 계산하면 {other['score']:.1f}점으로, 지금 점수보다 {abs(diff):.1f}점 {'높습니다' if diff > 0 else '낮습니다' if diff < 0 else '같습니다'}. "
                         "이 점수는 매일 따로 기록만 하고 라이브에 쓰지 않습니다(과거 시험에서 더 낫다는 근거가 없었고, 240거래일 뒤 한 번 읽어 정합니다).")
        else:
            lines.append("연간 보고서보다 새로운 분기 보고서가 없어, 최근 4분기 기준 점수도 같습니다.")
    elif other.get("score") is not None and live.get("score") is not None:
        lines.append(f"연간 보고서({other.get('fiscal_end')}까지)로 계산하면 {other['score']:.1f}점입니다. 라이브는 판정에 따라 최근 4분기 재무를 씁니다.")
    return lines


# ---------------------------------------------------------------------- the two scores far apart
def fund_gaps(snaps: Sequence[Dict[str, Any]], interest: Sequence[str] = (), gap: float = GAP, strategy: str = "LONG_TERM") -> Dict[str, Any]:
    """Stocks whose score on annual statements and on trailing four quarters differ by ``gap`` points or more (one strategy).
    ``listed``: those among ``interest`` (held, watched, candidates), widest first.  ``all``: how many in the whole scan."""
    rows = []
    for s in snaps:
        fp = s.get("fund_period") or {}
        a, t = (fp.get("annual") or {}).get("score"), (fp.get("trailing") or {}).get("score")
        if s.get("strategy") != strategy or a is None or t is None or not (fp.get("trailing") or {}).get("newer_quarter") or abs(t - a) < gap:
            continue
        rows.append({"ticker": s["ticker"], "annual": a, "trailing": t, "diff": t - a, "live": fp.get("live"), "annual_end": (fp.get("annual") or {}).get("fiscal_end")})
    mine = set(interest)
    return {"all": len(rows), "up": sum(1 for r in rows if r["diff"] > 0), "listed": sorted((r for r in rows if r["ticker"] in mine), key=lambda r: -abs(r["diff"]))}


def gap_line(fp: Optional[Dict[str, Any]], strategy: str, gap: float = GAP) -> Optional[str]:
    """One stock's sentence when its long-term score differs by ``gap`` points or more between the two statement bases.  The
    card kept both scores but showed the difference only inside a folded section (assessment 2026-11-25: INCY 82.5 against 64.8);
    this line goes where the conclusion is read.  Display only: the live score and the record are as they were."""
    fp = fp or {}
    a, t = (fp.get("annual") or {}).get("score"), (fp.get("trailing") or {}).get("score")
    if strategy != "LONG_TERM" or a is None or t is None or not (fp.get("trailing") or {}).get("newer_quarter") or abs(t - a) < gap:
        return None
    live = "최근 4분기" if fp.get("live") == "TRAILING" else "연간"
    return (f"재무 기준에 따라 장기 점수가 크게 다릅니다: 연간 재무로 {a:.1f}점, 최근 4분기 재무로 {t:.1f}점({t - a:+.1f}점). 화면의 점수는 {live} 기준입니다. "
            "최근 분기 실적이 연간 숫자와 다른 쪽으로 움직였다는 뜻이니 실적을 직접 확인하세요.")


# ---------------------------------------------------------------------- marks that are new today
def newly_marked(base: Any) -> Dict[str, Any]:
    """Korean avoid marks on the newest record that the record before did not carry.  A code the earlier record did not know is
    left out: new to the record is not newly marked."""
    from terminal.qsf import kr_events_forward, kr_forward
    out: Dict[str, Any] = {"financing": [], "high_risk": [], "session": None, "previous": None}
    try:
        now, then = kr_events_forward.marks(base), kr_events_forward.marks(base, 1)
        if now["session"] and then["session"]:
            out.update(session=now["session"], previous=then["session"], financing=sorted((set(now["financing"]) - set(then["financing"])) & set(then["known"])))
    except (OSError, ValueError, KeyError):
        pass
    try:
        now, then = kr_forward.high_risk(base), kr_forward.high_risk(base, 1)
        if now["session"] and then["session"]:
            out.update(high_risk=sorted((set(now["codes"]) - set(then["codes"])) & set(then["ranked"])), risk_session=now["session"], risk_previous=then["session"])
    except (OSError, ValueError, KeyError):
        pass
    return out
