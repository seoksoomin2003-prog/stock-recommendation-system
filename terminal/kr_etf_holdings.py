"""Holdings of the Korean sector funds on the rotation graph (KODEX, Samsung Asset Management), kept as dated snapshots.

Source: the fund pages' own public data feed, ``https://m.samsungfund.com/api/v1/kodex/product/{id}.do`` (robots.txt allows all).
Its ``pdf.list`` gives each holding's code, name and weight; the page shows the largest 30, which ``shown`` and ``total`` record.

The site sits behind a bot check.  This module asks politely: one fund at a time with a pause between, a plain client name, and
at the first refusal (HTTP 429/403, or a challenge page instead of data) it stops and keeps the previous snapshot.  It never
retries in a loop and never tries to pass the check.  Only a complete set of funds becomes a new snapshot, so the screen never
mixes an old fund list with a new one.

Snapshots live in ``data/kr/etf_holdings/`` (git-ignored): ``holdings_YYYYMMDD.json`` and ``LATEST.json``.  Index funds
rebalance a few times a year, so a snapshot older than ``STALE_DAYS`` is still used but flagged on screen.
"""
import json
import re
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional

FUNDS = {   # rotation symbol: (page id, fund name)
    "091160": ("2ETF07", "KODEX 반도체"), "091170": ("2ETF08", "KODEX 은행"), "102970": ("2ETF15", "KODEX 증권"),
    "091180": ("2ETF06", "KODEX 자동차"), "117460": ("2ETF21", "KODEX 에너지화학"), "117680": ("2ETF23", "KODEX 철강"),
    "117700": ("2ETF22", "KODEX 건설"), "102960": ("2ETF16", "KODEX 기계장비"), "266420": ("2ETF78", "KODEX 헬스케어"),
    "266390": ("2ETF79", "KODEX 경기소비재"), "266410": ("2ETF80", "KODEX 필수소비재"), "140710": ("2ETF30", "KODEX 운송"),
}
URL = "https://m.samsungfund.com/api/v1/kodex/product/{id}.do"
PAGE = "https://m.samsungfund.com/etf/product/view.do?id={id}"
PAUSE_S = 10
STALE_DAYS = 200
STOCK_CODE = re.compile(r"^[0-9A-Z]{6}$")   # listed shares; cash (원화예금 KRD…), futures and bonds carry 12-character ISINs


class Blocked(Exception):
    """The site refused (rate limit or bot check).  Stop and keep what we have."""


def folder(base: Path) -> Path:
    return Path(base) / "data" / "kr" / "etf_holdings"


def _get(url: str) -> Dict[str, Any]:
    import requests
    from terminal.sources import GENERIC_UA
    r = requests.get(url, headers={"User-Agent": GENERIC_UA, "Accept": "application/json"}, timeout=20)
    if r.status_code in (403, 429) or r.text.lstrip().startswith("<"):
        raise Blocked(f"HTTP {r.status_code}")
    r.raise_for_status()
    return r.json()


def parse(doc: Dict[str, Any], symbol: str) -> Dict[str, Any]:
    """One fund's stock holdings from the feed; cash, futures and other non-share lines dropped.  Raises ValueError when the document is not this fund's."""
    info, pdf = doc.get("info") or {}, doc.get("pdf") or {}
    if str(info.get("stkCd") or "").strip() not in ("", symbol):
        raise ValueError("FUND_MISMATCH")
    rows = []
    for x in pdf.get("list") or []:
        code = str(x.get("itmNo") or "").strip()
        if not STOCK_CODE.match(code):
            continue
        try:
            weight = float(x["ratio"]) if x.get("ratio") not in (None, "") else None
        except (TypeError, ValueError):
            weight = None
        rows.append({"code": code, "name": x.get("secNm"), "weight_pct": weight})
    if not rows:
        raise ValueError("NO_HOLDINGS")
    total = pdf.get("totalCnt")
    return {"as_of": _iso(pdf.get("gijunYMD")), "holdings": rows, "shown": len(rows), "total": int(total) if str(total or "").isdigit() else None}


def _iso(ymd: Optional[str]) -> Optional[str]:
    s = str(ymd or "")
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}" if len(s) == 8 and s.isdigit() else None


def refresh(base: Path, get: Callable[[str], Dict[str, Any]] = _get, pause: float = PAUSE_S, now: Callable[[], datetime] = None) -> Dict[str, Any]:
    """Fetch every fund once.  A refusal stops the run; nothing partial is saved."""
    now = now or (lambda: datetime.now(timezone.utc))
    funds: Dict[str, Any] = {}
    for i, (symbol, (fid, name)) in enumerate(FUNDS.items()):
        if i and pause:
            time.sleep(pause)
        try:
            got = parse(get(URL.format(id=fid)), symbol)
        except Blocked as exc:
            return {"status": "BLOCKED", "reason": str(exc), "fetched": len(funds), "stopped_at": name, "kept": status(base)}
        except Exception as exc:
            return {"status": "FAILED", "reason": type(exc).__name__, "fetched": len(funds), "stopped_at": name, "kept": status(base)}
        funds[symbol] = {"fund": name, "page": PAGE.format(id=fid), **got}
    stamp = now()
    doc = {"retrieved_at": stamp.isoformat(timespec="seconds"), "source": "삼성자산운용 KODEX 상품 페이지 구성종목(PDF)", "funds": funds}
    out = folder(base)
    out.mkdir(parents=True, exist_ok=True)
    name = f"holdings_{stamp.strftime('%Y%m%d')}.json"
    tmp = out / (name + ".tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(out / name)
    (out / "LATEST.json.tmp").write_text(json.dumps({"file": name, "retrieved_at": doc["retrieved_at"]}), encoding="utf-8")
    (out / "LATEST.json.tmp").replace(out / "LATEST.json")
    return {"status": "OK", "file": name, "funds": len(funds)}


def load(base: Path) -> Optional[Dict[str, Any]]:
    try:
        meta = json.loads((folder(base) / "LATEST.json").read_text(encoding="utf-8"))
        return json.loads((folder(base) / meta["file"]).read_text(encoding="utf-8"))
    except (OSError, ValueError, KeyError):
        return None


def status(base: Path, today: Optional[date] = None) -> Dict[str, Any]:
    doc = load(base)
    if not doc:
        return {"status": "NONE"}
    got = date.fromisoformat(doc["retrieved_at"][:10])
    age = ((today or datetime.now(timezone.utc).date()) - got).days
    return {"status": "STALE" if age > STALE_DAYS else "OK", "retrieved_at": doc["retrieved_at"], "age_days": age, "funds": len(doc.get("funds") or {})}


def members(base: Path, symbol: str) -> Optional[Dict[str, Any]]:
    """The stored holdings of one fund, or None when there is no snapshot for it."""
    doc = load(base)
    fund = ((doc or {}).get("funds") or {}).get(symbol)
    if not fund:
        return None
    return {**fund, "retrieved_at": doc["retrieved_at"], "codes": [h["code"] for h in fund["holdings"]]}


def import_documents(base: Path, docs: Dict[str, Dict[str, Any]], now: Callable[[], datetime] = None) -> Dict[str, Any]:
    """Save a snapshot from feed documents saved by hand (``{page id: document}``), e.g. when the site refuses scripted reads.
    The same checks as ``refresh`` apply and every fund must be present."""
    by_id = {fid: sym for sym, (fid, _) in FUNDS.items()}
    missing = [fid for fid in by_id if fid not in docs]
    if missing:
        raise ValueError("MISSING_FUNDS:" + ",".join(missing))
    return refresh(base, get=lambda url: docs[url.rsplit("/", 1)[1][:-3]], pause=0, now=now)
