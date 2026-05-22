from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class OpenAPITests(unittest.TestCase):
    def test_openapi_file_exists_and_contains_required_paths(self):
        path = ROOT / "OPENAPI.yaml"

        self.assertTrue(path.exists())
        content = path.read_text(encoding="utf-8")

        required = [
            "openapi:",
            "info:",
            "paths:",
            "components:",
            "/.well-known/neuralclear/agent.json:",
            "/neuralclear/quote:",
            "/neuralclear/tasks:",
            "/neuralclear/settlements:",
            "/neuralclear/disputes:",
        ]

        for item in required:
            with self.subTest(item=item):
                self.assertIn(item, content)

    def test_openapi_is_multiline_yaml(self):
        path = ROOT / "OPENAPI.yaml"
        lines = path.read_text(encoding="utf-8").splitlines()

        self.assertGreater(len(lines), 100)
        self.assertEqual(lines[0], "openapi: 3.1.0")
        self.assertIn("paths:", lines)
