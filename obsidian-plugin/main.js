const { ItemView, Notice, Plugin, PluginSettingTab, Setting, WorkspaceLeaf } = require("obsidian");
const crypto = require("crypto");
const fs = require("fs");
const os = require("os");
const path = require("path");
const { spawn } = require("child_process");

const VIEW_TYPE = "bookmark-intelligence-status";
const DEFAULT_SETTINGS = {
  agentCommand: process.platform === "win32" ? "bookmark-agent.exe" : "bookmark-agent",
  configPath: "",
  refreshSeconds: 30
};

function vaultPath(plugin) {
  return plugin.app.vault.adapter.getBasePath();
}

function stateDirectory(plugin) {
  const id = crypto.createHash("sha256").update(path.resolve(vaultPath(plugin))).digest("hex").slice(0, 16);
  let root;
  if (process.platform === "win32") root = process.env.LOCALAPPDATA || path.join(os.homedir(), "AppData", "Local");
  else if (process.platform === "darwin") root = path.join(os.homedir(), "Library", "Application Support");
  else root = process.env.XDG_STATE_HOME || path.join(os.homedir(), ".local", "state");
  return path.join(root, "Bookmark Intelligence", id);
}

function configPath(plugin) {
  return plugin.settings.configPath.trim() || path.join(vaultPath(plugin), "config.toml");
}

function readActivity(plugin) {
  const activityPath = path.join(stateDirectory(plugin), "activity.jsonl");
  if (!fs.existsSync(activityPath)) return [];
  return fs.readFileSync(activityPath, "utf8").split(/\r?\n/).filter(Boolean).slice(-40).map((line) => {
    try { return JSON.parse(line); } catch (_) { return null; }
  }).filter(Boolean).reverse();
}

class StatusView extends ItemView {
  constructor(leaf, plugin) {
    super(leaf);
    this.plugin = plugin;
  }

  getViewType() { return VIEW_TYPE; }
  getDisplayText() { return "Bookmark Intelligence"; }
  getIcon() { return "bookmark"; }

  async onOpen() {
    this.refresh();
  }

  refresh() {
    const container = this.containerEl.children[1];
    container.empty();
    container.createEl("h2", { text: "Bookmark Intelligence" });
    container.createEl("p", { text: `Activity: ${stateDirectory(this.plugin)}` });
    const actions = container.createDiv({ cls: "bookmark-intelligence-actions" });
    const refreshButton = actions.createEl("button", { text: "Refresh" });
    refreshButton.addEventListener("click", () => this.refresh());
    const runButton = actions.createEl("button", { text: "Run worker once" });
    runButton.addEventListener("click", () => this.plugin.runWorkerOnce());
    const entries = readActivity(this.plugin);
    if (!entries.length) {
      container.createEl("p", { text: "No local activity has been recorded yet." });
      return;
    }
    const list = container.createEl("ul");
    for (const entry of entries) {
      const item = list.createEl("li");
      const title = entry.title || entry.event_type || "Activity";
      const time = entry.timestamp ? ` [${entry.timestamp}]` : "";
      item.createEl("strong", { text: `${title}${time}` });
      item.createEl("div", { text: entry.message || entry.details?.error || "" });
    }
  }
}

class BookmarkIntelligenceSettings extends PluginSettingTab {
  constructor(app, plugin) {
    super(app, plugin);
    this.plugin = plugin;
  }

  display() {
    const { containerEl } = this;
    containerEl.empty();
    containerEl.createEl("h2", { text: "Bookmark Intelligence" });
    containerEl.createEl("p", { text: "The Obsidian plugin is a local status and control surface. Chrome/Firefox capture still requires the browser extension and Native Messaging agent." });
    containerEl.createEl("p", { text: "Local Ollama summarization requires hardware capable of running the selected model. Larger models may require substantial RAM and a compatible GPU." });

    new Setting(containerEl)
      .setName("Agent command")
      .setDesc("Executable name or absolute path for bookmark-agent.")
      .addText((text) => text.setValue(this.plugin.settings.agentCommand).onChange(async (value) => {
        this.plugin.settings.agentCommand = value.trim() || DEFAULT_SETTINGS.agentCommand;
        await this.plugin.saveData(this.plugin.settings);
      }));
    new Setting(containerEl)
      .setName("Config path")
      .setDesc("Absolute path to config.toml. Empty uses the vault root config.toml.")
      .addText((text) => text.setValue(this.plugin.settings.configPath).onChange(async (value) => {
        this.plugin.settings.configPath = value.trim();
        await this.plugin.saveData(this.plugin.settings);
      }));
    new Setting(containerEl)
      .setName("Activity refresh interval")
      .setDesc("Seconds between status view refreshes.")
      .addText((text) => text.setValue(String(this.plugin.settings.refreshSeconds)).onChange(async (value) => {
        const seconds = Math.max(5, Math.min(3600, Number(value) || 30));
        this.plugin.settings.refreshSeconds = seconds;
        await this.plugin.saveData(this.plugin.settings);
        this.plugin.configureRefresh();
      }));
    new Setting(containerEl)
      .setName("Open status view")
      .setDesc("Show the latest local queue and worker activity.")
      .addButton((button) => button.setButtonText("Open").onClick(() => this.plugin.activateView()));
  }
}

module.exports = class BookmarkIntelligencePlugin extends Plugin {
  async onload() {
    this.settings = Object.assign({}, DEFAULT_SETTINGS, await this.loadData());
    this.registerView(VIEW_TYPE, (leaf) => new StatusView(leaf, this));
    this.addRibbonIcon("bookmark", "Open Bookmark Intelligence", () => this.activateView());
    this.addCommand({ id: "open-status", name: "Open status", callback: () => this.activateView() });
    this.addCommand({ id: "refresh-status", name: "Refresh status", callback: () => this.refreshViews() });
    this.addCommand({ id: "run-worker-once", name: "Run worker once", callback: () => this.runWorkerOnce() });
    this.addSettingTab(new BookmarkIntelligenceSettings(this.app, this));
    this.configureRefresh();
  }

  configureRefresh() {
    if (this.refreshTimer) window.clearInterval(this.refreshTimer);
    this.refreshTimer = window.setInterval(() => this.refreshViews(), this.settings.refreshSeconds * 1000);
    this.registerInterval(this.refreshTimer);
  }

  refreshViews() {
    for (const leaf of this.app.workspace.getLeavesOfType(VIEW_TYPE)) leaf.view.refresh();
  }

  async activateView() {
    const existing = this.app.workspace.getLeavesOfType(VIEW_TYPE);
    if (existing.length) {
      this.app.workspace.revealLeaf(existing[0]);
      existing[0].view.refresh();
      return;
    }
    const leaf = this.app.workspace.getRightLeaf(false) || this.app.workspace.getLeaf(false);
    await leaf.setViewState({ type: VIEW_TYPE, active: true });
    this.app.workspace.revealLeaf(leaf);
  }

  runWorkerOnce() {
    const command = this.settings.agentCommand.trim();
    if (!command) {
      new Notice("Configure the Bookmark Intelligence agent command first.");
      return;
    }
    const child = spawn(command, ["--config", configPath(this), "worker", "--once"], { windowsHide: true });
    child.once("error", (error) => new Notice(`Could not start bookmark-agent: ${error.message}`));
    child.once("exit", (code) => {
      new Notice(code === 0 ? "Bookmark worker finished." : `Bookmark worker exited with code ${code}.`);
      this.refreshViews();
    });
    new Notice("Bookmark worker started.");
  }

  onunload() {
    if (this.refreshTimer) window.clearInterval(this.refreshTimer);
  }
};
