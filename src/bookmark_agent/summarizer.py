from __future__ import annotations

import requests
import os

from .config import AppConfig
from .vault_state import state_dir


DEFAULT_SUMMARY_PROMPT = """
You summarize bookmarked resources for an Obsidian knowledge vault.

Return Korean Markdown with these sections:

## Summary
3-6 concise sentences.

## Key Points
- 3-7 bullets.

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


def summarize(config: AppConfig, title: str, url: str, text: str) -> str:
    prompt = render_prompt(read_summary_prompt(config), title=title, url=url, text=text)
    provider = config.summarizer.provider
    api_key = os.environ.get(config.summarizer.api_key_env) if config.summarizer.api_key_env else None
    headers = {"Content-Type": "application/json"}
    if api_key and provider in {"openai", "anthropic"}:
        headers["Authorization"] = f"Bearer {api_key}"

    if provider == "ollama":
        endpoint = f"{config.summarizer.base_url}/api/generate"
        payload = {"model": config.summarizer.model, "prompt": prompt, "stream": False}
    elif provider == "gemini":
        endpoint = f"{config.summarizer.base_url}/models/{config.summarizer.model}:generateContent"
        if api_key:
            endpoint = f"{endpoint}?key={api_key}"
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
    elif provider == "anthropic":
        endpoint = f"{config.summarizer.base_url}/messages"
        headers["x-api-key"] = api_key or ""
        headers["anthropic-version"] = "2023-06-01"
        payload = {"model": config.summarizer.model, "max_tokens": 600, "messages": [{"role": "user", "content": prompt}]}
    else:
        endpoint = f"{config.summarizer.base_url}/chat/completions"
        payload = {"model": config.summarizer.model, "messages": [{"role": "user", "content": prompt}], "temperature": 0.2}

    response = requests.post(endpoint, headers=headers, json=payload, timeout=config.summarizer.timeout_seconds)
    response.raise_for_status()
    data = response.json()
    if provider == "ollama":
        result = data.get("response")
    elif provider == "gemini":
        result = (((data.get("candidates") or [{}])[0].get("content") or {}).get("parts") or [{}])[0].get("text")
    elif provider == "anthropic":
        result = (((data.get("content") or [{}])[0]).get("text"))
    else:
        result = (((data.get("choices") or [{}])[0].get("message") or {}).get("content"))
    return (result or "").strip()


summarize_with_ollama = summarize
