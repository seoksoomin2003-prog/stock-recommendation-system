"""Pre-registered Korean earnings-surprise test.  Rules: reports/QSF_KR_SUE_PROTOCOL.md.

Two signals from the periodic reports already on disk (``research_data/dart/multi``): how far the newest single quarter's operating
profit and sales moved from the same quarter a year before, each over the market value at the report's receipt.  A figure is usable
only from the day after every report it reads was received (an amended report carries its later receipt date), and a signal goes
blank 150 days after that.  The evaluation runs once and a second run is refused.  Nothing here downloads, and nothing here changes
the live score or P6-11B.

What is new against the earlier financial test (``research_kr_fund``): that one read the change of the last four quarters together
over assets, as one of twelve signals.  This one reads the newest quarter alone, and its verdict has a condition the earlier tests
did not have: the signal must still rank stocks after the existing themes are taken out of it.
"""
import bisect
import json
import math
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from terminal.qsf import config, research_ensemble as en, research_kr as kr, research_kr_events as ke, research_kr_fund as kf, research_kr_holder as rh, research_swing as rs, validate
from terminal.qsf.research_score import test_verdict

PROTOCOL = "reports/QSF_KR_SUE_PROTOCOL.md"
REPORT = Path("reports") / "qsf" / "QSF_KR_SUE.json"
DATA = kf.DATA
FEATURES = Path("research_data") / "dart" / "sue_features.npz"
REF_START, TEST_START = kf.REF_START, kf.TEST_START
PRIMARY = "SWING_20"                 # the horizon the verdict reads; the long horizon is reported for reference only
HORIZONS = kr.HORIZONS
SIGNALS = ("sue_op", "sue_sales")
THEMES = {"sue_op": ["sue_op"], "sue_sales": ["sue_sales"]}
GROUPS = [["sue_op"], ["sue_sales"]]
GOOD_HIGH = {"sue_op": True, "sue_sales": True}
FLOWS = ("op", "sales")
STALE_DAYS = 150                     # a quarter's surprise is read until the next report is due, not beyond
TOLERANCE = 0.02                     # a three-month figure must agree this closely with the difference of the year-to-date figures
FRESH_SESSIONS = 30                  # reference split only: evaluation days within this many sessions of the receipt
MIN_RESIDUAL_STOCKS = 50
PARTIAL_IC, PARTIAL_T = 0.02, 2.24   # condition C: the same two figures condition A asks of the raw score
PREVIOUS = {"H1": "Q1", "Q3": "H1"}
PORTFOLIO_PERIODS = ke.PORTFOLIO_PERIODS


# ----------------------------------------------------------------------------- one quarter's figure
def _pair(reports: Dict[Tuple[int, str], Dict[str, Any]], year: int, report: str, basis: str, name: str) -> Optional[Tuple[Optional[float], Optional[float]]]:
    return ((reports.get((year, report)) or {}).get(basis) or {}).get(name)


def quarter_value(reports: Dict[Tuple[int, str], Dict[str, Any]], year: int, report: str, basis: str, name: str) -> Optional[float]:
    """The three months a report closes, all from one basis.  First quarter: its own column.  Half-year and third quarter: the
    three-month column, which must agree with the year-to-date column less the year to date one report before when both are on
    file; a report whose columns disagree is left empty rather than guessed.  Annual: the year less the first nine months."""
    v = _pair(reports, year, report, basis, name)
    if v is None:
        return None
    if report == "Q1":
        return v[0]
    if report == "FY":
        nine = _pair(reports, year, "Q3", basis, name)
        return None if v[0] is None or nine is None or nine[1] is None else v[0] - nine[1]
    three, so_far = v
    before = _pair(reports, year, PREVIOUS[report], basis, name)
    before_so_far = None if before is None else kf.year_to_date({name: before}, name, PREVIOUS[report])
    if so_far is not None and before_so_far is not None:
        implied = so_far - before_so_far
        if three is None:
            return implied
        return three if abs(three - implied) <= TOLERANCE * max(abs(three), abs(implied), 1.0) else None
    return three


def _receipts(reports: Dict[Tuple[int, str], Dict[str, Any]], year: int, report: str, basis: str) -> List[str]:
    """Receipt days of every report one quarter's figure reads."""
    need = {"Q1": ["Q1"], "H1": ["H1", "Q1"], "Q3": ["Q3", "H1"], "FY": ["FY", "Q3"]}[report]
    return [reports[(year, r)][basis]["rcept"] for r in need if basis in reports.get((year, r), {})]


def timeline(reports: Dict[Tuple[int, str], Dict[str, Any]]) -> Tuple[List[str], List[Tuple[str, float, float]]]:
    """Days in order, and for each the newest quarter's two changes with the day they became known: (known day, operating profit
    change, sales change) against the same quarter a year before, in won.  Consolidated when the report has total assets, else
    separate, and the year-before quarter must be on the same basis.  An amended older quarter never replaces a newer one."""
    items = []
    for (y, r), by in reports.items():
        basis = next((b for b in ("CFS", "OFS") if by.get(b, {}).get("assets") and by[b]["assets"][0] is not None), None)
        if basis is None:
            continue
        change = {}
        for n in FLOWS:
            now, then = quarter_value(reports, y, r, basis, n), quarter_value(reports, y - 1, r, basis, n)
            change[n] = math.nan if now is None or then is None else now - then
        used = _receipts(reports, y, r, basis) + _receipts(reports, y - 1, r, basis)
        known = max(used)          # an amended input may arrive later than the report that reads it
        items.append((known, y, kf.ORDER[r], (known, change["op"], change["sales"])))
    items.sort(key=lambda x: x[:3])
    days, rows, best, kept = [], [], (-1, -1), None
    for known, y, order, values in items:
        if (y, order) >= best:
            best, kept = (y, order), values
        days.append(known)
        rows.append(kept)
    return days, rows


def latest(days: List[str], rows: List[Tuple[str, float, float]], on: str) -> Optional[Tuple[str, float, float]]:
    """The newest quarter known strictly before ``on``, unless it has gone stale."""
    n = bisect.bisect_left(days, on) - 1
    if n < 0 or (date.fromisoformat(on) - date.fromisoformat(rows[n][0])).days > STALE_DAYS:
        return None
    return rows[n]


# ----------------------------------------------------------------------------- features
def build_features(px: kr.KrPrices, rows: Sequence[int], reports: Dict[str, Any], log=print) -> Tuple[np.ndarray, np.ndarray]:
    """(evaluation day, stock, signal) and how many sessions old each signal is.  The divisor is the market value at the last close
    on or before the day the figures became known, so later price moves do not change the signal."""
    lines = {c: timeline(r) for c, r in reports.items()}
    tensor = np.full((len(rows), len(px.symbols), len(SIGNALS)), np.nan, dtype=np.float32)
    age = np.full((len(rows), len(px.symbols)), np.nan, dtype=np.float32)
    cap, dates = px.data["cap"], [str(d) for d in px.dates]
    for n, i in enumerate(rows):
        on = dates[i]
        if on < REF_START:
            continue
        for j in np.flatnonzero(kr.eligible(px.data, i)):
            line = lines.get(px.symbols[j])
            got = latest(line[0], line[1], on) if line else None
            if got is None:
                continue
            known, d_op, d_sales = got
            k = bisect.bisect_right(dates, known) - 1
            c = float(cap[k, j]) if k >= 0 else math.nan
            if not np.isfinite(c) or c <= 0:
                continue
            tensor[n, j] = [d_op / c, d_sales / c]
            age[n, j] = i - k
        if n % 100 == 0:
            log(f"{n}/{len(rows)} {on}")
    return tensor, age


def theme_ranks(tensor: np.ndarray) -> Dict[str, np.ndarray]:
    r = rs.rank_tensor(tensor, SIGNALS, GOOD_HIGH)
    return en.theme_scores({s: r[:, :, k] for k, s in enumerate(SIGNALS)}, THEMES)


def score_of(tensor: np.ndarray) -> np.ndarray:
    """The two signals with the same weight.  A stock needs both."""
    return en.combine(theme_ranks(tensor), GROUPS)


def residual(score: np.ndarray, controls: Dict[str, np.ndarray]) -> np.ndarray:
    """What is left of the score after the same day's existing themes are taken out of it by least squares.  A missing control counts
    as the middle (0.5), so a stock is not dropped for lacking one; the result is on no particular scale and only its order is read."""
    out = np.full(score.shape, np.nan)
    for n in range(score.shape[0]):
        y = score[n].astype(float) / 100
        ok = np.isfinite(y)
        if ok.sum() < MIN_RESIDUAL_STOCKS:
            continue
        x = np.column_stack([np.ones(int(ok.sum()))] + [np.where(np.isfinite(c[n][ok]), c[n][ok], 0.5).astype(float) for c in controls.values()])
        beta, *_ = np.linalg.lstsq(x, y[ok], rcond=None)
        out[n, ok] = y[ok] - x @ beta
    return out


def _inputs(base: Path):
    return ke._inputs(base)


def _controls(base: Path, px: kr.KrPrices, rows: Sequence[int]) -> Dict[str, np.ndarray]:
    """The existing Korean themes a new signal must add to: five from the statements, the price themes, and size."""
    with np.load(Path(base) / kf.FEATURES) as z:
        fund = kf.theme_ranks(z["tensor"])
    with np.load(Path(base) / kr.FEATURES) as z:
        price = kr.theme_ranks(z["tensor"])
    cap = np.stack([px.data["cap"][i] for i in rows]).astype(float)
    size = rs.rank_tensor(np.where(np.isfinite(cap) & (cap > 0), cap, np.nan)[:, :, None].astype(np.float32), ("size",), {"size": True})[:, :, 0]
    return {**fund, **price, "size": size}


def prepare(base: Path, log=print) -> Dict[str, Any]:
    """Signals, how much of the sample has them, how often a report's columns disagreed, and how alike the score is to the existing
    themes.  No forward return is computed."""
    base = Path(base)
    px, rows, _ = _inputs(base)
    reports = kf.load_reports(base / DATA)
    tensor, age = build_features(px, rows, reports, log)
    np.savez_compressed(base / FEATURES, tensor=tensor, age=age)
    score = score_of(tensor)
    gone = ~np.isfinite(px.data["adj_close"][-1])
    cover: Dict[int, Any] = {}
    for year in range(2018, 2027):
        ns = [n for n, i in enumerate(rows) if str(px.dates[i])[:4] == str(year)]
        if not ns:
            continue
        ok = np.stack([kr.eligible(px.data, rows[n]) for n in ns])
        have = np.isfinite(score[ns])
        cover[year] = {"eligible": float(ok.sum(axis=1).mean()), "covered": float(have.sum() / ok.sum()), "later_gone_covered": float(have[:, gone].sum() / max(1, ok[:, gone].sum())),
                       "least_covered_day": float((have.sum(axis=1) / ok.sum(axis=1)).min()), "median_age_sessions": float(np.nanmedian(age[ns]))}
    picks = [n for n, i in enumerate(rows) if REF_START <= str(px.dates[i]) < TEST_START]
    alike = en.theme_correlation({**theme_ranks(tensor), "sue": score / 100, **_controls(base, px, rows)}, picks)
    return {"status": "PREPARED", "companies": len(reports), "coverage": cover, "columns": column_check(reports), "samsung": known_quarters(reports),
            "correlation": {a: alike[a] for a in ("sue_op", "sue_sales", "sue")},
            "percentiles": {s: [float(x) for x in np.nanpercentile(tensor[picks][:, :, k], [5, 25, 50, 75, 95])] for k, s in enumerate(SIGNALS)}}


def column_check(reports: Dict[str, Any]) -> Dict[str, Any]:
    """How many half-year and third-quarter figures had both columns to compare, and how many disagreed and were left empty."""
    compared = dropped = 0
    for by_report in reports.values():
        for (y, r), by in by_report.items():
            if r not in PREVIOUS:
                continue
            for basis in by:
                for n in FLOWS:
                    v, before = _pair(by_report, y, r, basis, n), _pair(by_report, y, PREVIOUS[r], basis, n)
                    if not v or v[0] is None or v[1] is None or before is None:
                        continue
                    b = kf.year_to_date({n: before}, n, PREVIOUS[r])
                    if b is None:
                        continue
                    compared += 1
                    dropped += quarter_value(by_report, y, r, basis, n) is None
    return {"compared": compared, "left_empty": dropped, "share_left_empty": dropped / compared if compared else None}


def known_quarters(reports: Dict[str, Any], code: str = "005930", year: int = 2023) -> Dict[str, Optional[float]]:
    """One company's four quarters of operating profit, to set against its published results by eye."""
    r = reports.get(code) or {}
    return {q: quarter_value(r, year, q, "CFS", "op") for q in ("Q1", "H1", "Q3", "FY")}


# ----------------------------------------------------------------------------- the one run
def condition_c(partial: Dict[str, Any]) -> bool:
    ic, t = partial.get("ic"), partial.get("t")
    return ic is not None and t is not None and ic >= PARTIAL_IC and t >= PARTIAL_T


def reading(primary: Dict[str, Any], independent: bool, conditions: Dict[str, bool]) -> str:
    """The protocol's reading, fixed before the run."""
    if primary["verdict"] != "WEAK_POSITIVE_EVIDENCE":
        return "NO_EVIDENCE"
    if not independent:
        return "A_NOT_INDEPENDENT"
    if conditions["b1_top_beats_market"]:
        return "A_C_AND_B1"
    return "A_C_AND_B2" if conditions["b2_avoiding_bottom_helps"] else "A_C_ONLY"


def run_once(base: Path, log=print) -> Dict[str, Any]:
    base = Path(base)
    target = base / REPORT
    if target.exists():
        raise RuntimeError("이미 시험을 실행했습니다. 프로토콜상 다시 실행할 수 없습니다.")
    px, rows, top300 = _inputs(base)
    with np.load(base / FEATURES) as z:
        tensor, age = z["tensor"], z["age"]
    controls = _controls(base, px, rows)
    themes = theme_ranks(tensor)
    primary = score_of(tensor)
    left = residual(primary, controls)
    fund = {k: controls[k] for k in kf.THEMES}
    ref = [n for n, i in enumerate(rows) if REF_START <= str(px.dates[i]) < TEST_START]
    corr = en.theme_correlation(fund, ref)
    fund_groups = en.merge_groups({a: {b: corr[a][b] for b in kf.THEMES} for a in kf.THEMES})
    with np.errstate(invalid="ignore"):
        fresh = np.where(age <= FRESH_SESSIONS, primary, np.nan)
        older = np.where(age > FRESH_SESSIONS, primary, np.nan)
    scores = {"SUE": primary, "SUE_RESIDUAL": left, "SUE_OP": themes["sue_op"] * 100, "SUE_SALES": themes["sue_sales"] * 100, "SUE_FRESH": fresh, "SUE_OLDER": older,
              "EARNINGS_CHANGE": fund["earnings_change"] * 100, "FUND_ONLY": en.combine(fund, fund_groups), "FUND_WITH_SUE": en.combine({**fund, "sue": primary / 100}, fund_groups + [["sue"]])}
    cost = config.round_trip_cost("KR")
    masks = {"kospi": np.tile(px.kospi, (len(rows), 1)), "kosdaq": np.tile(~px.kospi, (len(rows), 1)), "top300": top300}
    out: Dict[str, Any] = {"status": "TESTED", "protocol": PROTOCOL, "cost": cost, "primary_horizon": PRIMARY, "scores": {}}
    for name, score in scores.items():
        res: Dict[str, Any] = {}
        for s, h in HORIZONS.items():
            w = kr.windows(px, rows, h)
            w["early"] = [n for n in w["early"] if str(px.dates[rows[n]]) >= REF_START]
            test = en.evaluate(score, px, rows, w["test"], h, {}, cost)
            early = en.evaluate(score, px, rows, w["early"], h, {}, cost)
            res[s] = {"horizon": h, **test, **test_verdict(test), "reference_2018_2021": early}
            if name == "SUE":
                res[s]["subsets"] = {label: {k: {x: en.evaluate(np.where(mask, score, np.nan), px, rows, w[k], h, {}, cost).get(x) for x in ("ic", "t", "top_excess", "spread_net", "mean_stocks", "dates")} for k in w} for label, mask in masks.items()}
            log(f"{name} {s} done")
        out["scores"][name] = res
    money = {k: rh._portfolios(primary, px, rows, a, b, cost) for k, (a, b) in PORTFOLIO_PERIODS.items()}
    conditions = rh.money_conditions(money)
    partial = {k: out["scores"]["SUE_RESIDUAL"][PRIMARY].get(k) for k in ("ic", "t", "dates", "mean_stocks")}
    independent = condition_c(partial)
    out.update(money_20d=money, conditions={**conditions, "c_independent": independent}, partial=partial, controls=list(controls),
               reading=reading(out["scores"]["SUE"][PRIMARY], independent, conditions), overlap={"fund_groups": fund_groups})
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return out
