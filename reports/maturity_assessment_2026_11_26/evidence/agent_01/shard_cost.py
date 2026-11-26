import time, gzip, json, resource
from pathlib import Path
from terminal.qsf.ledger import Ledger
led = Ledger(Path('.'))
rows = led._live_rows()
print('live shards', len(rows), 'US', sum(r['market']=='US' for r in rows), 'KR', sum(r['market']=='KR' for r in rows))
for m in ('US', 'KR'):
    r = [x for x in rows if x['market'] == m][-1]
    raw = (led.dir / r['file']).read_bytes()
    t = time.time(); s = led._load(r); dt = time.time() - t
    print(m, r['file'], 'gz bytes', len(raw), 'json bytes', len(gzip.decompress(raw)), 'records', len(s), f'parse {dt:.2f}s')
    del s
t = time.time(); v = led.verify(); print('verify', v['status'], v['shards'], 'voided', v['voided'], f'{time.time()-t:.2f}s')
print('peak rss MB', resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e6)
