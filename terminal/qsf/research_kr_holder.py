"""Pre-registered Korean largest-holder test.  Rules: reports/QSF_KR_HOLDER_PROTOCOL.md.

Two signals from the annual report's largest-shareholder table: the group's share of common stock at year end, and how far it moved during the year.
Usable from the day after receipt, blank once 500 days old.  Holder names are not kept.  The evaluation runs once and a second run is refused.
Nothing here changes the live score or P6-11B.
"""
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

from terminal.qsf import config, dart_history as dh, research_ensemble as en, research_kr as kr, research_kr_events as ke, research_kr_fund as kf, research_swing as rs, validate
from terminal.qsf.research_score import test_verdict

PROTOCOL = "reports/QSF_KR_HOLDER_PROTOCOL.md"
REPORT = Path("reports") / "qsf" / "QSF_KR_HOLDER.json"
DATA = Path("research_data") / "dart" / "holders"
FEATURES = DATA / "features.npz"
REF_START, TEST_START = kf.REF_START, kf.TEST_START
HORIZONS = kr.HORIZONS
SIGNALS = ("stake", "stake_change")
THEMES = {"stake": ["stake"], "change": ["stake_change"]}
GROUPS = [["stake"], ["change"]]
GOOD_HIGH = {"stake": True, "stake_change": True}
FIRST_YEAR, LAST_YEAR = 2016, 2025
COMMON = {"보통주", "보통주식", "의결권있는주식", "의결권있는보통주"}
TOTAL = {"계", "합계", "총계"}
ANNUAL = "11011"
MAX_CALLS = 12000          # leaves the day's limit for the live steps; the download resumes where it stopped
PAUSE = 0.15               # stays well under the service's per-minute limit
LIMIT, NO_DATA = "020", "013"
KEY_TROUBLE = ("010", "011", "012", "901")
PORTFOLIO_PERIODS = ke.PORTFOLIO_PERIODS


def _num(x: Any) -> Optional[float]:
    try:
        v = float(str(x).replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    return v if np.isfinite(v) else None


def parse_table(rows: Optional[Sequence[Dict[str, Any]]]) -> Tuple[Optional[str], Optional[float], Optional[float]]:
    """Receipt number, year-end share and start-of-year share of common stock.  The table's own total row, or the sum of its rows when it has none.  A share outside 0 to 100 is left empty."""
    rows = rows or []
    receipt = next((str(r["rcept_no"]) for r in rows if r.get("rcept_no")), None)
    common = [r for r in rows if re.sub(r"\s+", "", str(r.get("stock_knd") or "")) in COMMON]
    if not common:
        return receipt, None, None
    total = [r for r in common if re.sub(r"\s+", "", str(r.get("nm") or "")) in TOTAL]

    def share(field: str) -> Optional[float]:
        if total:
            v = _num(total[-1].get(field))
        else:
            parts = [_num(r.get(field)) for r in common]
            v = sum(parts) if all(p is not None for p in parts) else None
        return round(v, 4) if v is not None and 0 <= v <= 100 else None
    return receipt, share("trmend_posesn_stock_qota_rt"), share("bsis_posesn_stock_qota_rt")


def targets(px: kr.KrPrices, rows: Sequence[int], corp_of: Dict[str, str], first: int = FIRST_YEAR, last: int = LAST_YEAR) -> List[Tuple[str, str, int]]:
    """Each company for the years it could feed a signal: from two years before it first qualified to the year it last did, newest years first."""
    span: Dict[str, List[int]] = {}
    for i in rows:
        if px.dates[i] < REF_START:
            continue
        year = int(px.dates[i][:4])
        for j in np.flatnonzero(kr.eligible(px.data, i)):
            code = px.symbols[j]
            lo_hi = span.setdefault(code, [year, year])
            lo_hi[0], lo_hi[1] = min(lo_hi[0], year), max(lo_hi[1], year)
    out = [(corp_of[c], c, y) for c, (lo, hi) in span.items() if c in corp_of for y in range(max(first, lo - 2), min(last, hi) + 1)]
    return sorted(out, key=lambda t: (-t[2], t[1]))


def _done(root: Path) -> set:
    seen = set()
    for f in root.glob("*.jsonl"):
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                seen.add((r[0], r[1]))
    return seen


def download(base: Path, todo: Iterable[Tuple[str, str, int]], log=print, get: Optional[Callable[..., Any]] = None, sleep: Callable[[float], None] = time.sleep, key: Optional[str] = None, max_calls: int = MAX_CALLS) -> Dict[str, Any]:
    """One line per company and year, written as it comes, so a stop loses nothing.  Stops at once on the daily limit or a key problem.  Errors report the type only."""
    key = key or os.environ.get("OPENDART_API_KEY")
    if not key:
        return {"status": "NO_KEY"}
    if get is None:
        import requests
        get = requests.get
    root = Path(base) / DATA
    root.mkdir(parents=True, exist_ok=True)
    seen = _done(root)
    pending = [t for t in todo if (t[1], t[2]) not in seen]
    calls = fails = 0
    for corp, code, year in pending:
        if calls >= max_calls:
            return {"status": "PAUSED", "stopped": "CALL_CAP", "calls": calls, "left": len(pending) - calls}
        calls += 1
        try:
            body = get(dh.BASE + "hyslrSttus.json", params={"crtfc_key": key, "corp_code": corp, "bsns_year": str(year), "reprt_code": ANNUAL}, timeout=60).json()
        except Exception as exc:
            fails += 1
            log(f"{code} {year} {type(exc).__name__}")
            if fails >= 10:
                return {"status": "STOPPED", "stopped": "TOO_MANY_FAILURES", "calls": calls}
            sleep(5)
            continue
        state = str(body.get("status"))
        if state == LIMIT or state in KEY_TROUBLE:
            return {"status": "STOPPED", "stopped": f"DART_{state}", "calls": calls}
        if state not in ("000", NO_DATA):
            fails += 1
            log(f"{code} {year} DART {state}")
            if fails >= 10:
                return {"status": "STOPPED", "stopped": "TOO_MANY_FAILURES", "calls": calls}
            sleep(5)
            continue
        fails = 0
        receipt, end, begin = parse_table(body.get("list"))
        with open(root / f"{year}.jsonl", "a", encoding="utf-8") as fh:
            fh.write(json.dumps([code, year, receipt, end, begin]) + "\n")
        if calls % 1000 == 0:
            log(f"calls {calls}")
        sleep(PAUSE)
    return {"status": "DONE", "calls": calls}


def load_reports(root: Path) -> Dict[str, Tuple[List[str], List[Tuple[Optional[float], Optional[float]]]]]:
    """Stock code -> receipt days in order and the two values of each.  A company asked twice for a year keeps its later receipt."""
    by: Dict[str, Dict[str, Tuple[Optional[float], Optional[float]]]] = {}
    for f in sorted(Path(root).glob("*.jsonl")):
        for line in f.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            code, _, receipt, end, begin = json.loads(line)
            if receipt and end is not None:
                day = f"{receipt[:4]}-{receipt[4:6]}-{receipt[6:8]}"
                by.setdefault(code, {})[day] = (end, None if begin is None else round(end - begin, 4))
    return {c: (sorted(v), [v[d] for d in sorted(v)]) for c, v in by.items()}


def build_features(px: kr.KrPrices, rows: Sequence[int], reports: Dict[str, Any], log=print) -> np.ndarray:
    tensor = np.full((len(rows), len(px.symbols), len(SIGNALS)), np.nan, dtype=np.float32)
    for n, i in enumerate(rows):
        on = px.dates[i]
        if on < REF_START:
            continue
        for j in np.flatnonzero(kr.eligible(px.data, i)):
            got = reports.get(px.symbols[j])
            k = kf.latest(got[0], on) if got else None
            if k is not None:
                end, change = got[1][k]
                tensor[n, j, 0] = end
                tensor[n, j, 1] = np.nan if change is None else change
        if n % 200 == 0:
            log(f"{n}/{len(rows)} {on}")
    return tensor


def theme_ranks(tensor: np.ndarray) -> Dict[str, np.ndarray]:
    r = rs.rank_tensor(tensor, SIGNALS, GOOD_HIGH)
    return en.theme_scores({s: r[:, :, k] for k, s in enumerate(SIGNALS)}, THEMES)


def score_of(tensor: np.ndarray) -> np.ndarray:
    """The two signals with the same weight.  A stock needs both."""
    return en.combine(theme_ranks(tensor), GROUPS)


def _inputs(base: Path):
    return ke._inputs(base)


def prepare(base: Path, log=print) -> Dict[str, Any]:
    """Signals, how much of the sample has them, and how alike they are to the existing Korean themes.  No forward return is computed."""
    px, rows, _ = _inputs(base)
    tensor = build_features(px, rows, load_reports(Path(base) / DATA), log)
    np.savez_compressed(Path(base) / FEATURES, tensor=tensor)
    score = score_of(tensor)
    gone = ~np.isfinite(px.data["adj_close"][-1])
    cover: Dict[str, Any] = {}
    for year in range(2018, 2027):
        ns = [n for n, i in enumerate(rows) if px.dates[i][:4] == str(year)]
        if not ns:
            continue
        ok = np.stack([kr.eligible(px.data, rows[n]) for n in ns])
        have = np.isfinite(score[ns])
        cover[year] = {"eligible": float(ok.sum(axis=1).mean()), "covered": float(have.sum() / ok.sum()), "later_gone_covered": float(have[:, gone].sum() / max(1, ok[:, gone].sum())), "change_is_zero": float(np.nanmean(tensor[ns, :, 1] == 0) / np.mean(np.isfinite(tensor[ns, :, 1])))}
    picks = [n for n, i in enumerate(rows) if REF_START <= px.dates[i] < TEST_START]
    with np.load(Path(base) / kf.FEATURES) as z:
        fund = z["tensor"]
    with np.load(Path(base) / kr.FEATURES) as z:
        price = z["tensor"]
    extra: Dict[str, np.ndarray] = {}
    events = Path(base) / ke.FEATURES
    if events.exists():
        with np.load(events) as z:
            extra = {"not_financing": 1 - z["tensor"][:, :, 0], "buyback": z["tensor"][:, :, 1]}
    cap = np.stack([np.where(np.isfinite(px.data["cap"][i]), px.data["cap"][i], np.nan) for i in rows]).astype(float)
    alike = en.theme_correlation({**theme_ranks(tensor), "holder": score / 100, "large_cap": cap, **extra, **kf.theme_ranks(fund), **kr.theme_ranks(price)}, picks)
    flat = tensor[picks][np.isfinite(tensor[picks, :, 1])]
    stake = tensor[picks, :, 0]
    return {"status": "PREPARED", "reports": sum(len(v[0]) for v in load_reports(Path(base) / DATA).values()), "coverage": cover, "correlation": {a: alike[a] for a in ("stake", "change", "holder")},
            "stake_percentiles": [float(x) for x in np.nanpercentile(stake, [5, 25, 50, 75, 95])], "change_percentiles": [float(x) for x in np.percentile(flat[:, 1], [5, 25, 50, 75, 95])]}


def _portfolios(score: np.ndarray, px: kr.KrPrices, rows: List[int], first: str, last: str, cost: float, h: int = 20) -> Dict[str, Any]:
    """Fixed by the same rank rule as the evaluation, so a tie cannot be settled by stock code.  Rebalanced every 20 sessions, cost on what is replaced."""
    ns = [n for n, i in enumerate(rows) if first <= px.dates[i] < last and i + h < len(px.dates)][::h // kr.STEP]
    ret = np.stack([px.forward(rows[n], h) for n in ns])
    sets: Dict[str, List[np.ndarray]] = {"all_equal": [], "no_bottom": [], "bottom": [], "top": []}
    for n in ns:
        s = score[n].astype(float)
        ok = np.isfinite(s)
        q = np.full(s.shape, np.nan)
        q[ok] = validate.rank(s[ok]) / max(1, ok.sum() - 1)
        with np.errstate(invalid="ignore"):
            sets["all_equal"].append(ok)
            sets["no_bottom"].append(q > 0.2)
            sets["bottom"].append(q <= 0.2)
            sets["top"].append(q >= 0.8)
    out: Dict[str, Any] = {"periods": len(ns), "first": px.dates[rows[ns[0]]], "last": px.dates[rows[ns[-1]]]}
    for name, p in sets.items():
        out[name] = {"annual_net": kr.annual_growth(kr.rebalance_path(p, ret, cost), h), "mean_holdings": float(np.mean([x.sum() for x in p]))}
    out["cap_weighted_market"] = {"annual": kr.annual_growth([float(v) for v in ret[:, px.col[kr.MARKET]]], h)}
    return out


def money_conditions(money: Dict[str, Dict[str, Any]]) -> Dict[str, bool]:
    """B1: the top fifth beats the cap-weighted market in both periods.  B2: leaving out the bottom fifth beats holding everything in both periods."""
    both = ("2022_2023", "2024_on")
    return {"b1_top_beats_market": all(money[k]["top"]["annual_net"] > money[k]["cap_weighted_market"]["annual"] for k in both),
            "b2_avoiding_bottom_helps": all(money[k]["no_bottom"]["annual_net"] > money[k]["all_equal"]["annual_net"] for k in both)}


def reading(primary: Dict[str, Any], conditions: Dict[str, bool]) -> str:
    """The protocol's reading, fixed before the run."""
    if not all(primary[s]["verdict"] == "WEAK_POSITIVE_EVIDENCE" for s in HORIZONS):
        return "NO_EVIDENCE"
    if conditions["b1_top_beats_market"]:
        return "A_AND_B1"
    return "A_AND_B2" if conditions["b2_avoiding_bottom_helps"] else "A_ONLY"


def run_once(base: Path, log=print) -> Dict[str, Any]:
    target = Path(base) / REPORT
    if target.exists():
        raise RuntimeError("이미 시험을 실행했습니다. 프로토콜상 다시 실행할 수 없습니다.")
    px, rows, top300 = _inputs(base)
    with np.load(Path(base) / FEATURES) as z:
        tensor = z["tensor"]
    with np.load(Path(base) / kf.FEATURES) as z:
        fund = kf.theme_ranks(z["tensor"])
    ref = [n for n, i in enumerate(rows) if REF_START <= px.dates[i] < TEST_START]
    corr = en.theme_correlation(fund, ref)
    fund_groups = en.merge_groups({a: {b: corr[a][b] for b in kf.THEMES} for a in kf.THEMES})
    themes = theme_ranks(tensor)
    primary = score_of(tensor)
    scores = {"HOLDER": primary, "STAKE": themes["stake"] * 100, "CHANGE": themes["change"] * 100, "FUND_ONLY": en.combine(fund, fund_groups), "FUND_WITH_HOLDER": en.combine({**fund, "holder": primary / 100}, fund_groups + [["holder"]])}
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
            if name == "HOLDER":
                res[s]["subsets"] = {label: {k: {x: en.evaluate(np.where(mask, score, np.nan), px, rows, w[k], h, {}, cost).get(x) for x in ("ic", "t", "top_excess", "spread_net", "mean_stocks", "dates")} for k in w} for label, mask in masks.items()}
            log(f"{name} {s} done")
        out["scores"][name] = res
    money = {k: _portfolios(primary, px, rows, a, b, cost) for k, (a, b) in PORTFOLIO_PERIODS.items()}
    conditions = money_conditions(money)
    out.update(money_20d=money, conditions=conditions, reading=reading(out["scores"]["HOLDER"], conditions), overlap={"fund_groups": fund_groups})
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return out


def plan(base: Path) -> List[Tuple[str, str, int]]:
    px, rows, _ = _inputs(base)
    stock_of = json.loads((Path(base) / ke.DATA / "corp.json").read_text(encoding="utf-8"))
    return targets(px, rows, {v: k for k, v in stock_of.items()})
