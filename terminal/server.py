"""Local web server for the terminal (standard library only).

Binds to 127.0.0.1 only (never 0.0.0.0): the terminal is reachable from this Mac alone.
JSON API under /api/..., static files from terminal/static/.  Read-only except the local watchlist, alert rules and journal.
"""
import json
import logging
import mimetypes
import os
import re
import sys
import threading
import traceback
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Callable, Dict, Optional
from urllib.parse import parse_qs, urlparse

from terminal.services import Terminal, clean_ticker

STATIC = Path(__file__).resolve().parent / "static"
from terminal import automation, model_scan, record_status, server_agent, today  # noqa: E402
from terminal.qsf import changes as qsf_changes, forecast as qsf_forecast, kr_cap_view as qsf_cap_view, kr_method as qsf_kr_method, lookahead as qsf_lookahead, paper_book as qsf_paper_book, regime_weights as qsf_regime_weights, screen as qsf_screen, track_record as qsf_track_record  # noqa: E402

HOST = "127.0.0.1"
log = logging.getLogger("terminal")
REQUEST_TIMEOUT_S = 60          # a client that connects and sends nothing does not hold a thread forever
MAX_BODY = 10_000
ERROR_LOG_BYTES, ERROR_LOG_KEEP = 1_000_000, 3

# Values that must never reach a log: every environment variable whose name says it is a credential or private setting
# (the .env values are loaded into the environment), and any e-mail address.
_SECRET_NAME = re.compile(r"KEY|TOKEN|SECRET|AGENT|PASS|CAPITAL|CHAT|EMAIL|CRUMB|COOKIE", re.I)
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")


def redact(text: str) -> str:
    for k, v in os.environ.items():
        if v and len(v) >= 4 and _SECRET_NAME.search(k):
            text = text.replace(v, "[REDACTED]")
    return _EMAIL.sub("[EMAIL]", text)


class _RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return redact(super().format(record))


class ErrorTally:
    """Unexpected server errors since start, for the health line.  Type and API path only."""

    def __init__(self):
        self._lock = threading.Lock()
        self.count, self.last = 0, None

    def note(self, path: str, exc: BaseException) -> None:
        with self._lock:
            self.count += 1
            self.last = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "path": path, "type": type(exc).__name__}

    def view(self) -> Dict:
        with self._lock:
            return {"count": self.count, "last": self.last}


def setup_error_log(base: Path) -> Path:
    """Unexpected errors go, with their traceback and secrets removed, to data/terminal/logs/server_errors.log (rotated at 1MB,
    3 kept).  Without this the server's errors were visible only on a console that is often not open."""
    folder = Path(base) / "data" / "terminal" / "logs"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "server_errors.log"
    if not any(getattr(h, "baseFilename", None) == str(path) for h in log.handlers):
        h = RotatingFileHandler(path, maxBytes=ERROR_LOG_BYTES, backupCount=ERROR_LOG_KEEP, encoding="utf-8")
        h.setLevel(logging.WARNING)
        h.setFormatter(_RedactingFormatter("%(asctime)s %(levelname)s %(message)s"))
        log.addHandler(h)
    return path


def _market(m: str) -> str:
    if m not in ("US", "KR"):
        raise ValueError("INVALID_MARKET")
    return m


def _days(raw) -> int:
    if raw in (None, ""):
        return 14
    try:
        v = int(raw)
    except (TypeError, ValueError):
        raise ValueError("INVALID_DAYS") from None
    if not 1 <= v <= 60:
        raise ValueError("INVALID_DAYS")
    return v


def _kr_name(t):
    """Korean company names by code, for lists that hold codes only.  A missing master gives no names, never an error."""
    def name(code: str):
        try:
            return (t.qsf._kr_identity(code) or {}).get("company_name")
        except Exception:
            return None
    return name


def _code(ticker: str, market: str) -> str:
    """A ticker in the form its market uses; the same checks as score evaluation."""
    if market == "KR":
        code = (ticker or "").strip().upper()
        if not re.fullmatch(r"[0-9A-Z]{6}", code):
            raise ValueError("INVALID_TICKER")
        return code
    return clean_ticker(ticker)


def _strategy(s: str) -> str:
    if s not in ("SWING", "LONG_TERM"):
        raise ValueError("INVALID_STRATEGY")
    return s


def routes(t: Terminal, errors: Optional[ErrorTally] = None) -> Dict[str, Callable]:
    errors = errors or ErrorTally()
    return {
        ("GET", "/api/health"): lambda q, b: {**t.health(), "server_errors": errors.view()},
        ("GET", "/api/overview"): lambda q, b: t.overview(_market(q.get("market", "US"))),
        ("GET", "/api/chart"): lambda q, b: t.chart(q.get("t", ""), q.get("range", "1y")),
        ("GET", "/api/compare"): lambda q, b: t.compare(q.get("t", ""), q.get("range", "1y")),
        ("GET", "/api/rotation"): lambda q, b: t.rotation(_market(q.get("market", "US"))),
        ("GET", "/api/company"): lambda q, b: t.company(q.get("t", "")),
        ("GET", "/api/filings"): lambda q, b: t.filings(q.get("t", "")),
        ("GET", "/api/macro"): lambda q, b: t.macro(_market(q.get("market", "US"))),
        ("GET", "/api/watchlist"): lambda q, b: t.watchlist_quotes(_market(q.get("market", "US"))),
        ("POST", "/api/watchlist/add"): lambda q, b: {"tickers": t.watchlist_add(b.get("ticker", ""))},
        ("GET", "/api/calendar"): lambda q, b: t.econ_calendar(_market(q.get("market", "US")), _days(q.get("days") or "60")),
        ("GET", "/api/alerts"): lambda q, b: t.alerts_view(),
        ("GET", "/api/alerts/check"): lambda q, b: {k: v for k, v in t.alert_check().items() if k != "state"},
        ("POST", "/api/alerts/add"): lambda q, b: t.alert_add(b),
        ("POST", "/api/alerts/remove"): lambda q, b: t.alert_remove(b.get("id", "")),
        ("POST", "/api/alerts/rearm"): lambda q, b: t.alert_rearm(b.get("id", "")),
        ("POST", "/api/watchlist/remove"): lambda q, b: {"tickers": t.watchlist_remove(b.get("ticker", ""))},
        ("GET", "/api/model"): lambda q, b: t.model(_market(q.get("market", "US"))),
        ("GET", "/api/portfolio"): lambda q, b: t.portfolio(_market(q.get("market", "US"))),
        ("GET", "/api/portfolio/equity"): lambda q, b: t.equity(_market(q.get("market", "US"))),
        ("GET", "/api/portfolio/risk"): lambda q, b: t.portfolio_risk(_market(q.get("market", "US"))),
        ("GET", "/api/portfolio/signals"): lambda q, b: t.portfolio_signals(_market(q.get("market", "US"))),
        ("POST", "/api/journal/add"): lambda q, b: t.journal_add(b),
        ("GET", "/api/paper-trade"): lambda q, b: t.paper_trades(_market(q.get("market", "US"))),
        ("GET", "/api/paper-trade/fee"): lambda q, b: t.paper_fee(q),
        ("POST", "/api/paper-trade/add"): lambda q, b: t.paper_add(b),
        ("POST", "/api/paper-trade/void"): lambda q, b: t.paper_void(b.get("ref", "")),
        ("POST", "/api/journal/void"): lambda q, b: t.journal_void(b.get("ref", "")),
        ("GET", "/api/capital"): lambda q, b: t.capital(_market(q.get("market", "US"))),
        ("POST", "/api/capital"): lambda q, b: t.capital_set(b),
        ("GET", "/api/model/scan"): lambda q, b: model_scan.status(t.base),
        ("POST", "/api/model/scan"): lambda q, b: t.model_scan_start(b),
        ("GET", "/api/settings"): lambda q, b: t.settings(),
        ("POST", "/api/settings"): lambda q, b: t.settings_set(b),
        ("GET", "/api/sizing"): lambda q, b: t.sizing(q.get("t", ""), q.get("entry"), q.get("stop"), q.get("equity"), q.get("style"), _market(q.get("market", "US"))),
        ("GET", "/api/kr/search"): lambda q, b: {"items": t.qsf.kr_search(q.get("q", ""))},
        ("GET", "/api/model/plan"): lambda q, b: t.model_plan(),
        ("GET", "/api/lab/status"): lambda q, b: t.lab.status(),
        ("GET", "/api/automation/status"): lambda q, b: {**automation.status(t.base), "server_agent": server_agent.status(t.base)},
        ("GET", "/api/qsf/evaluate"): lambda q, b: t.qsf_evaluate(q.get("t", ""), q.get("market", "US")),
        ("GET", "/api/qsf/earnings"): lambda q, b: t.qsf.earnings_upcoming(_market(q.get("market", "US")), _days(q.get("days"))),
        ("GET", "/api/qsf/history"): lambda q, b: t.qsf_history(q.get("t", ""), q.get("market", "US")),
        ("GET", "/api/qsf/latest"): lambda q, b: t.qsf.latest(_market(q.get("market", "US"))),
        ("GET", "/api/qsf/screen"): lambda q, b: qsf_screen.screen(t.qsf.screen_rows(_market(q.get("market", "US"))), q),
        ("GET", "/api/qsf/changes"): lambda q, b: qsf_changes.report(t.qsf.latest(_market(q.get("market", "US"))), t.qsf.ledger, _market(q.get("market", "US")), _strategy(q.get("strategy", "SWING"))),
        ("GET", "/api/qsf/validation"): lambda q, b: t.qsf.validation(),
        ("GET", "/api/qsf/track-record"): lambda q, b: qsf_track_record.summary(t.base, _market(q.get("market", "US"))),
        ("GET", "/api/qsf/former-universe"): lambda q, b: qsf_cap_view.view(t.base, _strategy(q.get("strategy", "SWING")), name_of=_kr_name(t)),
        ("GET", "/api/qsf/kr-method"): lambda q, b: qsf_kr_method.status(t.base),
        ("GET", "/api/qsf/regime-weights"): lambda q, b: qsf_regime_weights.status(t.base),
        ("GET", "/api/qsf/lookahead"): lambda q, b: qsf_lookahead.status(t.base),
        ("GET", "/api/qsf/forecast"): lambda q, b: qsf_forecast.view(t.base, _market(q.get("market", "US"))),
        ("GET", "/api/qsf/forecast-stock"): lambda q, b: qsf_forecast.stock(t.base, _market(q.get("market", "US")), _code(q.get("t", ""), _market(q.get("market", "US")))),
        ("GET", "/api/qsf/paper-book"): lambda q, b: qsf_paper_book.status(t.base, _market(q.get("market", "US"))),
        ("GET", "/api/qsf/order-plan"): lambda q, b: t.order_plan(_market(q.get("market", "US"))),
        ("GET", "/api/qsf/top3"): lambda q, b: t.qsf.top3(_market(q.get("market", "US"))),
        ("GET", "/api/qsf/peers"): lambda q, b: t.qsf.peers(clean_ticker(q.get("t", "")), _market(q.get("market", "US"))),
        ("GET", "/api/qsf/sector-picks"): lambda q, b: t.sector_picks(_market(q.get("market", "US")), q.get("fund", "")),
        ("GET", "/api/qsf/heatmap"): lambda q, b: t.qsf.heatmap(_market(q.get("market", "US")), _strategy(q.get("strategy", "SWING"))),
        ("GET", "/api/record"): lambda q, b: record_status.build(t),
        ("GET", "/api/today"): lambda q, b: today.build(t, q.get("t", ""), _market(q.get("market", "US"))),
        ("GET", "/api/lab/compare"): lambda q, b: t.lab.comparison(),
        ("GET", "/api/lab/research"): lambda q, b: t.lab.research(),
        ("POST", "/api/lab/run"): lambda q, b: t.lab.run_background(),
        ("POST", "/api/automation/run"): lambda q, b: automation.start_now(t.base),
    }


GONE = (BrokenPipeError, ConnectionResetError, ConnectionAbortedError)      # the client closed the connection
STORED_UNREADABLE = (json.JSONDecodeError, UnicodeError)                    # ValueErrors that are never about the request's own values


def make_handler(t: Terminal, errors: Optional[ErrorTally] = None):
    errors = errors or ErrorTally()
    table = routes(t, errors)
    writes = threading.Lock()       # saves (watchlist, alerts, journal, settings) run one at a time: no lost update, no shared temp file

    class Handler(BaseHTTPRequestHandler):
        server_version = "QSETerminal/1.0"
        timeout = REQUEST_TIMEOUT_S

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

        def _internal(self, method: str, path: str, exc: BaseException):
            errors.note(path, exc)
            log.error("api error on %s %s: %s\n%s", method, path, type(exc).__name__, traceback.format_exc())
            try:
                return self._json(500, {"error": "INTERNAL_ERROR", "type": type(exc).__name__})
            except GONE:
                return None

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
                    try:
                        n = int(self.headers.get("Content-Length") or 0)
                    except ValueError:
                        return self._json(400, {"error": "BAD_LENGTH"})
                    if n < 0 or n > MAX_BODY:
                        return self._json(413 if n > MAX_BODY else 400, {"error": "BAD_LENGTH"})
                    try:
                        body = json.loads(self.rfile.read(n) or b"{}")
                        if not isinstance(body, dict):
                            raise ValueError
                    except (ValueError, RecursionError):
                        return self._json(400, {"error": "BAD_JSON"})
                q = {k: v[0] for k, v in parse_qs(u.query).items()}
                try:
                    if method == "POST":
                        with writes:
                            out = fn(q, body)
                    else:
                        out = fn(q, body)
                    return self._json(200, _finite(out))
                except GONE:                             # the browser left before the answer was written: nothing failed here
                    log.debug("client left during %s %s", method, u.path)
                    return None
                except ValueError as exc:
                    if isinstance(exc, STORED_UNREADABLE):      # a stored file that cannot be parsed is this program's fault, not the request's
                        return self._internal(method, u.path, exc)
                    log.info("rejected %s %s: %s", method, u.path, str(exc)[:160])
                    return self._json(400, {"error": str(exc)})
                except Exception as exc:                 # never leak internals or credentials to the page
                    return self._internal(method, u.path, exc)
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


class _Server(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address):
        exc = sys.exc_info()[1]
        if isinstance(exc, (ConnectionError, TimeoutError)):       # the browser left mid-reply, or sent nothing in time
            return
        log.error("request failed: %s\n%s", type(exc).__name__, traceback.format_exc())


def serve(port: int = 8765, base_dir: Path = Path("."), terminal: Optional[Terminal] = None,
          background: bool = False) -> ThreadingHTTPServer:
    t = terminal or Terminal(base_dir)
    httpd = _Server((HOST, port), make_handler(t))
    if background:
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd
