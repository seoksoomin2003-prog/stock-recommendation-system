from common import *
import tempfile, time, types
from pathlib import Path
from terminal.cache import FileCache
from terminal.qsf import service, fundamentals as F
tmp = Path(tempfile.mkdtemp(prefix="cache_", dir=str(Path(__file__).parent)))
now = time.time()
old_clock = lambda: now - 400 * 86400                     # the copy was stored 400 days ago
FileCache(tmp, old_clock).write("info:XYZ", {"sharesOutstanding": 1_000_000_000, "marketCap": 1.0e11, "currentPrice": 100.0, "heldPercentInsiders": 0.30, "dividendYield": 2.0, "sector": "Technology"})
cache = FileCache(tmp)
class DeadSource:
    def yahoo_info(self, t):
        raise ConnectionError("provider down")
fake = types.SimpleNamespace(cache=cache, src=DeadSource())
res = cache.cached("info:XYZ", service.TTL["info"], lambda: fake.src.yahoo_info("XYZ"))
print("FileCache answer when the provider fails:", {k: res[k] for k in ("status", "age_s", "error")}, "| age days", round(res["age_s"] / 86400))
info, moved = service.QSF._us_info(fake, "XYZ", 105.0)
print("QSF._us_info returns:", {"sharesOutstanding": info.get("sharesOutstanding"), "heldPercentInsiders": info.get("heldPercentInsiders")}, "| count_unknown:", moved, "| any stale marker in the return value:", "status" in info or "stale" in info)
print("service._stale() on that answer WOULD give:", service._stale("Yahoo 기업 정보", res))
# the company halved its share count by buyback/reverse split 300 days ago; the 400-day-old count goes into market value, PER, PBR
def series(**cols):
    ends, filed = ["2023-12-31", "2024-12-31", "2025-12-31"], ["2024-02-20", "2025-02-20", "2026-02-20"]
    return {k: [{"end": e, "val": float(v), "filed": f} for e, f, v in zip(ends, filed, vals)] for k, vals in cols.items()}
A = series(revenue=[10e9, 11e9, 12e9], net_income=[1e9, 1.1e9, 1.2e9], eps=[1.0, 1.1, 1.2], shares_avg=[1e9, 1e9, 1e9], equity=[8e9, 8.5e9, 9e9], assets=[20e9] * 3, ocf=[1.5e9] * 3, capex=[0.5e9] * 3)
for tag, shares in (("fresh count 1.25bn (after a 25% share issue)", 1.25e9), ("400-day-old stored count 1.0bn", info["sharesOutstanding"])):
    m = F.metrics(A, 105.0, "2026-11-20", shares=shares, insider_pct=info["heldPercentInsiders"])
    print(f"   {tag}: status {m['status']} market_cap {m['market_cap']:.3e} pb {m['pb']:.2f} fcf_yield {m['fcf_yield']:.4f} pe {m['pe']:.1f} ({m['pe_basis']}) | stale_inputs key present: {'stale_inputs' in m}")
print("\nannual statements: how old may the newest fiscal year be before the status is STALE?  STALE_DAYS =", F.STALE_DAYS)
for as_of in ("2027-04-13", "2027-04-15"):
    print("   FY2025 read on", as_of, "->", F.metrics(A, 105.0, as_of, shares=1e9)["status"])
import shutil; shutil.rmtree(tmp)
