# Bookmark Intelligence Specification

## Goal

Bookmark Intelligence detects Chrome and Firefox bookmark changes, deduplicates canonical URLs, extracts compact webpage or YouTube source data, summarizes it with a configured AI provider, and writes one concise Markdown note per URL into the configured Obsidian Vault.

The free core is real-time bookmark processing. Existing-bookmark bulk analysis is a Pro capability. The local Ollama and user-owned API-key paths do not impose an application daily quota.

## Non-Goals

- Store videos, full webpages, screenshots, browser history, or raw transcripts in Obsidian.
- Create Vault index, inbox, activity, recommendation, or database folders.
- Automatically move browser bookmarks by default.
- Replace Obsidian as the human-readable final store.

## Architecture

```text
Chrome / Firefox WebExtension
  -> Native Messaging
  -> local Python agent
  -> canonical URL + dedupe
  -> SQLite queue in OS app data
  -> worker
  -> trafilatura or yt-dlp
  -> Ollama / OpenAI-compatible / Gemini / Anthropic
  -> one Markdown note in the configured Vault
```

The extension observes bookmark events and displays browser notifications. It does not crawl pages, call AI providers, or write files.

## Storage Boundary

Only final summary notes are written to the Vault:

```text
D:\obsidian\Bookmarks\bookmark--<canonical-url-hash>.md
```

SQLite, event JSONL, retry state, and the editable prompt are stored outside the Vault:

```text
Windows: %LOCALAPPDATA%\Bookmark Intelligence\<vault-id>\
macOS:   ~/Library/Application Support/Bookmark Intelligence/<vault-id>/
Linux:   $XDG_STATE_HOME/Bookmark Intelligence/<vault-id>/
```

The configured Vault path is never hardcoded. `${state}` in `config.toml` resolves to the OS app-data directory.

## Component Responsibilities

### WebExtension

- Uses one shared JavaScript codebase for Chrome and Firefox.
- Stores a random `profile_id` per extension profile.
- Listens to `bookmarks.onCreated`, `onChanged`, `onMoved`, and `onRemoved`.
- Sends compact event payloads through Native Messaging.
- Shows connection status, agent download, settings, and browser notifications.
- Polls recent activity through the Native Host while the browser is running.

### Native Host

- Receives bookmark events and control commands.
- Canonicalizes URLs and inserts/upserts queue state.
- Provides `ping`, `get-agent-settings`, `save-agent-settings`, `recent-activity`, and Pro-gated bulk import commands.
- Never receives or stores provider API keys from extension storage.

### Worker

- Claims due queue entries in batches.
- Extracts webpage content with `trafilatura`.
- Extracts YouTube metadata and subtitles with `yt-dlp`; it never downloads video files.
- Calls the selected summarizer provider.
- Writes the final note and updates success/failure/retry state.
- Emits `worker_started`, `extraction_started`, `summarizer_started`, `summarizer_completed`, `processing_succeeded`, and `processing_failed` activity events.

## Event Schema

```json
{
  "schema_version": 1,
  "source": {
    "browser": "chrome",
    "extension": "bookmark-intelligence",
    "profile_id": "profile-uuid"
  },
  "event": {"type": "created", "timestamp": "2026-08-11T03:30:00Z"},
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

Event types are `created`, `changed`, `moved`, and `removed`. Browser/profile/bookmark identity is kept separate; processing identity is the canonical URL.

## SQLite Schema

SQLite is an internal queue, not a user-facing knowledge database.

### `bookmark_events`

Append-only event mirror: `id`, `received_at`, `browser`, `profile_id`, `event_type`, `bookmark_id`, `payload_json`.

### `bookmarks`

Current browser state: `browser`, `profile_id`, `bookmark_id`, `url`, `canonical_url`, `title`, `parent_id`, `status`, `updated_at`.

### `resources`

Deduplicated processing targets: `canonical_url` (unique), `url`, `resource_type`, `title`, `process_status`, `retry_count`, `next_retry_at`, `last_error`, `content_hash`, `markdown_path`, timestamps.

### `resource_metadata`

Compact extracted metadata and summary: `resource_id`, `metadata_json`, `summary`, timestamps. Legacy recommendation columns may remain for schema compatibility but are not emitted to Markdown or used by the worker.

## URL Canonicalization

- Lowercase scheme and host.
- Remove fragments.
- Remove common tracking parameters such as `utm_*`, `fbclid`, `gclid`, and `msclkid`.
- Sort query parameters using `w3lib.url.canonicalize_url` when available.
- Use the canonical URL as the unique queue key and the note filename hash.

## Processing and Retry Flow

1. The browser emits an event.
2. Native Messaging sends it to the local agent.
3. The agent records the event and upserts the canonical resource.
4. The worker claims a pending or due-retry resource.
5. Extraction runs.
6. The selected AI provider summarizes the compact source text.
7. The worker writes `bookmark--<hash>.md`.
8. The resource becomes `succeeded`, or `failed` with `retry_count`, `next_retry_at`, and `last_error`.

If YouTube subtitles are unavailable, metadata and description can still be summarized. If extraction or the AI provider fails, no raw source is written to the Vault and the queue retries according to configuration.

## AI Providers

`[summarizer]` supports:

- `ollama`: local `http://localhost:11434`, default model `qwen2.5:7b`.
- `openai`: OpenAI-compatible `/chat/completions` endpoint.
- `gemini`: Gemini `generateContent` endpoint.
- `anthropic`: Anthropic Messages endpoint.
- Other OpenAI-compatible providers by setting `provider` and `base_url` as appropriate.

API keys are read only from the environment variable named by `api_key_env`. They are not written to SQLite, logs, prompts, or Markdown.

## Markdown Contract

```markdown
---
source_url: "https://example.com/article"
canonical_url: "https://example.com/article"
resource_type: "webpage"
processed_at: "2026-08-11T03:30:00Z"
---

# Interesting article

핵심 요약입니다.
```

Changing a bookmark title updates the same URL resource and note content. Removing a bookmark marks browser state as removed but does not delete a human-readable Obsidian note.

## Notifications

The default is browser notifications, not Windows desktop notifications. The extension polls `recent-activity`; the durable JSONL log remains in OS app data. Console output is also available from the worker.

## Security Model

- Extension permissions are limited to bookmarks, nativeMessaging, storage, notifications, and alarms.
- The extension has no filesystem access.
- The Native Host is installed explicitly for the current user.
- API keys stay in environment variables.
- Full pages, videos, and raw transcripts are not stored in the Vault.
- Automatic browser-folder movement is not enabled.

## Execution Order

1. Run `install.ps1` on Windows or `install.sh` on Linux/macOS.
2. Configure the Vault path and `[summarizer]` provider.
3. Install/load the generated Chrome or Firefox extension.
4. Run `bookmark-agent --config .\config.toml doctor`.
5. Start the worker, or let the installer register its user startup service.
6. Create a bookmark and confirm one summary note appears under the configured notes folder.
