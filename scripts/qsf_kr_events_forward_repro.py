"""Does the daily record's score match the one-shot test on the same days?  Uses the test's frozen filing lists and features.  Reads no return."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from terminal.qsf import kr_events_forward as ef, research_kr as kr, research_kr_events as ke  # noqa: E402


def main():
    ef.LISTS = ke.DATA
    px, rows, _ = ke._inputs(ROOT)
    with np.load(ROOT / ke.FEATURES) as z:
        tensor = z["tensor"]
    total = 0
    for n in range(len(rows) - 1, len(rows) - 13, -1):
        i = rows[n]
        day = px.dates[i]
        got = {r["code"]: r for r in ef.score_day(ROOT, day)["rows"]}
        want = {px.symbols[j]: tensor[n, j] for j in np.flatnonzero(np.isfinite(tensor[n, :, 0]))}
        wrong = [c for c in set(got) & set(want) if got[c]["financing"] != int(want[c][0]) or got[c]["buyback"] != int(want[c][1])]
        print(day, "record", len(got), "test", len(want), "only record", len(set(got) - set(want)), "only test", len(set(want) - set(got)), "different", len(wrong), sorted(set(got) ^ set(want))[:6])
        total += len(wrong)
    print("different in all", total)


if __name__ == "__main__":
    main()
