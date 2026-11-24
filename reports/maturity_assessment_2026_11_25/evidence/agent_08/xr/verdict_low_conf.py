"""'사도 돼?' conclusion (pure function assistant.buy_verdict) on the stored LOW-confidence card 005830, under the stored KR stance.
No POST, no provider call.  Gates and marks taken as empty (the KR Today reply lists no avoid mark on it)."""
import sys
from pathlib import Path
repo = Path.home() / "Developer/quant-stock-engine"
sys.path.insert(0, str(repo))
from terminal.qsf.ledger import Ledger
from terminal import assistant
from terminal.qsf import stance
led = Ledger(repo)
rows = [r for r in led._live_rows() if r["market"] == "KR" and str(r.get("session", "")).startswith("2026-11-23")]
s = next(x for x in led._load(rows[-1]) if x["ticker"] == "005830" and x["strategy"] == "LONG_TERM")
lv = stance.level(repo, "KR")
for level in (lv, "DEFENSIVE"):
    v = assistant.buy_verdict(s, "LONG_TERM", "KR", gates=[], marks=[], earnings={}, soon=False, level=level, wide=set(),
                              state={"size_factor": 1.0, "score_100": 26.3, "label": "나쁨"}, held=False)
    print(level, "->", v["label"], "|", v["why"], "| notes:", v["notes"])
