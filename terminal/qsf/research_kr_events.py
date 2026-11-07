"""Pre-registered Korean filing-event test.  Rules: reports/QSF_KR_EVENTS_PROTOCOL.md.

Two yes-or-no signals from the market-wide OpenDART list of major-matter reports: a financing decision and a buyback decision in the last
252 sessions.  Only the first filing counts, usable from the day after its receipt date, so an amendment cannot reach back or extend a signal.
The evaluation runs once and a second run is refused.  Nothing here changes the live score or P6-11B.
"""
import bisect
import gzip
import json
import os
import re
import time
from datetime import date
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

from terminal.qsf import config, dart_history as dh, research_ensemble as en, research_kr as kr, research_kr_fund as kf, research_swing as rs, validate
from terminal.qsf.research_score import test_verdict

PROTOCOL = "reports/QSF_KR_EVENTS_PROTOCOL.md"
REPORT = Path("reports") / "qsf" / "QSF_KR_EVENTS.json"
DATA = Path("research_data") / "dart" / "events"
FEATURES = DATA / "features.npz"
REF_START, TEST_START = kf.REF_START, kf.TEST_START
FIRST_YEAR = 2016
WINDOW = 252
HORIZONS = kr.HORIZONS
FINANCING = ("유상증자결정", "유무상증자결정", "전환사채권발행결정", "신주인수권부사채권발행결정")
BUYBACK = ("자기주식취득결정", "자기주식취득신탁계약체결결정")
KINDS = {**{t: "financing" for t in FINANCING}, **{t: "buyback" for t in BUYBACK}}
SIGNALS = ("financing", "buyback")
FORM = re.compile(r"^주요사항보고서\((.+)\)$")
MAX_CALLS = 3000
MIN_KEPT = 0.9             # a quarter asked again may lose a withdrawn filing, not a tenth of its list
LIMIT, NO_DATA = "020", "013"
KEY_TROUBLE = ("010", "011", "012", "901")
PORTFOLIO_PERIODS = {"2018_2021": (REF_START, TEST_START), "2022_2023": (TEST_START, "2024-01-01"), "2024_on": ("2024-01-01", "2099"), "2022_on": (TEST_START, "2099")}


def classify(report_nm: Optional[str]) -> Optional[str]:
    """The signal a first filing belongs to.  An amendment, an extension or a subsidiary's report starts with a bracket or has another title."""
    m = FORM.match(re.sub(r"\s+", "", report_nm or ""))
    return KINDS.get(m.group(1)) if m else None


def quarters(first_year: int, last: date) -> List[Tuple[str, str, str]]:
    """Name, first day and last day of each calendar quarter up to ``last``: the list reads at most three months without a company."""
    ends = (("0331", "Q1", "0101"), ("0630", "Q2", "0401"), ("0930", "Q3", "0701"), ("1231", "Q4", "1001"))
    out = []
    for y in range(first_year, last.year + 1):
        for end, q, start in ends:
            if f"{y}{start}" > last.strftime("%Y%m%d"):
                continue
            out.append((f"{y}{q}", f"{y}{start}", min(f"{y}{end}", last.strftime("%Y%m%d"))))
    return out


def download(base: Path, log=print, get: Optional[Callable[..., Any]] = None, sleep: Callable[[float], None] = time.sleep, today: Optional[date] = None, pause: float = 0.2,
             key: Optional[str] = None, root: Optional[Path] = None, first_year: int = FIRST_YEAR, refresh: Optional[Callable[[str], bool]] = None) -> Dict[str, Any]:
    """A finished quarter stored once is not asked again, unless ``refresh`` names it.  Stops at once on the daily limit or a key problem.  Errors report the type only.
    A quarter asked again keeps its stored list if the new one is empty or much shorter: an odd answer must not erase filings."""
    key = key or os.environ.get("OPENDART_API_KEY")
    if not key:
        return {"status": "NO_KEY"}
    if get is None:
        import requests
        get = requests.get
    root = root or base / DATA
    root.mkdir(parents=True, exist_ok=True)
    today = today or date.today()
    corp_file = root / "corp.json"
    if not corp_file.exists():
        r = get(dh.BASE + "corpCode.xml", params={"crtfc_key": key}, timeout=120)
        corp_file.write_text(json.dumps({v: k for k, v in dh.parse_corp_list(r.content).items()}), encoding="utf-8")
    calls = fails = 0
    for name, start, end in quarters(first_year, today):
        p = root / f"{name}.json.gz"
        if p.exists() and not (refresh and refresh(name)):
            continue
        rows, page, total = [], 1, 1
        while page <= total:
            if calls >= MAX_CALLS:
                return {"status": "STOPPED", "stopped": "CALL_CAP", "calls": calls}
            calls += 1
            try:
                body = get(dh.BASE + "list.json", params={"crtfc_key": key, "bgn_de": start, "end_de": end, "pblntf_detail_ty": "B001", "last_reprt_at": "N", "page_count": 100, "page_no": page}, timeout=60).json()
            except Exception as exc:
                fails += 1
                log(f"{name} {page} {type(exc).__name__}")
                if fails >= 10:
                    return {"status": "STOPPED", "stopped": "TOO_MANY_FAILURES", "calls": calls}
                sleep(5)
                continue
            state = str(body.get("status"))
            if state == LIMIT or state in KEY_TROUBLE:
                return {"status": "STOPPED", "stopped": f"DART_{state}", "calls": calls}
            if state not in ("000", NO_DATA):
                fails += 1
                log(f"{name} {page} DART {state}")
                if fails >= 10:
                    return {"status": "STOPPED", "stopped": "TOO_MANY_FAILURES", "calls": calls}
                sleep(5)
                continue
            fails = 0
            rows += [[x.get("rcept_no"), x.get("corp_code"), (x.get("stock_code") or "").strip(), x.get("report_nm")] for x in body.get("list") or []]
            total = int(body.get("total_page") or 1)
            page += 1
            sleep(pause)
        if p.exists():
            with gzip.open(p, "rt", encoding="utf-8") as fh:
                stored = len(json.load(fh))
            if len(rows) < stored * MIN_KEPT:
                return {"status": "STOPPED", "stopped": "LIST_SHRANK", "calls": calls}
        tmp = p.with_suffix(".tmp")
        with gzip.open(tmp, "wt", encoding="utf-8") as fh:
            json.dump(rows, fh, ensure_ascii=False)
        tmp.replace(p)
        log(f"{name} rows={len(rows)} calls={calls}")
    return {"status": "DONE", "calls": calls}


def load_events(root: Path) -> Dict[str, Dict[str, List[str]]]:
    """Stock code -> signal -> receipt days of first filings, in order.  A company with a blank code is found through the company list."""
    stock_of = json.loads((root / "corp.json").read_text(encoding="utf-8"))
    out: Dict[str, Dict[str, List[str]]] = {}
    for f in sorted(root.glob("*Q?.json.gz")):
        with gzip.open(f, "rt", encoding="utf-8") as fh:
            rows = json.load(fh)
        for rc, corp, stock, name in rows:
            kind = classify(name)
            code = stock or stock_of.get(corp)
            if kind and code and rc:
                out.setdefault(code, {}).setdefault(kind, []).append(f"{rc[:4]}-{rc[4:6]}-{rc[6:8]}")
    for by in out.values():
        for days in by.values():
            days.sort()
    return out


def seen_within(days: Sequence[str], first: str, on: str) -> bool:
    """A filing from ``first`` up to the day before ``on``: a receipt day is not usable on that day."""
    return bisect.bisect_left(days, first) < bisect.bisect_left(days, on)


def build_features(px: kr.KrPrices, rows: Sequence[int], events: Dict[str, Dict[str, List[str]]], log=print) -> np.ndarray:
    """Yes or no for each eligible stock.  The list covers the whole market, so a company without a filing is a true no; an ineligible stock stays empty."""
    tensor = np.full((len(rows), len(px.symbols), len(SIGNALS)), np.nan, dtype=np.float32)
    for n, i in enumerate(rows):
        on = px.dates[i]
        if on < REF_START or i < WINDOW:
            continue
        first = px.dates[i - WINDOW]
        ok = kr.eligible(px.data, i)
        for j in np.flatnonzero(ok):
            by = events.get(px.symbols[j]) or {}
            tensor[n, j] = [float(seen_within(by.get(s) or [], first, on)) for s in SIGNALS]
        if n % 200 == 0:
            log(f"{n}/{len(rows)} {on}")
    return tensor


def score_of(tensor: np.ndarray) -> np.ndarray:
    """0, 50 or 100: the two signals with the same weight, a financing decision counting against.  Ties are shared, never broken by code order."""
    fin, buy = tensor[:, :, SIGNALS.index("financing")], tensor[:, :, SIGNALS.index("buyback")]
    return (1 - fin + buy) * 50


def tier_summary(tensor: np.ndarray, rows: Sequence[int], px: kr.KrPrices) -> Dict[int, Dict[str, float]]:
    """Share of eligible stocks in each tier by year, and whether the evaluation's top and bottom fifths are defined.  Reads no return."""
    score, out = score_of(tensor), {}
    for year in range(2018, 2027):
        ns = [n for n, i in enumerate(rows) if px.dates[i][:4] == str(year) and np.isfinite(score[n]).sum() >= 30]
        if not ns:
            continue
        s = np.concatenate([score[n][np.isfinite(score[n])] for n in ns])
        tops = [(lambda x: (validate.rank(x) / (len(x) - 1) >= 0.8).mean())(score[n][np.isfinite(score[n])].astype(float)) for n in ns]
        bots = [(lambda x: (validate.rank(x) / (len(x) - 1) <= 0.2).mean())(score[n][np.isfinite(score[n])].astype(float)) for n in ns]
        fin = np.concatenate([tensor[n, :, 0][np.isfinite(tensor[n, :, 0])] for n in ns])
        buy = np.concatenate([tensor[n, :, 1][np.isfinite(tensor[n, :, 1])] for n in ns])
        out[year] = {"eligible": float(len(s) / len(ns)), "low": float((s == 0).mean()), "middle": float((s == 50).mean()), "high": float((s == 100).mean()), "financing": float(fin.mean()), "buyback": float(buy.mean()),
                     "dates_with_empty_top": sum(t == 0 for t in tops), "dates_with_empty_bottom": sum(b == 0 for b in bots), "mean_top_share": float(np.mean(tops)), "mean_bottom_share": float(np.mean(bots))}
    return out


def _inputs(base: Path):
    px = kr._load(base)
    with np.load(base / kr.FEATURES) as z:
        rows, top300 = [int(i) for i in z["rows"]], z["top300"]
    return px, rows, top300


def _themes(tensor: np.ndarray) -> Dict[str, np.ndarray]:
    return {"financing": 1 - tensor[:, :, 0], "buyback": tensor[:, :, 1], "events": score_of(tensor) / 100}


def prepare(base: Path, log=print) -> Dict[str, Any]:
    """Signals, tier sizes and how alike they are to the existing Korean themes.  No forward return is computed."""
    px, rows, _ = _inputs(base)
    events = load_events(base / DATA)
    tensor = build_features(px, rows, events, log)
    np.savez_compressed(base / FEATURES, tensor=tensor)
    gone = ~np.isfinite(px.data["adj_close"][-1])
    by_kind = {k: {} for k in SIGNALS}
    for by in events.values():
        for k, days in by.items():
            for d in days:
                by_kind[k][d[:4]] = by_kind[k].get(d[:4], 0) + 1
    picks = [n for n, i in enumerate(rows) if REF_START <= px.dates[i] < TEST_START]
    with np.load(base / kf.FEATURES) as z:
        fund = z["tensor"]
    with np.load(base / kr.FEATURES) as z:
        price = z["tensor"]
    alike = en.theme_correlation({**_themes(tensor), **kf.theme_ranks(fund), **kr.theme_ranks(price)}, picks)
    iss = fund[:, :, kf.SIGNALS.index("issuance")]
    flat = np.isfinite(iss) & np.isfinite(tensor[:, :, 0])
    per_gone = [float(np.nanmean(tensor[n, gone, 0])) for n in picks if np.isfinite(tensor[n, gone, 0]).any()]
    per_live = [float(np.nanmean(tensor[n, ~gone, 0])) for n in picks if np.isfinite(tensor[n, ~gone, 0]).any()]
    return {"status": "PREPARED", "companies": len(events), "filings_by_year": by_kind, "tiers": tier_summary(tensor, rows, px), "correlation": {a: alike[a] for a in ("financing", "buyback", "events")},
            "issuance_mean_with_financing": float(np.mean(iss[flat & (tensor[:, :, 0] == 1)])), "issuance_mean_without_financing": float(np.mean(iss[flat & (tensor[:, :, 0] == 0)])), "financing_share_later_gone": float(np.mean(per_gone)), "financing_share_still_listed": float(np.mean(per_live))}


def _portfolios(tensor: np.ndarray, px: kr.KrPrices, rows: List[int], first: str, last: str, cost: float, h: int = 20) -> Dict[str, Any]:
    """Fixed sets with no ranking inside, so a tie cannot be settled by stock code.  Rebalanced every 20 sessions, cost on what is replaced."""
    ns = [n for n, i in enumerate(rows) if first <= px.dates[i] < last and i + h < len(px.dates)][::h // kr.STEP]
    r = np.stack([px.forward(rows[n], h) for n in ns])
    fin, buy = [tensor[n, :, 0] for n in ns], [tensor[n, :, 1] for n in ns]
    sets = {"all_equal": [np.isfinite(f) for f in fin], "no_financing": [f == 0 for f in fin], "financing": [f == 1 for f in fin], "buyback_clean": [(b == 1) & (f == 0) for f, b in zip(fin, buy)]}
    out: Dict[str, Any] = {"periods": len(ns), "first": px.dates[rows[ns[0]]], "last": px.dates[rows[ns[-1]]]}
    for name, p in sets.items():
        out[name] = {"annual_net": kr.annual_growth(kr.rebalance_path(p, r, cost), h), "mean_holdings": float(np.mean([x.sum() for x in p]))}
    out["cap_weighted_market"] = {"annual": kr.annual_growth([float(v) for v in r[:, px.col[kr.MARKET]]], h)}
    return out


def money_conditions(money: Dict[str, Dict[str, Any]]) -> Dict[str, bool]:
    """B1: the buyback set beats the cap-weighted market in both periods.  B2: leaving out financing beats holding everything in both periods."""
    both = ("2022_2023", "2024_on")
    return {"b1_buyback_beats_market": all(money[k]["buyback_clean"]["annual_net"] > money[k]["cap_weighted_market"]["annual"] for k in both),
            "b2_avoiding_financing_helps": all(money[k]["no_financing"]["annual_net"] > money[k]["all_equal"]["annual_net"] for k in both)}


def reading(primary: Dict[str, Any], conditions: Dict[str, bool]) -> str:
    """The protocol's reading, fixed before the run."""
    a = all(primary[s]["verdict"] == "WEAK_POSITIVE_EVIDENCE" for s in HORIZONS)
    if not a:
        return "NO_EVIDENCE"
    if conditions["b1_buyback_beats_market"]:
        return "A_AND_B1"
    return "A_AND_B2" if conditions["b2_avoiding_financing_helps"] else "A_ONLY"


def run_once(base: Path, log=print) -> Dict[str, Any]:
    target = base / REPORT
    if target.exists():
        raise RuntimeError("이미 시험을 실행했습니다. 프로토콜상 다시 실행할 수 없습니다.")
    px, rows, top300 = _inputs(base)
    with np.load(base / FEATURES) as z:
        tensor = z["tensor"]
    with np.load(base / kf.FEATURES) as z:
        fund = kf.theme_ranks(z["tensor"])
    ref = [n for n, i in enumerate(rows) if REF_START <= px.dates[i] < TEST_START]
    corr = en.theme_correlation(fund, ref)
    fund_groups = en.merge_groups({a: {b: corr[a][b] for b in kf.THEMES} for a in kf.THEMES})
    themes = _themes(tensor)
    fund_score = en.combine(fund, fund_groups)
    with_events = en.combine({**fund, "events": themes["events"]}, fund_groups + [["events"]])
    scores = {"EVENTS": score_of(tensor), "FINANCING": themes["financing"] * 100, "BUYBACK": themes["buyback"] * 100, "FUND_ONLY": fund_score, "FUND_WITH_EVENTS": with_events}
    cost = config.round_trip_cost("KR")
    masks = {"kospi": np.tile(px.kospi, (len(rows), 1)), "kosdaq": np.tile(~px.kospi, (len(rows), 1)), "top300": top300}
    out: Dict[str, Any] = {"status": "TESTED", "protocol": PROTOCOL, "cost": cost, "scores": {}}
    for name, score in scores.items():
        res: Dict[str, Any] = {}
        for s, h in HORIZONS.items():
            w = kr.windows(px, rows, h)
            w["early"] = [n for n in w["early"] if px.dates[rows[n]] >= REF_START]
            test = en.evaluate(score, px, rows, w["test"], h, {}, cost)
            early = en.evaluate(score, px, rows, w["early"], h, {}, cost)
            res[s] = {"horizon": h, **test, **test_verdict(test), "reference_2018_2021": early}
            if name == "EVENTS":
                res[s]["subsets"] = {label: {k: {x: en.evaluate(np.where(mask, score, np.nan), px, rows, w[k], h, {}, cost).get(x) for x in ("ic", "t", "top_excess", "spread_net", "mean_stocks", "dates")} for k in w} for label, mask in masks.items()}
                res[s]["tiers"] = _tier_returns(score, px, rows, w["test"], h)
            log(f"{name} {s} done")
        out["scores"][name] = res
    money = {k: _portfolios(tensor, px, rows, a, b, cost) for k, (a, b) in PORTFOLIO_PERIODS.items()}
    conditions = money_conditions(money)
    out.update(money_20d=money, conditions=conditions, reading=reading(out["scores"]["EVENTS"], conditions), overlap={"fund_groups": fund_groups})
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return out


def _tier_returns(score: np.ndarray, px: kr.KrPrices, rows: List[int], picks: List[int], h: int) -> Dict[str, Any]:
    """What each tier did against the same day's average, with a median to show whether a few stocks carry it."""
    excess, median, count = {t: [] for t in (0, 50, 100)}, {t: [] for t in (0, 50, 100)}, {t: [] for t in (0, 50, 100)}
    for n in picks:
        r, s = px.forward(rows[n], h), score[n].astype(float)
        ok = np.isfinite(r) & np.isfinite(s)
        if ok.sum() < 30:
            continue
        avg = r[ok].mean()
        for t in excess:
            m = ok & (s == t)
            if m.any():
                excess[t].append(r[m].mean() - avg)
                median[t].append(np.median(r[m]))
                count[t].append(int(m.sum()))
    return {str(t): {"excess": float(np.mean(excess[t])) if excess[t] else None, "median": float(np.mean(median[t])) if median[t] else None, "stocks": float(np.mean(count[t])) if count[t] else None} for t in excess}
