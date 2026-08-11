from __future__ import annotations

from dataclasses import dataclass
import json
import re

import requests
import trafilatura
from yt_dlp import YoutubeDL


@dataclass(frozen=True)
class ExtractedResource:
    title: str
    text: str
    metadata: dict


def extract_webpage(url: str) -> ExtractedResource:
    downloaded = trafilatura.fetch_url(url)
    if not downloaded:
        raise RuntimeError("Failed to download webpage")

    extracted_json = trafilatura.extract(
        downloaded,
        url=url,
        output_format="json",
        with_metadata=True,
        include_comments=False,
        include_tables=False,
    )
    if not extracted_json:
        raise RuntimeError("Failed to extract webpage text")

    data = json.loads(extracted_json)
    title = data.get("title") or url
    text = data.get("text") or ""
    metadata = {
        "title": title,
        "author": data.get("author"),
        "date": data.get("date"),
        "hostname": data.get("hostname"),
        "sitename": data.get("sitename"),
    }
    return ExtractedResource(title=title, text=text, metadata=metadata)


def _strip_caption_text(raw: str) -> str:
    lines = []
    seen_recent = set()
    for line in raw.splitlines():
        stripped = line.strip()
        if (
            not stripped
            or stripped == "WEBVTT"
            or stripped.startswith(("Kind:", "Language:", "NOTE"))
            or "-->" in stripped
            or stripped.isdigit()
        ):
            continue
        stripped = re.sub(r"<[^>]+>", "", stripped)
        stripped = stripped.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
        if stripped in seen_recent:
            continue
        lines.append(stripped)
        seen_recent.add(stripped)
        if len(seen_recent) > 30:
            seen_recent = set(lines[-10:])
    return "\n".join(lines)


def _download_caption(info: dict, preferred_languages: tuple[str, ...] = ("ko", "en")) -> tuple[str | None, str]:
    caption_sources = info.get("subtitles") or {}
    automatic_sources = info.get("automatic_captions") or {}

    for language in preferred_languages:
        for source in (caption_sources, automatic_sources):
            entries = source.get(language) or []
            vtt_entry = next((entry for entry in entries if entry.get("ext") == "vtt"), None)
            entry = vtt_entry or (entries[0] if entries else None)
            if not entry or not entry.get("url"):
                continue
            try:
                response = requests.get(entry["url"], timeout=30)
                response.raise_for_status()
            except requests.RequestException:
                continue
            return language, _strip_caption_text(response.text)
    return None, ""


def extract_youtube(url: str) -> ExtractedResource:
    with YoutubeDL({"skip_download": True, "quiet": True, "no_warnings": True}) as ydl:
        data = ydl.extract_info(url, download=False)

    subtitles = data.get("subtitles") or {}
    automatic_captions = data.get("automatic_captions") or {}
    caption_languages = sorted(set(subtitles.keys()) | set(automatic_captions.keys()))
    selected_caption_language, caption_text = _download_caption(data)

    title = data.get("title") or url
    metadata = {
        "title": title,
        "channel": data.get("channel") or data.get("uploader"),
        "duration": data.get("duration"),
        "upload_date": data.get("upload_date"),
        "webpage_url": data.get("webpage_url"),
        "caption_languages": caption_languages,
        "selected_caption_language": selected_caption_language,
    }
    text = "\n".join(
        str(part)
        for part in [
            f"Title: {title}",
            f"Channel: {metadata.get('channel') or ''}",
            f"Duration: {metadata.get('duration') or ''}",
            f"Caption languages: {', '.join(caption_languages)}",
            "Transcript:",
            caption_text[:60000] if caption_text else "Transcript unavailable; summarize from metadata and description.",
            "Description:",
            data.get("description") or "",
        ]
        if part
    )
    return ExtractedResource(title=title, text=text, metadata=metadata)


def extract_resource(url: str, resource_type: str) -> ExtractedResource:
    if resource_type == "youtube":
        return extract_youtube(url)
    if resource_type == "webpage":
        return extract_webpage(url)
    raise RuntimeError(f"Unsupported resource type: {resource_type}")
