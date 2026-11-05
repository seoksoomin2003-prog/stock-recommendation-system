"""Local web server for the terminal (standard library only).

Binds to 127.0.0.1 only (never 0.0.0.0): the terminal is reachable from this Mac alone.
JSON API under /api/..., static files from terminal/static/.  Read-only except the local watchlist.
"""
import json
import logging
import mimetypes
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable, Dict, Optional
from urllib.parse import parse_qs, urlparse

from terminal.services import Terminal

STATIC = Path(__file__).resolve().parent / "static"
from terminal import automation  # noqa: E402

HOST = "127.0.0.1"
log = logging.getLogger("terminal")


def _market(m: str) -> str:
    if m not in ("US", "KR"):
        raise ValueError("INVALID_MARKET")
    return m


def routes(t: Terminal) -> Dict[str, Callable]:
    return {
        ("GET", "/api/health"): lambda q, b: t.health(),
        ("GET", "/api/overview"): lambda q, b: t.overview(),
        ("GET", "/api/chart"): lambda q, b: t.chart(q.get("t", ""), q.get("range", "1y")),
        ("GET", "/api/company"): lambda q, b: t.company(q.get("t", "")),
        ("GET", "/api/filings"): lambda q, b: t.filings(q.get("t", "")),
        ("GET", "/api/macro"): lambda q, b: t.macro(),
        ("GET", "/api/watchlist"): lambda q, b: t.watchlist_quotes(),
        ("POST", "/api/watchlist/add"): lambda q, b: {"tickers": t.watchlist_add(b.get("ticker", ""))},
        ("POST", "/api/watchlist/remove"): lambda q, b: {"tickers": t.watchlist_remove(b.get("ticker", ""))},
        ("GET", "/api/model"): lambda q, b: t.model(),
        ("GET", "/api/portfolio"): lambda q, b: t.portfolio(),
        ("GET", "/api/portfolio/equity"): lambda q, b: t.equity(),
        ("POST", "/api/journal/add"): lambda q, b: t.journal_add(b),
        ("POST", "/api/journal/void"): lambda q, b: t.journal_void(b.get("ref", "")),
        ("GET", "/api/settings"): lambda q, b: t.settings(),
        ("POST", "/api/settings"): lambda q, b: t.settings_set(b),
        ("GET", "/api/sizing"): lambda q, b: t.sizing(q.get("t", ""), q.get("entry"), q.get("stop"), q.get("equity")),
        ("GET", "/api/model/plan"): lambda q, b: t.model_plan(),
        ("GET", "/api/lab/status"): lambda q, b: t.lab.status(),
        ("GET", "/api/automation/status"): lambda q, b: automation.status(t.base),
        ("GET", "/api/qsf/evaluate"): lambda q, b: t.qsf_evaluate(q.get("t", ""), q.get("market", "US")),
        ("GET", "/api/qsf/latest"): lambda q, b: t.qsf.latest(_market(q.get("market", "US"))),
        ("GET", "/api/qsf/validation"): lambda q, b: t.qsf.validation(),
        ("GET", "/api/lab/compare"): lambda q, b: t.lab.comparison(),
        ("GET", "/api/lab/research"): lambda q, b: t.lab.research(),
        ("POST", "/api/lab/run"): lambda q, b: t.lab.run_background(),
    }


def make_handler(t: Terminal):
    table = routes(t)

    class Handler(BaseHTTPRequestHandler):
        server_version = "QSETerminal/1.0"

        def log_message(self, fmt, *args):          # quiet; never logs request bodies or headers
            log.debug("%s %s", self.command, self.path.split("?")[0])

        def _send(self, code: int, body: bytes, ctype: str):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code: int, obj):
            self._send(code, json.dumps(obj, ensure_ascii=False, default=str, allow_nan=False).encode("utf-8"),
                       "application/json; charset=utf-8")

        def _dispatch(self, method: str):
            u = urlparse(self.path)
            if u.path.startswith("/api/"):
                fn = table.get((method, u.path))
                if not fn:
                    return self._json(404, {"error": "NOT_FOUND"})
                body = {}
                if method == "POST":
                    if self.headers.get("Origin") not in (None, f"http://{HOST}:{self.server.server_port}",
                                                          f"http://localhost:{self.server.server_port}"):
                        return self._json(403, {"error": "FORBIDDEN_ORIGIN"})
                    n = min(int(self.headers.get("Content-Length") or 0), 10_000)
                    try:
                        body = json.loads(self.rfile.read(n) or b"{}")
                        if not isinstance(body, dict):
                            raise ValueError
                    except ValueError:
                        return self._json(400, {"error": "BAD_JSON"})
                q = {k: v[0] for k, v in parse_qs(u.query).items()}
                try:
                    return self._json(200, _finite(fn(q, body)))
                except ValueError as exc:
                    return self._json(400, {"error": str(exc)})
                except Exception as exc:                 # never leak internals or credentials
                    log.warning("api error on %s: %s", u.path, type(exc).__name__)
                    return self._json(500, {"error": "INTERNAL_ERROR", "type": type(exc).__name__})
            if method != "GET":
                return self._json(405, {"error": "METHOD_NOT_ALLOWED"})
            rel = "index.html" if u.path in ("", "/") else u.path.lstrip("/")
            f = (STATIC / rel).resolve()
            if STATIC not in f.parents or not f.is_file():
                return self._send(404, b"not found", "text/plain; charset=utf-8")
            ctype = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype in ("application/javascript",):
                ctype += "; charset=utf-8"
            self._send(200, f.read_bytes(), ctype)

        def do_GET(self):
            self._dispatch("GET")

        def do_POST(self):
            self._dispatch("POST")

    return Handler


def _finite(o):
    """JSON has no NaN/Infinity: non-finite numbers become null (missing), never 0."""
    if isinstance(o, float):
        return o if o == o and o not in (float("inf"), float("-inf")) else None
    if isinstance(o, dict):
        return {k: _finite(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_finite(v) for v in o]
    return o


def serve(port: int = 8765, base_dir: Path = Path("."), terminal: Optional[Terminal] = None,
          background: bool = False) -> ThreadingHTTPServer:
    t = terminal or Terminal(base_dir)
    httpd = ThreadingHTTPServer((HOST, port), make_handler(t))
    httpd.daemon_threads = True
    if background:
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd
