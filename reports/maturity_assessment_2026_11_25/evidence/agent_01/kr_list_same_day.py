"""Agent 01 scratch: the scan/stock-card path of _kr_filing_list (whole_day=True) when the asked session is TODAY (a Korean card
built after the close and before midnight).  Fake DART, temp folder, no network."""
import sys, tempfile
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo
REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
from terminal.cache import FileCache
from terminal.qsf.service import QSF, TTL

class _R:
    def __init__(self, b): self.b = b
    def json(self): return self.b
class _Dart:
    def __init__(self): self.asked = 0
    def _get(self, endpoint, **p):
        self.asked += 1
        return _R({"status": "000", "total_page": 1, "list": [{"rcept_dt": p["end_de"], "report_nm": "x"}]})

seoul = ZoneInfo("Asia/Seoul")
with tempfile.TemporaryDirectory() as tmp:
    now = [datetime(2026, 11, 24, 16, 0, tzinfo=seoul).timestamp()]
    q = object.__new__(QSF); q.cache, q._dart = FileCache(Path(tmp), clock=lambda: now[0]), _Dart()
    for k in range(6):          # six stock-card builds between 16:00 and 21:00 for session 2026-11-24
        q._kr_filing_list("1", date(2026, 11, 24), TTL["subm"], whole_day=True)
        now[0] += 3600
    print("requests for 6 card builds 16:00-21:00 of the session day (whole_day=True):", q._dart.asked)
    now[0] = datetime(2026, 11, 25, 7, 30, tzinfo=seoul).timestamp()
    q._kr_filing_list("1", date(2026, 11, 24), TTL["subm"], whole_day=True); q._kr_filing_list("1", date(2026, 11, 24), TTL["subm"], whole_day=True)
    print("after midnight, two more builds:", q._dart.asked)
