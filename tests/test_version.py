from __future__ import annotations

from pathlib import Path
import tomllib
import unittest

from bookmark_agent import __version__


class VersionTests(unittest.TestCase):
    def test_package_version_matches_project_version(self) -> None:
        project = tomllib.loads((Path(__file__).parents[1] / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(__version__, project["project"]["version"])


if __name__ == "__main__":
    unittest.main()
