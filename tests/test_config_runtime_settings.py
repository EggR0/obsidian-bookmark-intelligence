from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from bookmark_agent.config import load_config, runtime_settings_path, save_runtime_settings
from bookmark_agent.native_host import _handle_control_message
from bookmark_agent.summarizer import read_summary_prompt, write_summary_prompt


class RuntimeSettingsTests(unittest.TestCase):
    def test_ping_reports_agent_version(self) -> None:
        base = load_config(Path("config.toml"))
        response = _handle_control_message(base, {"command": "ping"})
        self.assertEqual(response["agent_version"], "0.2.33")

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
                    "entitlement_endpoint": "https://billing.example.test",
                    "account_id": "acct-test",
                    "access_token_env": "BOOKMARK_ACCESS_TOKEN",
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
            self.assertEqual(applied.entitlements.endpoint, "https://billing.example.test")
            self.assertEqual(applied.entitlements.account_id, "acct-test")
            self.assertEqual(applied.entitlements.access_token_env, "BOOKMARK_ACCESS_TOKEN")
            self.assertNotIn("secret", path.read_text(encoding="utf-8"))

    def test_ai_settings_save_does_not_clear_summary_prompt(self) -> None:
        base = load_config(Path("config.toml"))
        with tempfile.TemporaryDirectory() as directory:
            vault = Path(directory) / "vault"
            config = replace(base, obsidian=replace(base.obsidian, vault_path=vault))
            write_summary_prompt(config, "keep this prompt")
            response = _handle_control_message(
                config,
                {
                    "command": "save-agent-settings",
                    "provider": "ollama",
                    "model": "qwen2.5:1.5b",
                    "base_url": "http://localhost:11434",
                    "api_key_env": "",
                },
            )
            self.assertTrue(response["ok"])
            self.assertEqual(read_summary_prompt(config), "keep this prompt")


if __name__ == "__main__":
    unittest.main()
