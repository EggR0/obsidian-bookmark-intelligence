# Store Submission Guide

This project can produce Chrome Web Store and Firefox Add-ons packages, but the final public listing requires store developer accounts, upload, review, and approval.

## What Is Ready

- Chrome extension ZIP: `outputs/chrome-extension.zip`
- Firefox extension XPI: `outputs/firefox-extension.xpi`
- Extension options page: `options.html`
- Browser notifications: `notifications` and `alarms`
- Native Messaging permission and local agent bridge
- Local agent download button pointing to GitHub Releases
- Store-safe local-first design: no hosted summarization service, no advertising, no daily quota service

## What Still Requires Store Accounts

Chrome Web Store:

1. Register or use a Chrome Web Store developer account.
2. Upload `outputs/chrome-extension.zip`.
3. Complete listing information and privacy fields.
4. Submit for review.
5. After approval and public visibility, users can find it through Chrome Web Store search.

Firefox Add-ons:

1. Register or use an AMO developer account.
2. Upload `outputs/firefox-extension.xpi`.
3. Complete listing information and source disclosure if requested.
4. Submit for review.
5. After approval and public visibility, users can find it through Firefox Add-ons search.

## Important Native Messaging Note

The browser extension cannot silently install or run the local Python/native agent from a web store listing. Users must install the local agent separately. This extension provides a `Get local agent` button that opens the GitHub Releases page where the local installer and packages are available.

## Suggested Listing

Name:

```text
Obsidian Bookmark Intelligence
```

Short description:

```text
Local-first Chrome/Firefox bookmark intelligence pipeline for Obsidian.
```

Full description:

```text
Obsidian Bookmark Intelligence captures Chrome and Firefox bookmark changes, sends them to a local Native Messaging agent, deduplicates canonical URLs, and writes compact Markdown summaries into an Obsidian vault.

The extension is local-first. It does not use advertising-backed bookmark services or daily quota summarization services by default. Webpage extraction is handled by the local agent with trafilatura. YouTube metadata and captions are handled with yt-dlp without downloading video files. Summaries are generated through a local Ollama model.

The extension includes:
- Real-time bookmark event capture
- Native Host connection test
- Existing bookmark index preview
- Existing bookmark index creation in Obsidian
- Browser notifications for queued, succeeded, and failed processing
- Settings page for notification and local agent download settings

The local agent must be installed separately from GitHub Releases.
```

Privacy summary:

```text
Bookmark URLs and titles are sent only to the user's locally installed Native Messaging host. The extension does not send bookmark data to a hosted service. The local agent may fetch bookmarked webpages or YouTube metadata/captions to create summaries, according to the user's local configuration.
```

Permissions explanation:

```text
bookmarks: read bookmark changes and existing bookmark trees.
nativeMessaging: communicate with the locally installed Obsidian Bookmark Intelligence agent.
storage: store extension profile id, settings, and last notification cursor.
notifications: show browser notifications for queued/completed/failed work.
alarms: poll local activity status while the browser is running.
```

## Official References

- Chrome Web Store publish flow: https://developer.chrome.com/docs/webstore/publish
- Chrome Web Store preparation: https://developer.chrome.com/docs/webstore/prepare
- Chrome Native Messaging: https://developer.chrome.com/docs/extensions/develop/concepts/native-messaging
- Firefox Add-ons submission: https://extensionworkshop.com/documentation/publish/submitting-an-add-on/
- Firefox Native Messaging: https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/Native_messaging
