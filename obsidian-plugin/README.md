# Bookmark Intelligence Obsidian Plugin

This is a thin desktop-only Obsidian control surface for the local Bookmark Intelligence agent. It shows the app-state activity log and can run `bookmark-agent worker --once`.

The package includes `manifest.json` and `versions.json` for community-plugin compatibility metadata.

The Chrome/Firefox extension and Native Messaging agent remain required for real-time bookmark capture. The plugin does not duplicate browser integration or create a Vault index.

Set the absolute path to `bookmark-agent` and `config.toml` in the plugin settings. Local Ollama summarization requires hardware capable of running the selected model.

Paid plans, hosted API credits, and external AI provider connections are displayed as future UI only and are currently disabled. No payment is requested or processed by this plugin yet.
