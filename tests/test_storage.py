"""Room on the disk and the scan cache: a warning before it is short, and nothing removed unless asked.  No network."""
from collections import namedtuple
from pathlib import Path

import pytest

from terminal import storage
from terminal.automation import Daily
from tests.conftest import _clone

Usage = namedtuple("Usage", "total used free")


def room(gb):
    return lambda p: Usage(100 * storage.GB, 0, int(gb * storage.GB))


@pytest.mark.parametrize("gb,level", [(8.2, "ok"), (5.0, "ok"), (4.9, "warn"), (2.0, "warn"), (1.9, "bad")])
def test_the_level_follows_the_room_left(gb, level):
    assert storage.disk(Path("."), room(gb))["level"] == level
    assert (storage.low_disk_text(Path("."), room(gb)) is None) == (level == "ok")


def test_the_daily_summary_says_so_only_when_short():
    alerts = {"status": "OK", "items": []}
    assert "디스크" not in Daily.compose("2026-11-09", {}, alerts, [], [])
    assert "⚠️ 디스크 여유가 1.0GB" in Daily.compose("2026-11-09", {}, alerts, [], [], storage.low_disk_text(Path("."), room(1)))


def cache(tmp_path, sessions, extra=("annual2_1_ab.json", "scanbars_notes.json", "bars_2020-01-01_ab_cd.json")):
    root = tmp_path / storage.CACHE
    root.mkdir(parents=True)
    for day in sessions:
        for n in range(2):
            (root / f"scanbars_{day}_{n:016x}_{n + 1:010x}.json").write_bytes(b"x" * 1024)
    for name in extra:
        (root / name).write_text("{}")
    return root


DAYS = [f"2026-11-{d:02d}" for d in range(1, 9)]


def test_a_report_removes_nothing(tmp_path):
    root = cache(tmp_path, DAYS)
    before = sorted(p.name for p in root.iterdir())
    got = storage.prune_scanbars(tmp_path, keep=5)
    assert got["old_sessions"] == DAYS[:3] and got["old_files"] == 6 and got["kept"] == DAYS[3:] and got["applied"] is False and got["removed"] == 0
    assert sorted(p.name for p in root.iterdir()) == before and "_paths" not in got


def test_apply_removes_only_old_scan_files(tmp_path):
    root = cache(tmp_path, DAYS)
    got = storage.prune_scanbars(tmp_path, keep=5, apply=True)
    left = sorted(p.name for p in root.iterdir())
    assert got["removed"] == 6 and not any(d in n for d in DAYS[:3] for n in left if n.startswith("scanbars_2"))
    assert sum(n.startswith("scanbars_2") for n in left) == 10
    assert {"annual2_1_ab.json", "scanbars_notes.json", "bars_2020-01-01_ab_cd.json"} <= set(left)


def test_the_newest_session_cannot_be_removed(tmp_path):
    cache(tmp_path, DAYS)
    with pytest.raises(ValueError):
        storage.prune_scanbars(tmp_path, keep=0, apply=True)


def test_no_cache_folder_is_fine(tmp_path):
    assert storage.prune_scanbars(tmp_path)["files"] == 0


def test_nothing_on_a_schedule_removes_files():
    code = (Path(__file__).resolve().parents[1] / "terminal" / "automation.py").read_text(encoding="utf-8")
    assert "prune_scanbars" not in code


def test_a_test_copy_is_independent_of_the_original(tmp_path):
    src, dst = tmp_path / "a.txt", tmp_path / "b.txt"
    src.write_text("one")
    _clone(src, dst)
    src.write_text("two")
    assert dst.read_text() == "one" and src.read_text() == "two"
    dst.write_text("three")
    assert src.read_text() == "two"


def test_superseded_annual_entries_listed_then_removed_only_on_apply(tmp_path):
    root = cache(tmp_path, DAYS)
    for name in ("annual_0001811074_97517_2_46b69d446d.json", "annual_0000320193_ab12cd34ef.json"):
        (root / name).write_text("{}")
    got = storage.prune_cache(tmp_path)
    assert got["superseded"]["files"] == 2 and got["superseded"]["removed"] == 0 and len(list(root.glob("annual_0*"))) == 2
    assert "_paths" not in got["superseded"]["groups"][0]
    got = storage.prune_cache(tmp_path, apply=True)
    left = {p.name for p in root.iterdir()}
    assert got["superseded"]["removed"] == 2 and not any(n.startswith("annual_0") for n in left)
    assert "annual2_1_ab.json" in left and got["scanbars"]["removed"] == 6


def test_every_superseded_key_is_unread_by_code():
    """The cache file name is the key with ':' turned into '_'; no code may still build the old key."""
    import subprocess
    code = subprocess.run(["git", "grep", "-n", "-E", r"f?[\"']annual:", "--", "terminal", "app.py", "markets"],
                          capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1]).stdout
    assert code == ""
    assert "prune_cache" not in (Path(__file__).resolve().parents[1] / "terminal" / "automation.py").read_text(encoding="utf-8")
