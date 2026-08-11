const api = globalThis.browser || globalThis.chrome;
const isPromiseApi = Boolean(globalThis.browser);

const statusText = document.getElementById("status");
const agentDownloadUrl = document.getElementById("agent-download-url");
const notificationsEnabled = document.getElementById("notifications-enabled");
const notifyQueued = document.getElementById("notify-queued");
const notifySucceeded = document.getElementById("notify-succeeded");
const notifyFailed = document.getElementById("notify-failed");
const activityPollingEnabled = document.getElementById("activity-polling-enabled");
const pollInterval = document.getElementById("poll-interval");
const vaultPath = document.getElementById("vault-path");
const ollamaModel = document.getElementById("ollama-model");
const profileId = document.getElementById("profile-id");
const openDownloadButton = document.getElementById("open-download-button");
const testNativeButton = document.getElementById("test-native-button");
const saveButton = document.getElementById("save-button");
const pollButton = document.getElementById("poll-button");

function sendMessage(message) {
  if (isPromiseApi) {
    return api.runtime.sendMessage(message);
  }

  return new Promise((resolve, reject) => {
    api.runtime.sendMessage(message, (response) => {
      const lastError = api.runtime.lastError;
      if (lastError) {
        reject(new Error(lastError.message));
        return;
      }
      resolve(response);
    });
  });
}

function renderSettings(payload) {
  const settings = payload.settings || {};
  agentDownloadUrl.value = settings.agentDownloadUrl || payload.defaultAgentDownloadUrl || "";
  notificationsEnabled.checked = Boolean(settings.notificationsEnabled);
  notifyQueued.checked = Boolean(settings.notifyQueued);
  notifySucceeded.checked = Boolean(settings.notifySucceeded);
  notifyFailed.checked = Boolean(settings.notifyFailed);
  activityPollingEnabled.checked = Boolean(settings.activityPollingEnabled);
  pollInterval.value = String(settings.pollIntervalMinutes || 1);
  profileId.textContent = payload.profileId || "Unknown";
}

function collectSettings() {
  return {
    agentDownloadUrl: agentDownloadUrl.value.trim(),
    notificationsEnabled: notificationsEnabled.checked,
    notifyQueued: notifyQueued.checked,
    notifySucceeded: notifySucceeded.checked,
    notifyFailed: notifyFailed.checked,
    activityPollingEnabled: activityPollingEnabled.checked,
    pollIntervalMinutes: Math.max(1, Math.min(60, Number(pollInterval.value) || 1))
  };
}

async function loadSettings() {
  statusText.textContent = "Loading settings...";
  const payload = await sendMessage({ type: "get-extension-settings" });
  if (!payload || !payload.ok) {
    throw new Error((payload && payload.error) || "Could not read settings");
  }
  renderSettings(payload);
  statusText.textContent = "Settings loaded.";
}

async function saveSettings() {
  saveButton.disabled = true;
  statusText.textContent = "Saving settings...";
  try {
    const response = await sendMessage({
      type: "save-extension-settings",
      settings: collectSettings()
    });
    if (!response || !response.ok) {
      throw new Error((response && response.error) || "Could not save settings");
    }
    statusText.textContent = "Settings saved.";
  } finally {
    saveButton.disabled = false;
  }
}

async function testNativeHost() {
  testNativeButton.disabled = true;
  statusText.textContent = "Testing native host...";
  try {
    const status = await sendMessage({ type: "ping-native-host" });
    if (!status || !status.ok) {
      throw new Error((status && status.error) || "Native host is not connected");
    }
    const response = status.response || {};
    vaultPath.textContent = response.vault_path || "Unknown";
    ollamaModel.textContent = response.ollama_model || "Unknown";
    statusText.textContent = "Native host connected.";
  } finally {
    testNativeButton.disabled = false;
  }
}

openDownloadButton.addEventListener("click", () => {
  const url = agentDownloadUrl.value.trim() || "https://github.com/EggR0/obsidian-bookmark-intelligence/releases/latest";
  window.open(url, "_blank", "noopener,noreferrer");
});

testNativeButton.addEventListener("click", () => {
  testNativeHost().catch((error) => {
    statusText.textContent = String(error && error.message ? error.message : error);
  });
});

saveButton.addEventListener("click", () => {
  saveSettings().catch((error) => {
    statusText.textContent = String(error && error.message ? error.message : error);
  });
});

pollButton.addEventListener("click", () => {
  sendMessage({ type: "poll-recent-activity" })
    .then(() => {
      statusText.textContent = "Activity checked.";
    })
    .catch((error) => {
      statusText.textContent = String(error && error.message ? error.message : error);
    });
});

loadSettings()
  .then(testNativeHost)
  .catch((error) => {
    statusText.textContent = String(error && error.message ? error.message : error);
  });
