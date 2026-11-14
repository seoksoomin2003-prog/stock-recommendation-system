"""The layout after the 2026-11-14 split: one function per ``qsf`` action behind two tables, and the read-only screen methods of
the two large classes in modules of their own.  The moved code was checked statement by statement when it moved; these tests keep
the shape from growing back into one function or one class."""
import ast
import inspect
from pathlib import Path

import app
from terminal import services, services_model
from terminal.qsf import service, views

ROOT = Path(__file__).resolve().parents[1]


def test_every_qsf_action_has_exactly_one_place():
    plain, live, one_shot = set(app.QSF_HANDLERS), set(app.QSF_LIVE_HANDLERS), set(app.QSF_ONE_SHOT)
    assert not plain & live and not (plain | live) & one_shot
    assert set(app.QSF_ACTIONS) == plain | live | one_shot | {"evaluate"}       # evaluate is the dispatcher's own tail
    for fn in set(app.QSF_HANDLERS.values()):
        assert list(inspect.signature(fn).parameters) == ["args"]
    for fn in set(app.QSF_LIVE_HANDLERS.values()):
        assert list(inspect.signature(fn).parameters) == ["args", "q", "market"]


def test_the_dispatcher_stays_small_and_no_handler_grows_into_another_one():
    tree = ast.parse((ROOT / "app.py").read_text(encoding="utf-8"))
    size = {n.name: n.end_lineno - n.lineno + 1 for n in tree.body if isinstance(n, ast.FunctionDef)}
    assert size["cmd_qsf"] <= 45
    assert max(v for k, v in size.items() if k.startswith("_qsf_")) <= 60


def test_the_scorer_and_the_terminal_inherit_their_screen_methods():
    assert issubclass(service.QSF, views.ScreenViews) and issubclass(services.Terminal, services_model.ModelViews)
    assert service.QSF.heatmap is views.ScreenViews.heatmap and service.QSF.PEER_MIN == 6 and service._n is views._n
    assert services.Terminal.model is services_model.ModelViews.model
    for cls, mixin in ((service.QSF, views.ScreenViews), (services.Terminal, services_model.ModelViews)):
        own = {k for k, v in vars(cls).items() if callable(v)}
        assert not own & {k for k, v in vars(mixin).items() if callable(v)}          # a method lives in one of the two, never both


def test_the_screen_modules_do_not_import_the_classes_that_inherit_them():
    for mod, banned in ((views, "terminal.qsf.service"), (services_model, "terminal.services")):
        tree = ast.parse(Path(mod.__file__).read_text(encoding="utf-8"))
        top = [n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))]
        names = {a.name for n in top if isinstance(n, ast.Import) for a in n.names} | {n.module for n in top if isinstance(n, ast.ImportFrom)}
        assert banned not in names
