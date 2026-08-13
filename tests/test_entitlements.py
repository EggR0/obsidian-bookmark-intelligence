from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import os
import tempfile
import unittest
from unittest.mock import Mock, patch

from bookmark_agent.config import default_state_dir, load_config
from bookmark_agent.entitlements import current_plan, entitlement_path, has_feature, refresh_entitlement, refresh_if_stale


class EntitlementTests(unittest.TestCase):
    def setUp(self) -> None:
        self.base = load_config(Path("config.toml"))

    def test_expired_cached_entitlement_is_free(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = replace(
                self.base,
                obsidian=replace(self.base.obsidian, vault_path=Path(directory)),
            )
            state = default_state_dir(Path(directory))
            state.mkdir(parents=True, exist_ok=True)
            (state / "entitlement.json").write_text(
                '{"plan":"Solo","status":"active","features":["backup"],"expires_at":"2000-01-01T00:00:00Z"}',
                encoding="utf-8",
            )
            self.assertFalse(has_feature(config, "backup"))
            self.assertEqual(current_plan(config), "Free")

    def test_user_config_cannot_grant_pro_without_development_environment(self) -> None:
        config = replace(self.base, features=replace(self.base.features, pro_enabled=True))
        with patch.dict(os.environ, {"BOOKMARK_INTELLIGENCE_DEV_PRO": ""}):
            self.assertFalse(has_feature(config, "bulk_analysis"))
        with patch.dict(os.environ, {"BOOKMARK_INTELLIGENCE_DEV_PRO": "1"}):
            self.assertTrue(has_feature(config, "bulk_analysis"))
            self.assertEqual(current_plan(config), "Pro (development override)")

    def test_refresh_caches_only_entitlement_fields(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = replace(
                self.base,
                obsidian=replace(self.base.obsidian, vault_path=Path(directory)),
                entitlements=replace(
                    self.base.entitlements,
                    endpoint="https://billing.example.test",
                    account_id="acct-1",
                    access_token_env="TEST_ACCESS_TOKEN",
                ),
            )
            response = Mock()
            response.json.return_value = {
                "plan": "Solo",
                "status": "active",
                "features": ["bulk_analysis", "backup"],
                "expires_at": "2099-01-01T00:00:00Z",
                "access_token": "must-not-be-cached",
            }
            response.raise_for_status.return_value = None
            with patch.dict(os.environ, {"TEST_ACCESS_TOKEN": "secret"}), patch("bookmark_agent.entitlements.requests.get", return_value=response) as get:
                payload = refresh_entitlement(config)
            get.assert_called_once()
            self.assertTrue(has_feature(config, "bulk_analysis"))
            self.assertEqual(payload["plan"], "Solo")
            cached = (default_state_dir(Path(directory)) / "entitlement.json").read_text(encoding="utf-8")
            self.assertNotIn("must-not-be-cached", cached)
            self.assertNotIn("secret", cached)

    def test_refresh_if_stale_uses_cached_entitlement_when_server_is_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = replace(
                self.base,
                obsidian=replace(self.base.obsidian, vault_path=Path(directory)),
                entitlements=replace(
                    self.base.entitlements,
                    endpoint="http://127.0.0.1:1",
                    account_id="acct-1",
                    access_token_env="MISSING_ACCESS_TOKEN",
                ),
            )
            entitlement_path(config).write_text(
                '{"account_id":"acct-1","plan":"Solo","status":"active","features":["bulk_analysis"],"refreshed_at":"2000-01-01T00:00:00Z"}',
                encoding="utf-8",
            )
            self.assertEqual(refresh_if_stale(config)["plan"], "Solo")
            self.assertTrue(has_feature(config, "bulk_analysis"))


if __name__ == "__main__":
    unittest.main()
