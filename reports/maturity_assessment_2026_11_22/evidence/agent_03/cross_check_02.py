"""Agent 03 cross-review of Agent 02: two factual claims, from the 2026-11-20 ledger record (scores and stored factor values only)."""
import sys, pathlib, json, collections
real = pathlib.Path.home() / "Developer/quant-stock-engine"; sys.path.insert(0, str(real))
from terminal.qsf.ledger import Ledger
led = Ledger(real); out = {}
ext = json.load(open(pathlib.Path(__file__).parent / "exp_ext.json"))
for m in ("US", "KR"):
    snaps = []
    for r in led._live_rows():
        if r["market"] == m and r["session"] == "2026-11-20": snaps += led._load(r)
    S = [s for s in snaps if s["strategy"] == "LONG_TERM" and s.get("data_date") == "2026-11-20" and s["ticker"] != "SPY"]
    f = lambda s, k: next((x for x in s["factors"] if x["factor"] == k), {})
    fin = [s for s in S if f(s, "leverage").get("status") == "NOT_APPLICABLE"]
    non = [s for s in S if f(s, "leverage").get("status") != "NOT_APPLICABLE"]
    bq = [f(s, "business_quality") for s in S if f(s, "business_quality").get("normalized") is not None]
    fr = [f(s, "financial_resilience") for s in non if f(s, "financial_resilience").get("normalized") is not None and "interest_cover" in (f(s, "financial_resilience").get("raw") or {})]
    gm_all = sum(1 for x in bq if x["raw"].get("gross_margin") is None)
    gm_non = sum(1 for s in non if f(s, "business_quality").get("normalized") is not None and f(s, "business_quality")["raw"].get("gross_margin") is None)
    three = sum(1 for x in bq if all(x["raw"].get(k) is not None for k in ("roe", "op_margin", "gross_margin")))
    ic_miss = sum(1 for x in fr if x["raw"].get("interest_cover") is None)
    all3 = sum(1 for x in fr if all(x["raw"].get(k) is not None for k in ("current_ratio", "interest_cover", "cash_debt")))
    buy = [s for s in S if (s.get("score") or 0) >= 70]
    sec = ext[f"{m}_LONG_TERM"]["x9_sector_size"]["sectors"].get("금융", {})
    out[m] = {"n": len(S), "financial_by_rule": len(fin), "non_financial": len(non),
              "gross_margin_missing": {"of_scored_business_quality": [gm_all, len(bq), round(gm_all / len(bq), 3)], "of_non_financial": [gm_non, len(non), round(gm_non / len(non), 3)]},
              "roe_opmargin_grossmargin_all_present": [three, len(bq)],
              "interest_cover_missing": {"of_non_financial_with_factor": [ic_miss, len(fr), round(ic_miss / len(fr), 3)], "if_financials_counted_as_missing_of_all": round((ic_miss + len(fin)) / len(S), 3)},
              "resilience_all_three_inputs": [all3, len(fr)],
              "buy_band": len(buy), "buy_band_scored_as_financial_rule": sum(1 for s in buy if f(s, "leverage").get("status") == "NOT_APPLICABLE"),
              "sector_label_financials": sec}
    if m == "US":
        for tk in ("PHM", "CME"):
            s = next((x for x in S if x["ticker"] == tk), None)
            if s: out[tk] = {"score": round(s["score"], 1), **{k: {"norm": f(s, k).get("normalized"), "raw": f(s, k).get("raw")} for k in ("leverage", "balance_dilution", "financial_resilience")}}
json.dump(out, open(pathlib.Path(__file__).parent / "cross_check_02.json", "w"), ensure_ascii=False, indent=1, default=str)
print(json.dumps(out, ensure_ascii=False, indent=1, default=str))
