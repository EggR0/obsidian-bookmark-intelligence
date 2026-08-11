from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import os
import sqlite3

from .config import AppConfig
from .service import ingest_bookmark_event
from .vault_state import state_dir


@dataclass(frozen=True)
class ScannedBookmark:
    browser: str
    profile: str
    bookmark_id: str
    title: str
    url: str
    parent_id: str | None = None
    folder: str | None = None

    @property
    def key(self) -> str:
        return f"{self.browser}:{self.profile}:{self.bookmark_id}"

    @property
    def fingerprint(self) -> str:
        return json.dumps(
            {
                "title": self.title,
                "url": self.url,
                "parent_id": self.parent_id,
                "folder": self.folder,
            },
            ensure_ascii=False,
            sort_keys=True,
        )


def chrome_profile_dirs() -> list[Path]:
    root = Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "User Data"
    if not root.exists():
        return []
    return sorted(path for path in root.iterdir() if path.is_dir() and (path / "Bookmarks").exists())


def firefox_profile_dirs() -> list[Path]:
    root = Path(os.environ.get("APPDATA", "")) / "Mozilla" / "Firefox" / "Profiles"
    if not root.exists():
        return []
    return sorted(path for path in root.iterdir() if path.is_dir() and (path / "places.sqlite").exists())


def _walk_chrome_node(profile_name: str, node: dict, folder_path: list[str]) -> list[ScannedBookmark]:
    found: list[ScannedBookmark] = []
    children = node.get("children") or []
    for child in children:
        child_type = child.get("type")
        if child_type == "url" and child.get("url"):
            found.append(
                ScannedBookmark(
                    browser="chrome-scan",
                    profile=profile_name,
                    bookmark_id=str(child.get("id") or child.get("guid") or child.get("url")),
                    title=child.get("name") or child.get("url"),
                    url=child["url"],
                    parent_id=str(node.get("id") or ""),
                    folder="/".join(folder_path) or None,
                )
            )
        elif child_type == "folder":
            found.extend(
                _walk_chrome_node(
                    profile_name,
                    child,
                    [*folder_path, child.get("name") or "Folder"],
                )
            )
    return found


def scan_chrome() -> list[ScannedBookmark]:
    bookmarks: list[ScannedBookmark] = []
    for profile_dir in chrome_profile_dirs():
        try:
            data = json.loads((profile_dir / "Bookmarks").read_text(encoding="utf-8"))
        except Exception:
            continue
        roots = data.get("roots") or {}
        for root_name, root_node in roots.items():
            if isinstance(root_node, dict):
                bookmarks.extend(_walk_chrome_node(profile_dir.name, root_node, [root_name]))
    return bookmarks


def scan_firefox() -> list[ScannedBookmark]:
    bookmarks: list[ScannedBookmark] = []
    for profile_dir in firefox_profile_dirs():
        db_path = profile_dir / "places.sqlite"
        uri = f"file:{db_path.as_posix()}?mode=ro"
        try:
            connection = sqlite3.connect(uri, uri=True)
            connection.row_factory = sqlite3.Row
        except Exception:
            continue
        try:
            rows = connection.execute(
                """
                SELECT b.guid, b.title, b.parent, parent.title AS parent_title, p.url
                FROM moz_bookmarks b
                JOIN moz_places p ON b.fk = p.id
                LEFT JOIN moz_bookmarks parent ON b.parent = parent.id
                WHERE b.type = 1 AND p.url IS NOT NULL
                """
            ).fetchall()
        except Exception:
            rows = []
        finally:
            connection.close()

        for row in rows:
            bookmarks.append(
                ScannedBookmark(
                    browser="firefox-scan",
                    profile=profile_dir.name,
                    bookmark_id=row["guid"],
                    title=row["title"] or row["url"],
                    url=row["url"],
                    parent_id=str(row["parent"]),
                    folder=row["parent_title"],
                )
            )
    return bookmarks


def _state_path(config: AppConfig) -> Path:
    return state_dir(config) / "bookmark-scan-state.json"


def load_scan_state(config: AppConfig) -> dict:
    path = _state_path(config)
    if not path.exists():
        return {"bookmarks": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"bookmarks": {}}


def save_scan_state(config: AppConfig, state: dict) -> None:
    _state_path(config).write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _event_for(bookmark: ScannedBookmark, event_type: str) -> dict:
    return {
        "schema_version": 1,
        "source": {
            "browser": bookmark.browser,
            "extension": "profile-scanner",
            "profile": bookmark.profile,
        },
        "event": {"type": event_type},
        "bookmark": {
            "id": bookmark.key,
            "parentId": bookmark.parent_id,
            "title": bookmark.title,
            "url": bookmark.url,
            "folder": bookmark.folder,
        },
        "change": {},
    }


def scan_browser_bookmarks(config: AppConfig, dry_run: bool = False, mark_seen: bool = False) -> dict:
    previous_state = load_scan_state(config)
    previous = previous_state.get("bookmarks", {})
    current_bookmarks = {bookmark.key: bookmark for bookmark in [*scan_chrome(), *scan_firefox()]}

    created = 0
    changed = 0
    removed = 0

    for key, bookmark in current_bookmarks.items():
        prior = previous.get(key)
        if prior is None:
            if not dry_run:
                ingest_bookmark_event(config, _event_for(bookmark, "created"))
            created += 1
        elif prior.get("fingerprint") != bookmark.fingerprint:
            if not dry_run:
                ingest_bookmark_event(config, _event_for(bookmark, "changed"))
            changed += 1

    for key, prior in previous.items():
        if key not in current_bookmarks:
            removed_bookmark = ScannedBookmark(
                browser=prior.get("browser", "profile-scan"),
                profile=prior.get("profile", "unknown"),
                bookmark_id=prior.get("bookmark_id", key),
                title=prior.get("title", ""),
                url=prior.get("url", ""),
                parent_id=prior.get("parent_id"),
                folder=prior.get("folder"),
            )
            if not dry_run:
                ingest_bookmark_event(config, _event_for(removed_bookmark, "removed"))
            removed += 1

    new_state = {
        "bookmarks": {
            key: {
                "browser": bookmark.browser,
                "profile": bookmark.profile,
                "bookmark_id": bookmark.bookmark_id,
                "title": bookmark.title,
                "url": bookmark.url,
                "parent_id": bookmark.parent_id,
                "folder": bookmark.folder,
                "fingerprint": bookmark.fingerprint,
            }
            for key, bookmark in current_bookmarks.items()
        }
    }
    if not dry_run or mark_seen:
        save_scan_state(config, new_state)

    return {
        "ok": True,
        "seen": len(current_bookmarks),
        "created": created,
        "changed": changed,
        "removed": removed,
        "dry_run": dry_run,
        "mark_seen": mark_seen,
    }
