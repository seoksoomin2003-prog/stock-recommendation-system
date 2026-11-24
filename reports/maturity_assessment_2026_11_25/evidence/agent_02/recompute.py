"""Agent 02 scratch (copied 2026-11-25 from the 2026-11-23 assessment, unchanged logic): hand recomputation of fundamental figures from the stored annual series, against what the ledger stored.
Read only.  No provider, no returns.  One ledger session per market."""
import json, sys
from pathlib import Path
repo = Path.home() / "Developer" / "quant-stock-engine"
sys.path.insert(0, str(repo))
from terminal.qsf.ledger import Ledger
from terminal.cache import FileCache
from terminal import sources

market = sys.argv[1]
tickers = sys.argv[2].split(",")
led = Ledger(repo)
row = [r for r in led._live_rows() if r["market"] == market][-1]
snaps = led._load(row)
cache = FileCache(repo / "data" / "qsf" / "cache")
session = row["session"]
out = {}


def raws(t):
    got = {}
    for s in snaps:
        if s["ticker"] == t:
            for f in s["factors"]:
                if isinstance(f.get("raw"), dict):
                    for k, v in f["raw"].items():
                        got.setdefault(k, v)
            got.setdefault("_price", s.get("price"))
            got.setdefault("_cik", s.get("cik"))
            got["_score_" + s["strategy"]] = s.get("score")
            got["_band_" + s["strategy"]] = s.get("band")
            got["_entry_" + s["strategy"]] = s.get("entry_status")
            got["_filed_" + s["strategy"]] = next((f.get("as_of") for f in s["factors"] if f["factor"] in ("valuation", "profitability")), None)
    return got


def last(series, n=4):
    """Latest vintage per fiscal year end, newest n years."""
    per = {}
    for r in series or []:
        if r["filed"] <= session and (r["end"] not in per or r["filed"] >= per[r["end"]]["filed"]):
            per[r["end"]] = r
    return [per[k] for k in sorted(per)][-n:]


def d(a, b):
    return None if a is None or b in (None, 0) else a / b


for t in tickers:
    r = raws(t)
    if market == "US":
        key = f"annual4:{sources.facts_key(t, r['_cik'])}"
    else:
        key = f"krfund3:{t}"
    rec = cache.read(key)
    if rec is None:
        print(t, "NO CACHE", key)
        continue
    a = rec["data"]
    S = {k: last(v) for k, v in a.items() if isinstance(v, list) and not k.startswith("_")}
    ends = sorted({x["end"] for v in S.values() for x in v})
    latest = ends[-1]
    def at(k, i=-1):
        rows = [x for x in S.get(k, [])]
        byend = {x["end"]: x["val"] for x in rows}
        e = ends[i] if len(ends) >= -i else None
        return byend.get(e)
    print(f"\n===== {t} ({market}) fiscal ends {ends[-4:]} cache stored_at day; bases {a.get('_bases')}")
    for k in ("revenue", "gross_profit", "op_income", "net_income", "net_income_all", "equity", "equity_all", "assets", "liabilities", "current_assets", "current_liabilities", "cash", "ocf", "capex",
              "interest", "debt_total", "debt_long", "debt_short", "debt_borrow", "eps", "shares_avg", "buyback", "dividends"):
        if k in S:
            print(f"  {k:20s}", [(x["end"][:7], round(x["val"] / (1e6 if abs(x["val"]) > 1e7 else 1), 2), x.get("alias", "")[:28]) for x in S[k][-3:]])
        else:
            print(f"  {k:20s} -- not in stored series")
    rev, ni, eq, ocf, capex = at("revenue"), at("net_income"), at("equity"), at("ocf"), at("capex")
    rev0, ni0, eq0 = at("revenue", -2), at("net_income", -2), at("equity", -2)
    hand = {
        "roe": d(ni, eq), "op_margin": d(at("op_income"), rev), "gross_margin": d(at("gross_profit"), rev),
        "rev_growth": None if d(rev, rev0) is None else rev / rev0 - 1,
        "ocf_to_ni": d(ocf, at("net_income_all") if (market == "KR" and at("net_income_all") is not None and at("equity_all") is not None) else ni),
        "fcf_margin": None if ocf is None or capex is None else d(ocf - capex, rev),
        "current_ratio": d(at("current_assets"), at("current_liabilities")),
        "interest_cover": d(at("op_income"), at("interest")),
        "equity_assets": d(at("equity_all") or eq, at("assets")),
        "liab_equity": d(at("liabilities"), at("equity_all") or eq),
        "roe_prev": d(ni0, eq0),
        "share_change": None if d(at("shares_avg"), at("shares_avg", -2)) is None else at("shares_avg") / at("shares_avg", -2) - 1,
        "eps_growth_reported": None if not at("eps") or not at("eps", -2) or at("eps", -2) <= 0 else at("eps") / at("eps", -2) - 1,
        "pe_price_over_eps": d(r.get("_price"), at("eps")),
    }
    if len(ends) >= 4 and at("revenue", -4) and rev and at("revenue", -4) > 0 and rev > 0:
        hand["rev_cagr3"] = (rev / at("revenue", -4)) ** (1 / 3) - 1
    # implied share count behind stored PBR: pb * equity / price
    if r.get("pb") and eq and r.get("_price"):
        hand["implied_shares_from_pb(M)"] = r["pb"] * eq / r["_price"] / 1e6
    print("  price", r.get("_price"), "| long score", r.get("_score_LONG_TERM"), r.get("_band_LONG_TERM"), r.get("_entry_LONG_TERM"), "| swing", r.get("_score_SWING"), "| filed", r.get("_filed_LONG_TERM"))
    print("  figure               hand        stored")
    for k, v in hand.items():
        sk = {"liab_equity": "debt_equity", "eps_growth_reported": "eps_growth", "pe_price_over_eps": "pe"}.get(k, k)
        st = r.get(sk)
        flag = ""
        if isinstance(v, (int, float)) and isinstance(st, (int, float)) and abs(v - st) > 1e-3 * max(1, abs(st)):
            flag = "  <-- differs"
        print(f"  {k:26s} {v if v is None else round(v, 4)!s:>12}  {st if not isinstance(st, float) else round(st, 4)!s:>12}{flag}")
    print("  other stored:", {k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items() if k in ("pb", "fcf_yield", "eps_cagr3", "roe_years_positive", "fcf_years_positive", "cash_debt", "returns_capital", "insider_pct")})
