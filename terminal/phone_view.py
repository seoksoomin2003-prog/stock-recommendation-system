"""Opening the terminal to a phone on the same Wi-Fi (user decisions 2026-11-22).

Off until the button on this computer's screen turns it on.  The first listener (127.0.0.1, this computer only) never
changes.  When on, a second listener answers on ``PORT`` for devices of the local network:

- a device sees nothing but the pairing page until someone types the six-digit code this computer's screen shows;
- the code lives ``CODE_MINUTES`` and ``CODE_TRIES`` wrong tries, then a new one must be made on this computer;
- a paired device holds a cookie; this computer stores only the cookie's hash;
- a paired device reads every screen and makes the entries of ``PHONE_WRITES`` (journal, paper trades, watchlist,
  alerts, questions).  Rule switches, scans, settings and this module's own switches stay on this computer;
- turning it off closes the listener and forgets every device.

Plain HTTP on the local network: nothing is encrypted, so this is for a home network.  Nothing here is tied to one
operating system: sockets and files only.
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import secrets
import socket
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from utils import durable

PORT = 8766
STATE = Path("data") / "terminal" / "phone_view.json"       # git-ignored; holds the code while it lives and the devices' cookie hashes
COOKIE = "qpp_phone"
CODE_MINUTES, CODE_TRIES = 10, 5
DEVICE_DAYS, MAX_DEVICES = 180, 5
SEEN_EVERY = timedelta(hours=1)                              # a device's "last seen" is written at most this often

# What a paired phone may send.  Everything else that changes something answers PHONE_MAC_ONLY.
PHONE_WRITES = frozenset({"/api/journal/add", "/api/journal/void", "/api/paper-trade/add", "/api/paper-trade/void", "/api/watchlist/add",
                          "/api/watchlist/remove", "/api/alerts/add", "/api/alerts/remove", "/api/alerts/rearm", "/api/assistant/ask"})

PAIR_PAGE = """<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>퀀트 터미널 · 연결</title><style>
body{font-family:-apple-system,system-ui,sans-serif;background:#0f1419;color:#e6e9ee;margin:0;padding:24px;line-height:1.6}
main{max-width:420px;margin:8vh auto 0}h1{font-size:20px}input{font-size:28px;letter-spacing:8px;width:100%;box-sizing:border-box;padding:12px;border-radius:8px;border:1px solid #3a4452;background:#161c24;color:inherit;text-align:center}
button{margin-top:12px;width:100%;font-size:17px;padding:14px;border:0;border-radius:8px;background:#6e9bff;color:#0f1419;font-weight:600}
p{color:#a8b1bd;font-size:14px}#msg{color:#ff8f8f;min-height:22px}</style></head><body><main>
<h1>퀀트 터미널에 이 기기 연결</h1>
<p>터미널을 띄운 컴퓨터 화면에서 <b>폰 연결</b> 버튼을 누르면 여섯 자리 코드가 보입니다. 그 코드를 넣으세요.</p>
<form id="f"><input id="c" inputmode="numeric" pattern="[0-9]*" maxlength="6" autocomplete="one-time-code" aria-label="연결 코드" autofocus>
<button type="submit">연결</button></form><p id="msg" role="alert"></p>
<p>같은 와이파이 안에서만 열리고 통신은 암호화되지 않습니다. 집 와이파이에서만 쓰세요.</p></main><script>
const KO={PHONE_CODE_WRONG:"코드가 맞지 않습니다.",PHONE_CODE_EXPIRED:"코드의 시간이 지났습니다. 컴퓨터 화면에서 새 코드를 만드세요.",
PHONE_CODE_LOCKED:"틀린 횟수가 많아 이 코드는 더 쓸 수 없습니다. 컴퓨터 화면에서 새 코드를 만드세요.",PHONE_TOO_MANY:"연결된 기기가 이미 다섯 대입니다. 컴퓨터 화면에서 하나를 끊으세요."};
document.getElementById("f").onsubmit=async(e)=>{e.preventDefault();const m=document.getElementById("msg");m.textContent="";
try{const r=await fetch("/api/phone/pair",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({code:document.getElementById("c").value})});
const j=await r.json().catch(()=>({}));if(r.ok){location.replace("/");return;}m.textContent=KO[j.error]||"연결하지 못했습니다.";}catch(x){m.textContent="컴퓨터에 닿지 않습니다. 같은 와이파이인지 확인하세요.";}};
</script></body></html>"""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _private(text: str) -> bool:
    try:
        ip = ipaddress.ip_address(text)
    except ValueError:
        return False
    return ip.version == 4 and ip.is_private


def client_ok(ip: str) -> bool:
    """Only a device of a private network (or this computer itself) is answered: never an address of the open internet."""
    return _private(ip)


def host_ok(host: Optional[str], port: int) -> bool:
    """The address the browser asked for must be a private IPv4 number and this port.  A page of another site that points
    its own name at this computer (DNS rebinding) sends that name here, and a name is never answered."""
    if not host or host.count(":") != 1:
        return False
    name, _, p = host.partition(":")
    return p == str(port) and _private(name)


def lan_addresses() -> List[str]:
    """This computer's address on the local network, as far as it can be told without sending anything."""
    out: List[str] = []
    for probe in ("10.255.255.255", "192.168.255.255", "172.31.255.255"):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect((probe, 1))                     # a datagram socket's connect sends nothing: it only picks the route
            ip = s.getsockname()[0]
        except OSError:
            continue
        finally:
            s.close()
        if _private(ip) and not ip.startswith("127.") and ip not in out:
            out.append(ip)
    return out


def device_name(agent: Optional[str]) -> str:
    """A word for the list on the screen.  The browser's full description is not stored."""
    a = agent or ""
    for mark, name in (("iPhone", "아이폰"), ("iPad", "아이패드"), ("Android", "안드로이드 기기"), ("Macintosh", "맥"), ("Windows", "윈도우 컴퓨터")):
        if mark in a:
            return name
    return "기타 기기"


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class PhoneView:
    def __init__(self, base: Path, port: int = PORT, now: Callable[[], datetime] = _utcnow):
        self.path, self.port, self.now = Path(base) / STATE, port, now
        self._lock = threading.RLock()
        self._httpd: Any = None
        self.factory: Optional[Callable[[], Any]] = None          # set by the server: builds the second listener
        self.listen_error: Optional[str] = None
        self._seen_written: Dict[str, datetime] = {}

    # ------------------------------------------------------------------ the stored state
    def _load(self) -> Dict[str, Any]:
        try:
            doc = json.loads(self.path.read_text(encoding="utf-8"))
            doc = doc if isinstance(doc, dict) else {}
        except (OSError, ValueError):
            doc = {}
        return {"on": doc.get("on") is True, "code": doc.get("code"), "code_until": doc.get("code_until"), "tries": int(doc.get("tries") or 0),
                "devices": [d for d in doc.get("devices") or [] if isinstance(d, dict) and d.get("hash")]}

    def _save(self, doc: Dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        durable.write_text(self.path, json.dumps(doc, ensure_ascii=False, indent=1))

    def _fresh(self, doc: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Devices whose pairing has not run out."""
        limit = (self.now() - timedelta(days=DEVICE_DAYS)).isoformat()
        return [d for d in doc["devices"] if str(d.get("paired_at") or "") >= limit]

    def _code_state(self, doc: Dict[str, Any]) -> str:
        if not doc.get("code"):
            return "NONE"
        if doc["tries"] >= CODE_TRIES:
            return "LOCKED"
        return "LIVE" if str(doc.get("code_until") or "") > self.now().isoformat() else "EXPIRED"

    # ------------------------------------------------------------------ this computer's screen
    def status(self) -> Dict[str, Any]:
        with self._lock:
            doc = self._load()
            state = self._code_state(doc)
            return {"on": doc["on"], "listening": self._httpd is not None, "port": self.port, "listen_error": self.listen_error,
                    "addresses": [f"http://{ip}:{self.port}/" for ip in lan_addresses()] if doc["on"] else [],
                    "code": doc["code"] if state == "LIVE" else None, "code_state": state, "code_until": doc.get("code_until") if state == "LIVE" else None,
                    "tries_left": max(0, CODE_TRIES - doc["tries"]) if state == "LIVE" else 0, "code_minutes": CODE_MINUTES,
                    "devices": [{"id": d["hash"][:8], "name": d.get("name"), "paired_at": d.get("paired_at"), "last_seen": d.get("last_seen")} for d in self._fresh(doc)],
                    "max_devices": MAX_DEVICES, "device_days": DEVICE_DAYS, "writes": sorted(PHONE_WRITES),
                    "note": "같은 와이파이 안에서만 열립니다. 통신은 암호화되지 않으므로 집 와이파이에서만 켜세요. 끄면 연결된 기기도 모두 끊깁니다."}

    def _new_code(self, doc: Dict[str, Any]) -> None:
        doc.update(code=f"{secrets.randbelow(1_000_000):06d}", code_until=(self.now() + timedelta(minutes=CODE_MINUTES)).isoformat(), tries=0)

    def switch(self, on: bool) -> Dict[str, Any]:
        with self._lock:
            doc = self._load()
            if on:
                doc["on"] = True
                if self._code_state(doc) != "LIVE" and not self._fresh(doc):
                    self._new_code(doc)
                self._save(doc)
                self.start()
            else:
                self._save({"on": False, "code": None, "code_until": None, "tries": 0, "devices": []})      # off forgets every device
                self.stop()
            return self.status()

    def new_code(self) -> Dict[str, Any]:
        with self._lock:
            doc = self._load()
            if not doc["on"]:
                raise ValueError("PHONE_VIEW_OFF")
            self._new_code(doc)
            self._save(doc)
            return self.status()

    def unpair(self, device_id: str) -> Dict[str, Any]:
        with self._lock:
            doc = self._load()
            doc["devices"] = [d for d in doc["devices"] if d["hash"][:8] != str(device_id)]
            self._save(doc)
            return self.status()

    # ------------------------------------------------------------------ the phone's side
    def pair(self, code: Any, agent: Optional[str]) -> Dict[str, Any]:
        """``{"token": ...}`` for the right code, else ``{"error": ...}``.  A wrong try is counted before anything is compared."""
        with self._lock:
            doc = self._load()
            state = self._code_state(doc)
            if not doc["on"] or state == "NONE":
                return {"error": "PHONE_CODE_EXPIRED"}
            if state != "LIVE":
                return {"error": "PHONE_CODE_LOCKED" if state == "LOCKED" else "PHONE_CODE_EXPIRED"}
            if not secrets.compare_digest(str(code or "").strip(), str(doc["code"])):
                doc["tries"] += 1
                self._save(doc)
                return {"error": "PHONE_CODE_LOCKED" if doc["tries"] >= CODE_TRIES else "PHONE_CODE_WRONG"}
            devices = self._fresh(doc)
            if len(devices) >= MAX_DEVICES:
                return {"error": "PHONE_TOO_MANY"}
            token, at = secrets.token_urlsafe(32), self.now().isoformat()
            devices.append({"hash": _hash(token), "name": device_name(agent), "paired_at": at, "last_seen": at})
            doc.update(devices=devices, code=None, code_until=None, tries=0)          # a code pairs one device
            self._save(doc)
            return {"token": token, "max_age": DEVICE_DAYS * 86400}

    def device(self, token: Optional[str]) -> Optional[str]:
        """The id of the paired device this cookie belongs to, or None."""
        if not token:
            return None
        with self._lock:
            doc = self._load()
            if not doc["on"]:
                return None
            want = _hash(token)
            for d in self._fresh(doc):
                if secrets.compare_digest(d["hash"], want):
                    now = self.now()
                    if now - self._seen_written.get(want, datetime.min.replace(tzinfo=timezone.utc)) >= SEEN_EVERY:
                        self._seen_written[want] = now
                        d["last_seen"] = now.isoformat()
                        doc["devices"] = self._fresh(doc)
                        self._save(doc)
                    return d["hash"][:8]
        return None

    # ------------------------------------------------------------------ the second listener
    def start(self) -> None:
        with self._lock:
            if self._httpd is not None or self.factory is None:
                return
            try:
                self._httpd = self.factory()
            except OSError as exc:                       # the port is taken, or the system refused: the screen says so
                self.listen_error = type(exc).__name__
                return
            self.listen_error = None
            if self.port == 0:
                self.port = self._httpd.server_address[1]
            threading.Thread(target=self._httpd.serve_forever, daemon=True).start()

    def stop(self) -> None:
        with self._lock:
            httpd, self._httpd = self._httpd, None
        if httpd is not None:
            httpd.shutdown()
            httpd.server_close()

    def start_if_on(self) -> None:
        if self._load()["on"]:
            self.start()
