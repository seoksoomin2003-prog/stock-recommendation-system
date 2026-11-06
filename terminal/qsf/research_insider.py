"""Pre-registered insider purchase research.  Rules: reports/QSF_INSIDER_RESEARCH_PROTOCOL.md.

Only filings up to the evaluation date count.  Development sees only returns that end before TEST_START; the test runs once and a
second run is refused.  Names and addresses in the source files are never extracted.  Nothing here changes the live score, the QSF
ledger or P6-11B.
"""
import bisect
import csv
import gzip
import io
import json
import math
import time
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple

import numpy as np

from terminal.qsf import config, research_swing as rs, validate, validate_open, validate_oos
from terminal.qsf.research_score import TEST_START, dev_rows, test_rows

FACTORS = ("insider_buyers", "insider_opp_buyers", "insider_buy_value", "insider_cluster", "insider_net")
GOOD_HIGH = {f: True for f in FACTORS}
HORIZONS = rs.HORIZONS
REFERENCE_H = 63
WINDOW_BUY, WINDOW_CLUSTER, WINDOW_NET = 91, 30, 182
CLUSTER_MIN = 2
ROUTINE_YEARS = 3
MIN_DATES, MIN_SIGNAL = 60, 5
TOP = 0.8
QUARTERS = [(y, q) for y in range(2006, 2027) for q in (1, 2, 3, 4) if (y, q) <= (2026, 1)]
URL = "https://www.sec.gov/files/structureddata/data/insider-transactions-data-sets/{}q{}_form345.zip"
FOLDER = Path("data") / "qsf" / "research" / "insider"
TRADES = "trades.json.gz"
ALIASES = Path("reports") / "qsf" / "QSF_INSIDER_CIK_ALIASES.json"
DEV_REPORT = Path("reports") / "qsf" / "QSF_INSIDER_DEV.json"
TEST_REPORT = Path("reports") / "qsf" / "QSF_INSIDER_TEST.json"
PROTOCOL = "reports/QSF_INSIDER_RESEARCH_PROTOCOL.md"
MONTHS = {m: i + 1 for i, m in enumerate(("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"))}
BUY, SELL = "P", "S"


def parse_date(text: Any) -> Optional[str]:
    """'31-JAN-2024' to '2024-01-31'; anything else is empty."""
    try:
        d, m, y = str(text).strip().split("-")
        return date(int(y), MONTHS[m.upper()], int(d)).isoformat()
    except (ValueError, KeyError):
        return None


def _number(text: Any) -> Optional[float]:
    try:
        v = float(text)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) and v > 0 else None


def _rows(z: zipfile.ZipFile, name: str) -> Iterable[Dict[str, str]]:
    with z.open(name) as fh:
        yield from csv.DictReader(io.TextIOWrapper(fh, encoding="utf-8", errors="replace"), delimiter="\t", quoting=csv.QUOTE_NONE)


def extract(z: zipfile.ZipFile, wanted: Set[int]) -> Dict[str, Any]:
    """Open-market buys and sells by officers and directors of the wanted issuers.  Rows: [filed, traded, owner, side, value or None]."""
    csv.field_size_limit(10_000_000)
    subs: Dict[str, Tuple[str, int]] = {}
    last_filed, dropped = None, 0
    for r in _rows(z, "SUBMISSION.tsv"):
        filed = parse_date(r.get("FILING_DATE"))
        if not filed:
            dropped += 1
            continue
        last_filed = max(last_filed or filed, filed)
        if (r.get("DOCUMENT_TYPE") or "").strip() != "4":
            continue
        try:
            issuer = int(r["ISSUERCIK"])
        except (KeyError, TypeError, ValueError):
            dropped += 1
            continue
        if issuer in wanted:
            subs[r["ACCESSION_NUMBER"]] = (filed, issuer)
    owners: Dict[str, int] = {}
    for r in _rows(z, "REPORTINGOWNER.tsv"):
        acc = r.get("ACCESSION_NUMBER")
        if acc not in subs:
            continue
        roles = {x.strip() for x in (r.get("RPTOWNER_RELATIONSHIP") or "").split(",")}
        if not roles & {"Officer", "Director"}:
            continue
        try:
            cik = int(r["RPTOWNERCIK"])
        except (KeyError, TypeError, ValueError):
            continue
        owners[acc] = min(owners.get(acc, cik), cik)
    out: Dict[int, List[List[Any]]] = {}
    seen = set()
    for r in _rows(z, "NONDERIV_TRANS.tsv"):
        acc = r.get("ACCESSION_NUMBER")
        if acc not in owners or (acc, r.get("NONDERIV_TRANS_SK")) in seen:
            continue
        seen.add((acc, r.get("NONDERIV_TRANS_SK")))
        code, direction = (r.get("TRANS_CODE") or "").strip(), (r.get("TRANS_ACQUIRED_DISP_CD") or "").strip()
        if (code, direction) not in ((BUY, "A"), (SELL, "D")):
            continue
        traded = parse_date(r.get("TRANS_DATE"))
        if not traded:
            dropped += 1
            continue
        shares, price = _number(r.get("TRANS_SHARES")), _number(r.get("TRANS_PRICEPERSHARE"))
        filed, issuer = subs[acc]
        out.setdefault(issuer, []).append([filed, traded, owners[acc], code, shares * price if shares and price else None])
    return {"trades": out, "last_filed": last_filed, "dropped": dropped}


def mark_routine(rows: List[List[Any]]) -> List[List[Any]]:
    """Adds whether each trade is routine: the same person traded in that calendar month in each of the three prior years."""
    months: Dict[int, Set[Tuple[int, int]]] = {}
    for r in rows:
        months.setdefault(r[2], set()).add((int(r[1][:4]), int(r[1][5:7])))
    out = []
    for r in rows:
        y, m = int(r[1][:4]), int(r[1][5:7])
        out.append([*r[:5], all((y - k, m) in months[r[2]] for k in range(1, ROUTINE_YEARS + 1))])
    out.sort(key=lambda x: x[0])
    return out


def _since(day: str, days: int) -> str:
    return (datetime.strptime(day, "%Y-%m-%d").date() - timedelta(days=days - 1)).isoformat()


def factors_at(rows: List[List[Any]], day: str, adv: Optional[float]) -> Dict[str, float]:
    """Rows sorted by filing date.  Only filings up to ``day`` are read.  No trade in a window is a true zero."""
    filed = [r[0] for r in rows]
    end = bisect.bisect_right(filed, day)

    def window(n: int) -> List[List[Any]]:
        return rows[bisect.bisect_left(filed, _since(day, n)):end]
    buys = [r for r in window(WINDOW_BUY) if r[3] == BUY]
    value = sum(r[4] for r in buys if r[4] is not None)
    recent = {r[2] for r in window(WINDOW_CLUSTER) if r[3] == BUY}
    long_window = window(WINDOW_NET)
    bought = sum(r[4] for r in long_window if r[3] == BUY and r[4] is not None)
    sold = sum(r[4] for r in long_window if r[3] == SELL and r[4] is not None)
    return {"insider_buyers": float(len({r[2] for r in buys})), "insider_opp_buyers": float(len({r[2] for r in buys if not r[5]})),
            "insider_buy_value": value / adv if adv and adv > 0 else float("nan"), "insider_cluster": 1.0 if len(recent) >= CLUSTER_MIN else 0.0,
            "insider_net": (bought - sold) / (bought + sold) if bought + sold > 0 else 0.0}


def build_features(px: validate.Prices, members: Callable[[str], List[str]], ciks: Dict[str, int], trades: Dict[int, List[List[Any]]], source_end: str, progress=None) -> Dict[str, Any]:
    d = px.data
    rows = list(range(rs.HISTORY, len(px.dates) - 1, rs.STEP))
    tensor = np.full((len(rows), len(px.symbols), len(FACTORS)), np.nan, dtype=np.float32)
    counts = []
    for n, i in enumerate(rows):
        day = px.dates[i]
        if day > source_end:            # past the data: unknown, not "no trades"
            counts.append({"date": day, "eligible": 0, "linked": 0})
            continue
        cols = sorted({px.col[t] for t in members(day) if t in px.col})
        keep = rs.eligible(d, i, cols)
        linked = 0
        for j in keep:
            cik = ciks.get(px.symbols[j])
            if cik is None or cik not in trades:     # no filing of this kind anywhere: unknown, not "no trades"
                continue
            linked += 1
            adv = float(np.nanmean(d["close"][max(0, i - 19):i + 1, j] * d["volume"][max(0, i - 19):i + 1, j]))
            f = factors_at(trades[cik], day, adv)
            for k, name in enumerate(FACTORS):
                tensor[n, j, k] = f[name]
        counts.append({"date": day, "eligible": len(keep), "linked": linked})
        if progress:
            progress(n + 1, len(rows), day)
    return {"rows": rows, "tensor": tensor, "counts": counts}


def per_date(s: np.ndarray, r: np.ndarray, cost: float) -> Optional[Dict[str, Any]]:
    """Signal group (top fifth by rank, ties at their average rank) against everyone else."""
    ok = np.isfinite(s) & np.isfinite(r)
    n = int(ok.sum())
    if n < 30 or s[ok].std() == 0:
        return None
    ex = r[ok] - r[ok].mean()
    q = validate.rank(s[ok]) / (n - 1)
    top, rest = q >= TOP, q < TOP
    if not top.any() or not rest.any():
        return None
    return {"n": n, "signal_n": int(top.sum()), "ic": float(np.corrcoef(validate.rank(s[ok]), validate.rank(ex))[0, 1]) if ex.std() > 0 else None,
            "signal_excess": float(ex[top].mean()), "spread_net": float(ex[top].mean() - ex[rest].mean() - cost)}


def summarize(days: List[Dict[str, Any]], h: int) -> Dict[str, Any]:
    if not days:
        return {"dates": 0, "status": "UNAVAILABLE"}
    half = len(days) // 2

    def mean(sel: List[Dict[str, Any]], key: str) -> Optional[float]:
        v = [x[key] for x in sel if x.get(key) is not None]
        return float(np.mean(v)) if v else None
    early, late = days[:half], days[half:]
    spread = [x["spread_net"] for x in days]
    ic = [x["ic"] for x in days if x.get("ic") is not None]
    return {"dates": len(days), "first": days[0]["date"], "last": days[-1]["date"], "split": days[half]["date"], "lag": rs.lag_of(h), "mean_n": mean(days, "n"), "mean_signal_n": mean(days, "signal_n"),
            "spread_net": float(np.mean(spread)), "t_spread": validate.newey_west_t(spread, rs.lag_of(h)), "signal_excess": mean(days, "signal_excess"), "ic": mean(days, "ic"), "t_ic": validate.newey_west_t(ic, rs.lag_of(h)),
            "early": {"spread_net": mean(early, "spread_net"), "ic": mean(early, "ic"), "dates": len(early)}, "late": {"spread_net": mean(late, "spread_net"), "ic": mean(late, "ic"), "dates": len(late)}}


def verdict(s: Dict[str, Any]) -> Dict[str, Any]:
    """The protocol's five conditions for a rare signal."""
    gt = lambda v: v is not None and v > 0      # noqa: E731
    e, la = s.get("early") or {}, s.get("late") or {}
    checks = {"spread": gt(s.get("spread_net")), "t": s.get("t_spread") is not None and s["t_spread"] >= validate.MIN_T,
              "spread_both_halves": gt(e.get("spread_net")) and gt(la.get("spread_net")), "ic_both_halves": gt(e.get("ic")) and gt(la.get("ic")),
              "signal_group": gt(s.get("signal_excess")) and s.get("dates", 0) >= MIN_DATES and (s.get("mean_signal_n") or 0) >= MIN_SIGNAL}
    return {"verdict": "WEAK_POSITIVE_EVIDENCE" if all(checks.values()) else "NO_EVIDENCE", "checks": checks}


def evaluate(ranks: np.ndarray, px: validate.Prices, rows: List[int], picks: List[int], h: int, chosen: Sequence[str]) -> Dict[str, Any]:
    cost = config.round_trip_cost("US")
    days, sc, rt, be, ex = [], [], [], [], []
    spy = px.col["SPY"]
    a = px.data["adj_close"][:, spy]
    above, below = [], []
    for n in picks:
        i = rows[n]
        r = px.forward(i, h)
        s = rs.composite(ranks[n], list(chosen), FACTORS)
        day = per_date(s, r, cost)
        if not day:
            continue
        day["date"] = px.dates[i]
        days.append(day)
        (above if a[i] > np.nanmean(a[i - 199:i + 1]) else below).append(day["spread_net"])
        ok = np.isfinite(s) & np.isfinite(r)
        sc.append(s[ok]); rt.append(r[ok]); ex.append(r[ok] - r[ok].mean()); be.append(np.full(int(ok.sum()), r[spy]))     # noqa: E702
    out = summarize(days, h)
    if days:
        out["buckets"] = validate.bucket_table(*(np.concatenate(x) for x in (sc, rt, be, ex)), cost)
        out["spread_spy_above_200d"] = {"spread_net": float(np.mean(above)) if above else None, "dates": len(above)}
        out["spread_spy_below_200d"] = {"spread_net": float(np.mean(below)) if below else None, "dates": len(below)}
    return out


# ---------------------------------------------------------------------- runs
def cik_map(base: Path) -> Dict[str, int]:
    root = base / "data" / "qsf" / "research"
    classified = json.loads((root / "survivorship" / "classified.json").read_text(encoding="utf-8"))
    out: Dict[str, int] = {}
    for src in (validate._universe(base)["ciks"], {t: v.get("cik") for t, v in classified.items()},
                {t: v["cik"] for t, v in validate_open.load_universe(base).items()}, {a: v["cik"] for a, v in validate_oos.load_old(base).items()}):
        for t, c in src.items():
            try:
                out[t] = int(c)
            except (TypeError, ValueError):
                continue
    return out


def alias_map(base: Path, ciks: Dict[str, int]) -> Dict[int, int]:
    """Earlier company number to the number the ticker uses now.  A number that is itself some ticker's current one is refused."""
    table = json.loads((base / ALIASES).read_text(encoding="utf-8"))
    current = set(ciks.values())
    out: Dict[int, int] = {}
    for t, old in table.items():
        for c in old:
            if c in current:
                raise ValueError(f"{t}: 이전 번호가 다른 종목의 현재 번호입니다.")
            out[int(c)] = ciks[t]
    return out


def merge_aliases(trades: Dict[int, List[List[Any]]], aliases: Dict[int, int]) -> Dict[int, List[List[Any]]]:
    out: Dict[int, List[List[Any]]] = {}
    for issuer, rows in trades.items():
        out.setdefault(aliases.get(issuer, issuer), []).extend(rows)
    return out


def prepare(base: Path, log=print, http=None, pause: float = 0.2) -> Dict[str, Any]:
    """Downloads the quarterly files once each, then keeps only the fields the protocol uses."""
    import requests
    from terminal import sources
    from utils.runtime_config import load_local_env
    load_local_env()
    http = http or requests
    folder = base / FOLDER / "zips"
    folder.mkdir(parents=True, exist_ok=True)
    headers = {"User-Agent": sources.sec_user_agent()}
    ciks = cik_map(base)
    aliases = alias_map(base, ciks)
    wanted = set(ciks.values()) | set(aliases)
    merged: Dict[int, List[List[Any]]] = {}
    last, dropped, t0 = None, 0, time.time()
    for k, (y, q) in enumerate(QUARTERS, 1):
        path = folder / f"{y}q{q}_form345.zip"
        if not path.exists():
            for attempt in range(4):
                try:
                    r = http.get(URL.format(y, q), headers=headers, timeout=180)
                    if r.status_code == 200:
                        tmp = path.with_suffix(".tmp")
                        tmp.write_bytes(r.content)
                        tmp.replace(path)
                        break
                    raise RuntimeError(f"HTTP {r.status_code}")
                except Exception as exc:     # the message stays generic: request details never reach a log
                    if attempt == 3:
                        raise RuntimeError(f"{y}q{q} 내려받기 실패: {type(exc).__name__}") from None
                    time.sleep(5 * (attempt + 1))
            time.sleep(pause)
        with zipfile.ZipFile(path) as z:
            part = extract(z, wanted)
        for issuer, rows in part["trades"].items():
            merged.setdefault(issuer, []).extend(rows)
        last = max(last or part["last_filed"], part["last_filed"]) if part["last_filed"] else last
        dropped += part["dropped"]
        log(f"{k}/{len(QUARTERS)} {y}q{q} {time.time() - t0:.0f}s")
    out = {"source_end": last, "dropped": dropped, "trades": {str(c): mark_routine(r) for c, r in merge_aliases(merged, aliases).items()}}
    with gzip.open(base / FOLDER / TRADES, "wt", encoding="utf-8") as fh:
        json.dump(out, fh)
    n = sum(len(v) for v in out["trades"].values())
    buys = sum(1 for v in out["trades"].values() for r in v if r[3] == BUY)
    return {"status": "PREPARED", "source_end": last, "issuers": len(out["trades"]), "wanted": len(wanted), "trades": n, "buys": buys, "dropped": dropped}


def _trades(base: Path) -> Tuple[Dict[int, List[List[Any]]], str]:
    with gzip.open(base / FOLDER / TRADES, "rt", encoding="utf-8") as fh:
        d = json.load(fh)
    return {int(k): v for k, v in d["trades"].items()}, d["source_end"]


def develop(base: Path, log=print) -> Dict[str, Any]:
    root, _, px = rs._load(base)
    trades, end = _trades(base)
    t0 = time.time()
    b = build_features(px, rs._members(base, root), cik_map(base), trades, end, progress=lambda n, m, d: n % 100 == 0 and log(f"{n}/{m} {d} {time.time() - t0:.0f}s"))
    np.savez_compressed(root / "insider_features.npz", rows=np.array(b["rows"]), tensor=b["tensor"])
    ranks = rs.rank_tensor(b["tensor"], FACTORS, GOOD_HIGH)
    res = {}
    for s, h in HORIZONS.items():
        picks = dev_rows(px, b["rows"], h)
        res[s] = rs.select(ranks, px, b["rows"], picks, h, FACTORS)
        res[s]["each_factor_spread"] = {f: {k: v for k, v in evaluate(ranks, px, b["rows"], picks, h, [f]).items() if k in ("spread_net", "t_spread", "mean_signal_n", "signal_excess", "dates")} for f in FACTORS}
    active = [c for c in b["counts"] if c["eligible"]]
    out = {"status": "DEVELOPED", "protocol": PROTOCOL, "strategies": res, "factors": list(FACTORS), "source_end": end, "mean_eligible": float(np.mean([c["eligible"] for c in active])), "mean_linked": float(np.mean([c["linked"] for c in active]))}
    (base / DEV_REPORT).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def test_once(base: Path) -> Dict[str, Any]:
    target = base / TEST_REPORT
    if target.exists():
        raise RuntimeError("이미 시험을 실행했습니다. 프로토콜상 다시 실행할 수 없습니다.")
    root, _, px = rs._load(base)
    dev = json.loads((base / DEV_REPORT).read_text(encoding="utf-8"))
    z = np.load(root / "insider_features.npz")
    rows = [int(i) for i in z["rows"]]
    ranks = rs.rank_tensor(z["tensor"], FACTORS, GOOD_HIGH)
    out: Dict[str, Any] = {"status": "TESTED", "protocol": PROTOCOL, "source_end": dev["source_end"], "strategies": {}}
    for s, h in HORIZONS.items():
        chosen = dev["strategies"][s]["chosen"]
        picks = [n for n in test_rows(px, rows, h) if px.dates[rows[n]] <= dev["source_end"]]
        each = {}
        for f in FACTORS:
            k = FACTORS.index(f)
            ics = [v for v in (rs._ic(ranks[n, :, k].astype(float), px.forward(rows[n], h)) for n in picks) if v is not None]
            each[f] = {"ic": float(np.mean(ics)) if ics else None, "t": validate.newey_west_t(ics, rs.lag_of(h)), "dates": len(ics)}
        if not chosen:
            out["strategies"][s] = {"status": "NO_MODEL", "chosen": [], "horizon": h, "reason": "개발 구간에서 채택된 요인이 없어 합성 점수를 시험하지 않았습니다."}
            continue
        res = evaluate(ranks, px, rows, picks, h, chosen)
        ref_picks = [n for n in test_rows(px, rows, REFERENCE_H) if px.dates[rows[n]] <= dev["source_end"]]
        ref = evaluate(ranks, px, rows, ref_picks, REFERENCE_H, chosen)
        out["strategies"][s] = {"status": "TESTED", "chosen": chosen, "horizon": h, **res, **verdict(res), "each_factor": {f: each[f] for f in chosen}, "reference_63d": {k: ref.get(k) for k in ("ic", "t_ic", "spread_net", "t_spread", "dates")},
                                "reference_old_ic_rule": bool(res.get("ic") is not None and res["ic"] >= validate.MIN_IC)}
    target.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out
