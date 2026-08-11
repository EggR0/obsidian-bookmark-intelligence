const api = globalThis.browser || globalThis.chrome;
const isPromiseApi = Boolean(globalThis.browser);

const dot = document.getElementById("status-dot");
const hostStatus = document.getElementById("host-status");
const vaultPath = document.getElementById("vault-path");
const lastCheck = document.getElementById("last-check");
const detail = document.getElementById("detail");
const testButton = document.getElementById("test-button");

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
  detail.textContent = status.ok
    ? `Queue: ${response.database_path || "unknown"}`
    : status.error || response.error || "Connection failed";
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
