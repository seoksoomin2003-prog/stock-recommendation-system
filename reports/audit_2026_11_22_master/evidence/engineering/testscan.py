import ast, sys, re
from pathlib import Path
root = Path(sys.argv[1]) / "tests"
tot = src = 0
perfile = {}
kw = re.compile(r"getsource|\.read_text\(|STATIC|static/|app\.js|index\.html|\.py\"\)|_src\b|SOURCE|source\b")
strong = re.compile(r"inspect\.getsource|read_text\([^)]*\)\s*$|(app\.js|index\.html|style\.css|\.py)['\"]")
for p in sorted(root.glob("test_*.py")):
    text = p.read_text(encoding="utf-8")
    tree = ast.parse(text)
    # module-level names bound to source text
    srcnames = set()
    for node in tree.body:
        if isinstance(node, ast.Assign):
            seg = ast.get_source_segment(text, node) or ""
            if re.search(r"read_text\(|getsource", seg) and re.search(r"static|\.js|\.html|\.css|\.py|__file__|getsource", seg):
                for t in node.targets:
                    if isinstance(t, ast.Name): srcnames.add(t.id)
    n = s = 0
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef,)) and node.name.startswith("test"):
            n += 1
            seg = ast.get_source_segment(text, node) or ""
            names = {x.id for x in ast.walk(node) if isinstance(x, ast.Name)}
            if re.search(r"inspect\.getsource|getsource\(", seg) or (re.search(r"read_text\(", seg) and re.search(r"static|\.js\b|\.html\b|\.css\b|\.py\b|__file__", seg)) or (names & srcnames) or re.search(r"\b(_js|_html|js|html|css|page|src|source|code)\(\)", seg) and re.search(r" in (js|html|css|page|src|source|code|text|body)\b", seg):
                s += 1
    perfile[p.name] = (n, s)
    tot += n; src += s
print("test functions (def-level, unparametrised):", tot, "reading source text:", src, f"{src/tot:.1%}")
for k, (n, s) in sorted(perfile.items(), key=lambda x: -x[1][1])[:30]:
    if s: print(f"  {k:45s} {s}/{n}")
