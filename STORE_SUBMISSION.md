# Bookmark Intelligence Store Submission Guide

This project can produce Chrome Web Store and Firefox Add-ons packages, but the final public listing requires store developer accounts, upload, review, and approval.

It also produces an Obsidian community-plugin package. Obsidian publication still requires a public repository, plugin manifest review, and acceptance by the Obsidian community plugins process.

## What Is Ready

- Chrome extension ZIP: `outputs/chrome-extension.zip`
- Firefox extension XPI: `outputs/firefox-extension.xpi`
- Obsidian plugin ZIP: `outputs/obsidian-bookmark-intelligence-plugin.zip`
- Obsidian community-plugin metadata: root `manifest.json` and `versions.json`
- Extension options page: `options.html`
- Browser notifications: `notifications` and `alarms`
- Native Messaging permission and local agent bridge
- Local agent download button for the latest GitHub Release bundle selected for the user's desktop OS
- Store-safe local-first design: no advertising and no daily quota in the local/Ollama path
- Chrome listing assets: `store-assets/bookmark-intelligence-store-1280x800.png` and `store-assets/bookmark-intelligence-promo-440x280.png`
- Firefox manifest declares the required `bookmarksInfo` data collection permission for AMO's built-in consent flow

### Listing graphics

The prepared Chrome listing assets use the shipped product terminology and contain no personal Vault data. Upload the 1280x800 image as the required screenshot and the 440x280 image as the small promotional tile. Chrome's listing form also accepts up to five screenshots; a marquee tile and video are optional for this first submission. Firefox can reuse the screenshot when completing its AMO listing.

### Firefox signing status

`outputs/firefox-extension.xpi` is the build/submission package and is not Mozilla-signed yet. Before AMO publication, regular Firefox users should use `about:debugging` -> **This Firefox** -> **Load Temporary Add-on** for local testing. After the AMO listing is approved, users should install from AMO so Firefox can handle signed updates. Do not describe the GitHub XPI as a normal permanent Firefox installation until it has been signed by AMO.

## What Still Requires Store Accounts

Obsidian community plugins:

1. Keep the plugin source in a public GitHub repository.
2. Submit the repository through the Obsidian community plugins submission process.
3. Confirm root `manifest.json` version `0.2.37` and exact release tag `0.2.37`.
4. Complete review and wait for acceptance before claiming marketplace availability.

Chrome Web Store:

1. Register or use a Chrome Web Store developer account.
2. Enable the account's required two-step verification before publishing.
3. Upload `outputs/chrome-extension.zip`.
4. Complete listing information, privacy fields, and the public privacy-policy URL.
5. Because the product offers paid features, complete any publisher address or business-information fields required by the dashboard.
6. Submit for review.
7. After approval and public visibility, users can find it through Chrome Web Store search.

Firefox Add-ons:

1. Register or use an AMO developer account.
2. Upload `outputs/firefox-extension.xpi`.
3. Complete listing information and source disclosure if requested.
4. Submit for review.
5. After approval and public visibility, users can find it through Firefox Add-ons search.

## Important Native Messaging Note

The browser extension cannot silently install or run the local Python/native agent from a web store listing. Users must install the local agent separately. This extension provides a `Get local agent` button that downloads the latest Windows bundle on Windows or the source bundle on Linux/macOS; the user then runs the matching installer once.

## Reviewer Test Instructions

The core real-time flow does not require an account or a hosted service. Use a disposable Obsidian Vault and a test browser profile.

Windows test path:

1. Download `bookmark-intelligence-windows.zip` from the `v0.2.37` GitHub release and extract it.
2. Install Ollama and make a small model available, for example `ollama pull qwen2.5:1.5b`. Larger models require more RAM/VRAM.
3. Open PowerShell in the extracted directory and run `powershell -ExecutionPolicy Bypass -File .\install.ps1 -VaultPath C:\Temp\BookmarkIntelligenceReview -SkipOpen`.
4. Load `outputs\chrome-extension` as an unpacked Chrome extension, or use the AMO-signed Firefox listing after publication. Before AMO signing, Firefox local testing uses `about:debugging` -> **This Firefox** -> **Load Temporary Add-on**.
5. Open the extension popup, select **Test connection**, then create a disposable bookmark such as `https://example.com`.
6. Confirm that the browser notification reports queue and completion activity and that one compact Markdown note appears in the configured Vault.

The reviewer can also test failure behavior by stopping Ollama: the bookmark event remains captured, the worker records `processing_failed`, and the queue schedules a retry. Pro-only bulk analysis, duplicate reports, and backup/restore require a paid entitlement and are not needed to verify the free real-time path.

Source reproduction:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[build]"
python scripts\build_extensions.py
```

## Public Privacy Policy URL

Use the following public URL in Chrome Web Store and Firefox Add-ons privacy fields:

```text
https://eggr0.github.io/obsidian-bookmark-intelligence/privacy.html
```

## Hardware Requirements Disclosure

The public listing must clearly disclose that summarization runs on the user's own computer through Ollama and therefore requires local hardware capable of running the selected model.

Suggested plain-language disclosure:

```text
Important hardware requirement: this extension relies on a separately installed local agent and a local Ollama model for summarization. It does not include a hosted AI service. To summarize bookmarks, your computer must be able to run the selected local model. Larger models may require a modern CPU, substantial RAM, and preferably a compatible GPU with enough VRAM. If Ollama cannot load the selected model, if GPU acceleration is unavailable and CPU fallback is too slow, or if the local agent is not installed, bookmark capture can still work but automatic summaries may fail or wait for retry.
```

Short listing warning:

```text
Requires a separately installed local agent and local Ollama model. Summary speed and reliability depend on your computer's CPU/RAM/GPU and the selected model.
```

Recommended model note:

```text
The default configuration uses qwen2.5:7b when available. Users may choose a smaller Ollama model on lower-powered machines.
```

## Suggested Listing

Name:

```text
Bookmark Intelligence
```

Short description:

```text
Local-first Chrome/Firefox bookmark intelligence pipeline for Obsidian.
```

Full description:

```text
Bookmark Intelligence captures Chrome and Firefox bookmark changes, sends them to a local Native Messaging agent, deduplicates canonical URLs, and writes compact Markdown summaries into an Obsidian vault.

The extension is local-first. It does not use advertising-backed bookmark services or daily quota summarization services in the default local path. Webpage extraction is handled by the local agent with trafilatura. YouTube metadata and captions are handled with yt-dlp without downloading video files. Summaries are generated through a local Ollama model by default, with optional user-configured AI APIs.

The extension includes:
- Real-time bookmark event capture
- Native Host connection test
- Optional Pro bulk analysis of existing bookmarks through the local queue
- Browser notifications for queued, succeeded, and failed processing
- Settings page for notification and local agent download settings
- Editable local summary prompt with variables for title, URL, and source text
- Options-page controls to preview or queue existing bookmarks for Pro bulk analysis

The local agent must be installed separately from GitHub Releases. Local summarization requires Ollama and hardware capable of running the selected local model.
```

Privacy summary:

```text
Bookmark URLs and titles are sent only to the user's locally installed Native Messaging host. The extension does not send bookmark data to a hosted service. The local agent may fetch bookmarked webpages or YouTube metadata/captions to create summaries, according to the user's local configuration.
```

Firefox data collection declaration:

```text
Required: bookmarksInfo. The extension sends bookmark names, URLs, and folder information to the user's locally installed Native Messaging host for the primary bookmark-to-Obsidian function. It does not collect website content from pages through the extension, and it does not transmit data to a developer-operated remote service.
```

Permissions explanation:

```text
bookmarks: read bookmark changes and existing bookmark trees.
nativeMessaging: communicate with the locally installed Bookmark Intelligence agent.
storage: store extension profile id, settings, and last notification cursor.
downloads: download the user-requested local agent installation bundle.
notifications: show browser notifications for queued/completed/failed work.
alarms: poll local activity status while the browser is running.
```

## Chrome Web Store Privacy Practices Draft

Single purpose:

```text
Capture browser bookmark changes and send them to a user-installed local agent so the user can create compact Obsidian Markdown summaries.
```

Data usage:

```text
The extension sends bookmark titles, URLs, folder ids, event types, and extension profile id only to the local Native Messaging host installed on the user's computer. The extension does not send this data to a remote server operated by the developer.
```

Limited Use disclosure:

```text
Use of bookmark data is limited to providing the user-facing bookmark-to-Obsidian functionality. Bookmark data is not sold, used for advertising, used for creditworthiness, or transferred to unrelated third parties.
```

Remote code:

```text
The extension package does not load remote code. The Get local agent button downloads a user-requested static installation archive from the project's GitHub Releases asset URL.
```

## Firefox Add-ons Data Disclosure Draft

Data collection/transmission description:

```text
The extension transmits bookmark titles, URLs, folder ids, event types, and a local extension profile id to a native application installed on the user's computer. This transmission is required for the primary function of creating Obsidian bookmark summaries. The extension does not transmit this data to a developer-operated remote service.
```

Native application disclosure:

```text
The native application stores processing state under the configured Obsidian vault, fetches bookmarked webpage text or YouTube metadata/captions when processing is requested, and sends extracted text to the user's local Ollama endpoint for summarization.
```

User control:

```text
Users can uninstall the extension, remove the Native Messaging manifest, stop the worker, disable browser notifications in extension settings, and edit or delete the local agent configuration and Obsidian state files.
```

## Review Checklist

- The listing states that a local agent is required.
- The listing states that local Ollama and suitable hardware are required for summarization.
- The listing explains that bookmark data is sent to the local Native Messaging host.
- The listing explains that the local agent may fetch bookmarked webpages or YouTube metadata/captions.
- The listing explains all requested permissions.
- The package contains no secrets, local config, SQLite files, build folders, or generated personal paths.
- The package does not include remote code loading.
- The support/homepage URL is one click away from the privacy and Limited Use disclosure.

## Official References

- Chrome Web Store publish flow: https://developer.chrome.com/docs/webstore/publish
- Chrome Web Store developer account setup: https://developer.chrome.com/docs/webstore/set-up-account
- Chrome Web Store preparation: https://developer.chrome.com/docs/webstore/prepare
- Chrome Web Store user data FAQ: https://developer.chrome.com/docs/webstore/program-policies/user-data-faq
- Chrome Web Store program policies: https://developer.chrome.com/docs/webstore/program-policies
- Chrome extension permission declaration: https://developer.chrome.com/docs/extensions/develop/concepts/declare-permissions
- Chrome Native Messaging: https://developer.chrome.com/docs/extensions/develop/concepts/native-messaging
- Chrome Web Store best practices: https://developer.chrome.com/docs/webstore/best-practices
- Chrome Web Store listing graphics: https://developer.chrome.com/docs/webstore/cws-dashboard-listing
- Chrome Web Store image dimensions: https://developer.chrome.com/docs/webstore/images
- Firefox Add-ons submission: https://extensionworkshop.com/documentation/publish/submitting-an-add-on/
- Firefox Add-on policies: https://extensionworkshop.com/documentation/publish/add-on-policies/
- Firefox Native Messaging: https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/Native_messaging
