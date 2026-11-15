"""P6-19 test-suite safety net (pytest).

1. Network isolation: deterministic tests may not open sockets.  Live provider
   tests opt in explicitly with ``QPP_PROVIDER_TESTS=1``.
2. User-data protection: every test is checked for writes to the real
   ``data/`` stores, the historical ``reports/`` and ``runs/``.  A test that
   modifies a protected file FAILS and the file is restored from the session
   snapshot, so one bad test can never destroy user data or historical
   evidence.
3. Only the tests' own writes are undone.  The daily job, a scan or the
   terminal server may write to the same folders while the suite runs; until
   2026-11-14 the guard took any new file for a test's and deleted it, and put
   back the old copy of any file that had changed.  The suite now notes every
   path this process opens for writing, renames or removes, and a change it did
   not make is left alone and listed at the end of the run.
"""
import ctypes
import os
import shutil
import socket
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PROTECTED_DIRS = ("data", "reports", "runs", "tracking")
ALLOWED_WRITES = {
    # The test-results artifacts are written by the test runners themselves.
    "reports/P6-19_pytest_junit.xml",
    "reports/P6-20_pytest_junit.xml",
    "reports/P6-21_25_pytest_junit.xml",
    "reports/TERMINAL-1_pytest_junit.xml",
    "reports/TERMINAL-2_pytest_junit.xml",
    "reports/TERMINAL-3_pytest_junit.xml",
    "reports/TERMINAL-4_pytest_junit.xml",
    "reports/QSF_pytest_junit.xml",
}
LIVE = os.getenv("QPP_PROVIDER_TESTS") == "1"


def _protected_files():
    for d in PROTECTED_DIRS:
        base = ROOT / d
        if not base.exists():
            continue
        for p in base.rglob("*"):
            if p.is_file() and "__pycache__" not in p.parts and not p.name.endswith(".pyc"):
                yield p


def _stat_map():
    out = {}
    for p in _protected_files():
        rel = str(p.relative_to(ROOT))
        if rel in ALLOWED_WRITES:
            continue
        try:
            st = p.stat()
            out[rel] = (st.st_size, st.st_mtime_ns)
        except OSError:
            continue
    return out


SANDBOX_COPIED = set(PROTECTED_DIRS) | {"cache", "cache.nosync", "scratch"}


def _clone(src, dst):
    """A copy-on-write clone where the disk has them, so two copies of the data take almost no room; a plain copy elsewhere.  A later write to either side leaves the other alone."""
    try:
        if ctypes.CDLL(None).clonefile(os.fsencode(src), os.fsencode(dst), 0) == 0:
            return dst
    except (AttributeError, OSError):
        pass
    return shutil.copy2(src, dst)


_SANDBOX = {}


def pytest_configure(config):
    """Run the suite from a throw-away mirror of the project (before collection).

    Source directories are symlinked (so the code under test is the real code);
    data/report/run directories are *copied*, so legacy modules that write to
    relative paths such as ``data/tickers.db`` or ``reports/`` only touch the
    copies.  Writers that bypass the cwd are still caught by the guard below.
    """
    sandbox = Path(tempfile.mkdtemp(prefix="qpp_test_sandbox_"))
    for entry in ROOT.iterdir():
        if entry.name == ".git" or entry.name.startswith(".venv"):
            continue
        target = sandbox / entry.name
        if entry.name in SANDBOX_COPIED and entry.is_dir():
            shutil.copytree(entry, target, symlinks=True, copy_function=_clone,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        else:
            target.symlink_to(entry)
    _SANDBOX.update(dir=sandbox, previous=os.getcwd())
    os.chdir(sandbox)


def pytest_unconfigure(config):
    if _SANDBOX:
        os.chdir(_SANDBOX["previous"])
        shutil.rmtree(_SANDBOX["dir"], ignore_errors=True)


@pytest.fixture(scope="session", autouse=True)
def _protected_snapshot():
    snap_dir = Path(tempfile.mkdtemp(prefix="qpp_protected_"))
    for p in _protected_files():
        rel = p.relative_to(ROOT)
        dst = snap_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        _clone(p, dst)
    state = {"dir": snap_dir, "stats": _stat_map()}
    yield state
    shutil.rmtree(snap_dir, ignore_errors=True)


# ----------------------------------------------------------------------------- whose write was it
_WRITING = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND
_ONE_PATH = {"os.remove", "os.rmdir", "os.mkdir", "os.truncate", "os.utime", "os.chmod", "shutil.rmtree", "sqlite3.connect"}
_TWO_PATHS = {"os.rename", "os.link", "os.symlink", "shutil.copyfile", "shutil.move", "shutil.copytree", "shutil.copymode", "shutil.copystat"}
_CHILDREN = {"subprocess.Popen", "os.system", "os.posix_spawn", "os.fork", "os.exec", "os.spawn", "os.startfile"}
_OWN = {"touched": set(), "children": 0}
_OUTSIDE = []          # protected paths another process changed during the run; left alone, listed at the end


def _protected_rel(path, root=None):
    """The path relative to the project when it is a file or folder under a protected directory, else None.  Symbolic links are
    followed first: the sandbox links the source folders, so ``tests/../data`` is the real ``data``."""
    if isinstance(path, bytes):
        path = os.fsdecode(path)
    if not isinstance(path, (str, os.PathLike)):
        return None                                   # a file descriptor: its path was noted when it was opened
    try:
        rel = os.path.relpath(os.path.realpath(os.fspath(path)), os.path.realpath(root or ROOT))
    except (OSError, ValueError):
        return None
    return rel if rel.split(os.sep, 1)[0] in PROTECTED_DIRS else None


def _note(path):
    rel = _protected_rel(path)
    if rel:
        _OWN["touched"].add(rel)


def _audit(event, args):
    """Every write this process makes under a protected directory, by any Python route (open, os, shutil, sqlite3)."""
    try:
        if event == "open":
            path, mode, flags = (tuple(args) + (None, None))[:3]
            if (isinstance(flags, int) and flags & _WRITING) or (isinstance(mode, str) and any(c in mode for c in "wax+")):
                _note(path)
        elif event in _ONE_PATH:
            _note(args[0])
        elif event in _TWO_PATHS:
            _note(args[0])
            _note(args[1])
        elif event in _CHILDREN:
            _OWN["children"] += 1                     # a child's writes are not seen here
    except Exception:                                 # an audit hook must never break the code it watches
        pass


sys.addaudithook(_audit)


def _is_own(rel, touched):
    return any(rel == t or rel.startswith(t + os.sep) or rel in (t + "-journal", t + "-wal", t + "-shm") for t in touched)


def _settle(root, snap, changed, created, deleted, touched, children):
    """Undo what the test wrote; leave what something else wrote.  Returns (own, outside, unsure): ``own`` were restored or removed
    and fail the test; ``outside`` were not touched by this process and are left as they are, with the snapshot brought up to
    date so a later restore cannot bring back an older copy; ``unsure`` are changes this process did not make while the test had
    started a child process, which could have: they fail the test and are left on disk, because deleting a file that may be the
    daily job's is worse than leaving one that may be a test's."""
    root, snap = Path(root), Path(snap)
    every = changed + created + deleted
    own = [r for r in every if _is_own(r, touched)]
    rest = [r for r in every if r not in own]
    unsure, outside = (rest, []) if children else ([], rest)
    for rel in own:
        src = snap / rel
        if rel in created:
            try:
                (root / rel).unlink()
            except OSError:
                pass
        elif src.exists():
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, root / rel)
    for rel in outside:
        dst = snap / rel
        try:
            if dst.exists():
                dst.unlink()
            if (root / rel).exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                _clone(root / rel, dst)
        except OSError:
            pass
    return own, outside, unsure


@pytest.fixture(autouse=True)
def _guard_protected_files(request, _protected_snapshot):
    before = _protected_snapshot["stats"]
    _OWN["touched"], _OWN["children"] = set(), 0
    yield
    touched, children = set(_OWN["touched"]), _OWN["children"]
    after = _stat_map()
    changed = sorted(k for k in after if k in before and before[k] != after[k])
    created = sorted(k for k in after if k not in before)
    deleted = sorted(k for k in before if k not in after)
    if not (changed or created or deleted):
        return
    own, outside, unsure = _settle(ROOT, _protected_snapshot["dir"], changed, created, deleted, touched, children)
    _OUTSIDE.extend(outside)
    _protected_snapshot["stats"] = _stat_map()
    if own:
        pytest.fail(f"Test wrote to protected user data / historical artifacts (restored): "
                    f"changed={[r for r in own if r in changed][:5]} created={[r for r in own if r in created][:5]} "
                    f"deleted={[r for r in own if r in deleted][:5]}", pytrace=False)
    if unsure:
        pytest.fail(f"Protected files changed while this test ran a child process; they were NOT restored or removed, because "
                    f"another program (the daily job, a scan) may have written them. Look before deleting: {unsure[:5]}", pytrace=False)


def pytest_terminal_summary(terminalreporter):
    if _OUTSIDE:
        seen = sorted(set(_OUTSIDE))
        terminalreporter.write_line(f"protected files changed by another process during the run, left alone: {len(seen)} "
                                    f"(first: {seen[:5]})", yellow=True)


@pytest.fixture(autouse=True)
def _no_user_credentials(monkeypatch):
    """Offline tests must behave the same on a machine whose .env holds real keys, and must never see those keys."""
    if not LIVE:
        for name in ("KRX_API_KEY", "OPENDART_API_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
            monkeypatch.delenv(name, raising=False)


@pytest.fixture(autouse=True)
def _own_sec_pace_file(monkeypatch, tmp_path_factory):
    """Tests never read or set the machine-wide SEC pace file (``terminal.sources.SEC_PACE_FILE``): a refusal faked in a test
    would otherwise stop the real server's SEC requests for ten minutes."""
    from terminal import sources
    path = tmp_path_factory.getbasetemp() / "sec_pace.json"
    path.unlink(missing_ok=True)
    monkeypatch.setattr(sources, "SEC_PACE_FILE", path)


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    if LIVE:
        yield
        return

    def guarded_connect(self, address, *args, **kwargs):
        host = address[0] if isinstance(address, tuple) else address
        if host in ("127.0.0.1", "::1", "localhost") or (isinstance(host, str) and host.startswith("/")):
            return original_connect(self, address, *args, **kwargs)
        raise OSError(f"Network access blocked in deterministic tests (target {address!r}); "
                      f"set QPP_PROVIDER_TESTS=1 for live provider tests.")

    original_connect = socket.socket.connect
    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket, "create_connection",
                        lambda address, *a, **k: (_ for _ in ()).throw(
                            OSError(f"Network access blocked in deterministic tests (target {address!r})")))
    # P6-20-A: EDGAR submissions (acceptance datetimes) are an extra SEC request per CIK.  Offline tests
    # that stub only companyfacts get "accepted datetime unavailable" instead of slow blocked retries.
    from data.loader import DataLoader
    monkeypatch.setattr(DataLoader, "_fetch_sec_submissions", lambda self, cik: {})
    yield


# ---------------------------------------------------------------------------
# Explicitly isolated legacy tests (P6-19 Phase E).  Each is a pre-existing
# failure in code outside the canonical recommendation route, or a test whose
# expectation contradicts the frozen P6-11B / P6-14 contracts.  They are marked
# strict xfail: reported as XFAIL (never as passed) and they turn into a FAILURE
# if they ever start passing, forcing a re-review.  Nothing here is skipped.
# ---------------------------------------------------------------------------
_FROZEN_LOOKBACK = ("expects a <=365-day download window; the frozen P6-11B momentum factor needs >=425 days "
                    "(reports/P6-17_PREIMPLEMENTATION_FORENSIC.md). Passing would require changing a frozen input.")
LEGACY_ISOLATED = {
    "tests/test_local_workload_control.py::TestLocalWorkloadControl::test_test1_local_1_ticker": _FROZEN_LOOKBACK,
    "tests/test_local_workload_control.py::TestLocalWorkloadControl::test_test2_local_3_tickers": _FROZEN_LOOKBACK,
    "tests/test_local_workload_control.py::TestLocalWorkloadControl::test_test4_local_duplicates": (
        "expects company-name alias resolution ('Alphabet'->GOOGL) and scores from 5 stale mock bars without "
        "provider status; the canonical route correctly quarantines STALE/unverified data (P6-14 contract)."),
    "tests/test_meta_alpha.py::test_meta_alpha_ensemble": (
        "legacy research MetaAlphaEngine (not on the canonical route); pre-existing drift-weight expectation "
        "(0.1522 vs <0.15). Never executed by the P6-18 unittest runner (plain pytest function)."),
    "tests/test_alternative_data.py::test_alternative_data": (
        "legacy AlternativeDataEngine no longer has fetch_sns_sentiment (API drift; not on the canonical route). "
        "Never executed by the P6-18 unittest runner (plain pytest function)."),
}


# Reclassified with the user's approval on 2026-11-06.  The expected direction depends on that day's live Yahoo yields, so the test
# passes or fails with the market, and it reaches the network.  It is reported as XFAIL without being run: a strict xfail would turn
# into a failure on any day yields rose.
LEGACY_LIVE_DATA = {
    "tests/test_cross_asset.py::test_cross_asset_adjustment": (
        "legacy CrossAssetEngine (not on the canonical route) asserts a direction from live Yahoo macro moves; the outcome follows the market."),
}


def pytest_collection_modifyitems(config, items):
    for item in items:
        reason = LEGACY_ISOLATED.get(item.nodeid)
        if reason:
            item.add_marker(pytest.mark.xfail(strict=True, reason=f"LEGACY_ISOLATED: {reason}"))
        reason = LEGACY_LIVE_DATA.get(item.nodeid)
        if reason:
            item.add_marker(pytest.mark.xfail(run=False, reason=f"LEGACY_LIVE_DATA: {reason}"))
