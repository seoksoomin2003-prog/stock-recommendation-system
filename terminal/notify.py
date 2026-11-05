"""Outbound notifications: Telegram and the macOS notification centre.

The bot token lives only in the git-ignored ``.env`` (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID).  It is part of the
request URL, so errors are reported by exception TYPE or HTTP status only: never the exception text, which could
contain the URL.  Messages are plain text (no parse mode, so a ticker or price can never break the formatting).
"""
import os
import re
import subprocess
import sys
from typing import Any, Callable, Dict, List, Optional

API = "https://api.telegram.org"
MAX_LEN = 4000                      # Telegram's hard limit is 4096
TOKEN_RE = re.compile(r"^\d{3,}:[A-Za-z0-9_-]{20,}$")
CHAT_RE = re.compile(r"^-?\d{3,}$")


def _http(method: str, url: str, **kw):
    import requests
    return getattr(requests, method)(url, timeout=20, **kw)


def telegram_status() -> str:
    """CONFIGURED | NOT_CONFIGURED | INVALID (a status word only: the values are never returned)."""
    token, chat = os.getenv("TELEGRAM_BOT_TOKEN", "").strip(), os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token and not chat:
        return "NOT_CONFIGURED"
    if not TOKEN_RE.match(token) or not CHAT_RE.match(chat):
        return "INVALID"
    return "CONFIGURED"


def split_text(text: str, limit: int = MAX_LEN) -> List[str]:
    """Split on line boundaries; a single over-long line is hard-cut."""
    parts, cur = [], ""
    for line in text.splitlines():
        while len(line) > limit:
            if cur:
                parts.append(cur)
                cur = ""
            parts.append(line[:limit])
            line = line[limit:]
        if cur and len(cur) + 1 + len(line) > limit:
            parts.append(cur)
            cur = line
        else:
            cur = f"{cur}\n{line}" if cur else line
    if cur:
        parts.append(cur)
    return parts


def send_telegram(text: str, http: Callable = _http) -> Dict[str, Any]:
    st = telegram_status()
    if st != "CONFIGURED":
        return {"status": st}
    token, chat = os.environ["TELEGRAM_BOT_TOKEN"].strip(), os.environ["TELEGRAM_CHAT_ID"].strip()
    for part in split_text(text):
        try:
            r = http("post", f"{API}/bot{token}/sendMessage", json={"chat_id": chat, "text": part})
        except Exception as exc:
            return {"status": "FAILED", "error": type(exc).__name__}
        if r.status_code != 200:
            return {"status": "FAILED", "error": f"HTTP {r.status_code}"}
    return {"status": "SENT"}


def find_chats(http: Callable = _http) -> Dict[str, Any]:
    """Chats that have messaged the bot (used once, to find TELEGRAM_CHAT_ID)."""
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not TOKEN_RE.match(token):
        return {"status": "NO_TOKEN", "chats": []}
    try:
        r = http("get", f"{API}/bot{token}/getUpdates")
    except Exception as exc:
        return {"status": "FAILED", "error": type(exc).__name__, "chats": []}
    if r.status_code != 200:
        return {"status": "FAILED", "error": f"HTTP {r.status_code}", "chats": []}
    seen = {}
    for u in r.json().get("result") or []:
        chat = (u.get("message") or {}).get("chat") or {}
        if chat.get("id") is not None:
            seen[chat["id"]] = {"id": chat["id"], "type": chat.get("type"), "name": chat.get("first_name") or chat.get("title")}
    return {"status": "OK", "chats": list(seen.values())}


def send_macos(title: str, body: str, run: Optional[Callable] = None, platform: Optional[str] = None) -> Dict[str, Any]:
    """Text goes through argv, never into the AppleScript source, so it cannot be interpreted as code."""
    if (platform or sys.platform) != "darwin":
        return {"status": "NOT_AVAILABLE"}
    script = ["osascript", "-e", "on run argv", "-e",
              "display notification (item 2 of argv) with title (item 1 of argv)", "-e", "end run", title, body[:220]]
    try:
        res = (run or subprocess.run)(script, capture_output=True, timeout=15)
    except Exception as exc:
        return {"status": "FAILED", "error": type(exc).__name__}
    return {"status": "SENT"} if res.returncode == 0 else {"status": "FAILED", "error": f"exit {res.returncode}"}
