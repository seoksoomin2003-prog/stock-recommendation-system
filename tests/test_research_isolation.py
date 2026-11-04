import ast
import pathlib
import unittest


class TestResearchIsolation(unittest.TestCase):
    def test_research_entrypoint_does_not_import_execution(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        for path in [root / "research" / "orchestrator.py", root / "application" / "query_service.py"]:
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = [x.name for x in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [node.module or ""]
                else:
                    continue
                self.assertFalse(any(name.startswith("execution") or "portfolio" in name for name in names), path)
