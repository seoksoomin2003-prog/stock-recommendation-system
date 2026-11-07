"""Before the Korean filing-event test: is a stock with no filing in the market-wide lists really without one?  Asks company by company.  Reads no return.

The address carries the key, so a failure prints the exception type only and the replies keep only the fields counted here.
"""
import gzip
import json
import os
import re
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import requests  # noqa: E402

from terminal.qsf import dart_history as dh, research_kr as kr, research_kr_events as ke  # noqa: E402
from utils.runtime_config import load_local_env  # noqa: E402


def explain_list_only(rows, stock_of):
    """Filings the sample's detail reports do not show: the sample has no trust-buyback report, and a detail report may hold only the amended version."""
    sample = ROOT / "research_data" / "kr_share_probe" / "candidates"
    detail, codes = set(), set()
    for f in sample.glob("*.json"):
        m = re.match(r"^(\d{6})_([A-Za-z]+)\.json$", f.name)
        if m:
            codes.add(m.group(1))
            if m.group(2) in ("piicDecsn", "cvbdIsDecsn", "bdwtIsDecsn", "tsstkAqDecsn"):
                detail |= {str(x.get("rcept_no")) for x in json.loads(f.read_text(encoding="utf-8")).get("list") or []}
    by_corp_title = {}
    for rc, corp, stock, name in rows:
        by_corp_title.setdefault((corp, re.sub(r"^\[[^\]]*\]", "", re.sub(r"\s+", "", name or ""))), []).append((rc, name))
    out = Counter()
    for rc, corp, stock, name in rows:
        code = stock or stock_of.get(corp)
        if code not in codes or not ke.classify(name) or rc in detail:
            continue
        title = re.sub(r"\s+", "", name)
        if "신탁계약체결" in title:
            out["trust buyback: no such detail report in the sample"] += 1
            continue
        later = [r for r, n in by_corp_title[(corp, title)] if r > rc and n != name]
        out["amended later, detail shows the amended version" if any(r in detail for r in later) else "no amendment found in detail"] += 1
    return out


def main():
    load_local_env()
    key = os.environ.get("OPENDART_API_KEY")
    if not key:
        print("NO_KEY")
        return
    root = ROOT / ke.DATA
    stock_of = json.loads((root / "corp.json").read_text(encoding="utf-8"))
    corp_of = {v: k for k, v in stock_of.items()}
    rows = []
    for f in sorted(root.glob("*Q?.json.gz")):
        with gzip.open(f, "rt", encoding="utf-8") as fh:
            rows += json.load(fh)
    print("list only explained", dict(explain_list_only(rows, stock_of)))

    px = kr._load(ROOT)
    events = ke.load_events(root)
    with np.load(ROOT / kr.FEATURES) as z:
        fr = [int(i) for i in z["rows"]]
    ever = set()
    for i in fr:
        if px.dates[i] >= ke.REF_START:
            ever.update(np.flatnonzero(kr.eligible(px.data, i)).tolist())
    gone_mask = ~np.isfinite(px.data["adj_close"][-1])
    none_gone = sorted(px.symbols[j] for j in ever if gone_mask[j] and px.symbols[j] not in events)
    none_live = sorted(px.symbols[j] for j in ever if not gone_mask[j] and px.symbols[j] not in events)
    rng = np.random.default_rng(20261108)
    picks = none_gone + sorted(rng.choice(none_live, size=min(50, len(none_live)), replace=False).tolist())
    print("no filing: later gone", len(none_gone), "still listed", len(none_live), "asked", len(picks))
    print("no DART company for the code:", sum(c not in corp_of for c in picks), "of", len(picks))

    counts, misses = Counter(), []
    for code in picks:
        corp = corp_of.get(code)
        if not corp:
            counts["no company"] += 1
            continue
        try:
            body = requests.get(dh.BASE + "list.json", params={"crtfc_key": key, "corp_code": corp, "bgn_de": "20160101", "end_de": "20261108", "pblntf_detail_ty": "B001", "last_reprt_at": "N", "page_count": 100}, timeout=60).json()
        except Exception as exc:
            counts[type(exc).__name__] += 1
            continue
        state = str(body.get("status"))
        if state not in ("000", "013"):
            counts[f"DART {state}"] += 1
            if state in ("020", "010", "011", "012", "901"):
                break
            continue
        used = [x for x in body.get("list") or [] if ke.classify(x.get("report_nm"))]
        counts["asked"] += 1
        counts["any major report"] += bool(body.get("list"))
        if used:
            misses.append((code, len(used), used[0].get("report_nm"), used[0].get("rcept_no")))
        time.sleep(0.2)
    print(dict(counts), "names with a missed filing", len(misses))
    print(misses[:10])


if __name__ == "__main__":
    main()
