import sys,os
sys.dont_write_bytecode=True
from pathlib import Path
from terminal import automation as a
base=Path('.')
covered=set()
for g in a.BACKUP_GLOBS:
    covered|={str(p) for p in base.glob(g)}
covered|={str(p) for p in (base/'data/qsf/ledger').glob('*.jsonl.gz')}
for n in a.FORWARD_STORES: covered|={str(p) for p in (base/'research_data'/n).glob('*.json.gz')}
covered|={str(p) for p in (base/'reports/qsf').glob('QSF_*.json')}
covered|={str(p) for p in (base/'data/news').glob('*/*.jsonl.gz')}
def du(p): return sum(f.stat().st_size for f in p.rglob('*') if f.is_file())
for top in ('data','research_data','tracking'):
    for d in sorted((base/top).iterdir()):
        if d.is_dir():
            files=[f for f in d.rglob('*') if f.is_file()]
            c=sum(1 for f in files if str(f) in covered)
            print(f"{str(d):45s} files={len(files):6d} in_backup={c:6d} MB={sum(f.stat().st_size for f in files)/1e6:9.1f}")
        else:
            print(f"{str(d):45s} file in_backup={str(d) in covered}")
print('reports/qsf not QSF_*:',[p.name for p in (base/'reports/qsf').glob('*') if not p.name.startswith('QSF_')][:10])
import subprocess
ig=subprocess.run(['git','ls-files','--others','--ignored','--exclude-standard','--directory'],capture_output=True,text=True).stdout.split('\n')
print('ignored top-level:',[x for x in ig if x.count('/')<=1][:40])
