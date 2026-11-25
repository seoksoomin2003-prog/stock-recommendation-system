"""Agent 5: the calibrated t bar (terminal/qsf/calibrate.bar) for the design of each RECORDED reading.
Random numbers only (fixed seed inside calibrate): no price, no return, no record is read.  Type (d) in the brief."""
import math, sys
sys.path.insert(0, ".")
from terminal.qsf import calibrate
STEP = 21
designs = [  # label, n dates, horizon, recorded t
    ("US BT-1 SWING 5", 152, 5, 1.14), ("US BT-1 SWING 10", 152, 10, 0.43), ("US BT-1 SWING 20", 152, 20, 0.27),
    ("US BT-1 LONG 63", 151, 63, 1.38), ("US BT-1 LONG 126", 148, 126, 2.14), ("US BT-1 LONG 252", 142, 252, 1.98),
    ("KR BT-1 SWING 5", 90, 5, 4.02), ("KR BT-1 SWING 10", 89, 10, 4.33), ("KR BT-1 SWING 20", 89, 20, 5.13),
    ("KR BT-1 LONG 63", 87, 63, 2.92), ("KR BT-1 LONG 126", 84, 126, 2.31), ("KR BT-1 LONG 252", 78, 252, 1.99),
    ("KR replay(value) LONG 63", 86, 63, 7.18), ("KR replay(value) LONG 126", 83, 126, 6.98), ("KR replay(value) LONG 252", 77, 252, 8.20),
    ("KR replay(value) SWING 20", 88, 20, 1.90),
    ("KR universe(cap) LONG 63", 86, 63, 3.40), ("KR universe(cap) LONG 126", 83, 126, 2.73), ("KR universe(cap) LONG 252", 77, 252, 2.46),
    ("KR long early LONG 63", 32, 63, 3.02), ("KR long early LONG 126", 29, 126, 2.77), ("KR long early LONG 252", 23, 252, 2.05),
    ("US open A LONG 126 (2026-11-06)", 148, 126, 2.30), ("US open A LONG 252 (2026-11-06)", 142, 252, 2.00),
    ("US OOS A LONG 252", 22, 252, 0.10),
]
print(f"{'design':36s} {'n':>4s} {'h':>4s} {'lag':>3s} {'bar':>5s} {'t':>6s}  pass@2.24 pass@bar")
for label, n, h, t in designs:
    lag = max(1, math.ceil(h / STEP))
    bar = calibrate.bar(2.24, n, h, STEP, lag)
    print(f"{label:36s} {n:4d} {h:4d} {lag:3d} {bar:5.2f} {t:6.2f}  {str(t >= 2.24):9s} {t >= bar}")
