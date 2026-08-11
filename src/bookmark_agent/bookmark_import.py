from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit
import json
import re

from .browser_scan import ScannedBookmark, _event_for, scan_chrome, scan_firefox
from .canonical import canonicalize_url, resource_type_for_url
from .config import AppConfig
from .service import ingest_bookmark_event
from .vault_state import state_dir


INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


@dataclass(frozen=True)
class ImportFilters:
    browser: str | None = None
    profile: str | None = None
    folder: str | None = None
    domain: str | None = None
    url_contains: str | None = None
    resource_type: str | None = None
    limit: int | None = None


@dataclass(frozen=True)
class ImportItem:
    bookmark: ScannedBookmark
    canonical_url: str
    resource_type: str
    domain: str


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_filename(value: str, fallback: str = "unknown") -> str:
    cleaned = INVALID_FILENAME_CHARS.sub(" ", value).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return (cleaned or fallback)[:120].rstrip(". ")


def collect_bookmarks() -> list[ScannedBookmark]:
    return [*scan_chrome(), *scan_firefox()]


def _domain_for(url: str) -> str:
    host = urlsplit(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host or "local"


def _matches_filter(item: ImportItem, filters: ImportFilters) -> bool:
    bookmark = item.bookmark
    if filters.browser and filters.browser.lower() not in bookmark.browser.lower():
        return False
    if filters.profile and filters.profile.lower() not in bookmark.profile.lower():
        return False
    if filters.folder and filters.folder.lower() not in (bookmark.folder or "").lower():
        return False
    if filters.domain and filters.domain.lower() not in item.domain.lower():
        return False
    if filters.url_contains and filters.url_contains.lower() not in bookmark.url.lower():
        return False
    if filters.resource_type and filters.resource_type != item.resource_type:
        return False
    return True


def prepare_import_items(filters: ImportFilters) -> tuple[list[ImportItem], dict]:
    raw_bookmarks = collect_bookmarks()
    by_canonical: dict[str, ImportItem] = {}
    duplicate_count = 0
    skipped_count = 0

    for bookmark in raw_bookmarks:
        if not bookmark.url.startswith(("http://", "https://")):
            skipped_count += 1
            continue
        canonical_url = canonicalize_url(bookmark.url)
        item = ImportItem(
            bookmark=bookmark,
            canonical_url=canonical_url,
            resource_type=resource_type_for_url(canonical_url),
            domain=_domain_for(canonical_url),
        )
        if not _matches_filter(item, filters):
            continue
        if canonical_url in by_canonical:
            duplicate_count += 1
            continue
        by_canonical[canonical_url] = item

    items = sorted(by_canonical.values(), key=lambda item: (item.domain, item.bookmark.title.lower()))
    if filters.limit is not None:
        items = items[: filters.limit]

    stats = {
        "raw_seen": len(raw_bookmarks),
        "selected": len(items),
        "duplicates_skipped": duplicate_count,
        "non_http_skipped": skipped_count,
    }
    return items, stats


def _bookmark_line(item: ImportItem) -> str:
    bookmark = item.bookmark
    title = (bookmark.title or item.canonical_url).replace("\n", " ").strip()
    folder = bookmark.folder or "-"
    return (
        f"- [{title}]({item.canonical_url})\n"
        f"  source: {bookmark.browser} / {bookmark.profile} | folder: {folder} | "
        f"type: {item.resource_type} | tags: #bookmark #unprocessed"
    )


def write_index(config: AppConfig, items: list[ImportItem], stats: dict, dry_run: bool = False) -> dict:
    notes_dir = config.obsidian.vault_path / config.obsidian.notes_subdir
    by_domain_dir = notes_dir / "by-domain"
    index_path = notes_dir / "_Index.md"
    inbox_path = notes_dir / "_Inbox.md"
    state_path = state_dir(config) / "bookmark-import-index.json"

    domain_groups: dict[str, list[ImportItem]] = defaultdict(list)
    type_counts: dict[str, int] = defaultdict(int)
    for item in items:
        domain_groups[item.domain].append(item)
        type_counts[item.resource_type] += 1

    if dry_run:
        return {
            "ok": True,
            "mode": "index",
            "dry_run": True,
            **stats,
            "domain_count": len(domain_groups),
            "type_counts": dict(sorted(type_counts.items())),
        }

    notes_dir.mkdir(parents=True, exist_ok=True)
    by_domain_dir.mkdir(parents=True, exist_ok=True)

    generated_at = _now()
    top_domains = sorted(domain_groups.items(), key=lambda pair: (-len(pair[1]), pair[0]))[:50]

    index_lines = [
        "---",
        f'generated_at: "{generated_at}"',
        "kind: bookmark-index",
        f"bookmark_count: {len(items)}",
        f"domain_count: {len(domain_groups)}",
        "---",
        "",
        "# Bookmark Index",
        "",
        f"- Imported bookmarks: {len(items)}",
        f"- Domains: {len(domain_groups)}",
        f"- Duplicates skipped: {stats.get('duplicates_skipped', 0)}",
        f"- Non-HTTP skipped: {stats.get('non_http_skipped', 0)}",
        "",
        "## Views",
        "",
        "- [[_Inbox]]",
        "- [[by-domain]]",
        "",
        "## Resource Types",
        "",
    ]
    for resource_type, count in sorted(type_counts.items()):
        index_lines.append(f"- {resource_type}: {count}")

    index_lines.extend(["", "## Top Domains", ""])
    for domain, domain_items in top_domains:
        filename = _safe_filename(domain)
        index_lines.append(f"- [[by-domain/{filename}|{domain}]]: {len(domain_items)}")

    inbox_lines = [
        "---",
        f'generated_at: "{generated_at}"',
        "kind: bookmark-inbox",
        f"bookmark_count: {len(items)}",
        "---",
        "",
        "# Bookmark Inbox",
        "",
        "These are imported bookmarks that have not necessarily been summarized into individual notes.",
        "",
    ]
    inbox_lines.extend(_bookmark_line(item) for item in items)

    index_path.write_text("\n".join(index_lines) + "\n", encoding="utf-8")
    inbox_path.write_text("\n\n".join(inbox_lines) + "\n", encoding="utf-8")

    domain_paths = []
    for domain, domain_items in sorted(domain_groups.items()):
        filename = _safe_filename(domain)
        domain_path = by_domain_dir / f"{filename}.md"
        lines = [
            "---",
            f'generated_at: "{generated_at}"',
            "kind: bookmark-domain-index",
            f'domain: "{domain}"',
            f"bookmark_count: {len(domain_items)}",
            "---",
            "",
            f"# {domain}",
            "",
        ]
        lines.extend(_bookmark_line(item) for item in domain_items)
        domain_path.write_text("\n\n".join(lines) + "\n", encoding="utf-8")
        domain_paths.append(str(domain_path))

    state_payload = {
        "generated_at": generated_at,
        "stats": stats,
        "items": [
            {
                "title": item.bookmark.title,
                "url": item.bookmark.url,
                "canonical_url": item.canonical_url,
                "resource_type": item.resource_type,
                "domain": item.domain,
                "browser": item.bookmark.browser,
                "profile": item.bookmark.profile,
                "folder": item.bookmark.folder,
            }
            for item in items
        ],
    }
    state_path.write_text(json.dumps(state_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "ok": True,
        "mode": "index",
        "dry_run": False,
        **stats,
        "domain_count": len(domain_groups),
        "type_counts": dict(sorted(type_counts.items())),
        "index_path": str(index_path),
        "inbox_path": str(inbox_path),
        "domain_files": len(domain_paths),
    }


def enqueue_summaries(config: AppConfig, items: list[ImportItem], stats: dict, dry_run: bool = False) -> dict:
    if dry_run:
        return {"ok": True, "mode": "summarize", "dry_run": True, **stats}

    enqueued = 0
    for item in items:
        ingest_bookmark_event(config, _event_for(item.bookmark, "created"))
        enqueued += 1
    return {"ok": True, "mode": "summarize", "dry_run": False, **stats, "enqueued": enqueued}


def import_bookmarks(config: AppConfig, mode: str, filters: ImportFilters, dry_run: bool = False) -> dict:
    items, stats = prepare_import_items(filters)
    if mode == "index":
        return write_index(config, items, stats, dry_run=dry_run)
    if mode == "summarize":
        return enqueue_summaries(config, items, stats, dry_run=dry_run)
    raise ValueError(f"Unsupported import mode: {mode}")
