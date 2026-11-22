import sys, socket
from pathlib import Path
def _no(*a, **k): raise RuntimeError("NETWORK BLOCKED")
socket.socket.connect = _no; socket.create_connection = _no
sys.path.insert(0, "~/Developer/quant-stock-engine")
from terminal.qsf.service import QSF
from tests.test_qsf import NOW, FakeTerm
from tests.test_qsf_stored_rank import Src, TICKERS
tmp = Path(sys.argv[1])
q = QSF(tmp / "a", src=Src(), now=lambda: NOW, terminal=FakeTerm())
first = q.scan("US", tickers=TICKERS[:3], publish=False)          # what `qsf scan --tickers T0 T1 T2` does
full = q.scan("US", tickers=TICKERS)
rows = {(r["ticker"], r["strategy"]): r["score"] for r in full["rows"]}
print("first scan ledger:", first["ledger"], "| full scan ledger:", full["ledger"])
for t in ("T0", "T1", "T2", "T3"):
    snaps = q.ledger.snapshots(market="US", ticker=t, strategy="SWING")
    rs = next(f for f in snaps[0]["factors"] if f["factor"] == "relative_strength")
    print(f"  {t}: ledger records={len(snaps)} ledger score={snaps[0]['score']:.3f} full-scan row score={rows[(t, 'SWING')]:.3f} RS raw keys={sorted(rs['raw'])}")
