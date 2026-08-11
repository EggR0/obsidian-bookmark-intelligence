# Obsidian Bookmark Intelligence - SPEC

## Goal

Chrome and Firefox bookmark changes are captured in near real time, normalized locally, summarized through Ollama, and written into an Obsidian vault as compact Markdown notes.

Obsidian is the final knowledge database. The local SQLite file is only an internal queue under the vault for dedupe, retry state, and event recovery.

## Non-Goals

- Store videos, full webpages, screenshots, or browser history.
- Use advertising-backed services, hosted bookmark managers, hosted summarization APIs, or quota-limited SaaS by default.
- Automatically move browser bookmarks by default.
- Replace Obsidian as the user's final knowledge store.

## Current Local Defaults

```text
Vault:          D:\obsidian
Final notes:    D:\obsidian\Bookmarks
Internal state: D:\obsidian\.bookmark-agent
Queue DB:       D:\obsidian\.bookmark-agent\bookmark-agent.sqlite3
Event log:      D:\obsidian\.bookmark-agent\events.jsonl
Ollama model:   qwen2.5:7b
```

## Architecture

```text
Chrome / Firefox
  WebExtension
    bookmarks API events
    native messaging
        |
        v
Native host executable
  canonical URL
  event log in vault
  processing queue in vault
        |
        v
Worker
  webpage extraction: trafilatura
  YouTube metadata/subtitles: yt-dlp
  summarization: local Ollama
        |
        v
Obsidian vault
  compact Markdown notes
```

## Component Responsibilities

### WebExtension

- Runs in Chrome and Firefox from one shared JavaScript codebase.
- Listens to:
  - `bookmarks.onCreated`
  - `bookmarks.onChanged`
  - `bookmarks.onMoved`
  - `bookmarks.onRemoved`
- Sends small event payloads to the local native host.
- Does not crawl webpages, call LLMs, or write files.

### Native Host

- Receives browser events over Native Messaging.
- Canonicalizes URLs.
- Appends a human-inspectable event log to `D:\obsidian\.bookmark-agent\events.jsonl`.
- Adds or updates queue state in `D:\obsidian\.bookmark-agent\bookmark-agent.sqlite3`.
- Returns a compact response to the browser.

### Worker

- Reads due queue entries.
- Extracts compact source data:
  - General webpages: `trafilatura`.
  - YouTube: `yt-dlp`, metadata and subtitle text only.
- Calls Ollama on `localhost`.
- Writes final Markdown into the configured Obsidian notes folder.
- Records success, failure, retry count, and the generated Markdown path.

## Why There Is SQLite

SQLite is not the knowledge store. It is a local work queue because bookmark processing has state that Markdown alone handles awkwardly:

- The same canonical URL may appear in multiple bookmarks.
- Web extraction can fail.
- YouTube captions may be unavailable or rate-limited by the source site.
- Ollama may be stopped or missing the configured model.
- Native Messaging host processes are short-lived.
- Failed resources need retry state without duplicating final notes.

Final readable knowledge remains Markdown in Obsidian.

## Event Schema

```json
{
  "schema_version": 1,
  "source": {
    "browser": "chrome",
    "extension": "obsidian-bookmark-intelligence"
  },
  "event": {
    "type": "created",
    "timestamp": "2026-08-11T03:30:00Z"
  },
  "bookmark": {
    "id": "23891",
    "parentId": "123",
    "index": 4,
    "title": "Interesting article",
    "url": "https://example.com/article"
  },
  "change": {}
}
```

Event types:

- `created`
- `changed`
- `moved`
- `removed`

## SQLite Schema

The queue database is stored inside the vault state directory.

### `bookmark_events`

Append-only event log mirror.

| column | type | notes |
| --- | --- | --- |
| `id` | integer primary key | local event id |
| `received_at` | text | UTC timestamp |
| `browser` | text | chrome/firefox/unknown |
| `event_type` | text | created/changed/moved/removed |
| `bookmark_id` | text | browser bookmark id |
| `payload_json` | text | compact original event |

### `bookmarks`

Current local bookmark view by browser and bookmark id.

| column | type | notes |
| --- | --- | --- |
| `browser` | text | part of primary key |
| `bookmark_id` | text | part of primary key |
| `url` | text | original URL |
| `canonical_url` | text | normalized URL |
| `title` | text | browser title |
| `parent_id` | text | browser folder id |
| `status` | text | active/removed |
| `updated_at` | text | UTC timestamp |

### `resources`

Deduplicated processing targets.

| column | type | notes |
| --- | --- | --- |
| `id` | integer primary key | local resource id |
| `canonical_url` | text unique | dedupe key |
| `url` | text | preferred original URL |
| `resource_type` | text | webpage/youtube/unknown |
| `title` | text | latest known title |
| `process_status` | text | pending/processing/succeeded/failed/skipped |
| `retry_count` | integer | failed attempts |
| `next_retry_at` | text | UTC timestamp |
| `last_error` | text | compact error |
| `content_hash` | text | extracted-content hash |
| `markdown_path` | text | written Obsidian note path |
| `created_at` | text | UTC timestamp |
| `updated_at` | text | UTC timestamp |

### `resource_metadata`

Compact extraction and recommendation result.

| column | type | notes |
| --- | --- | --- |
| `resource_id` | integer primary key | references resources |
| `metadata_json` | text | title, author, date, channel, duration, captions |
| `summary` | text | compact summary |
| `recommended_folder` | text | suggested folder |
| `recommended_tags_json` | text | suggested tags |
| `updated_at` | text | UTC timestamp |

## URL Canonicalization

- Lowercase scheme and host.
- Remove URL fragments.
- Remove common tracking parameters, including `utm_*`, `fbclid`, `gclid`, `msclkid`, and similar noise.
- Sort query parameters.
- Use `w3lib.url.canonicalize_url` when available.

## Processing Flow

1. Browser fires a bookmark event.
2. Extension sends event through Native Messaging.
3. Native host appends `events.jsonl`.
4. Native host upserts queue state.
5. Worker extracts metadata/text.
6. Worker summarizes with Ollama.
7. Worker writes a Markdown note to Obsidian.
8. Worker marks the queue entry succeeded or failed with retry state.

## Markdown Output

```markdown
---
source_url: "https://example.com/article"
canonical_url: "https://example.com/article"
resource_type: "webpage"
processed_at: "2026-08-11T03:30:00Z"
recommended_folder: "AI/Reading"
tags:
  - bookmark
  - ai
---

# Interesting article

## Summary

...

## Key Points

- ...

## Recommendation

- Suggested folder: AI/Reading
- Suggested tags: bookmark, ai
```

## Security Model

- The extension only requests `bookmarks` and `nativeMessaging`.
- The extension has no filesystem access.
- The local agent writes only under the configured vault path for notes/state.
- Native Messaging registration is explicit in HKCU registry keys.
- Ollama is called locally.
- Video files and full webpage archives are not stored.
- Automatic bookmark movement remains disabled unless explicitly enabled later.

## Execution Order

1. Install dependencies.
2. Generate `config.toml` for `D:\obsidian`.
3. Build extension artifacts and native host executable.
4. Register Chrome/Firefox native hosts.
5. Load extension in Chrome/Firefox.
6. Run `bookmark-agent --config .\config.toml doctor`.
7. Run `bookmark-agent --config .\config.toml worker`.
8. Create or edit a bookmark and confirm Markdown appears in `D:\obsidian\Bookmarks`.
