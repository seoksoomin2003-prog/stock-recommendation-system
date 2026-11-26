import ast, pathlib, re, collections, sys
root = pathlib.Path('.')
dirs = ['terminal','markets','utils','core','pipeline','data','tracking','execution','alpha_engine','contracts','audit','scripts','ops']
files = [p for d in dirs for p in root.joinpath(d).rglob('*.py') if '__pycache__' not in str(p)] + [root/'app.py', root/'main.py']
tot = 0; chars=0; longlines=0
funcs = []; broad = []; bare_pass = []
per_dir = collections.Counter(); per_dir_chars = collections.Counter()
for p in files:
    try: src = p.read_text()
    except Exception: continue
    lines = src.splitlines(); n = len(lines); tot += n; chars += len(src)
    longlines += sum(1 for l in lines if len(l) > 120)
    top = p.parts[0] if len(p.parts) > 1 else 'root'
    if top == 'terminal' and len(p.parts) > 2: top = 'terminal/' + p.parts[1]
    per_dir[top] += n; per_dir_chars[top] += len(src)
    try: tree = ast.parse(src)
    except SyntaxError as e: print('SYNTAX', p, e); continue
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            funcs.append((node.end_lineno - node.lineno + 1, str(p), node.name, node.lineno))
        if isinstance(node, ast.ExceptHandler):
            t = node.type
            isbroad = t is None or (isinstance(t, ast.Name) and t.id in ('Exception','BaseException'))
            if isbroad:
                body = node.body
                silent = all(isinstance(b, (ast.Pass, ast.Continue)) or (isinstance(b, ast.Return) and (b.value is None or isinstance(b.value, ast.Constant))) or (isinstance(b, ast.Expr) and isinstance(b.value, ast.Constant)) for b in body)
                uses_name = node.name and any(isinstance(x, ast.Name) and x.id == node.name for b in body for x in ast.walk(b))
                broad.append((str(p), node.lineno, silent, bool(uses_name)))
print('files', len(files), 'lines', tot, 'chars', chars, 'avg chars/line', round(chars/tot,1), 'lines>120', longlines)
for k, v in per_dir.most_common(): print(f'  {k:28s} {v:7d} lines {per_dir_chars[k]:9d} chars')
funcs.sort(reverse=True)
print('functions', len(funcs), '>60:', sum(1 for f in funcs if f[0] > 60), '>100:', sum(1 for f in funcs if f[0] > 100), '>150:', sum(1 for f in funcs if f[0]>150))
for f in funcs[:25]: print('  ', f)
print('broad excepts', len(broad), 'silent (pass/continue/return const):', sum(1 for b in broad if b[2]), 'error object used:', sum(1 for b in broad if b[3]))
c = collections.Counter(b[0] for b in broad); cs = collections.Counter(b[0] for b in broad if b[2])
for k, v in c.most_common(22): print(f'  {k:45s} broad {v:3d} silent {cs[k]:3d}')
