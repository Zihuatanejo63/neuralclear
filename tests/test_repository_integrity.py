from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class RepositoryIntegrityTests(unittest.TestCase):
    def test_no_accidental_git_artifacts(self):
        forbidden_patterns = [
            "*.sample",
            "pack-*.idx",
            "pack-*.pack",
            "pack-*.rev",
        ]
        forbidden_names = {
            "__pycache__",
            "simulation.py",
            "publish.sh",
            "republish.sh",
        }

        found = []
        for pattern in forbidden_patterns:
            found.extend(ROOT.glob(pattern))

        for path in ROOT.iterdir():
            if path.name in forbidden_names:
                found.append(path)

        self.assertEqual(found, [], f"Forbidden repository artifacts found: {found}")
