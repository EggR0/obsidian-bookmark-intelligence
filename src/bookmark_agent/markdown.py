from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import hashlib
import re

from .config import AppConfig


INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def slugify_title(title: str, fallback: str = "bookmark") -> str:
    cleaned = INVALID_FILENAME_CHARS.sub(" ", title).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    if not cleaned:
        cleaned = fallback
    return cleaned[:120].rstrip(". ")


def write_obsidian_note(
    config: AppConfig,
    *,
    title: str,
    url: str,
    canonical_url: str,
    resource_type: str,
    summary: str,
) -> Path:
    vault = config.obsidian.vault_path
    notes_dir = vault / config.obsidian.notes_subdir
    notes_dir.mkdir(parents=True, exist_ok=True)

    # The URL hash keeps one bookmark mapped to one note even when its title changes.
    url_hash = hashlib.sha256(canonical_url.encode("utf-8")).hexdigest()[:12]
    path = notes_dir / f"bookmark--{url_hash}.md"

    processed_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    content = f"""---
source_url: "{url}"
canonical_url: "{canonical_url}"
resource_type: "{resource_type}"
processed_at: "{processed_at}"
---

# {title}

{summary}
"""
    path.write_text(content, encoding="utf-8")
    return path
