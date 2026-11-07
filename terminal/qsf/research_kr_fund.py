"""Pre-registered Korean financial-statement signal test.  Rules: reports/QSF_KR_FUND_PROTOCOL.md.

A figure is usable only from the day after its DART receipt date.  An amended report carries its later receipt date, so a correction
cannot reach back.  The evaluation runs once and a second run is refused.  Nothing here changes the live score or P6-11B.
"""
import bisect
import gzip
import json
import math
import os
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from terminal.qsf import config, dart_history as dh, research_ensemble as en, research_kr as kr, research_swing as rs, validate
from terminal.qsf.research_score import test_verdict

PROTOCOL = "reports/QSF_KR_FUND_PROTOCOL.md"
REPORT = Path("reports") / "qsf" / "QSF_KR_FUND.json"
DATA = Path("research_data") / "dart" / "multi"
FEATURES = Path("research_data") / "dart" / "features.npz"
REF_START, TEST_START = "2018-01-01", "2022-01-01"
HORIZONS = kr.HORIZONS
ORDER = {"Q1": 1, "H1": 2, "Q3": 3, "FY": 4}
F = {name: n for n, name in enumerate(dh.FIELDS)}
ALIAS = {"매출액": "sales", "영업이익": "op", "영업이익(손실)": "op", "당기순이익": "ni", "당기순이익(손실)": "ni", "자산총계": "assets", "부채총계": "liab", "자본총계": "equity", "유동자산": "ca", "유동부채": "cl"}
FLOWS = ("sales", "op", "ni")
STALE_DAYS = 500     # older than this, the company has stopped reporting
THEMES: Dict[str, Sequence[str]] = {
    "value": ("bm", "ep", "oy", "sp"),
    "profitability": ("roe", "op_assets"),
    "safety": ("low_leverage", "current"),
    "investment": ("asset_growth", "issuance"),
    "earnings_change": ("ni_change", "op_change"),
}
SIGNALS = tuple(s for v in THEMES.values() for s in v)
GOOD_HIGH = {s: True for s in SIGNALS} | {"asset_growth": False, "issuance": False}
REPORT_FIELDS = ("equity", "assets", "liab", "ca", "cl", "sales", "op", "ni", "ni_prior", "op_prior", "assets_prior")


def load_reports(root: Path) -> Dict[str, Dict[Tuple[int, str], Dict[str, Any]]]:
    """Stock code -> (year, report) -> basis -> {'rcept': day, account: (this period, year to date)}.  The first row of an account wins."""
    out: Dict[str, Dict[Tuple[int, str], Dict[str, Any]]] = {}
    for folder in sorted(p for p in root.iterdir() if p.is_dir()):
        year, report = folder.name.split("_")
        for f in sorted(folder.glob("*.json.gz")):
            with gzip.open(f, "rt", encoding="utf-8") as fh:
                rows = json.load(fh)
            for r in rows:
                name = ALIAS.get(r[F["account_nm"]])
                stock, basis, rc = r[F["stock_code"]], r[F["fs_div"]], r[F["rcept_no"]]
                if not (name and stock and basis and rc):
                    continue
                b = out.setdefault(stock, {}).setdefault((int(year), report), {}).setdefault(basis, {"rcept": f"{rc[:4]}-{rc[4:6]}-{rc[6:8]}"})
                b.setdefault(name, (kr.num(r[F["thstrm_amount"]]), kr.num(r[F["thstrm_add_amount"]])))
    return out


def year_to_date(rep: Dict[str, Any], name: str, report: str) -> Optional[float]:
    """Half-year and third-quarter columns hold the three months in one field and the year to date in the other."""
    v = rep.get(name)
    if v is None:
        return None
    return v[1] if report in ("H1", "Q3") else v[0]


def ttm(reports: Dict[Tuple[int, str], Dict[str, Any]], year: int, report: str, basis: str, name: str) -> Optional[float]:
    """Last four quarters, all from one basis: last year's total, plus this year so far, less the same stretch last year."""
    def get(y: int, r: str) -> Optional[float]:
        x = (reports.get((y, r)) or {}).get(basis)
        return year_to_date(x, name, r) if x else None
    if report == "FY":
        return get(year, "FY")
    fy, now, then = get(year - 1, "FY"), get(year, report), get(year - 1, report)
    return None if fy is None or now is None or then is None else fy + now - then


def timeline(reports: Dict[Tuple[int, str], Dict[str, Any]]) -> Tuple[List[str], np.ndarray]:
    """Receipt days in order, and each report's figures.  Consolidated when it has total assets, else separate; never a mix."""
    items = []
    for (y, r), by in reports.items():
        basis = next((b for b in ("CFS", "OFS") if by.get(b, {}).get("assets") and by[b]["assets"][0] is not None), None)
        if basis is None:
            continue
        rep = by[basis]

        def inst(n: str, source: Dict[str, Any] = rep) -> float:
            v = source.get(n)
            return v[0] if v and v[0] is not None else math.nan
        flows = {n: ttm(reports, y, r, basis, n) for n in FLOWS}
        prior_rep = (reports.get((y - 1, r)) or {}).get(basis) or {}
        row = {"equity": inst("equity"), "assets": inst("assets"), "liab": inst("liab"), "ca": inst("ca"), "cl": inst("cl"),
               **{n: flows[n] if flows[n] is not None else math.nan for n in FLOWS}, "assets_prior": inst("assets", prior_rep)}
        for n in ("ni", "op"):
            p = ttm(reports, y - 1, r, basis, n)
            row[f"{n}_prior"] = p if p is not None else math.nan
        used = [(y - 1, "FY"), (y - 1, r), (y - 2, "FY"), (y - 2, r)] if r != "FY" else [(y - 1, "FY")]
        known = max([rep["rcept"]] + [reports[u][basis]["rcept"] for u in used if basis in reports.get(u, {})])      # an amended input may arrive later
        items.append((known, y, ORDER[r], [row[k] for k in REPORT_FIELDS]))
    items.sort(key=lambda x: x[:3])
    days, rows, best, kept = [], [], (-1, -1), None
    for known, y, order, values in items:
        if (y, order) >= best:      # an amendment of an older period never replaces a newer period
            best, kept = (y, order), values
        days.append(known)
        rows.append(kept)
    return days, np.array(rows, dtype=float).reshape(len(rows), len(REPORT_FIELDS))


def latest(days: List[str], on: str) -> Optional[int]:
    """Position of the newest report received strictly before ``on``, unless it has gone stale."""
    n = bisect.bisect_left(days, on) - 1
    if n < 0 or (date.fromisoformat(on) - date.fromisoformat(days[n])).days > STALE_DAYS:
        return None
    return n


def signals(m: Sequence[float], cap: float, issuance: float) -> Dict[str, float]:
    x = dict(zip(REPORT_FIELDS, m))
    with np.errstate(all="ignore"):
        def over(a: float, b: float, positive: bool = True) -> float:
            if not np.isfinite(a) or not np.isfinite(b) or b == 0 or (positive and b < 0):
                return math.nan
            return a / b
        return {"bm": over(x["equity"], cap), "ep": over(x["ni"], cap), "oy": over(x["op"], cap), "sp": over(x["sales"], cap), "roe": over(x["ni"], x["equity"]), "op_assets": over(x["op"], x["assets"]),
                "low_leverage": 1 - over(x["liab"], x["assets"]), "current": over(x["ca"], x["cl"]), "asset_growth": over(x["assets"], x["assets_prior"]) - 1, "issuance": issuance,
                "ni_change": over(x["ni"] - x["ni_prior"], x["assets_prior"]), "op_change": over(x["op"] - x["op_prior"], x["assets_prior"])}


def build_features(px: kr.KrPrices, rows: Sequence[int], reports: Dict[str, Any], log=print) -> np.ndarray:
    lines = {c: timeline(r) for c, r in reports.items()}
    tensor = np.full((len(rows), len(px.symbols), len(SIGNALS)), np.nan, dtype=np.float32)
    cap, adj = px.data["cap"], px.data["adj_close"]
    for n, i in enumerate(rows):
        on = px.dates[i]
        if on < REF_START:
            continue
        ok = kr.eligible(px.data, i)
        for j in np.flatnonzero(ok):
            days_m = lines.get(px.symbols[j])
            c = float(cap[i, j])
            if not days_m or not np.isfinite(c) or c <= 0:
                continue
            k = latest(days_m[0], on)
            before = i - 252
            iss = math.nan
            if before >= 0 and np.isfinite(cap[before, j]) and cap[before, j] > 0 and np.isfinite(adj[before, j]) and adj[before, j] > 0 and adj[i, j] > 0:
                iss = math.log(c / float(cap[before, j])) - math.log(float(adj[i, j]) / float(adj[before, j]))     # growth in value that price does not explain
            if k is None:
                tensor[n, j, SIGNALS.index("issuance")] = iss
                continue
            s = signals(days_m[1][k], c, iss)
            tensor[n, j] = [s[x] for x in SIGNALS]
        if n % 100 == 0:
            log(f"{n}/{len(rows)} {on}")
    return tensor


def theme_ranks(tensor: np.ndarray) -> Dict[str, np.ndarray]:
    r = rs.rank_tensor(tensor, SIGNALS, GOOD_HIGH)
    return en.theme_scores({s: r[:, :, k] for k, s in enumerate(SIGNALS)}, THEMES)


def _inputs(base: Path):
    px = kr._load(base)
    with np.load(base / kr.FEATURES) as z:
        rows, price_tensor, top300 = [int(i) for i in z["rows"]], z["tensor"], z["top300"]
    return px, rows, price_tensor, top300


def prepare(base: Path, log=print) -> Dict[str, Any]:
    """Signals, how much of the sample has them, and how alike the themes are.  No forward return is computed."""
    px, rows, price_tensor, _ = _inputs(base)
    reports = load_reports(base / DATA)
    tensor = build_features(px, rows, reports, log)
    (base / FEATURES).parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(base / FEATURES, tensor=tensor)
    scores = theme_ranks(tensor)
    picks = [n for n, i in enumerate(rows) if REF_START <= px.dates[i] < TEST_START]
    every = np.isfinite(price_tensor[:, :, 0])
    gone = np.isfinite(px.data["adj_close"][-1]) == False       # noqa: E712
    cover = {}
    for year in range(2018, 2027):
        ns = [n for n, i in enumerate(rows) if px.dates[i][:4] == str(year)]
        if not ns:
            continue
        have = np.isfinite(scores["value"][ns]) | np.isfinite(scores["profitability"][ns])
        elig = every[ns] | np.isfinite(tensor[ns][:, :, SIGNALS.index("issuance")])
        cover[year] = {"eligible": float(elig.sum(axis=1).mean()), "with_statements": float((have & elig).sum() / max(1, elig.sum())), "later_gone_with_statements": float((have & elig)[:, gone].sum() / max(1, elig[:, gone].sum()))}
    by_signal = {s: float(np.isfinite(tensor[picks][:, :, k]).sum() / max(1, np.isfinite(tensor[picks]).any(axis=2).sum())) for k, s in enumerate(SIGNALS)}
    all_scores = {**scores, **kr.theme_ranks(price_tensor)}
    corr = en.theme_correlation(all_scores, picks)
    fund_groups = en.merge_groups({a: {b: corr[a][b] for b in THEMES} for a in THEMES})
    return {"status": "PREPARED", "companies": len(reports), "coverage": cover, "signals": by_signal, "correlation": corr, "fund_groups": fund_groups, "all_groups": en.merge_groups(corr)}


def run_once(base: Path, log=print) -> Dict[str, Any]:
    target = base / REPORT
    if target.exists():
        raise RuntimeError("이미 시험을 실행했습니다. 프로토콜상 다시 실행할 수 없습니다.")
    px, rows, price_tensor, top300 = _inputs(base)
    with np.load(base / FEATURES) as z:
        tensor = z["tensor"]
    fund = theme_ranks(tensor)
    both = {**fund, **kr.theme_ranks(price_tensor)}
    ref = [n for n, i in enumerate(rows) if REF_START <= px.dates[i] < TEST_START]
    corr = en.theme_correlation(both, ref)
    fund_groups = en.merge_groups({a: {b: corr[a][b] for b in THEMES} for a in THEMES})
    groups = en.merge_groups(corr)
    scores = {"FUNDAMENTALS": en.combine(fund, fund_groups), "WITH_PRICE": en.combine(both, groups)}
    cost = config.round_trip_cost("KR")
    out: Dict[str, Any] = {"status": "TESTED", "protocol": PROTOCOL, "fund_groups": fund_groups, "all_groups": groups, "correlation": corr, "cost": cost, "scores": {}}
    masks = {"kospi": np.tile(px.kospi, (len(rows), 1)), "kosdaq": np.tile(~px.kospi, (len(rows), 1)), "top300": top300}
    for name, score in scores.items():
        res: Dict[str, Any] = {}
        for s, h in HORIZONS.items():
            w = kr.windows(px, rows, h)
            w["early"] = [n for n in w["early"] if px.dates[rows[n]] >= REF_START]
            test = en.evaluate(score, px, rows, w["test"], h, {}, cost)
            early = en.evaluate(score, px, rows, w["early"], h, {}, cost)
            themes = {}
            for t, m in (both if name == "WITH_PRICE" else fund).items():
                ics = {k: [v for v in (rs._ic(m[n].astype(float), px.forward(rows[n], h)) for n in w[k]) if v is not None] for k in w}
                themes[t] = {k: {"ic": float(np.mean(v)) if v else None, "t": validate.newey_west_t(v, rs.lag_of(h)), "dates": len(v)} for k, v in ics.items()}
            subsets = {}
            for label, mask in masks.items():
                sub = np.where(mask, score, np.nan)
                subsets[label] = {k: {x: en.evaluate(sub, px, rows, w[k], h, {}, cost).get(x) for x in ("ic", "t", "top_excess", "spread_net", "mean_stocks", "dates")} for k in w}
            res[s] = {"horizon": h, **test, **test_verdict(test), "reference_2017_2021": early, "themes": themes, "subsets": subsets, "quintiles": kr._quintiles(score, px, rows, w["test"], h)}
            log(f"{name} {s} done")
        money = {"2017_2021": kr._portfolios(score, top300, px, rows, REF_START, TEST_START, cost), "2022_2023": kr._portfolios(score, top300, px, rows, TEST_START, "2024-01-01", cost), "2024_on": kr._portfolios(score, top300, px, rows, "2024-01-01", "2099", cost), "2022_on": kr._portfolios(score, top300, px, rows, TEST_START, "2099", cost)}
        beats = all(money[k]["top_fifth_all"]["annual_net"] > money[k]["cap_weighted_market"]["annual"] for k in ("2022_2023", "2024_on"))
        res["money_20d"] = {**money, "top_fifth_beats_market_in_both": beats}
        out["scores"][name] = res
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return out


def download(base: Path, log=print) -> Dict[str, Any]:
    """Companies are every stock code the KRX snapshots show, delisted ones included, on the DART company list."""
    import requests
    key = os.environ.get("OPENDART_API_KEY")
    if not key:
        return {"status": "NO_KEY"}
    r = requests.get(dh.BASE + "corpCode.xml", params={"crtfc_key": key}, timeout=120)
    corp = dh.parse_corp_list(r.content)
    px = kr._load(base)
    codes = [corp[s] for s in px.symbols if s in corp]
    return dh.download(base / DATA, key, requests.get, codes, range(2015, date.today().year + 1), log=log)
