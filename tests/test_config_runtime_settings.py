from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from bookmark_agent.config import load_config, runtime_settings_path, save_runtime_settings


class RuntimeSettingsTests(unittest.TestCase):
    def test_runtime_ai_settings_are_applied_without_storing_secret(self) -> None:
        base = load_config(Path("config.toml"))
        with tempfile.TemporaryDirectory() as directory:
            vault = Path(directory) / "vault"
            config = replace(base, obsidian=replace(base.obsidian, vault_path=vault))
            path = save_runtime_settings(
                vault,
                {
                    "provider": "openai",
                    "model": "gpt-test",
                    "base_url": "https://api.example.test/v1",
                    "api_key_env": "BOOKMARK_TEST_KEY",
                },
            )
            self.assertEqual(path, runtime_settings_path(vault))
            config_path = Path(directory) / "config.toml"
            template = Path("config.example.toml").read_text(encoding="utf-8")
            config_path.write_text(
                template.replace('vault_path = "D:\\\\obsidian"', f'vault_path = "{vault.as_posix()}"'),
                encoding="utf-8",
            )
            applied = load_config(config_path)
            self.assertEqual(applied.summarizer.provider, "openai")
            self.assertEqual(applied.summarizer.model, "gpt-test")
            self.assertEqual(applied.summarizer.api_key_env, "BOOKMARK_TEST_KEY")
            self.assertNotIn("secret", path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
