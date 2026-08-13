from __future__ import annotations

from pathlib import Path
import json
import struct
import tomllib
import unittest

from bookmark_agent import __version__


class VersionTests(unittest.TestCase):
    def test_package_version_matches_project_version(self) -> None:
        project = tomllib.loads((Path(__file__).parents[1] / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(__version__, project["project"]["version"])

    def test_browser_manifests_disclose_local_runtime_requirements(self) -> None:
        root = Path(__file__).parents[1]
        project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
        for name in ("manifest.chrome.json", "manifest.firefox.json"):
            manifest = json.loads((root / "extension" / name).read_text(encoding="utf-8"))
            self.assertEqual(manifest["version"], project["project"]["version"])
            self.assertIn("local agent", manifest["description"])
            self.assertIn("hardware", manifest["description"])
            self.assertEqual(manifest["homepage_url"], "https://eggr0.github.io/obsidian-bookmark-intelligence/")

    def test_firefox_id_matches_native_host_registration_constant(self) -> None:
        root = Path(__file__).parents[1]
        manifest = json.loads((root / "extension" / "manifest.firefox.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["browser_specific_settings"]["gecko"]["id"], "bookmark-intelligence@eggr0.github.io")

    def test_extension_download_defaults_cover_all_desktop_platforms(self) -> None:
        source = (Path(__file__).parents[1] / "extension" / "background.js").read_text(encoding="utf-8")
        self.assertIn("bookmark-intelligence-windows.zip", source)
        self.assertIn("bookmark-intelligence-source.zip", source)
        self.assertIn("detectPlatform", source)
        self.assertIn("new URL(url).pathname", source)

    def test_public_install_page_discloses_unsigned_firefox_xpi(self) -> None:
        page = (Path(__file__).parents[1] / "site" / "index.html").read_text(encoding="utf-8")
        self.assertIn("unsigned submission package", page)
        self.assertIn("about:debugging", page)

    def test_store_graphics_have_required_dimensions(self) -> None:
        root = Path(__file__).parents[1] / "store-assets"
        for name, expected in {
            "bookmark-intelligence-store-1280x800.png": (1280, 800),
            "bookmark-intelligence-promo-440x280.png": (440, 280),
        }.items():
            data = (root / name).read_bytes()
            self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
            width, height = struct.unpack(">II", data[16:24])
            self.assertEqual((width, height), expected)


if __name__ == "__main__":
    unittest.main()
