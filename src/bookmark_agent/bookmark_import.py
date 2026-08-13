from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit

from .browser_scan import ScannedBookmark, _event_for, scan_chrome, scan_firefox
from .canonical import canonicalize_url, resource_type_for_url
from .config import AppConfig
from .service import ingest_bookmark_event


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

    return items, {
        "raw_seen": len(raw_bookmarks),
        "selected": len(items),
        "duplicates_skipped": duplicate_count,
        "non_http_skipped": skipped_count,
    }


def find_duplicate_groups(filters: ImportFilters) -> list[dict]:
    groups: dict[str, list[ScannedBookmark]] = {}
    for bookmark in collect_bookmarks():
        if not bookmark.url.startswith(("http://", "https://")):
            continue
        canonical_url = canonicalize_url(bookmark.url)
        item = ImportItem(
            bookmark=bookmark,
            canonical_url=canonical_url,
            resource_type=resource_type_for_url(canonical_url),
            domain=_domain_for(canonical_url),
        )
        if _matches_filter(item, filters):
            groups.setdefault(canonical_url, []).append(bookmark)

    duplicates = []
    for canonical_url, bookmarks in groups.items():
        if len(bookmarks) < 2:
            continue
        duplicates.append(
            {
                "canonical_url": canonical_url,
                "count": len(bookmarks),
                "bookmarks": [
                    {
                        "browser": bookmark.browser,
                        "profile": bookmark.profile,
                        "bookmark_id": bookmark.bookmark_id,
                        "title": bookmark.title,
                        "url": bookmark.url,
                        "folder": bookmark.folder,
                    }
                    for bookmark in bookmarks
                ],
            }
        )
    return sorted(duplicates, key=lambda group: (-group["count"], group["canonical_url"]))


def enqueue_summaries(config: AppConfig, items: list[ImportItem], stats: dict, dry_run: bool = False) -> dict:
    if dry_run:
        return {"ok": True, "mode": "summarize", "dry_run": True, **stats}

    enqueued = 0
    for item in items:
        ingest_bookmark_event(config, _event_for(item.bookmark, "created"))
        enqueued += 1
    return {"ok": True, "mode": "summarize", "dry_run": False, **stats, "enqueued": enqueued}


def import_bookmarks(config: AppConfig, mode: str, filters: ImportFilters, dry_run: bool = False) -> dict:
    if mode != "summarize":
        raise ValueError("Only summarize mode is supported; Vault index files are not created.")
    items, stats = prepare_import_items(filters)
    return enqueue_summaries(config, items, stats, dry_run=dry_run)
