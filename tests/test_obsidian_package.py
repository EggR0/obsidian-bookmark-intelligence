from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ObsidianPackageTests(unittest.TestCase):
    def test_official_root_plugin_files_and_metadata_match(self) -> None:
        manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
        versions = json.loads((ROOT / "versions.json").read_text(encoding="utf-8"))
        self.assertIn(manifest["version"], versions)
        self.assertEqual(versions[manifest["version"]], manifest["minAppVersion"])
        for name in ("main.js", "manifest.json", "styles.css"):
            self.assertTrue((ROOT / name).is_file(), name)

    def test_release_source_plugin_matches_official_metadata(self) -> None:
        root_manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
        source_manifest = json.loads((ROOT / "obsidian-plugin" / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(root_manifest["version"], source_manifest["version"])
        self.assertEqual(root_manifest["minAppVersion"], source_manifest["minAppVersion"])
        self.assertEqual((ROOT / "main.js").read_bytes(), (ROOT / "obsidian-plugin" / "main.js").read_bytes())
        self.assertEqual((ROOT / "styles.css").read_bytes(), (ROOT / "obsidian-plugin" / "styles.css").read_bytes())
