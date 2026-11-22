"""Read-only: classify test functions by whether they assert on source text (py/js/html) rather than behaviour.
Heuristic, per test function: SOURCE_TEXT if its body (or a module-level helper/constant it names) reads a repo source file
(.py/.js/.html/.css under app.py, terminal/, utils/, markets/) or uses inspect.getsource / ast.parse."""
import ast, re, sys
from pathlib import Path
root = Path(__file__).resolve().parents[4]
SRC = re.compile(r"""(getsource|ast\.parse|STATIC|static["'/ ]|\.js["']|\.html["']|\.css["']|app\.py["']|service\.py["']|["'][\w/]+\.py["'])""")
tot = src_tests = 0
per = {}
modlevel = {}
for f in sorted((root / "tests").glob("test_*.py")):
    text = f.read_text(encoding="utf-8")
    try:
        tree = ast.parse(text)
    except SyntaxError:
        continue
    # module-level names bound to source text (e.g. JS = (STATIC / "app.js").read_text())
    textnames = set()
    for node in tree.body:
        if isinstance(node, ast.Assign):
            seg = ast.get_source_segment(text, node) or ""
            if "read_text" in seg and SRC.search(seg):
                for t in node.targets:
                    if isinstance(t, ast.Name):
                        textnames.add(t.id)
        if isinstance(node, ast.FunctionDef) and not node.name.startswith("test_"):
            seg = ast.get_source_segment(text, node) or ""
            if ("read_text" in seg and SRC.search(seg)) or "getsource" in seg:
                textnames.add(node.name)
    n = s = 0
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test"):
            n += 1
            seg = ast.get_source_segment(text, node) or ""
            names = {x.id for x in ast.walk(node) if isinstance(x, ast.Name)}
            hit = ("getsource" in seg) or ("read_text" in seg and SRC.search(seg)) or bool(names & textnames)
            s += bool(hit)
    tot += n; src_tests += s
    if s:
        per[f.name] = (s, n)
print("test functions:", tot, "source-text tests (heuristic):", src_tests, f"= {100*src_tests/tot:.1f}%")
for k, v in sorted(per.items(), key=lambda kv: -kv[1][0])[:25]:
    print(f"  {k}: {v[0]}/{v[1]}")
