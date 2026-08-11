from __future__ import annotations

import re

from .config import AppConfig


TAG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,31}$")


def derive_recommendations(config: AppConfig, summary: str) -> tuple[str, list[str]]:
    folder = config.recommendations.default_folder
    tags = list(config.recommendations.default_tags)

    for line in summary.splitlines():
        normalized = line.strip().lstrip("-").strip()
        lower = normalized.lower()
        if lower.startswith("suggested folder:"):
            value = normalized.split(":", 1)[1].strip()
            if value:
                folder = value
        if lower.startswith("suggested tags:"):
            value = normalized.split(":", 1)[1]
            parsed = [tag.strip().lstrip("#").lower() for tag in value.split(",")]
            tags = [tag for tag in parsed if TAG_RE.match(tag)] or tags

    return folder, sorted(set(tags))
