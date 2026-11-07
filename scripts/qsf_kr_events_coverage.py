"""Before the Korean filing-event test: are the market-wide lists complete and are the titles read correctly?  Reads no return."""
import gzip
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from terminal.qsf import research_kr as kr, research_kr_events as ke  # noqa: E402

DETAIL = {"piicDecsn": "financing", "fricDecsn": None, "pifricDecsn": "financing", "cvbdIsDecsn": "financing", "bdwtIsDecsn": "financing", "tsstkAqDecsn": "buyback", "tsstkAqTrctrCnsDecsn": "buyback"}


def main():
    root = ROOT / ke.DATA
    stock_of = json.loads((root / "corp.json").read_text(encoding="utf-8"))
    files = sorted(root.glob("*Q?.json.gz"))
    rows = []
    for f in files:
        with gzip.open(f, "rt", encoding="utf-8") as fh:
            rows += json.load(fh)
    print("quarters", len(files), "rows", len(rows), "distinct receipts", len({r[0] for r in rows}))

    titles = Counter(re.sub(r"\s+", "", r[3] or "") for r in rows)
    plain = {t: n for t, n in titles.items() if ke.FORM.match(t)}
    print("first-form titles", len(plain), "rows", sum(plain.values()), "other titles rows", sum(titles.values()) - sum(plain.values()))
    prefixes = Counter(re.match(r"^\[[^\]]*\]", t).group(0) for t in titles for _ in range(titles[t]) if re.match(r"^\[[^\]]*\]", t))
    print("bracket prefixes", dict(prefixes.most_common()))
    print("--- first-form titles and how each is read")
    for t, n in sorted(plain.items(), key=lambda x: -x[1]):
        print(f"{n:6d} {ke.classify(t) or '-':10s} {t}")
    odd = [(t, n) for t, n in titles.items() if not ke.FORM.match(t) and not t.startswith("[")]
    print("--- other titles without a bracket", len(odd))
    for t, n in sorted(odd, key=lambda x: -x[1])[:15]:
        print(f"{n:6d} {t}")

    used = [r for r in rows if ke.classify(r[3])]
    blank = [r for r in used if not r[2]]
    found = [r for r in blank if stock_of.get(r[1])]
    print("--- used filings", len(used), "blank code", len(blank), "resolved through company list", len(found))

    px = kr._load(ROOT)
    syms = set(px.symbols.tolist() if hasattr(px.symbols, "tolist") else px.symbols)
    events = ke.load_events(root)
    print("codes with events", len(events), "in price panel", len(set(events) & syms))
    outside = [r for r in used if (r[2] or stock_of.get(r[1])) and (r[2] or stock_of.get(r[1])) not in syms]
    print("used filings outside the price panel", len(outside), "unresolved", len(blank) - len(found), "inside", len(used) - len(outside) - (len(blank) - len(found)))

    since = next(k for k, d in enumerate(px.dates) if d >= ke.REF_START)
    with np.load(ROOT / kr.FEATURES) as z:
        fr = [int(i) for i in z["rows"]]
    ever = set()
    for i in fr:
        if i >= since:
            ever.update(np.flatnonzero(kr.eligible(px.data, i)).tolist())
    gone_mask = ~np.isfinite(px.data["adj_close"][-1])
    ever_syms = {px.symbols[j] for j in ever}
    gone = {px.symbols[j] for j in ever if gone_mask[j]}
    print("ever eligible since 2018", len(ever_syms), "later gone", len(gone))
    print("with a used filing: ever eligible", len(ever_syms & set(events)), f"{len(ever_syms & set(events)) / len(ever_syms):.3f}", "later gone", len(gone & set(events)), f"{len(gone & set(events)) / max(1, len(gone)):.3f}")

    print("--- check against company-by-company detail reports for the 60-name sample")
    sample = ROOT / "research_data" / "kr_share_probe" / "candidates"
    from_list = {}
    for r in used:
        code = r[2] or stock_of.get(r[1])
        from_list.setdefault(code, set()).add(r[0])
    per = Counter()
    only_detail, only_list = [], []
    for f in sorted(sample.glob("*.json")):
        m = re.match(r"^(\d{6})_([A-Za-z]+)\.json$", f.name)
        if not m or m.group(2) not in DETAIL or DETAIL[m.group(2)] is None:
            continue
        code, kind = m.group(1), m.group(2)
        body = json.loads(f.read_text(encoding="utf-8"))
        for x in body.get("list") or []:
            rc = str(x.get("rcept_no") or "")
            if rc[:4] < "2016":
                continue
            per["detail rows"] += 1
            if rc in from_list.get(code, set()):
                per["found as first filing"] += 1
            else:
                only_detail.append((code, kind, rc))
    codes = {re.match(r"^(\d{6})_", f.name).group(1) for f in sample.glob("*.json") if re.match(r"^(\d{6})_", f.name)}
    detail_rcs = set()
    for f in sample.glob("*.json"):
        m = re.match(r"^(\d{6})_([A-Za-z]+)\.json$", f.name)
        if m and DETAIL.get(m.group(2)):
            detail_rcs |= {str(x.get("rcept_no")) for x in json.loads(f.read_text(encoding="utf-8")).get("list") or []}
    for code in codes:
        for rc in from_list.get(code, set()):
            per["list first filings in sample names"] += 1
            if rc not in detail_rcs:
                only_list.append((code, rc))
    print("sample codes", len(codes), dict(per), "list only", len(only_list))
    amended = {r[0]: r[3] for r in rows}
    reasons = Counter((amended.get(rc) or "not in list") for _, _, rc in only_detail)
    print("detail rows not read as a first filing, by title")
    for t, n in reasons.most_common(12):
        print(f"{n:5d} {t}")
    print("list only examples", only_list[:8])


if __name__ == "__main__":
    main()
