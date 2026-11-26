import json,sys,collections
from pathlib import Path
from datetime import date,datetime,timedelta,timezone
import pandas as pd
from terminal.qsf.ledger import Ledger
from utils import nyse_calendar as nc
led=Ledger(Path('.'))
def kr_next(d):
    d+=timedelta(days=1)
    while d.weekday()>=5: d+=timedelta(days=1)
    return d
print("market session file n rec_min_utc rec_max_utc next_open_utc late? entry_sessions data_dates(price_date!=session count) versions")
for r in led._live_rows():
    snaps=led._load(r)
    ts=sorted(pd.Timestamp(s['recorded_at']) for s in snaps)
    d=date.fromisoformat(r['session'])
    if r['market']=='US':
        nx=nc.next_session(d); op=pd.Timestamp(f"{nx} 09:30",tz="America/New_York").tz_convert("UTC")
        cl=pd.Timestamp(f"{nx} 16:00",tz="America/New_York").tz_convert("UTC")
    else:
        nx=kr_next(d); op=pd.Timestamp(f"{nx} 09:00",tz="Asia/Seoul").tz_convert("UTC")
        cl=pd.Timestamp(f"{nx} 15:30",tz="Asia/Seoul").tz_convert("UTC")
    late=sum(1 for t in ts if t>=op); vlate=sum(1 for t in ts if t>=cl)
    es=collections.Counter(s.get('entry_session') for s in snaps)
    dd=collections.Counter(s.get('data_date') for s in snaps)
    stale=sum(1 for s in snaps if s.get('data_date')!=r['session'])
    dup=len(snaps)-len({(s['ticker'],s['strategy']) for s in snaps})
    print(r['market'],r['session'],r['seq'],len(snaps),ts[0].strftime('%m-%d %H:%M'),ts[-1].strftime('%m-%d %H:%M'),'open',op.strftime('%m-%d %H:%M'),'LATE' if late else 'ok',late,'afterclose',vlate,'nextsess',nx,dict(es),'data_date!=session',stale,'dup',dup,set(s['model_version'] for s in snaps))
