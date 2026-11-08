"""The qsf one-shot commands: every action is accepted, resolves to a real function, and prints what it printed before the table."""
import importlib
import json
from argparse import Namespace

import pytest

import app

RES = {"status": "TESTED", "strategies": {"SWING": 1}, "scores": [1], "buckets": [2], "primary": {"p": 1}, "companies": 5, "failed": 0, "extra": "x"}


def run(action, monkeypatch, capsys):
    module, func, _, _ = app.QSF_ONE_SHOT[action]
    mod = importlib.import_module(f"terminal.qsf.{module}")
    monkeypatch.setattr(mod, func, lambda root: dict(RES))
    assert app.cmd_qsf(Namespace(action=action, market="US", tickers=[], dry_run=False, apply=False)) == 0
    return json.loads(capsys.readouterr().out)


@pytest.mark.parametrize("action,expected", [
    ("corrected-oos", {"status": "TESTED", "companies": 5, "failed": 0}),
    ("short-test", {k: v for k, v in RES.items() if k != "strategies"}),
    ("kr-events-run", {k: v for k, v in RES.items() if k != "scores"}),
    ("kr-forward-evaluate-events", {k: v for k, v in RES.items() if k != "buckets"}),
    ("research-test", {"SWING": 1}),
    ("oos-test", {"p": 1}),
    ("history-run", {"p": 1}),
])
def test_one_shot_output_is_unchanged(action, expected, monkeypatch, capsys):
    assert run(action, monkeypatch, capsys) == expected


def test_swing_prints_its_report_path(monkeypatch, capsys):
    from terminal.qsf import research_swing
    assert run("swing-test", monkeypatch, capsys) == {"status": "TESTED", "report": str(research_swing.TEST_REPORT)}


def test_every_action_is_accepted_and_resolves():
    assert len(app.QSF_ACTIONS) == len(set(app.QSF_ACTIONS))
    for action, (module, func, _, _) in app.QSF_ONE_SHOT.items():
        assert callable(getattr(importlib.import_module(f"terminal.qsf.{module}"), func)), action
