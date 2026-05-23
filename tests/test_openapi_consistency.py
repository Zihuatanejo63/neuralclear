from pathlib import Path
import re
import unittest

try:
    import server.app as app_module
except ModuleNotFoundError:  # pragma: no cover - exercised when HTTP deps are absent.
    app_module = None


ROOT = Path(__file__).resolve().parents[1]


CORE_PATHS = {
    "/.well-known/neuralclear/agent.json",
    "/registry/agents",
    "/registry/search",
    "/neuralclear/quote",
    "/neuralclear/tasks",
    "/neuralclear/tasks/{task_id}",
    "/neuralclear/receipts/{receipt_id}",
    "/neuralclear/disputes",
    "/dashboard/agents",
    "/dashboard/transactions",
    "/dashboard/receipts",
    "/dashboard/disputes",
    "/dashboard/balances",
}


@unittest.skipIf(app_module is None or app_module.app is None, "FastAPI is not installed")
class OpenAPIConsistencyTests(unittest.TestCase):
    def setUp(self):
        self.documented_paths = self._documented_paths()
        self.fastapi_paths = {route.path for route in app_module.app.routes}

    def test_openapi_paths_exist_in_fastapi_routes(self):
        missing = sorted(path for path in CORE_PATHS if path not in self.fastapi_paths)

        self.assertEqual(missing, [], f"FastAPI routes missing OpenAPI core paths: {missing}")

    def test_fastapi_core_routes_are_documented(self):
        undocumented = sorted(path for path in CORE_PATHS if path not in self.documented_paths)

        self.assertEqual(
            undocumented,
            [],
            f"Update OPENAPI.yaml for these FastAPI core routes: {undocumented}",
        )

    @staticmethod
    def _documented_paths() -> set[str]:
        content = (ROOT / "OPENAPI.yaml").read_text(encoding="utf-8")
        return set(re.findall(r"^  (/[^\n:]+(?:\\{[^}]+\\})?):$", content, re.MULTILINE))
