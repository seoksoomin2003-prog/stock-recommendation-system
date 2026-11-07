"""Measure whether OpenDART insider ownership filings could fill the empty Korean insider signal.  No score change.
Reads filings saved in the git-ignored research_data/kr_insider_probe (2026-11-07 fetch, 90 days to 2026-11-06).
Prints counts only, no reporter names.  Run with: python -I scripts/qsf_kr_insider_coverage.py"""
import collections, json, re, statistics
from datetime import date

OUT = "research_data/kr_insider_probe"
ROW = re.compile(r"([가-힣]{2,14})\s*\(\s*([+-])\s*\)\s*(\d{4})(?:년\s*|\.)(\d{1,2})(?:월\s*|\.)(\d{1,2})일?\s+(\S+)\s+([\d,]+|-)\s+(-?[\d,]+)\s+([\d,]+|-)\s+([\d,]+|-)")
BUY, SELL = "장내매수", "장내매도"


def num(s):
    return 0 if s == "-" else int(s.replace(",", ""))


filings = json.load(open(f"{OUT}/filings.json", encoding="utf-8"))
match = differ = unparsed = 0
stats = {k: {"rows": collections.Counter(), "lags": [], "buy": collections.Counter(), "sell": collections.Counter()} for k in ("officer", "shareholder")}
reasons = collections.Counter()
for x in filings:
    kind = "officer" if x.get("isu_exctv_rgist_at") not in (None, "-", "") else "shareholder"
    t = open(f"{OUT}/{x['rcept_no']}.txt", encoding="utf-8").read()
    i = t.find("세부변동내역")
    seg = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t[i:i + 200000])) if i >= 0 else ""
    end = seg.find("합 계")
    rows = ROW.findall(seg[:end] if end > 0 else seg)
    if not rows:
        unparsed += 1
        continue
    rep = (x.get("sp_stock_lmp_irds_cnt") or "").replace(",", "")
    if rep.lstrip("-").isdigit() and int(rep) == sum(num(r[7]) for r in rows):
        match += 1
    else:
        differ += 1
    filed = date.fromisoformat(x["rcept_dt"])
    for r in rows:
        reasons[r[0]] += 1
        if r[0] not in (BUY, SELL):
            continue
        s = stats[kind]
        s["rows"][r[0]] += 1
        s["lags"].append((filed - date(int(r[2]), int(r[3]), int(r[4]))).days)
        (s["buy"] if r[0] == BUY else s["sell"])[x["corp_code"]] += abs(num(r[7])) * num(r[9])
print("filings", len(filings), "| rows sum equals reported change", match, "differs", differ, "no rows", unparsed)
print("reasons", reasons.most_common(12))
for k, s in stats.items():
    lags = sorted(s["lags"])
    print(k, dict(s["rows"]), "names buy", len(s["buy"]), "sell", len(s["sell"]), "any", len(set(s["buy"]) | set(s["sell"])),
          "| KRW bn buy", round(sum(s["buy"].values()) / 1e9, 1), "sell", round(sum(s["sell"].values()) / 1e9, 1),
          "| lag days median", statistics.median(lags) if lags else None, "p90", lags[int(len(lags) * .9)] if lags else None)
o = stats["officer"]
sums = sorted(o["buy"].values(), reverse=True)
print("officer buy concentration: top 5 share", round(sum(sums[:5]) / sum(sums), 2) if sums else None, "names", len(sums))

# Filing-weighted lag, officers, last open-market row to receipt date.  Row counts above overweight long monthly filings.
flags = []
for x in filings:
    if x.get("isu_exctv_rgist_at") in (None, "-", ""):
        continue
    t = open(f"{OUT}/{x['rcept_no']}.txt", encoding="utf-8").read()
    i = t.find("세부변동내역")
    seg = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t[i:i + 200000])) if i >= 0 else ""
    end = seg.find("합 계")
    ds = [date(int(r[2]), int(r[3]), int(r[4])) for r in ROW.findall(seg[:end] if end > 0 else seg) if r[0] in (BUY, SELL)]
    if ds:
        flags.append((date.fromisoformat(x["rcept_dt"]) - max(ds)).days)
flags.sort()
print("officer filings with open-market rows", len(flags), "lag from last trade: median", statistics.median(flags), "p90", flags[int(len(flags) * .9)])
