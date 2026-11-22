"""Agent 01 scratch: pure-function probes of terminal/phone_view.py.  No server, no network; state in a temp folder outside the repo."""
import json, sys, tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from terminal import phone_view as pv

print("client_ok:", {ip: pv.client_ok(ip) for ip in ("127.0.0.1", "169.254.10.2", "100.64.0.5", "192.168.1.9", "0.0.0.0", "198.18.0.1", "8.8.8.8", "::ffff:192.168.0.2", "fe80::1")})
print("host_ok:", {h: pv.host_ok(h, 8766) for h in ("127.0.0.1:8766", "0.0.0.0:8766", "192.168.0.5:08766", "192.168.0.5:8766 ", "169.254.1.1:8766", "[::1]:8766", "localhost:8766", "192.168.0.5:8766:1")})
with tempfile.TemporaryDirectory() as d:
    base = Path(d)
    t = [datetime(2026, 11, 23, tzinfo=timezone.utc)]
    p = pv.PhoneView(base, port=0, now=lambda: t[0])
    code = p.switch(True)["code"]          # factory is None: no listener is started
    print("listening after switch without a factory:", p.status()["listening"])
    tok = p.pair(code, "iPhone")["token"]
    print("paired:", p.device(tok) is not None)
    # with a paired device and no live code, a stranger cannot even try a code
    print("pair with no live code:", p.pair("123456", None))
    # a state file that is cut or not JSON: every device is forgotten for that request (fails closed), nothing raised
    f = base / pv.STATE
    good = f.read_text(encoding="utf-8")
    f.write_text(good[: len(good) // 2], encoding="utf-8")
    print("torn file -> device:", p.device(tok), "| status on:", p.status()["on"])
    f.write_text(good, encoding="utf-8")
    print("restored -> device:", p.device(tok) is not None)
    # a hand-edited non-numeric 'tries'
    doc = json.loads(good); doc["tries"] = "x"; f.write_text(json.dumps(doc), encoding="utf-8")
    try:
        print("tries='x' -> device:", p.device(tok))
    except Exception as exc:
        print("tries='x' raises:", type(exc).__name__)
    f.write_text(good, encoding="utf-8")
    # the stored file: does it hold the live code in clear text while it lives?
    c2 = p.new_code()["code"]
    print("live code stored in clear in the state file:", c2 in f.read_text(encoding="utf-8"))
    # brute force budget per code
    print("tries per code:", pv.CODE_TRIES, "of 1,000,000 ->", pv.CODE_TRIES / 1_000_000)
    # last_seen write throttle
    t[0] += timedelta(minutes=5); p.device(tok); a = f.stat().st_mtime_ns
    t[0] += timedelta(minutes=5); p.device(tok); print("no write inside the hour:", f.stat().st_mtime_ns == a)
