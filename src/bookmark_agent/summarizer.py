from __future__ import annotations

import requests

from .config import AppConfig
from .vault_state import state_dir


DEFAULT_SUMMARY_PROMPT = """
You summarize bookmarked resources for an Obsidian knowledge vault.

Return Korean Markdown with these sections:

## Summary
3-6 concise sentences.

## Key Points
- 3-7 bullets.

## Recommendation
- Suggested folder: one short path
- Suggested tags: 3-8 lowercase tags

Title: {{title}}
URL: {{url}}

Source text:
{{source_text}}
""".strip()


def prompt_path(config: AppConfig):
    return state_dir(config) / "summary-prompt.md"


def read_summary_prompt(config: AppConfig) -> str:
    path = prompt_path(config)
    if not path.exists():
        return DEFAULT_SUMMARY_PROMPT
    text = path.read_text(encoding="utf-8-sig").strip()
    return text or DEFAULT_SUMMARY_PROMPT


def write_summary_prompt(config: AppConfig, prompt: str) -> None:
    path = prompt_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text((prompt or DEFAULT_SUMMARY_PROMPT).strip() + "\n", encoding="utf-8")


def render_prompt(template: str, *, title: str, url: str, text: str) -> str:
    source_text = text[:12000]
    rendered = (
        template.replace("{{title}}", title or "")
        .replace("{{url}}", url or "")
        .replace("{{source_text}}", source_text)
    )
    if "{{source_text}}" not in template:
        rendered = f"{rendered.rstrip()}\n\nSource text:\n{source_text}"
    return rendered.strip()


def summarize_with_ollama(config: AppConfig, title: str, url: str, text: str) -> str:
    prompt = render_prompt(read_summary_prompt(config), title=title, url=url, text=text)

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
