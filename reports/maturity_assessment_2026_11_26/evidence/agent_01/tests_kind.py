import ast, pathlib, re, collections
T = pathlib.Path('tests')
files = sorted(T.glob('test_*.py'))
tot = 0; src_tests = 0; per = []
pat = re.compile(r"inspect\.getsource|\.read_text\([^)]*\)|ast\.parse|open\(.*\.(py|js|html|css)")
srcfile = re.compile(r"""['"][\w/\.]*\.(py|js|html|css)['"]|STATIC|static\s*/|__file__|inspect\.getsource|ast\.parse""")
kinds = collections.Counter()
mock_http = 0; server_tests = 0
for f in files:
    s = f.read_text(); tree = ast.parse(s)
    # module-level helpers reading source
    mod_src = set()
    for n in tree.body:
        if isinstance(n, ast.Assign):
            seg = ast.get_source_segment(s, n) or ''
            if ('read_text' in seg or 'getsource' in seg) and srcfile.search(seg):
                for t in n.targets:
                    if isinstance(t, ast.Name): mod_src.add(t.id)
        if isinstance(n, ast.FunctionDef) and not n.name.startswith('test'):
            seg = ast.get_source_segment(s, n) or ''
            if ('read_text' in seg or 'getsource' in seg) and srcfile.search(seg): mod_src.add(n.name)
    n_t = n_s = 0
    for n in ast.walk(tree):
        if isinstance(n, ast.FunctionDef) and n.name.startswith('test'):
            n_t += 1
            seg = ast.get_source_segment(s, n) or ''
            direct = ('getsource' in seg) or (('read_text' in seg or 'ast.parse' in seg) and srcfile.search(seg))
            via = any(re.search(r'\b%s\b' % re.escape(m), seg) for m in mod_src)
            if direct or via: n_s += 1
    tot += n_t; src_tests += n_s
    per.append((n_s, n_t, f.name))
    if 'serve(' in s or 'urlopen' in s or 'http.client' in s: server_tests += 1
print('test files', len(files), 'test functions', tot, 'functions that read source text (py/js/html)', src_tests, f'{100*src_tests/tot:.1f}%')
print('files where >=50% of tests read source:', sum(1 for a,b,_ in per if b and a/b >= .5))
print('files with any source-reading test:', sum(1 for a,b,_ in per if a))
print('files that start the HTTP server or open URLs:', server_tests)
for a,b,n in sorted(per, reverse=True)[:25]: print(f'  {a:3d}/{b:3d} {n}')
