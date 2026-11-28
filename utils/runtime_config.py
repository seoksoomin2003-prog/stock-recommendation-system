"""P6-19 operational configuration: local .env loading, SEC_USER_AGENT and capital.

Nothing here participates in frozen P6-11B mathematics.  These helpers only
decide whether the application is allowed to start a run and with which
explicitly supplied operating parameters.

* ``load_local_env``  reads ``<project>/.env`` (git-ignored) without
  overriding variables that are already set in the shell.
* ``sec_user_agent_status``  validates the SEC fair-access identity.  The SEC
  asks automated clients to declare who they are ("<app> <contact email>").
  No default contact is ever invented; placeholder domains are rejected.
* ``resolve_capital``  returns the explicitly supplied capital and where it came
  from.  There is deliberately no default amount.
"""
import math
import os
import re
from pathlib import Path
from typing import Dict, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = PROJECT_ROOT / ".env"

PLACEHOLDER_DOMAINS = {"example.com", "example.org", "example.net", "example.edu", "test.com", "email.com",
                       "domain.com", "localhost", "invalid"}
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@([A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)+)")


class CapitalNotConfigured(ValueError):
    """Raised when no explicit, valid capital amount was supplied."""


def load_local_env(path: Optional[Path] = None) -> Dict[str, str]:
    """Load KEY=VALUE pairs from the project .env; existing environment wins. Returns keys loaded."""
    path = Path(path) if path else ENV_FILE
    loaded: Dict[str, str] = {}
    if not path.is_file():
        return loaded
    # utf-8-sig: Windows Notepad may put a byte-order mark before the first key.  errors="replace": a file saved in another
    # encoding (Korean comments in cp949) must not stop the program at start; keys and values are ASCII and read the same.
    for raw in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        elif " #" in value:
            value = value.split(" #", 1)[0].rstrip()
        if key and key not in os.environ:
            os.environ[key] = value
            loaded[key] = value
    return loaded


def sec_user_agent_status(value: Optional[str] = None) -> Dict[str, str]:
    """CONFIGURED / MISSING / INVALID for an SEC User-Agent value (default: $SEC_USER_AGENT)."""
    value = (os.getenv("SEC_USER_AGENT", "") if value is None else value).strip()
    if not value:
        return {"status": "MISSING", "reason": "SEC_USER_AGENT is not set."}
    if "<" in value or ">" in value or re.search(r"\byour[\s_.\-]*(real|e-?mail|contact|name|address)", value.lower()):
        return {"status": "INVALID", "reason": "SEC_USER_AGENT still contains template text."}
    match = _EMAIL_RE.search(value)
    if not match:
        return {"status": "INVALID", "reason": "SEC_USER_AGENT must contain a contact e-mail address."}
    domain = match.group(1).lower()
    if domain in PLACEHOLDER_DOMAINS or domain.endswith((".example", ".invalid", ".test", ".localhost")):
        return {"status": "INVALID", "reason": f"'{domain}' is a placeholder domain, not a real contact."}
    if len(value.split()) < 2:
        return {"status": "INVALID", "reason": "Use the form '<AppName>/<version> <contact e-mail>'."}
    return {"status": "CONFIGURED", "reason": "ok"}


def sec_configured() -> bool:
    return sec_user_agent_status()["status"] == "CONFIGURED"


def parse_capital(value) -> float:
    """Positive, finite amount. Accepts 50000, '50,000', '50_000', '$50000'."""
    if value is None or isinstance(value, bool):
        raise CapitalNotConfigured("Capital is not configured.")
    if isinstance(value, str):
        text = value.strip().replace(",", "").replace("_", "").lstrip("$").strip()
        if not text:
            raise CapitalNotConfigured("Capital is not configured.")
        try:
            amount = float(text)
        except ValueError as exc:
            raise CapitalNotConfigured(f"Capital {value!r} is not a number.") from exc
    else:
        try:
            amount = float(value)
        except (TypeError, ValueError) as exc:
            raise CapitalNotConfigured(f"Capital {value!r} is not a number.") from exc
    if not math.isfinite(amount) or amount <= 0:
        raise CapitalNotConfigured(f"Capital must be a positive amount (got {value!r}).")
    return amount


def resolve_capital(cli_value=None) -> Tuple[float, str]:
    """Explicit capital: --capital wins, else $QPP_CAPITAL (shell or .env). No default exists."""
    if cli_value is not None:
        return parse_capital(cli_value), "command line (--capital)"
    env_value = os.getenv("QPP_CAPITAL", "").strip()
    if env_value:
        return parse_capital(env_value), "QPP_CAPITAL (environment / .env)"
    raise CapitalNotConfigured(
        "Capital is not configured. Pass --capital AMOUNT (USD), e.g. `python app.py scan --capital 50000`, "
        "or set QPP_CAPITAL in the project .env file.")


CAPITAL_KEYS = {"US": "QPP_CAPITAL", "KR": "QPP_CAPITAL_KRW"}


def set_capital(market: str, value, path: Optional[Path] = None) -> Optional[float]:
    """Save one market's capital in the .env file and this process.  An empty value removes it.  Other lines stay exactly as they are."""
    key = CAPITAL_KEYS[market]
    amount = None if value is None or not str(value).strip() else parse_capital(value)
    path = Path(path) if path else ENV_FILE
    text = path.read_text(encoding="utf-8-sig", errors="replace") if path.is_file() else ""
    written = f"{key}={amount:.2f}".rstrip("0").rstrip(".") if amount is not None else None
    lines, placed = [], False
    for raw in text.splitlines():
        body = raw.strip()
        body = body[len("export "):].lstrip() if body.startswith("export ") else body
        if body.startswith("#") or body.split("=", 1)[0].strip() != key or "=" not in body:
            lines.append(raw)
        elif written and not placed:
            lines.append(written)
            placed = True
    if written and not placed:
        lines.append(written)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text("\n".join(lines) + "\n" if lines else "", encoding="utf-8")
    if path.is_file():
        os.chmod(tmp, path.stat().st_mode & 0o777)
    tmp.replace(path)
    if amount is None:
        os.environ.pop(key, None)
    else:
        os.environ[key] = written.split("=", 1)[1]
    return amount


def http_user_agent() -> str:
    """Identity for non-SEC public pages (Wikipedia): the SEC identity when configured, else generic."""
    if sec_configured():
        return os.getenv("SEC_USER_AGENT", "").strip()
    return "QuantStockEngine/1.0 (local personal research tool; python-requests)"
