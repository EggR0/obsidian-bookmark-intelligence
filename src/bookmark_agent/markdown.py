from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
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
    recommended_folder: str,
    recommended_tags: list[str],
) -> Path:
    vault = config.obsidian.vault_path
    notes_dir = vault / config.obsidian.notes_subdir
    notes_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{slugify_title(title)}.md"
    path = notes_dir / filename
    counter = 2
    while path.exists():
        path = notes_dir / f"{slugify_title(title)} {counter}.md"
        counter += 1

    processed_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    tags_yaml = "\n".join(f"  - {tag}" for tag in recommended_tags)
    content = f"""---
source_url: "{url}"
canonical_url: "{canonical_url}"
resource_type: "{resource_type}"
processed_at: "{processed_at}"
recommended_folder: "{recommended_folder}"
tags:
{tags_yaml}
---

# {title}

{summary}
"""
    path.write_text(content, encoding="utf-8")
    return path
