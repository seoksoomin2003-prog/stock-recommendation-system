"""Agent 01 scratch: time and memory of one kr_bars.panel() call (what each Korean price-fill and chart request does).  Read only."""
import sys, time, resource
from pathlib import Path
REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
from terminal.qsf import kr_bars
for k in range(2):
    t0 = time.time(); p = kr_bars.panel(REPO); dt = time.time() - t0
    print(f"call {k + 1}: {dt:.2f} s, codes {len(p['codes']) if p else None}, shape {getattr(p['data'], 'shape', None) if p else None}")
print("max RSS MB", resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e6)
