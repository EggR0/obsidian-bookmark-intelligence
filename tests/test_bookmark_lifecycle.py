from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from bookmark_agent.config import load_config
from bookmark_agent.database import connect, init_db
from bookmark_agent.markdown import write_obsidian_note
from bookmark_agent.service import ingest_bookmark_event


class BookmarkLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = load_config(Path("config.toml"))

    def test_title_change_requeues_succeeded_resource(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "state.sqlite3"
            config = replace(self.config, database=replace(self.config.database, path=db_path))
            init_db(db_path)
            base = {
                "schema_version": 1,
                "source": {"browser": "test", "profile_id": "profile-a"},
                "bookmark": {
                    "id": "1",
                    "parentId": "root",
                    "url": "https://example.com/article?utm_source=test",
                },
                "change": {},
            }
            ingest_bookmark_event(config, {**base, "event": {"type": "created"}, "bookmark": {**base["bookmark"], "title": "Old"}})
            connection = connect(db_path)
            try:
                connection.execute("UPDATE resources SET process_status = 'succeeded'")
                connection.commit()
            finally:
                connection.close()

            ingest_bookmark_event(config, {**base, "event": {"type": "changed"}, "bookmark": {**base["bookmark"], "title": "New"}})
            connection = connect(db_path)
            try:
                row = connection.execute("SELECT canonical_url, title, process_status FROM resources").fetchone()
            finally:
                connection.close()

            self.assertEqual(row["canonical_url"], "https://example.com/article")
            self.assertEqual(row["title"], "New")
            self.assertEqual(row["process_status"], "pending")

    def test_canonical_url_keeps_one_markdown_path_when_title_changes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            vault = Path(directory) / "vault"
            config = replace(self.config, obsidian=replace(self.config.obsidian, vault_path=vault))
            first = write_obsidian_note(
                config,
                title="Old title",
                url="https://example.com/article?utm_source=test",
                canonical_url="https://example.com/article",
                resource_type="webpage",
                summary="First summary",
            )
            second = write_obsidian_note(
                config,
                title="New title",
                url="https://example.com/article",
                canonical_url="https://example.com/article",
                resource_type="webpage",
                summary="Updated summary",
            )
            self.assertEqual(first, second)
            self.assertEqual(len(list((vault / "Bookmarks").glob("*.md"))), 1)
            self.assertIn("# New title", second.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
