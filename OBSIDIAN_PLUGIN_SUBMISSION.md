# Obsidian Community Plugin Submission

This repository now contains the files required for Obsidian Community Plugin packaging.

## Required Root Files

- `manifest.json`
- `versions.json`
- `README.md`

## Required Release Assets

For the version in `manifest.json`, the matching GitHub release must attach:

- `main.js`
- `manifest.json`
- `styles.css`

Obsidian looks up the plugin version from the repository root `manifest.json`, then downloads the matching release assets for that exact version. The release tag must match the manifest version exactly. For this package, the Obsidian-compatible tag is:

```text
0.1.0
```

Do not use a `v` prefix for the Obsidian community plugin release tag.

## Manual Installation Test

Create this folder in a vault:

```text
<vault>/.obsidian/plugins/bookmark-intelligence/
```

Copy these files into it:

```text
main.js
manifest.json
styles.css
```

Then reload Obsidian and enable the plugin in Settings -> Community plugins.

## Community Directory Submission

After the release exists and this repository is public:

1. Fork `obsidianmd/obsidian-releases`.
2. Add an entry to `community-plugins.json`.
3. Open a pull request.

Suggested entry:

```json
{
  "id": "bookmark-intelligence",
  "name": "Obsidian Bookmark Intelligence",
  "author": "EggR0",
  "description": "Control panel for the local-first browser bookmark intelligence agent for Obsidian.",
  "repo": "EggR0/obsidian-bookmark-intelligence"
}
```

## User-Facing Hardware Disclosure

Use this in the plugin description, README, and submission notes:

```text
Requires a separately installed local agent and local Ollama model. Summary speed and reliability depend on the user's CPU, RAM, GPU, and selected Ollama model. Bookmark capture and index viewing can work without a loaded model, but automatic summaries require Ollama to load and run the configured model.
```

## Official References

- Obsidian sample plugin release instructions: https://github.com/obsidianmd/obsidian-sample-plugin
- Obsidian releases directory behavior: https://github.com/obsidianmd/obsidian-releases
- Obsidian plugin submission guide: https://docs.obsidian.md/plugins/releasing/submit-plugin
