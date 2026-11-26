"""The suite's own guard (tests/conftest.py): a test's writes to protected folders are undone, and a write some other program made
while the suite ran (the daily job, a scan, the terminal server) is left alone.  Until 2026-11-14 the second kind was deleted."""
import os
import sqlite3
import sys
from pathlib import Path

import pytest

guard = sys.modules.get("tests.conftest") or sys.modules["conftest"]


@pytest.fixture()
def project(tmp_path):
    root, snap = tmp_path / "root", tmp_path / "snap"
    for base in (root, snap):
        (base / "data" / "kr").mkdir(parents=True)
        (base / "data" / "kr" / "kept.json").write_text("old")
    return root, snap


def test_a_file_the_test_changed_is_put_back_and_one_it_made_is_removed(project):
    root, snap = project
    (root / "data/kr/kept.json").write_text("spoiled by the test")
    (root / "data/kr/made.json").write_text("made by the test")
    own, outside, unsure = guard._settle(root, snap, ["data/kr/kept.json"], ["data/kr/made.json"], [], {"data/kr/kept.json", "data/kr/made.json"}, 0)
    assert own == ["data/kr/kept.json", "data/kr/made.json"] and not outside and not unsure
    assert (root / "data/kr/kept.json").read_text() == "old" and not (root / "data/kr/made.json").exists()


def test_a_file_the_test_deleted_comes_back(project):
    root, snap = project
    (root / "data/kr/kept.json").unlink()
    own, _, _ = guard._settle(root, snap, [], [], ["data/kr/kept.json"], {"data/kr"}, 0)          # removed with its folder
    assert own == ["data/kr/kept.json"] and (root / "data/kr/kept.json").read_text() == "old"


def test_what_another_program_wrote_is_left_alone(project):
    """The daily job writes a new day's file and updates its state while the suite runs: neither is the test's."""
    root, snap = project
    (root / "data/kr/kept.json").write_text("updated by the daily job")
    (root / "data/kr/new_day.json").write_text("a day of records")
    own, outside, unsure = guard._settle(root, snap, ["data/kr/kept.json"], ["data/kr/new_day.json"], [], set(), 0)
    assert not own and not unsure and outside == ["data/kr/kept.json", "data/kr/new_day.json"]
    assert (root / "data/kr/kept.json").read_text() == "updated by the daily job" and (root / "data/kr/new_day.json").read_text() == "a day of records"
    assert (snap / "data/kr/kept.json").read_text() == "updated by the daily job"      # a later restore cannot bring back the old copy
    assert (snap / "data/kr/new_day.json").exists()


def test_both_at_once_are_told_apart(project):
    root, snap = project
    (root / "data/kr/new_day.json").write_text("a day of records")
    (root / "data/kr/made.json").write_text("made by the test")
    own, outside, _ = guard._settle(root, snap, [], ["data/kr/made.json", "data/kr/new_day.json"], [], {"data/kr/made.json"}, 0)
    assert own == ["data/kr/made.json"] and outside == ["data/kr/new_day.json"]
    assert not (root / "data/kr/made.json").exists() and (root / "data/kr/new_day.json").exists()


def test_with_a_child_process_an_unexplained_change_fails_the_test_but_is_not_deleted(project):
    root, snap = project
    (root / "data/kr/new_day.json").write_text("the job's, or the child's")
    own, outside, unsure = guard._settle(root, snap, [], ["data/kr/new_day.json"], [], set(), 1)
    assert not own and not outside and unsure == ["data/kr/new_day.json"] and (root / "data/kr/new_day.json").exists()


def test_sqlite_side_files_and_folder_contents_count_as_the_tests_own():
    assert guard._is_own("data/x.db-journal", {"data/x.db"}) and guard._is_own("data/x.db-wal", {"data/x.db"})
    assert guard._is_own("data/kr/cache/a.csv.gz", {"data/kr/cache"}) and not guard._is_own("data/kr/cache2/a.csv.gz", {"data/kr/cache"})
    assert not guard._is_own("data/y.db", {"data/x.db"})


def test_a_write_to_the_forward_record_folder_is_noticed_and_an_empty_folder_there_is_not(tmp_path, monkeypatch):
    """Audit 2026-11-22 (ENG-11): research_data/ holds the forward records and nothing watched it."""
    root = tmp_path / "root"
    (root / "research_data" / "krx_live").mkdir(parents=True)
    monkeypatch.setattr(guard, "ROOT", root)
    monkeypatch.setitem(guard._OWN, "touched", set())
    assert guard._protected_rel(root / "research_data" / "krx_live" / "index.jsonl", root) == "research_data/krx_live/index.jsonl"
    with open(root / "research_data" / "krx_live" / "index.jsonl", "a") as fh:          # the audit hook sees the real open
        fh.write("{}")
    os.mkdir(root / "research_data" / "new_store")
    assert guard._watched(guard._OWN["touched"]) == ["research_data/krx_live/index.jsonl"]
    guard._OWN["touched"].clear()                      # this test's own write is to a temporary folder: it must not fail itself
    assert guard._watched({"data/x.json"}) == []


def test_only_protected_folders_are_noted_and_links_are_followed(tmp_path):
    root = tmp_path / "root"
    (root / "data").mkdir(parents=True)
    (root / "tests").mkdir()
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    (sandbox / "tests").symlink_to(root / "tests")              # as the suite's sandbox links the source folders
    assert guard._protected_rel(root / "data" / "a.json", root) == "data/a.json"
    assert guard._protected_rel(str(sandbox / "tests" / ".." / "data" / "a.json"), root) == "data/a.json"
    assert guard._protected_rel(os.fsencode(root / "data" / "a.json"), root) == "data/a.json"
    assert guard._protected_rel(root / "terminal" / "x.py", root) is None and guard._protected_rel(tmp_path / "elsewhere", root) is None
    assert guard._protected_rel(7, root) is None                 # a file descriptor


def test_the_hook_sees_every_python_route_of_writing(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(guard, "_note", seen.append)
    f = tmp_path / "a.txt"
    f.write_text("x")                                            # open for writing
    f.read_text()                                                # reading is not noted
    os.replace(f, tmp_path / "b.txt")                            # rename: both ends
    sqlite3.connect(tmp_path / "c.db").close()
    (tmp_path / "b.txt").unlink()
    (tmp_path / "d").mkdir()
    names = [os.path.basename(os.fspath(p)) for p in seen]
    assert names.count("a.txt") == 2 and names.count("b.txt") == 2 and "c.db" in names and "d" in names


def test_a_child_process_is_counted(monkeypatch):
    import subprocess
    before = guard._OWN["children"]
    subprocess.run([sys.executable, "-c", "pass"], check=True)
    assert guard._OWN["children"] > before


def test_the_guard_still_fails_a_test_that_writes_to_the_real_project(tmp_path):
    """The decision the fixture makes, on a stand-in project: an own write means a failure message, an outside one does not."""
    assert guard._settle(tmp_path, tmp_path, [], [], [], set(), 0) == ([], [], [])
    assert Path(guard.ROOT).is_dir() and set(guard.PROTECTED_DIRS) == {"data", "reports", "runs", "tracking"}
