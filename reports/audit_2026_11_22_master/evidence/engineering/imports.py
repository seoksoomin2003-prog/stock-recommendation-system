import ast, sys, os
from pathlib import Path
from collections import defaultdict
root = Path(sys.argv[1])
pk = ("terminal", "markets", "core", "utils", "pipeline", "execution", "alpha_engine", "contracts")
mods = {}
for p in list(root.glob("*.py")) + [q for d in pk for q in (root / d).rglob("*.py")]:
    if "__pycache__" in p.parts or "tests" in p.parts: continue
    name = ".".join(p.relative_to(root).with_suffix("").parts)
    if name.endswith(".__init__"): name = name[:-9]
    mods[name] = p
top, lazy = defaultdict(set), defaultdict(set)
def resolve(n):
    while n and n not in mods: n = n.rpartition(".")[0]
    return n or None
for name, p in mods.items():
    try: tree = ast.parse(p.read_text(encoding="utf-8"))
    except Exception as e: print("PARSE", name, e); continue
    def visit(node, depth):
        for ch in ast.iter_child_nodes(node):
            d2 = depth + (1 if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)) else 0)
            if isinstance(ch, ast.Import):
                for a in ch.names:
                    r = resolve(a.name)
                    if r and r != name: (lazy if d2 else top)[name].add(r)
            elif isinstance(ch, ast.ImportFrom) and ch.module and ch.level == 0:
                for a in ch.names:
                    r = resolve(ch.module + "." + a.name) or resolve(ch.module)
                    if r and r != name: (lazy if d2 else top)[name].add(r)
            visit(ch, d2)
    visit(tree, 0)
# package-level edges
def pkg(n):
    parts = n.split(".")
    return ".".join(parts[:2]) if parts[0] == "terminal" and len(parts) > 2 and parts[1] in ("qsf", "committee", "lab") else (".".join(parts[:2]) if parts[0]=="markets" and len(parts)>2 else parts[0])
pe_top, pe_lazy = defaultdict(int), defaultdict(int)
for a, bs in top.items():
    for b in bs:
        if pkg(a) != pkg(b): pe_top[(pkg(a), pkg(b))] += 1
for a, bs in lazy.items():
    for b in bs:
        if pkg(a) != pkg(b) and b not in top[a]: pe_lazy[(pkg(a), pkg(b))] += 1
print("PACKAGE EDGES top-level:"); [print("  ", a, "->", b, n) for (a, b), n in sorted(pe_top.items())]
print("PACKAGE EDGES lazy-only:"); [print("  ", a, "->", b, n) for (a, b), n in sorted(pe_lazy.items())]
# cycles in top-level graph (Tarjan SCC)
def scc(graph):
    idx, low, st, on, out, i = {}, {}, [], set(), [], [0]
    sys.setrecursionlimit(10000)
    def go(v):
        idx[v] = low[v] = i[0]; i[0] += 1; st.append(v); on.add(v)
        for w in graph.get(v, ()):
            if w not in idx: go(w); low[v] = min(low[v], low[w])
            elif w in on: low[v] = min(low[v], idx[w])
        if low[v] == idx[v]:
            c = []
            while True:
                w = st.pop(); on.discard(w); c.append(w)
                if w == v: break
            if len(c) > 1: out.append(c)
    for v in list(graph): 
        if v not in idx: go(v)
    return out
print("TOP-LEVEL CYCLES:", scc(top))
both = {k: top[k] | lazy[k] for k in set(top) | set(lazy)}
cyc = scc(both)
print("CYCLES incl. lazy:", len(cyc))
for c in cyc: print("  size", len(c), sorted(c)[:40])
# lazy edges that would close a top-level cycle
print("modules:", len(mods), "top edges:", sum(map(len, top.values())), "lazy edges:", sum(len(lazy[k] - top[k]) for k in lazy))
fan_in = defaultdict(int)
for a, bs in both.items():
    for b in bs: fan_in[b] += 1
print("highest fan-in:", sorted(fan_in.items(), key=lambda x: -x[1])[:15])
print("highest fan-out:", sorted(((k, len(v)) for k, v in both.items()), key=lambda x: -x[1])[:10])
