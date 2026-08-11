from __future__ import annotations

import requests

from .config import AppConfig


def summarize_with_ollama(config: AppConfig, title: str, url: str, text: str) -> str:
    prompt = f"""
You summarize bookmarked resources for an Obsidian knowledge vault.

Return Korean Markdown with these sections:

## Summary
3-6 concise sentences.

## Key Points
- 3-7 bullets.

## Recommendation
- Suggested folder: one short path
- Suggested tags: 3-8 lowercase tags

Title: {title}
URL: {url}

Source text:
{text[:12000]}
""".strip()

    response = requests.post(
        f"{config.ollama.base_url}/api/generate",
        json={
            "model": config.ollama.model,
            "prompt": prompt,
            "stream": False,
        },
        timeout=config.ollama.timeout_seconds,
    )
    response.raise_for_status()
    data = response.json()
    return (data.get("response") or "").strip()
