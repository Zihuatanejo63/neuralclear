"""HTTP extras must not be required just to import the reference app."""
import os
from pathlib import Path
import subprocess
import sys
import unittest


class OptionalHTTPDependencyTests(unittest.TestCase):
    def test_import_without_fastapi(self):
        script = """
import importlib.abc
import sys

class NoFastAPI(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'fastapi' or fullname.startswith('fastapi.'):
            raise ModuleNotFoundError('FastAPI intentionally unavailable')

sys.meta_path.insert(0, NoFastAPI())
import server.app as module
assert module.app is None
assert module.Header is None
assert not hasattr(module, '_require_read_key')
assert not hasattr(module, '_require_write_key')
import unittest
import tests.test_openapi_consistency as tests
result = unittest.TestResult()
unittest.defaultTestLoader.loadTestsFromModule(tests).run(result)
assert not result.errors and not result.failures
assert len(result.skipped) == 2
print('import OK; 2 tests skipped')
"""
        env = dict(os.environ)
        env.pop("NEURALCLEAR_DB", None)
        process = subprocess.run(
            [sys.executable, "-c", script],
            cwd=Path(__file__).resolve().parents[1], env=env,
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        self.assertIn("import OK; 2 tests skipped", process.stdout)
