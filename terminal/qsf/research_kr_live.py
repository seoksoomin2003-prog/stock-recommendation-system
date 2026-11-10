"""Historical replay of the live Korean score.  Rules: reports/QSF_KR_LIVE_REPLAY_PROTOCOL.md (committed before any return).

On each evaluation day the live scoring code (``engine.score`` with the live technical and fundamental calculations) is run on
what was public that day: KRX daily snapshots for prices and the universe, DART full annual statements by receipt date.  Regime,
events, the earnings calendar and insider ownership have no point-in-time history and are left out, as in the US replay.

Research only: nothing here touches the ledger, the forward records or the live score.  ``download`` and ``prepare`` see no return;
``run_once`` computes returns once and refuses a second run.
"""
import gzip
import json
import math
import os
import re
import time
from datetime import date
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

from terminal.qsf import config, engine, fundamentals, validate
from terminal.qsf import krx_history as kh
from terminal.qsf import research_kr as kr

PROTOCOL = "reports/QSF_KR_LIVE_REPLAY_PROTOCOL.md"
REPORT = Path("reports") / "qsf" / "QSF_KR_LIVE_REPLAY.json"
FIDELITY = Path("reports") / "qsf" / "QSF_KR_LIVE_REPLAY_FIDELITY.json"
KRX = Path("research_data") / "krx"
DATA = Path("research_data") / "krx_live"
SINGLE = Path("research_data") / "dart" / "single"
MULTI = Path("research_data") / "dart" / "multi"
FIRST = "2019-04-01"
STEP = 21
HISTORY = 540                 # sessions of bars a score reads, about the 800 calendar days of the live scan
SIZE, WINDOW, LOOK = 300, 20, 40          # the live universe: top 300 by mean traded value of the last 20 valid sessions
YEARS_BACK = 4
HORIZONS = {"SWING": (5, 10, 20), "LONG_TERM": (63, 126, 252)}
PRIMARY = {"SWING": 20, "LONG_TERM": 252}
DOMAINS = ("TECHNICAL", "FUNDAMENTAL", "RISK")
MIN_FIDELITY = 0.90
DAILY_CAP = 16000            # DART allows 20,000 calls a day; the rest stays for the daily job and the screen
ROW_FIELDS = ("rcept_no", "sj_div", "account_id", "account_nm", "account_detail", "thstrm_amount", "thstrm_add_amount", "currency")
F = {name: n for n, name in enumerate(kh.FIELDS)}
BOARD_INDEX = {"KOSPI": "IDX_KOSPI", "KOSDAQ": "IDX_KOSDAQ"}
MARKET = "IDX_ALL"            # every common stock, capitalisation-weighted: the comparison market of the money condition
CODE = re.compile(r"^[0-9A-Z]{5}0$")          # common shares end in 0; codes issued since 2024 carry letters
OLD_PREFIX, NEW_PREFIX = "ifrs_", "ifrs-full_"      # the live mapping knows only the newer spelling: it never reads years before 2019
NOT_OPERATING = ("TRUST_AND_COLLECTIVE_INVESTMENT", "REIT")
KSIC_CLASS = (("641", "BANK"), ("642", "TRUST_AND_COLLECTIVE_INVESTMENT"), ("649", "HOLDING_OR_OTHER_FINANCIAL"), ("651", "INSURANCE"), ("652", "INSURANCE"),
              ("661", "SECURITIES_AND_FINANCIAL_SERVICES"), ("662", "INSURANCE"))


# ---------------------------------------------------------------------- price panel
def eligible_stock(code: Optional[str], name: Optional[str], section: Optional[str]) -> bool:
    """The live security master's rule from what a snapshot row shows: common shares of a domestic operating company.
    SPACs and REITs go by name, foreign issuers by their 9xxxxx codes; fund vehicles are dropped later by industry class."""
    n = name or ""
    return bool(code and CODE.match(code)) and not code.startswith("9") and not any(w in n for w in ("스팩", "기업인수목적", "리츠")) \
        and "REIT" not in n.upper() and "SPAC" not in (section or "")


def build_panel(root: Path, log=print) -> Dict[str, np.ndarray]:
    """Arrays by day and stock from the KRX snapshots, read in two streaming passes.  ``close`` is the adjusted level chained from
    the exchange's change rate (``research_kr.next_level``); ``raw`` is the day's raw close, so any day's basis can be restored."""
    days = sorted({p.name[:10] for p in (root / "KOSPI").glob("*.json.gz")} & {p.name[:10] for p in (root / "KOSDAQ").glob("*.json.gz")})

    def rows_of(day: str) -> Iterable[Tuple[str, List[Any]]]:
        for board in kh.BOARDS:
            with gzip.open(kh.path_of(root, board, day), "rt", encoding="utf-8") as fh:
                for r in json.load(fh):
                    if eligible_stock(r[F["ISU_CD"]], r[F["ISU_NM"]], r[F["SECT_TP_NM"]]):
                        yield board, r
    boards: Dict[str, str] = {}
    traded = []
    for n, day in enumerate(days):
        any_close = False
        for board, r in rows_of(day):
            boards[r[F["ISU_CD"]]] = board
            any_close = any_close or bool(kr.num(r[F["TDD_CLSPRC"]]))
        if any_close:                       # the exchange answers for a holiday too, with nothing in it: that is not a session
            traded.append(day)
        if n % 500 == 0:
            log(f"codes {n}/{len(days)}")
    days = traded
    symbols = sorted(boards) + list(BOARD_INDEX.values()) + [MARKET]
    col = {c: j for j, c in enumerate(symbols)}
    D, S = len(days), len(symbols)
    out = {x: np.full((D, S), np.nan, dtype=np.float32) for x in ("open", "high", "low", "close", "raw", "volume", "value", "cap")}
    level: Dict[str, float] = {}
    seen: Dict[str, Any] = {}
    for i, day in enumerate(days):
        for board, r in rows_of(day):
            c = r[F["ISU_CD"]]
            close = kr.num(r[F["TDD_CLSPRC"]])
            if not close:
                continue
            j = col[c]
            cap, shares = kr.num(r[F["MKTCAP"]]), kr.num(r[F["LIST_SHRS"]])
            level[c] = kr.next_level(level.get(c), close, kr.num(r[F["FLUC_RT"]]), cap, shares, seen.get(c), i)
            seen[c] = (i, bool(kr.num(r[F["ACC_TRDVOL"]])), cap, shares)
            k = level[c] / close
            out["close"][i, j], out["raw"][i, j] = level[c], close
            for field, name in (("open", "TDD_OPNPRC"), ("high", "TDD_HGPRC"), ("low", "TDD_LWPRC")):
                v = kr.num(r[F[name]])
                if v:
                    out[field][i, j] = v * k
            for field, name in (("volume", "ACC_TRDVOL"), ("value", "ACC_TRDVAL"), ("cap", "MKTCAP")):
                v = kr.num(r[F[name]])
                if v is not None:
                    out[field][i, j] = v
        if i % 500 == 0:
            log(f"prices {i}/{D}")
    kospi = np.array([boards.get(c) == "KOSPI" for c in symbols])
    stock = np.array([c in boards for c in symbols])
    add_index(out, col[BOARD_INDEX["KOSPI"]], stock & kospi)
    add_index(out, col[BOARD_INDEX["KOSDAQ"]], stock & ~kospi)
    add_index(out, col[MARKET], stock)
    return {"dates": np.array(days), "symbols": np.array(symbols), "kospi": kospi, **out}


def add_index(d: Dict[str, np.ndarray], m: int, members: np.ndarray) -> None:
    """A capitalisation-weighted index of ``members`` on the previous day's weights, as ``research_kr.add_market`` does for the market."""
    a, cap = d["close"].astype(float), d["cap"].astype(float)
    level = 1000.0
    for x in ("close", "raw", "high", "low", "open"):
        d[x][0, m] = level
    d["volume"][0, m] = 1
    for i in range(1, a.shape[0]):
        prev, now, w = a[i - 1], a[i], cap[i - 1]
        ok = members & np.isfinite(prev) & np.isfinite(now) & np.isfinite(w) & (w > 0) & (prev > 0)
        before = level
        if ok.any():
            level *= 1 + float(np.sum(w[ok] * (now[ok] / prev[ok] - 1)) / np.sum(w[ok]))
        d["open"][i, m], d["close"][i, m], d["raw"][i, m] = before, level, level
        d["high"][i, m], d["low"][i, m], d["volume"][i, m] = max(before, level), min(before, level), 1


class Panel:
    """The saved arrays, with forward returns that close a stock gone before the exit day at its last traded price."""

    def __init__(self, z: Dict[str, np.ndarray]):
        self.dates = [str(d) for d in z["dates"]]
        self.symbols = [str(s) for s in z["symbols"]]
        self.col = {s: j for j, s in enumerate(self.symbols)}
        self.kospi = z["kospi"]
        self.data = {k: z[k] for k in ("open", "high", "low", "close", "raw", "volume", "value", "cap")}
        self.is_index = np.array([s in (*BOARD_INDEX.values(), MARKET) for s in self.symbols])

    def market_return(self, i: int, h: int) -> float:
        """The capitalisation-weighted market from day ``i``'s close to the h-th close (an index has no opening auction to miss)."""
        if i + h >= len(self.dates):
            return float("nan")
        m = self.data["close"][:, self.col[MARKET]]
        return float(m[i + h] / m[i] - 1)

    def forward(self, i: int, h: int, cost: float = 0.0) -> np.ndarray:
        n = len(self.symbols)
        if i + h >= len(self.dates):
            return np.full(n, np.nan)
        win = self.data["close"][i + 1:i + h + 1].astype(float)
        have = np.isfinite(win)
        last = win.shape[0] - 1 - np.argmax(have[::-1], axis=0)
        exit_ = win[last, np.arange(n)]
        exit_[~have.any(axis=0)] = np.nan
        with np.errstate(invalid="ignore", divide="ignore"):
            out = exit_ / self.data["open"][i + 1].astype(float) - 1 - cost
        out[self.is_index] = np.nan
        return out

    def bars(self, j: int, i: int, history: int = HISTORY) -> List[Dict[str, Any]]:
        """Bars up to day ``i`` on that day's price basis: prices scaled so the last close is the raw close, volume the other way."""
        d = self.data
        i0 = max(0, i - history + 1)
        c = d["close"][i0:i + 1, j].astype(float)
        raw = d["raw"][i0:i + 1, j].astype(float)
        if not (np.isfinite(c[-1]) and np.isfinite(raw[-1]) and c[-1] > 0):
            return []
        k = raw[-1] / c[-1]
        o, h, lo, v = (d[x][i0:i + 1, j].astype(float) for x in ("open", "high", "low", "volume"))
        with np.errstate(invalid="ignore", divide="ignore"):
            f = c / raw                                   # the adjustment factor of each day
            vol = v * (f[-1] / f)                         # shares on the last day's basis
        out = []
        for n in np.flatnonzero(np.isfinite(c)):
            px = float(c[n] * k)
            out.append({"date": self.dates[i0 + n], "open": float(o[n] * k) if o[n] == o[n] else None, "high": float(h[n] * k) if h[n] == h[n] else None,
                        "low": float(lo[n] * k) if lo[n] == lo[n] else None, "close": px, "adj_close": px,
                        "volume": float(vol[n]) if vol[n] == vol[n] else (float(v[n]) if v[n] == v[n] else None)})
        return out


def universe(px: Panel, i: int, size: int = SIZE, exclude: Optional[np.ndarray] = None) -> np.ndarray:
    """Columns of the day's liquid universe, by the live rule: mean traded value of the last 20 valid sessions, top ``size``.
    ``exclude`` marks columns that are not operating companies (fund vehicles), known only once the industry classes are."""
    d = px.data
    lo = max(0, i - LOOK + 1)
    val = d["value"][lo:i + 1].astype(float)
    have = np.isfinite(val)
    order = np.cumsum(have[::-1], axis=0)[::-1]                    # 1 for the newest valid session, counting back
    recent = have & (order <= WINDOW)
    count = recent.sum(axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        mean = np.where(recent, val, 0.0).sum(axis=0) / np.where(count > 0, count, np.nan)
    vol3 = d["volume"][max(0, i - 2):i + 1].astype(float)
    halted = (np.nan_to_num(vol3, nan=0.0) == 0).all(axis=0)
    ok = np.isfinite(d["close"][i]) & (count >= WINDOW) & ~halted & ~px.is_index
    if exclude is not None:
        ok &= ~exclude
    idx = np.flatnonzero(ok)
    idx = idx[np.lexsort((np.array(px.symbols)[idx], -mean[idx]))]
    return idx[:size]


def eval_rows(px: Panel, first: str = FIRST, step: int = STEP) -> List[int]:
    start = next(i for i, d in enumerate(px.dates) if d >= first)
    return list(range(max(start, config.MIN_BARS), len(px.dates), step))


def load_panel(base: Path) -> Panel:
    with np.load(Path(base) / DATA / "panel.npz", allow_pickle=False) as z:
        return Panel({k: z[k] for k in z.files})


# ---------------------------------------------------------------------- statements
def statement_path(root: Path, corp: str, year: int) -> Path:
    return root / str(year) / f"{corp}.json.gz"


def needs(px: Panel, rows: Sequence[int], extra_rows: Sequence[int] = ()) -> Dict[str, List[int]]:
    """Stock code -> business years a score will ask for (the last four before each day the stock is in the universe)."""
    out: Dict[str, set] = {}
    for i in [*rows, *extra_rows]:
        y = int(px.dates[i][:4])
        for j in universe(px, i):
            out.setdefault(px.symbols[j], set()).update(range(max(2015, y - YEARS_BACK), y))
    return {c: sorted(v) for c, v in out.items()}


def basis_hint(multi_root: Path) -> Dict[Tuple[str, int], str]:
    """(stock code, year) -> 'CFS' or 'OFS' from the major-accounts download already on disk, so only one call is needed."""
    out: Dict[Tuple[str, int], str] = {}
    from terminal.qsf import dart_history as dh
    f = {name: n for n, name in enumerate(dh.FIELDS)}
    for folder in sorted(p for p in Path(multi_root).glob("*_FY") if p.is_dir()):
        year = int(folder.name.split("_")[0])
        for file in sorted(folder.glob("*.json.gz")):
            with gzip.open(file, "rt", encoding="utf-8") as fh:
                for r in json.load(fh):
                    stock, fs = r[f["stock_code"]], r[f["fs_div"]]
                    if stock and fs in ("CFS", "OFS") and out.get((stock, year)) != "CFS":
                        out[(stock, year)] = fs
    return out


def slim(rows: List[Dict[str, Any]]) -> List[List[Any]]:
    return [[r.get(k) for k in ROW_FIELDS] for r in rows]


def download_statements(root: Path, wanted: Dict[str, List[int]], corp_of: Dict[str, str], hint: Dict[Tuple[str, int], str], fetch: Callable[[str, int, str], Dict[str, Any]],
                        cap: int = DAILY_CAP, log=print) -> Dict[str, Any]:
    """Full annual statements for every (stock, year) wanted and not on disk.  ``fetch(corp, year, fs)`` returns the DART body.
    Consolidated when it exists, otherwise separate, as the live loader chooses.  Resumable; stops at the daily cap or DART's limit."""
    calls = stored = empty = fails = 0
    todo = [(c, y) for c in sorted(wanted) for y in wanted[c] if c in corp_of and not statement_path(root, corp_of[c], y).exists()]
    log(f"to fetch {len(todo)} company-years, no DART code for {sum(1 for c in wanted if c not in corp_of)} stocks")
    for n, (code, year) in enumerate(todo, 1):
        corp = corp_of[code]
        order = [hint[(code, year)]] if (code, year) in hint else ["CFS", "OFS"]
        chosen: Dict[str, Any] = {"corp": corp, "stock": code, "year": year, "fs_div": None, "rows": []}
        failed = False
        for fs in order:
            if calls >= cap:
                return {"status": "STOPPED", "stopped": "DAILY_CAP", "calls": calls, "stored": stored, "empty": empty, "left": len(todo) - n + 1}
            try:
                body = fetch(corp, year, fs)
                calls += 1
            except Exception as exc:
                calls += 1
                fails += 1
                failed = True
                log(f"{code} {year} {fs} {type(exc).__name__}")
                if fails >= 20:
                    return {"status": "STOPPED", "stopped": "TOO_MANY_FAILURES", "calls": calls, "stored": stored, "empty": empty, "left": len(todo) - n + 1}
                time.sleep(3)
                break
            state = str(body.get("status"))
            if state == "020" or state in ("010", "011", "012", "101", "901"):
                return {"status": "STOPPED", "stopped": f"DART_{state}", "calls": calls, "stored": stored, "empty": empty, "left": len(todo) - n + 1}
            if state == "000" and body.get("list"):
                chosen.update(fs_div=fs, rows=slim(body["list"]))
                break
            if state not in ("000", "013"):
                failed = True
                fails += 1
                log(f"{code} {year} {fs} DART {state}")
                break
        if failed:
            continue                                    # nothing is written, so the next run asks again
        p = statement_path(root, corp, year)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + ".tmp")
        with gzip.open(tmp, "wt", encoding="utf-8") as fh:
            json.dump(chosen, fh, ensure_ascii=False)
        tmp.replace(p)
        stored += 1
        empty += not chosen["rows"]
        if n % 500 == 0:
            log(f"{n}/{len(todo)} calls {calls} stored {stored} no-data {empty}")
    return {"status": "OK", "calls": calls, "stored": stored, "empty": empty, "left": 0, "failed": fails}


def ksic_class(code: Optional[str]) -> str:
    c = str(code or "")
    return next((k for prefix, k in KSIC_CLASS if c.startswith(prefix)), "NON_FINANCIAL")


class Statements:
    """Stored statements run through the live mapping, one company-year at a time and kept."""

    def __init__(self, root: Path, corp_of: Dict[str, str], klass_of: Dict[str, str]):
        self.root, self.corp_of, self.klass_of = Path(root), corp_of, klass_of
        self._year: Dict[Tuple[str, int], Optional[Dict[str, Dict]]] = {}
        self._annual: Dict[Tuple[str, int], Dict[str, Any]] = {}

    def _concepts(self, code: str, year: int) -> Optional[Dict[str, Dict]]:
        key = (code, year)
        if key not in self._year:
            from markets.kr import dart
            self._year[key] = None
            corp = self.corp_of.get(code)
            p = statement_path(self.root, corp, year) if corp else None
            if p is not None and p.exists():
                with gzip.open(p, "rt", encoding="utf-8") as fh:
                    rec = json.load(fh)
                if rec.get("rows"):
                    rows = [dict(zip(ROW_FIELDS, r)) for r in rec["rows"]]
                    for r in rows:                      # DART wrote the same IFRS elements as ``ifrs_X`` until the 2019 business year
                        if str(r.get("account_id") or "").startswith(OLD_PREFIX):
                            r["account_id"] = NEW_PREFIX + r["account_id"][len(OLD_PREFIX):]
                    obs = dart.normalize_statements(rows, corp_code=corp, ticker=code, year=year, reprt_code="11011", fs_div=rec["fs_div"])
                    self._year[key] = dart.extract_concepts(obs, self.klass_of.get(code, "NON_FINANCIAL"))
        return self._year[key]

    def annual(self, code: str, as_of_year: int) -> Dict[str, Any]:
        """What ``fundamentals.load_kr_statements`` + ``extract_kr`` give the live score: the four business years before ``as_of_year``."""
        key = (code, as_of_year)
        if key not in self._annual:
            st = {y: c for y in range(as_of_year - YEARS_BACK, as_of_year) if (c := self._concepts(code, y))}
            self._annual[key] = fundamentals.extract_kr(st) if st else {}
        return self._annual[key]

    def not_operating(self, px: Panel) -> np.ndarray:
        return np.array([self.klass_of.get(s) in NOT_OPERATING for s in px.symbols])

    def fund(self, code: str, as_of: str, close: float, shares: Optional[float]) -> Dict[str, Any]:
        annual = self.annual(code, int(as_of[:4]))
        if not annual:
            return {"status": "UNAVAILABLE", "reason": "DART 재무제표 없음"}
        klass = self.klass_of.get(code, "NON_FINANCIAL")
        return fundamentals.blank_mixed_cash_flow(fundamentals.metrics(annual, close, as_of, is_financial=klass != "NON_FINANCIAL", shares=shares, source="OpenDART 사업보고서"), code)


# ---------------------------------------------------------------------- scoring
def score_day(px: Panel, i: int, st: Statements) -> List[Dict[str, Any]]:
    """Every universe stock scored by the live engine with what was public on day ``i``.  No return is read."""
    day = px.dates[i]
    bench = {b: px.bars(px.col[name], i) for b, name in BOARD_INDEX.items()}
    close = px.data["close"]
    ctxs, rets = {}, {}
    for j in universe(px, i, exclude=st.not_operating(px)):
        b = px.bars(j, i)
        if not b or b[-1]["date"] != day:
            continue
        t = px.symbols[j]
        cap = float(px.data["cap"][i, j])
        shares = cap / b[-1]["close"] if cap == cap and b[-1]["close"] else None
        board = "KOSPI" if px.kospi[j] else "KOSDAQ"
        ctxs[t] = {"market": "KR", "bars": b, "bench": bench[board], "bench_name": "코스피" if board == "KOSPI" else "코스닥", "events": None, "regime": None, "earnings": None,
                   "expected_session": day, "fund": st.fund(t, day, b[-1]["close"], shares)}
        if i >= 126 and close[i, j] == close[i, j] and close[i - 126, j] == close[i - 126, j] and close[i - 126, j] > 0:
            rets[t] = float(close[i, j] / close[i - 126, j] - 1)
    ordered = sorted(rets.values())
    ranks = {t: float(np.searchsorted(ordered, v, side="right") / len(ordered)) for t, v in rets.items()} if len(ordered) >= 20 else {}
    out = []
    for t, ctx in ctxs.items():
        rec: Dict[str, Any] = {"i": i, "t": t, "fund_status": (ctx["fund"] or {}).get("status")}
        base = dict(ctx, rs_rank=ranks.get(t))
        for strategy in HORIZONS:
            res = engine.score(base, strategy)
            base.setdefault("tech", res["tech"])
            base.setdefault("levels", res["levels"])
            rec[f"{strategy}|RAW"] = res["score"]
            for d in DOMAINS:
                rec[f"{strategy}|{d}"] = res["domains"][d]["score_100"]
            if validate.usable(res):
                rec[strategy] = res["score"]
            else:
                rec[f"{strategy}|WHY"] = [g["code"] for g in res["gates"]] + [f"SHORT_{d}" for d in res["short_domains"]]
        out.append(rec)
    return out


# ---------------------------------------------------------------------- steps without returns
def _scores_path(base: Path) -> Path:
    return Path(base) / DATA / "scores.json.gz"


def _live_session(base: Path) -> Optional[str]:
    try:
        return json.loads((Path(base) / "data" / "qsf" / "latest_KR.json").read_text(encoding="utf-8")).get("session")
    except (OSError, ValueError):
        return None


def _klass_from_master(base: Path) -> Dict[str, str]:
    from datetime import datetime, timezone
    from markets.kr import security_master
    m = security_master.load_master(Path(base) / "data" / "kr", now=datetime.now(timezone.utc))["master"]
    return {str(c): str(k) for c, k in zip(m["canonical_ticker"], m["industry_class"])}


def ensure_panel(base: Path, log=print) -> Panel:
    path = Path(base) / DATA / "panel.npz"
    newest = max(p.name[:10] for p in (Path(base) / KRX / "KOSPI").glob("*.json.gz"))
    if path.exists():
        px = load_panel(base)
        if px.dates[-1] >= newest:
            return px
    z = build_panel(Path(base) / KRX, log)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name("panel.tmp.npz")
    np.savez_compressed(tmp, **z)
    tmp.replace(path)
    return Panel(z)


def download(base: Path, log=print, cap: int = DAILY_CAP) -> Dict[str, Any]:
    """Statements and industry codes the replay needs.  Reads no return.  Run again on a later day if the cap stops it."""
    import requests
    from terminal.qsf import dart_history as dh
    base = Path(base)
    key = os.environ.get("OPENDART_API_KEY")
    if not key:
        return {"status": "NO_KEY"}
    px = ensure_panel(base, log)
    rows = eval_rows(px)
    live = _live_session(base)
    extra = [px.dates.index(live)] if live in px.dates else []
    wanted = needs(px, rows, extra)
    corp_of = dh.parse_corp_list(requests.get(dh.BASE + "corpCode.xml", params={"crtfc_key": key}, timeout=120).content)
    calls = 0

    def get(endpoint: str, **params) -> Dict[str, Any]:
        nonlocal calls
        calls += 1
        r = requests.get(dh.BASE + endpoint, params={"crtfc_key": key, **params}, timeout=30)
        time.sleep(0.12)
        return r.json()
    klass_path = base / DATA / "industry.json"
    klass = json.loads(klass_path.read_text(encoding="utf-8")) if klass_path.exists() else {}
    master = _klass_from_master(base)
    unknown = [c for c in sorted(wanted) if c not in master and c not in klass and c in corp_of]
    log(f"stocks {len(wanted)}, industry code to ask for {len(unknown)}")
    for n, c in enumerate(unknown, 1):
        if calls >= cap:
            break
        try:
            body = get("company.json", corp_code=corp_of[c])
        except Exception as exc:
            log(f"company {c} {type(exc).__name__}")
            continue
        if str(body.get("status")) == "020":
            return {"status": "STOPPED", "stopped": "DART_020", "calls": calls}
        if str(body.get("status")) == "000":
            klass[c] = {"induty_code": body.get("induty_code"), "class": ksic_class(body.get("induty_code"))}
        if n % 200 == 0:
            klass_path.write_text(json.dumps(klass, ensure_ascii=False), encoding="utf-8")
    klass_path.write_text(json.dumps(klass, ensure_ascii=False), encoding="utf-8")
    # A company-year the major-accounts download does not carry has no statement here either: 40 of 40 sampled ones came back
    # empty on both bases (2026-11-10).  Those are not asked for; the score then sees no statement for that year, as live would.
    hint = basis_hint(base / MULTI)
    known = {c: [y for y in ys if (c, y) in hint] for c, ys in wanted.items()}
    skipped = sum(len(ys) for ys in wanted.values()) - sum(len(ys) for ys in known.values())
    res = download_statements(base / SINGLE, known, corp_of, hint,
                              lambda corp, year, fs: get("fnlttSinglAcntAll.json", corp_code=corp, bsns_year=str(year), reprt_code="11011", fs_div=fs), cap=cap - calls, log=log)
    (base / DATA / "corp_codes.json").write_text(json.dumps({c: corp_of[c] for c in wanted if c in corp_of}), encoding="utf-8")
    return {**res, "calls": calls, "stocks": len(wanted), "company_years": sum(len(v) for v in wanted.values()), "not_asked_no_report": skipped,
            "no_dart_code": sorted(c for c in wanted if c not in corp_of)[:50]}


def _statements(base: Path) -> Statements:
    base = Path(base)
    corp_of = json.loads((base / DATA / "corp_codes.json").read_text(encoding="utf-8"))
    extra = json.loads((base / DATA / "industry.json").read_text(encoding="utf-8")) if (base / DATA / "industry.json").exists() else {}
    klass = {**{c: v["class"] for c, v in extra.items()}, **_klass_from_master(base)}
    return Statements(base / SINGLE, corp_of, klass)


def rank_corr(a: Sequence[float], b: Sequence[float]) -> Optional[float]:
    x, y = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    ok = np.isfinite(x) & np.isfinite(y)
    if ok.sum() < 20 or x[ok].std() == 0 or y[ok].std() == 0:
        return None
    return float(np.corrcoef(validate.rank(x[ok]), validate.rank(y[ok]))[0, 1])


def fidelity(base: Path, log=print) -> Dict[str, Any]:
    """The replay on the newest live session against the live ranking itself, domain by domain.  No return is read."""
    base = Path(base)
    live = json.loads((base / "data" / "qsf" / "latest_KR.json").read_text(encoding="utf-8"))
    px = load_panel(base)
    if live.get("session") not in px.dates:
        return {"status": "UNAVAILABLE", "reason": f"패널에 라이브 거래일 {live.get('session')}이 없습니다."}
    recs = {r["t"]: r for r in score_day(px, px.dates.index(live["session"]), _statements(base))}
    out: Dict[str, Any] = {"status": "REAL", "session": live["session"], "live_version": live.get("model_version"), "replay_names": len(recs), "tables": {}}
    names = {"SWING": "SWING", "LONG_TERM": "LONG_TERM"}
    live_names = {r["ticker"] for r in live["rows"]}
    out["live_names"], out["both"] = len(live_names), len(live_names & set(recs))
    passed = True
    for strategy in names:
        rows = [r for r in live["rows"] if r["strategy"] == strategy and r["ticker"] in recs]
        t: Dict[str, Any] = {"compared": len(rows)}
        for d in DOMAINS:
            a = [r["domains"].get(d) if r["domains"].get(d) is not None else np.nan for r in rows]
            b = [recs[r["ticker"]].get(f"{strategy}|{d}") if recs[r["ticker"]].get(f"{strategy}|{d}") is not None else np.nan for r in rows]
            diff = np.abs(np.array(a, dtype=float) - np.array(b, dtype=float))
            t[d] = {"rank_corr": rank_corr(a, b), "median_abs_diff": float(np.nanmedian(diff)) if np.isfinite(diff).any() else None,
                    "both_have": int(np.isfinite(diff).sum()), "only_live": int((np.isfinite(a) & ~np.isfinite(b)).sum()), "only_replay": int((~np.isfinite(np.array(a, dtype=float)) & np.isfinite(b)).sum())}
            passed = passed and t[d]["rank_corr"] is not None and t[d]["rank_corr"] >= MIN_FIDELITY
        out["tables"][strategy] = t
    out["passed"], out["threshold"] = passed, MIN_FIDELITY
    (base / FIDELITY).parent.mkdir(parents=True, exist_ok=True)
    (base / FIDELITY).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def prepare(base: Path, log=print) -> Dict[str, Any]:
    """Scores for every evaluation day, stored for the one test.  Reads no return."""
    base = Path(base)
    px = ensure_panel(base, log)
    st = _statements(base)
    rows = eval_rows(px)
    recs: List[Dict[str, Any]] = []
    t0 = time.time()
    for n, i in enumerate(rows, 1):
        day = score_day(px, i, st)
        recs.extend(day)
        if n % 5 == 0 or n == len(rows):
            log(f"scores {n}/{len(rows)} {px.dates[i]} {len(day)} stocks {time.time() - t0:.0f}s")
    with gzip.open(_scores_path(base), "wt", encoding="utf-8") as fh:
        json.dump({"dates": px.dates, "rows": rows, "records": recs}, fh)
    by_day: Dict[int, List[Dict[str, Any]]] = {}
    for r in recs:
        by_day.setdefault(r["i"], []).append(r)
    cover = {s: float(np.mean([np.mean([s in r for r in g]) for g in by_day.values()])) for s in HORIZONS}
    return {"status": "REAL", "days": len(rows), "first": px.dates[rows[0]], "last": px.dates[rows[-1]], "records": len(recs), "mean_universe": float(np.mean([len(g) for g in by_day.values()])),
            "scored_share": cover, "fund_real_share": float(np.mean([r.get("fund_status") in ("REAL", "STALE") for r in recs]))}


# ---------------------------------------------------------------------- the one test
class _View:
    """What the shared evaluation code reads: forward returns by stock column, and the comparison market under ``SPY``."""

    def __init__(self, px: Panel):
        self.px, self.dates = px, px.dates
        self.col = dict(px.col)
        self.col["SPY"] = px.col[MARKET]

    def forward(self, i: int, h: int, cost: float = 0.0) -> np.ndarray:
        out = self.px.forward(i, h, cost)
        out[self.col["SPY"]] = self.px.market_return(i, h)
        return out


def tables(view: _View, by_i: Dict[int, List[Dict[str, Any]]], key: str, h: int, first: Optional[str] = None) -> Dict[str, Any]:
    cost = config.round_trip_cost("KR")
    rows = []
    for i in sorted(by_i):
        if first and view.dates[i] < first:
            continue
        fwd = view.forward(i, h)
        g = by_i[i]
        score = np.array([r[key] if r.get(key) is not None else np.nan for r in g], dtype=float)
        ret = np.array([fwd[view.col[r["t"]]] for r in g], dtype=float)
        d = validate.per_date(score, ret, cost)
        if d:
            ok = np.isfinite(score) & np.isfinite(ret)
            q = validate.rank(score[ok]) / (ok.sum() - 1)
            ex = ret[ok] - ret[ok].mean()
            d.update(date=view.dates[i], top_excess=float(ex[q >= 0.8].mean()), bottom_excess=float(ex[q <= 0.2].mean()), average=float(ret[ok].mean()), market=float(fwd[view.col["SPY"]]))
            rows.append(d)
    out = validate.summarize(rows, h)
    if rows:
        out.update(top_fifth_excess=float(np.mean([r["top_excess"] for r in rows])), bottom_fifth_excess=float(np.mean([r["bottom_excess"] for r in rows])),
                   average_return=float(np.mean([r["average"] for r in rows])), market_return=float(np.nanmean([r["market"] for r in rows])))
    return out


def money(view: _View, by_i: Dict[int, List[Dict[str, Any]]], key: str, h: int = STEP) -> Dict[str, Any]:
    """Condition B: the top fifth by score rolled on every evaluation day, against the capitalisation-weighted market, in each half."""
    cost = config.round_trip_cost("KR")
    days = [i for i in sorted(by_i) if i + h < len(view.dates)]
    S = len(view.px.symbols)
    picks, universe_sets, rets, market = [], [], [], []
    for i in days:
        g = [r for r in by_i[i] if r.get(key) is not None]
        chosen, everyone = np.zeros(S, dtype=bool), np.zeros(S, dtype=bool)
        if len(g) >= 30:
            g.sort(key=lambda r: (-r[key], r["t"]))
            for r in g[:max(1, int(len(g) * 0.2))]:
                chosen[view.col[r["t"]]] = True
            for r in g:
                everyone[view.col[r["t"]]] = True
        picks.append(chosen)
        universe_sets.append(everyone)
        rets.append(view.px.forward(i, h))
        market.append(view.px.market_return(i, h))
    r = np.stack(rets) if rets else np.zeros((0, S))
    mid = len(days) // 2

    def part(lo: int, hi: int) -> Dict[str, Any]:
        if hi <= lo:
            return {"periods": 0}
        top = kr.rebalance_path(picks[lo:hi], r[lo:hi], cost)
        avg = kr.rebalance_path(universe_sets[lo:hi], r[lo:hi], cost)
        a, e, m = kr.annual_growth(top, h), kr.annual_growth(avg, h), kr.annual_growth(market[lo:hi], h)
        return {"periods": hi - lo, "first": view.dates[days[lo]], "last": view.dates[days[hi - 1]], "top_fifth_annual_net": a, "all_scored_equal_annual_net": e,
                "cap_weighted_market_annual": m, "beats_market": a is not None and m is not None and a > m}
    out = {"horizon": h, "early": part(0, mid), "late": part(mid, len(days)), "whole": part(0, len(days)),
           "mean_holdings": float(np.mean([p.sum() for p in picks])) if picks else None}
    out["passed"] = bool(out["early"].get("beats_market") and out["late"].get("beats_market"))
    return out


def reading(a: bool, b: bool) -> str:
    return "RANK_AND_MONEY" if a and b else "RANK_ONLY" if a else "NO_EVIDENCE"


def run_once(base: Path, log=print) -> Dict[str, Any]:
    from terminal.qsf import sim_picks
    base = Path(base)
    out = base / REPORT
    if out.exists():
        raise RuntimeError("시험은 한 번만 실행합니다. 이미 결과가 있습니다.")
    fid = json.loads((base / FIDELITY).read_text(encoding="utf-8")) if (base / FIDELITY).exists() else {}
    if not fid.get("passed"):
        raise RuntimeError("재현 정확도 점검을 통과한 뒤에만 수익 시험을 실행합니다.")
    with gzip.open(_scores_path(base), "rt", encoding="utf-8") as fh:
        stored = json.load(fh)
    px = load_panel(base)
    if px.dates[:len(stored["dates"])] != stored["dates"][:len(px.dates)]:
        raise RuntimeError("점수와 가격 패널의 날짜가 맞지 않습니다.")
    view = _View(px)
    by_i: Dict[int, List[Dict[str, Any]]] = {}
    for r in stored["records"]:
        by_i.setdefault(r["i"], []).append(r)
    result: Dict[str, Any] = {"status": "REAL", "protocol": PROTOCOL, "evaluations": len(stored["records"]), "evaluation_days": len(by_i), "first": px.dates[min(by_i)], "last": px.dates[max(by_i)],
                              "cost_round_trip": config.round_trip_cost("KR"), "fidelity": fid, "tables": {}, "reference_2022": {}, "domains": {}, "money": {}, "primary": {},
                              "note": "구성 신호가 같은 구간에서 시험된 적이 있어 완전히 독립된 증거가 아닙니다. 국면·이벤트 영역과 배당은 빠져 있습니다."}
    for strategy, hs in HORIZONS.items():
        for h in hs:
            result["tables"][f"{strategy}|{h}"] = tables(view, by_i, strategy, h)
            result["reference_2022"][f"{strategy}|{h}"] = tables(view, by_i, strategy, h, first="2022-01-01")
            for d in DOMAINS:
                result["domains"][f"{strategy}|{d}|{h}"] = {k: v for k, v in tables(view, by_i, f"{strategy}|{d}", h).items() if k in ("dates", "ic", "t", "early", "late")}
        h = PRIMARY[strategy]
        t = result["tables"][f"{strategy}|{h}"]
        a = validate.verdict(t)
        b = money(view, by_i, strategy)
        result["money"][strategy] = b
        result["primary"][strategy] = {"horizon": h, **{k: t.get(k) for k in ("dates", "ic", "t", "spread_net", "buy_excess", "buy_dates", "early", "late", "top_fifth_excess", "bottom_fifth_excess")},
                                       "condition_a": a, "condition_b": b["passed"], "reading": reading(a["verdict"] == "WEAK_POSITIVE_EVIDENCE", b["passed"])}
        log(f"{strategy} {h}: {result['primary'][strategy]['reading']}")
    # the three highest scores against random three-name screens, by the picks-simulation method (descriptive)
    rng = np.random.default_rng(sim_picks.SEED)
    cost = config.round_trip_cost("KR")
    result["top3"] = {}
    for strategy, hs in HORIZONS.items():
        for h in hs:
            rows = sim_picks.day_rows(by_i, view, strategy, h, STEP)
            if not rows:
                continue
            top = [sim_picks.pick_top(r["score"], r["names"], sim_picks.TOP) for r in rows]
            m = sim_picks.measure(rows, top, cost)
            sims = sim_picks.random_screens(rows, sim_picks.TOP, cost, rng, sim_picks.RANDOM_SCREENS)
            m["percentile_vs_random"] = float((sims < m["mean_excess"]).mean() * 100)
            m["random"] = {"p2_5": float(np.percentile(sims, 2.5)), "p50": float(np.percentile(sims, 50)), "p97_5": float(np.percentile(sims, 97.5))}
            m["reading"] = sim_picks.reading(m["percentile_vs_random"], m.get("early_excess"), m.get("late_excess"))
            result["top3"][f"{strategy}|{h}"] = m
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    return result
