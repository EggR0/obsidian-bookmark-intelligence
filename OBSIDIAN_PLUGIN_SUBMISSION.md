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
0.2.29
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

## Current Package Status

- Repository root contains `README.md`, `LICENSE`, `manifest.json`, and `versions.json`.
- `manifest.json` uses plugin id `bookmark-intelligence`.
- `manifest.json` version is `0.2.29`.
- GitHub release tag `0.2.29` must contain `main.js`, `manifest.json`, and `styles.css`.
- The browser/native-agent release tag `v0.2.29` remains separate from the Obsidian plugin release.

## Community Directory Submission

After the release exists and this repository is public:

1. Go to https://community.obsidian.md and sign in with an Obsidian account.
2. Link the GitHub account that owns this repository.
3. Add a new plugin from the Community Directory submission flow.
4. Use repository `EggR0/obsidian-bookmark-intelligence`.
5. Confirm that the directory sees root `manifest.json` from the default branch.
6. Confirm that the release tag exactly matches `manifest.json` version: `0.2.29`.
7. Address any automated review feedback with a new commit and an incremented release version.

Obsidian's current submission guide uses the Community Directory flow. The older `obsidianmd/obsidian-releases` pull request path is still useful as a reference for the plugin list format and download behavior.

Reference entry format:

```json
{
  "id": "bookmark-intelligence",
  "name": "Obsidian Bookmark Intelligence",
  "author": "EggR0",
  "description": "Local status and control surface for the Bookmark Intelligence browser agent.",
  "repo": "EggR0/obsidian-bookmark-intelligence"
}
```

## User-Facing Hardware Disclosure

Use this in the plugin description, README, and submission notes:

```text
Requires a separately installed local agent and local Ollama model. Summary speed and reliability depend on the user's CPU, RAM, GPU, and selected Ollama model. Bookmark capture and activity viewing can work without a loaded model, but automatic summaries require Ollama to load and run the configured model.
```

## Official References

- Obsidian sample plugin release instructions: https://github.com/obsidianmd/obsidian-sample-plugin
- Obsidian releases directory behavior: https://github.com/obsidianmd/obsidian-releases
- Obsidian plugin submission guide: https://docs.obsidian.md/plugins/releasing/submit-plugin
