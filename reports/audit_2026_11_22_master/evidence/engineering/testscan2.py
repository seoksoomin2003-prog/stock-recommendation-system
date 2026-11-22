import ast, sys, re
from pathlib import Path
root = Path(sys.argv[1]) / "tests"
SRC = re.compile(r"getsource|read_text\(")
HINT = re.compile(r"static|\.js|\.html|\.css|\.py['\"]|getsource|__file__|ROOT|BASE|REPO|terminal/|app\.py|reports/|RUNBOOK|\.md")
tot = src = 0; rows = []
for p in sorted(root.glob("test_*.py")):
    text = p.read_text(encoding="utf-8"); tree = ast.parse(text)
    helpers = set()   # module-level funcs/vars that return or hold source text
    for node in tree.body:
        seg = ast.get_source_segment(text, node) or ""
        if SRC.search(seg) and HINT.search(seg):
            if isinstance(node, ast.FunctionDef) and not node.name.startswith("test"): helpers.add(node.name)
            if isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name): helpers.add(t.id)
    n = s = 0
    for node in tree.body:
        fns = [node] if isinstance(node, ast.FunctionDef) else [x for x in node.body if isinstance(x, ast.FunctionDef)] if isinstance(node, ast.ClassDef) else []
        for fn in fns:
            if not fn.name.startswith("test"): continue
            n += 1
            seg = ast.get_source_segment(text, fn) or ""
            names = {x.id for x in ast.walk(fn) if isinstance(x, ast.Name)}
            if (SRC.search(seg) and HINT.search(seg) and "tmp_path" not in seg.split("read_text")[0][-60:]) or (names & helpers):
                s += 1
    tot += n; src += s; rows.append((p.name, n, s))
print("test functions:", tot, "touching source/doc text:", src, f"{src/tot:.1%}")
for name, n, s in sorted(rows, key=lambda r: -r[2])[:25]:
    if s: print(f"  {name:45s} {s}/{n}")
