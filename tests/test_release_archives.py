from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile
import unittest

from scripts.verify_release_archives import verify_archive


class ReleaseArchiveTests(unittest.TestCase):
    def test_rejects_generated_cache_files(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "bad.zip"
            with ZipFile(path, "w") as archive:
                archive.writestr("src/bookmark_agent/__pycache__/x.pyc", b"bad")
                archive.writestr('manifest.json', '{"version": "0.2.37"}')
            with self.assertRaises(ValueError):
                verify_archive(path, "0.2.37")

    def test_accepts_clean_archive(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "good.zip"
            with ZipFile(path, "w") as archive:
                archive.writestr('manifest.json', '{"version": "0.2.37"}')
                archive.writestr("main.js", "console.log('ok');")
            verify_archive(path, "0.2.37")


if __name__ == "__main__":
    unittest.main()
