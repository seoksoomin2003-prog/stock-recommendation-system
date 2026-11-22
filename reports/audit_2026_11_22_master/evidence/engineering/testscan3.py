import ast, sys, re
from pathlib import Path
root = Path(sys.argv[1]) / "tests"
SRC = re.compile(r"getsource|read_text\(")
tot = src = 0; rows = []
for p in sorted(root.glob("test_*.py")):
    text = p.read_text(encoding="utf-8"); tree = ast.parse(text)
    helpers = set()
    for node in tree.body:
        seg = ast.get_source_segment(text, node) or ""
        if SRC.search(seg) and "tmp_path" not in seg:
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
            direct = bool(re.search(r"getsource", seg)) or bool(re.search(r"(Path\(__file__\)|ROOT|REPO|STATIC|BASE_DIR|parents\[\d\])[^\n]*read_text\(", seg)) or bool(re.search(r"read_text\([^\n]*\n?[^\n]*(\.py|\.js|\.html|\.css|\.md)", seg) and "tmp_path" not in seg)
            if direct or (names & helpers): s += 1
    tot += n; src += s; rows.append((p.name, n, s))
print("test functions:", tot, "reading repo source/doc text:", src, f"{src/tot:.1%}")
print("files with >=50% such tests:", [(a, f"{c}/{b}") for a, b, c in rows if b and c / b >= 0.5])
