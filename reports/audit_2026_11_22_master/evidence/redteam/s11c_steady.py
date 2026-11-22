from common import *
from terminal.committee import portfolios as P
prev = {"A": 0.10}
path = []
for target in (0.095, 0.085, 0.081, 0.079, 0.060, 0.075, 0.081):
    w = P._fit(P._steady({"A": target}, prev), 0.12, 1.0)
    path.append((target, w["A"])); prev = w
print("target -> recorded weight:", path)
# a target that drifts by 0.019 forever is never followed
prev, gap = {"A": 0.10}, []
for target in (0.081,) * 5:
    prev = P._fit(P._steady({"A": target}, prev), 0.12, 1.0); gap.append(prev["A"])
print("target 0.081 for five days, start 0.10 ->", gap, "(kept 19% over its target every day)")
# exposure cut 1.0 -> 0.8 with 15 equal names: kept weights, then scaled by _fit
prev = {f"T{i}": 0.0667 for i in range(15)}
w = P._fit(P._steady({t: 0.8 / 15 for t in prev}, prev), 0.10, 0.8)
print("15 names, exposure limit lowered to 0.8: sum", round(sum(w.values()), 4))
