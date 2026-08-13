const { Plugin, PluginSettingTab, Setting, Notice, Platform } = require("obsidian");

const DEFAULT_SETTINGS = {
  agentReleaseUrl: "https://github.com/EggR0/obsidian-bookmark-intelligence/releases/latest",
  browserExtensionUrl: "https://github.com/EggR0/obsidian-bookmark-intelligence/releases/latest",
  activityNotePath: "Bookmarks/_Activity.md",
  indexNotePath: "Bookmarks/_Index.md",
  showHardwareWarning: true
};

module.exports = class ObsidianBookmarkIntelligencePlugin extends Plugin {
  async onload() {
    await this.loadSettings();

    this.addRibbonIcon("bookmark", "Bookmark Intelligence", () => {
      this.openActivityNote();
    });

    this.addCommand({
      id: "open-bookmark-activity",
      name: "Open bookmark agent activity",
      callback: () => this.openActivityNote()
    });

    this.addCommand({
      id: "open-bookmark-index",
      name: "Open bookmark index",
      callback: () => this.openIndexNote()
    });

    this.addCommand({
      id: "open-local-agent-release",
      name: "Open local agent download",
      callback: () => this.openExternal(this.settings.agentReleaseUrl)
    });

    this.addCommand({
      id: "copy-install-command",
      name: "Copy local agent install command",
      callback: () => this.copyInstallCommand()
    });

    this.addSettingTab(new BookmarkIntelligenceSettingTab(this.app, this));

    if (this.settings.showHardwareWarning) {
      new Notice(
        "Bookmark Intelligence requires the local agent, Ollama, and hardware capable of running the selected local model.",
        9000
      );
    }
  }

  async loadSettings() {
    this.settings = Object.assign({}, DEFAULT_SETTINGS, await this.loadData());
  }

  async saveSettings() {
    await this.saveData(this.settings);
  }

  openActivityNote() {
    this.openVaultFile(this.settings.activityNotePath);
  }

  openIndexNote() {
    this.openVaultFile(this.settings.indexNotePath);
  }

  async openVaultFile(path) {
    const file = this.app.vault.getAbstractFileByPath(path);
    if (!file) {
      new Notice(`${path} was not found. Run the local agent first.`);
      return;
    }
    await this.app.workspace.getLeaf(false).openFile(file);
  }

  openExternal(url) {
    if (!url) {
      new Notice("No URL configured.");
      return;
    }
    if (Platform.isDesktopApp) {
      try {
        const { shell } = require("electron");
        shell.openExternal(url);
        return;
      } catch (error) {
        window.open(url);
        return;
      }
    }
    window.open(url);
  }

  getVaultPath() {
    const adapter = this.app.vault.adapter;
    if (adapter && typeof adapter.getBasePath === "function") {
      return adapter.getBasePath();
    }
    return "";
  }

  installCommand() {
    const vaultPath = this.getVaultPath() || "<VaultPath>";
    if (Platform.isWin) {
      return `powershell -ExecutionPolicy Bypass -File .\\install.ps1 -VaultPath "${vaultPath}"`;
    }
    return `./install.sh --vault-path "${vaultPath}"`;
  }

  async copyInstallCommand() {
    const command = this.installCommand();
    try {
      await navigator.clipboard.writeText(command);
      new Notice("Install command copied.");
    } catch (error) {
      new Notice(command, 12000);
    }
  }
};

class BookmarkIntelligenceSettingTab extends PluginSettingTab {
  constructor(app, plugin) {
    super(app, plugin);
    this.plugin = plugin;
  }

  display() {
    const { containerEl } = this;
    containerEl.empty();
    containerEl.addClass("obi-settings");

    containerEl.createEl("h2", { text: "Obsidian Bookmark Intelligence" });
    containerEl.createEl("p", {
      text:
        "This plugin is a control panel for the separately installed local bookmark agent. Summaries require Ollama and local hardware capable of running the selected model."
    });

    new Setting(containerEl)
      .setName("Local agent download")
      .setDesc("Open the GitHub Releases page for installer scripts and native host assets.")
      .addButton((button) =>
        button.setButtonText("Open").onClick(() => this.plugin.openExternal(this.plugin.settings.agentReleaseUrl))
      );

    new Setting(containerEl)
      .setName("Browser extension download")
      .setDesc("Open the same Release page for Chrome and Firefox extension packages.")
      .addButton((button) =>
        button.setButtonText("Open").onClick(() => this.plugin.openExternal(this.plugin.settings.browserExtensionUrl))
      );

    new Setting(containerEl)
      .setName("Copy install command")
      .setDesc("Copies the unified local agent install command using this vault path.")
      .addButton((button) => button.setButtonText("Copy").onClick(() => this.plugin.copyInstallCommand()));

    new Setting(containerEl)
      .setName("Agent release URL")
      .setDesc("Used by the Open buttons above.")
      .addText((text) =>
        text
          .setPlaceholder(DEFAULT_SETTINGS.agentReleaseUrl)
          .setValue(this.plugin.settings.agentReleaseUrl)
          .onChange(async (value) => {
            this.plugin.settings.agentReleaseUrl = value.trim() || DEFAULT_SETTINGS.agentReleaseUrl;
            await this.plugin.saveSettings();
          })
      );

    new Setting(containerEl)
      .setName("Browser extension URL")
      .setDesc("Normally this is the same GitHub Release page.")
      .addText((text) =>
        text
          .setPlaceholder(DEFAULT_SETTINGS.browserExtensionUrl)
          .setValue(this.plugin.settings.browserExtensionUrl)
          .onChange(async (value) => {
            this.plugin.settings.browserExtensionUrl = value.trim() || DEFAULT_SETTINGS.browserExtensionUrl;
            await this.plugin.saveSettings();
          })
      );

    new Setting(containerEl)
      .setName("Activity note path")
      .setDesc("Path inside the vault.")
      .addText((text) =>
        text
          .setPlaceholder(DEFAULT_SETTINGS.activityNotePath)
          .setValue(this.plugin.settings.activityNotePath)
          .onChange(async (value) => {
            this.plugin.settings.activityNotePath = value.trim() || DEFAULT_SETTINGS.activityNotePath;
            await this.plugin.saveSettings();
          })
      );

    new Setting(containerEl)
      .setName("Index note path")
      .setDesc("Path inside the vault.")
      .addText((text) =>
        text
          .setPlaceholder(DEFAULT_SETTINGS.indexNotePath)
          .setValue(this.plugin.settings.indexNotePath)
          .onChange(async (value) => {
            this.plugin.settings.indexNotePath = value.trim() || DEFAULT_SETTINGS.indexNotePath;
            await this.plugin.saveSettings();
          })
      );

    new Setting(containerEl)
      .setName("Show hardware warning on startup")
      .setDesc("Reminds users that local summaries require Ollama and suitable CPU/RAM/GPU.")
      .addToggle((toggle) =>
        toggle.setValue(this.plugin.settings.showHardwareWarning).onChange(async (value) => {
          this.plugin.settings.showHardwareWarning = value;
          await this.plugin.saveSettings();
        })
      );

    new Setting(containerEl)
      .setName("Open activity note")
      .setDesc("Open the agent activity log note if it exists.")
      .addButton((button) => button.setButtonText("Open").onClick(() => this.plugin.openActivityNote()));

    new Setting(containerEl)
      .setName("Open bookmark index")
      .setDesc("Open the generated bookmark index if it exists.")
      .addButton((button) => button.setButtonText("Open").onClick(() => this.plugin.openIndexNote()));
  }
}
