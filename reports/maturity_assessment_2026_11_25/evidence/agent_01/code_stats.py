"""Agent 01 scratch: size and shape of the code (reads source text only)."""
import ast, re, subprocess, sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[4]
def py(folder): return [p for p in (REPO / folder).rglob("*.py") if "__pycache__" not in p.parts]
groups = {"app.py": [REPO / "app.py"], "terminal (all)": py("terminal"), "terminal/qsf": py("terminal/qsf"), "terminal/committee": py("terminal/committee"), "utils": py("utils"), "markets": py("markets"), "core": py("core"), "tests": py("tests")}
for name, files in groups.items():
    lines = sum(len(p.read_text(encoding="utf-8").splitlines()) for p in files)
    print(f"{name:20s} files {len(files):4d} lines {lines:6d}")
live = [REPO / "app.py"] + py("terminal") + py("utils") + py("markets")
fn = nodoc = longl = total = broad = big = 0
biggest = []
for p in live:
    src = p.read_text(encoding="utf-8")
    ls = src.splitlines(); total += len(ls); longl += sum(1 for l in ls if len(l) > 160)
    broad += len(re.findall(r"except Exception", src))
    tree = ast.parse(src)
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            fn += 1; nodoc += ast.get_docstring(n) is None
            size = (n.end_lineno or n.lineno) - n.lineno + 1
            if size > 60: big += 1; biggest.append((size, f"{p.relative_to(REPO)}:{n.lineno} {n.name}"))
print("live code lines", total, "| functions", fn, "| without docstring", nodoc, f"({nodoc / fn:.0%})", "| lines > 160 chars", longl, f"({longl / total:.1%})", "| except Exception", broad, "| functions > 60 lines", big)
print("largest functions:", sorted(biggest, reverse=True)[:8])
research = [p for p in py("terminal/qsf") if p.name.startswith(("research_", "validate", "walkforward", "sim_"))]
print("research/validation modules in terminal/qsf:", len(research), "lines", sum(len(p.read_text(encoding='utf-8').splitlines()) for p in research))
js = list((REPO / "terminal/static").glob("*.js"))
jl = [l for p in js for l in p.read_text(encoding="utf-8").splitlines()]
print("static js files", len(js), "lines", len(jl), "| lines > 200 chars", sum(1 for l in jl if len(l) > 200), "| longest", max(map(len, jl)))
print("tests: files", len([p for p in py('tests') if p.name.startswith('test_')]), "| test functions", sum(len(re.findall(r'^\s*def test_', p.read_text(encoding='utf-8'), re.M)) for p in py('tests')))
print("source-text tests (read_text of terminal/ or app.py):", sum(len(re.findall(r'read_text', p.read_text(encoding='utf-8'))) for p in py('tests')))
print("lint/type config present:", [f for f in ("pyproject.toml", "setup.cfg", "ruff.toml", ".flake8", "mypy.ini", ".pre-commit-config.yaml", ".github") if (REPO / f).exists()])
app = (REPO / "app.py").read_text(encoding="utf-8")
print("app.py qsf actions (choices strings):", len(set(re.findall(r'"([a-z0-9]+(?:-[a-z0-9]+)+)"', app))))
cfg = (REPO / "terminal/qsf/config.py").read_text(encoding="utf-8")
consts = sum(len(re.findall(r'^[A-Z][A-Z0-9_]+\s*(?::[^=]+)?=', p.read_text(encoding="utf-8"), re.M)) for p in py("terminal/qsf"))
print("module-level constants in terminal/qsf:", consts, "| in config.py:", len(re.findall(r'^[A-Z][A-Z0-9_]+\s*(?::[^=]+)?=', cfg, re.M)))
print("files that call Ledger._live_rows/_load outside ledger.py:", sum(1 for p in live if p.name != "ledger.py" and re.search(r"\._live_rows\(|\._load\(", p.read_text(encoding="utf-8"))))
print("logging calls in terminal/qsf:", sum(len(re.findall(r"\blog(?:ger|ging)?\.(?:debug|info|warning|error|exception)\(", p.read_text(encoding="utf-8"))) for p in py("terminal/qsf")))
