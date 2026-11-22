"""Read-only: the import graph of app.py, terminal/, markets/, utils/ (ast only; nothing is imported or run)."""
import ast, sys
from pathlib import Path
root = Path(__file__).resolve().parents[4]
files = [root / "app.py"] + [p for d in ("terminal", "markets", "utils") for p in (root / d).rglob("*.py")]
mod = lambda p: ".".join(p.relative_to(root).with_suffix("").parts).removesuffix(".__init__")
names = {mod(p) for p in files}
top, lazy, lines = {}, {}, {}
for p in files:
    text = p.read_text(encoding="utf-8"); tree = ast.parse(text); m = mod(p); lines[m] = text.count("\n")
    top[m], lazy[m] = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            tgt = []
            if isinstance(node, ast.Import):
                tgt = [a.name for a in node.names]
            elif node.module and node.level == 0:
                tgt = [node.module] + [f"{node.module}.{a.name}" for a in node.names]
            where = top if node.col_offset == 0 else lazy
            where[m] |= {t for t in tgt if t in names and t != m}
print("modules:", len(names), "lines:", sum(lines.values()))
print("terminal/qsf modules:", sum(1 for n in names if n.startswith("terminal.qsf.")), "lines:", sum(v for k, v in lines.items() if k.startswith("terminal.qsf.")))
research = {n for n in names if any(x in n for x in (".research_", ".validate", ".sim_picks"))}
print("research/validate modules:", len(research), "lines:", sum(lines[n] for n in research))
live = {"terminal.qsf.service", "terminal.qsf.engine", "terminal.qsf.factors", "terminal.qsf.ledger", "terminal.qsf.views", "terminal.services", "terminal.server", "terminal.automation", "terminal.assistant", "terminal.qsf.fund_period", "terminal.qsf.order_plan", "terminal.qsf.holding", "terminal.committee.service"}
for m in sorted(live):
    r_top, r_lazy = sorted(top.get(m, set()) & research), sorted(lazy.get(m, set()) & research)
    if r_top or r_lazy:
        print(f"LIVE->RESEARCH {m}: top={r_top} lazy={r_lazy}")
# top-level cycles (Tarjan-lite via DFS)
def cycles(graph):
    seen, out = set(), []
    def dfs(n, path):
        for t in graph.get(n, ()):
            if t in path:
                c = path[path.index(t):] + [t]
                k = frozenset(c)
                if k not in seen:
                    seen.add(k); out.append(c)
            elif len(path) < 12:
                dfs(t, path + [t])
    for n in graph: dfs(n, [n])
    return out
print("top-level cycles:", len(cycles(top)))
both = {m: top[m] | lazy[m] for m in names}
cy = cycles(both)
print("cycles incl. function-local imports:", len(cy))
for c in sorted(cy, key=len)[:12]:
    print("  ", " -> ".join(x.replace("terminal.", "t.") for x in c))
fan_in = {}
for m, ts in both.items():
    for t in ts: fan_in[t] = fan_in.get(t, 0) + 1
print("highest fan-in:", sorted(fan_in.items(), key=lambda kv: -kv[1])[:10])
print("lazy import statements:", sum(len(v) for v in lazy.values()), "top:", sum(len(v) for v in top.values()))
priv = 0
