from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile

from bookmark_agent.backup import backup_state, restore_state
from bookmark_agent.config import default_state_dir, load_config
from bookmark_agent.database import connect, init_db


class BackupTests(unittest.TestCase):
    def test_backup_excludes_vault_notes_and_restore_round_trip(self) -> None:
        base_config = load_config(Path("config.toml"))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            vault = root / "vault"
            vault.mkdir()
            config = replace(
                base_config,
                obsidian=replace(base_config.obsidian, vault_path=vault),
                database=replace(base_config.database, path=root / "state.sqlite3"),
            )
            init_db(config.database.path)
            connection = connect(config.database.path)
            try:
                connection.execute("INSERT INTO resources (canonical_url, url, resource_type, title, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)", ("https://example.com", "https://example.com", "webpage", "Example", "now", "now"))
                connection.commit()
            finally:
                connection.close()

            state = default_state_dir(vault)
            state.mkdir(parents=True, exist_ok=True)
            (state / "summary-prompt.txt").write_text("custom prompt", encoding="utf-8")
            (state / "agent-settings.json").write_text(
                '{"provider":"openai","model":"gpt-test","base_url":"https://api.example.test/v1","api_key_env":"BOOKMARK_TEST_KEY"}',
                encoding="utf-8",
            )
            (vault / "Bookmarks").mkdir()
            (vault / "Bookmarks" / "human-note.md").write_text("must not be archived", encoding="utf-8")
            archive_path = root / "backup.zip"

            result = backup_state(config, archive_path)
            self.assertTrue(result["ok"])
            with ZipFile(archive_path) as archive:
                names = set(archive.namelist())
                self.assertIn("manifest.json", names)
                self.assertIn("bookmark-agent.sqlite3", names)
                self.assertIn("summary-prompt.txt", names)
                self.assertIn("agent-settings.json", names)
                self.assertNotIn("human-note.md", names)

            restore_state(config, archive_path)
            connection = connect(config.database.path)
            try:
                row = connection.execute("SELECT title FROM resources").fetchone()
            finally:
                connection.close()
            self.assertEqual(row["title"], "Example")
            self.assertEqual(
                (state / "agent-settings.json").read_text(encoding="utf-8"),
                '{"provider":"openai","model":"gpt-test","base_url":"https://api.example.test/v1","api_key_env":"BOOKMARK_TEST_KEY"}',
            )


if __name__ == "__main__":
    unittest.main()
