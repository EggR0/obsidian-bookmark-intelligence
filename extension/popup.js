const api = globalThis.browser || globalThis.chrome;
const isPromiseApi = Boolean(globalThis.browser);

const dot = document.getElementById("status-dot");
const hostStatus = document.getElementById("host-status");
const vaultPath = document.getElementById("vault-path");
const lastCheck = document.getElementById("last-check");
const detail = document.getElementById("detail");
const testButton = document.getElementById("test-button");
const downloadAgentButton = document.getElementById("download-agent-button");
const settingsButton = document.getElementById("settings-button");

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

function getStorage(keys) {
  if (isPromiseApi) {
    return api.storage.local.get(keys);
  }

  return new Promise((resolve) => {
    api.storage.local.get(keys, resolve);
  });
}

function render(status) {
  dot.className = "";
  if (!status) {
    hostStatus.textContent = "Not checked";
    vaultPath.textContent = "Unknown";
    lastCheck.textContent = "-";
    detail.textContent = "";
    return;
  }

  dot.classList.add(status.ok ? "ok" : "error");
  hostStatus.textContent = status.ok ? "Connected" : "Not connected";
  lastCheck.textContent = status.checkedAt || "-";

  const response = status.response || {};
  vaultPath.textContent = response.vault_path || "Unknown";
  if (!status.ok) {
    detail.textContent = status.error || response.error || "Connection failed";
    return;
  }

  detail.textContent = `Queue: ${response.database_path || "unknown"}`;
}

async function testConnection() {
  testButton.disabled = true;
  hostStatus.textContent = "Checking...";
  detail.textContent = "";
  try {
    const status = await sendMessage({ type: "ping-native-host" });
    render(status);
  } catch (error) {
    render({
      ok: false,
      checkedAt: new Date().toISOString(),
      error: String(error && error.message ? error.message : error)
    });
  } finally {
    testButton.disabled = false;
  }
}

testButton.addEventListener("click", testConnection);

async function openAgentDownload() {
  const data = await getStorage(["settings"]);
  const settings = data.settings || {};
  const url = settings.agentDownloadUrl || "https://github.com/EggR0/obsidian-bookmark-intelligence/releases/latest";
  window.open(url, "_blank", "noopener,noreferrer");
}

downloadAgentButton.addEventListener("click", () => {
  openAgentDownload().catch((error) => {
    detail.textContent = String(error && error.message ? error.message : error);
  });
});

settingsButton.addEventListener("click", () => {
  if (api.runtime.openOptionsPage) {
    api.runtime.openOptionsPage();
  } else {
    window.open(api.runtime.getURL("options.html"), "_blank", "noopener,noreferrer");
  }
});

getStorage(["lastStatus"])
  .then((data) => render(data.lastStatus))
  .then(testConnection)
  .catch((error) => {
    render({
      ok: false,
      checkedAt: new Date().toISOString(),
      error: String(error && error.message ? error.message : error)
    });
  });
