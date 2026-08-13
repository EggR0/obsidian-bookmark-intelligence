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
const summaryPrompt = document.getElementById("summary-prompt");
const vaultPath = document.getElementById("vault-path");
const aiProvider = document.getElementById("ai-provider");
const aiModel = document.getElementById("ai-model");
const aiProviderSelect = document.getElementById("ai-provider-select");
const aiModelInput = document.getElementById("ai-model-input");
const aiBaseUrlInput = document.getElementById("ai-base-url-input");
const aiApiKeyEnvInput = document.getElementById("ai-api-key-env-input");
const entitlementEndpointInput = document.getElementById("entitlement-endpoint-input");
const accountIdInput = document.getElementById("account-id-input");
const accessTokenEnvInput = document.getElementById("access-token-env-input");
const plan = document.getElementById("plan");
const supportSection = document.getElementById("support-section");
const supportLinks = document.getElementById("support-links");
const profileId = document.getElementById("profile-id");
const promptPath = document.getElementById("prompt-path");
const openDownloadButton = document.getElementById("open-download-button");
const testNativeButton = document.getElementById("test-native-button");
const saveButton = document.getElementById("save-button");
const pollButton = document.getElementById("poll-button");
const savePromptButton = document.getElementById("save-prompt-button");
const resetPromptButton = document.getElementById("reset-prompt-button");
const saveAiButton = document.getElementById("save-ai-button");
const saveEntitlementButton = document.getElementById("save-entitlement-button");
const purchaseButton = document.getElementById("purchase-button");
const previewExistingButton = document.getElementById("preview-existing-button");
const importExistingButton = document.getElementById("import-existing-button");

let defaultSummaryPrompt = "";

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
  const billingUrl = String(payload.billing_url || "").trim();
  const billingEnabled = /^https?:\/\//i.test(billingUrl);
  purchaseButton.disabled = !billingEnabled;
  purchaseButton.dataset.billingUrl = billingUrl;
  saveEntitlementButton.disabled = !billingEnabled;
  importExistingButton.disabled = !billingEnabled;
  for (const option of aiProviderSelect.options) {
    option.disabled = option.value !== "ollama";
  }
}

function renderSupportLinks(links) {
  supportLinks.replaceChildren();
  const labels = {
    github: "GitHub Sponsors",
    polar: "Polar",
    ko_fi: "Ko-fi",
    buy_me_a_coffee: "Buy Me a Coffee",
    patreon: "Patreon",
    paypal: "PayPal",
    toss: "Toss",
    custom: "Support"
  };
  Object.entries(links || {}).forEach(([key, value]) => {
    if (!/^https?:\/\//i.test(value)) return;
    const link = document.createElement("a");
    link.href = value;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = labels[key] || key;
    link.className = "button secondary";
    supportLinks.append(link);
  });
  supportSection.hidden = supportLinks.childElementCount === 0;
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
    aiProvider.textContent = response.provider || "Unknown";
    aiModel.textContent = response.model || "Unknown";
    plan.textContent = response.plan || "Free";
    statusText.textContent = "Native host connected.";
  } finally {
    testNativeButton.disabled = false;
  }
}

async function loadAgentSettings() {
  const response = await sendMessage({ type: "get-agent-settings" });
  if (!response || !response.ok) {
    throw new Error((response && response.error) || "Could not load agent settings");
  }
  summaryPrompt.value = response.summary_prompt || "";
  defaultSummaryPrompt = response.default_summary_prompt || response.summary_prompt || "";
  promptPath.textContent = response.summary_prompt_path || "Unknown";
  vaultPath.textContent = response.vault_path || vaultPath.textContent;
  aiProvider.textContent = response.provider || aiProvider.textContent;
  aiModel.textContent = response.model || aiModel.textContent;
  aiProviderSelect.value = response.provider || aiProviderSelect.value;
  aiModelInput.value = response.model || "";
  aiBaseUrlInput.value = response.base_url || "";
  aiApiKeyEnvInput.value = response.api_key_env || "";
  entitlementEndpointInput.value = response.entitlement_endpoint || "";
  accountIdInput.value = response.account_id || "";
  accessTokenEnvInput.value = response.access_token_env || "";
  plan.textContent = response.plan || plan.textContent;
  renderSupportLinks(response.support_links);
}

async function saveSummaryPrompt() {
  savePromptButton.disabled = true;
  statusText.textContent = "Saving summary prompt...";
  try {
    const response = await sendMessage({
      type: "save-agent-settings",
      summaryPrompt: summaryPrompt.value
    });
    if (!response || !response.ok) {
      throw new Error((response && response.error) || "Could not save summary prompt");
    }
    promptPath.textContent = response.summary_prompt_path || promptPath.textContent;
    statusText.textContent = "Summary prompt saved.";
  } finally {
    savePromptButton.disabled = false;
  }
}

async function saveAiSettings() {
  saveAiButton.disabled = true;
  statusText.textContent = "Saving AI connection...";
  try {
    if (aiProviderSelect.value !== "ollama") {
      throw new Error("External AI API connections are not implemented yet. Use local Ollama.");
    }
    const response = await sendMessage({
      type: "save-agent-settings",
      provider: aiProviderSelect.value,
      model: aiModelInput.value.trim(),
      baseUrl: aiBaseUrlInput.value.trim(),
      apiKeyEnv: aiApiKeyEnvInput.value.trim()
    });
    if (!response || !response.ok) {
      throw new Error((response && response.error) || "Could not save AI connection");
    }
    aiProvider.textContent = aiProviderSelect.value;
    aiModel.textContent = aiModelInput.value.trim();
    statusText.textContent = "AI connection saved.";
  } finally {
    saveAiButton.disabled = false;
  }
}

async function saveEntitlementSettings() {
  saveEntitlementButton.disabled = true;
  statusText.textContent = "Saving Pro connection...";
  try {
    const response = await sendMessage({
      type: "save-agent-settings",
      entitlementEndpoint: entitlementEndpointInput.value.trim(),
      accountId: accountIdInput.value.trim(),
      accessTokenEnv: accessTokenEnvInput.value.trim()
    });
    if (!response || !response.ok) {
      throw new Error((response && response.error) || "Could not save Pro connection");
    }
    statusText.textContent = "Pro connection saved.";
  } finally {
    saveEntitlementButton.disabled = false;
  }
}

openDownloadButton.addEventListener("click", () => {
  sendMessage({ type: "download-agent" })
    .then((response) => {
      if (!response || !response.ok) {
        throw new Error((response && response.error) || "Could not start local agent download");
      }
      statusText.textContent = "Local agent package download started.";
    })
    .catch((error) => {
      statusText.textContent = String(error && error.message ? error.message : error);
    });
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

savePromptButton.addEventListener("click", () => {
  saveSummaryPrompt().catch((error) => {
    statusText.textContent = String(error && error.message ? error.message : error);
  });
});

resetPromptButton.addEventListener("click", () => {
  summaryPrompt.value = defaultSummaryPrompt;
  statusText.textContent = "Default prompt restored in the editor. Save to apply.";
});

saveAiButton.addEventListener("click", () => {
  saveAiSettings().catch((error) => {
    statusText.textContent = String(error && error.message ? error.message : error);
  });
});

saveEntitlementButton.addEventListener("click", () => {
  saveEntitlementSettings().catch((error) => {
    statusText.textContent = String(error && error.message ? error.message : error);
  });
});

purchaseButton.addEventListener("click", () => {
  const billingUrl = purchaseButton.dataset.billingUrl;
  if (billingUrl) api.tabs.create({ url: billingUrl });
});

async function importExistingBookmarks(dryRun) {
  const button = dryRun ? previewExistingButton : importExistingButton;
  button.disabled = true;
  statusText.textContent = dryRun ? "Scanning existing bookmarks..." : "Queuing existing bookmarks...";
  try {
    const response = await sendMessage({ type: "import-existing-bookmarks", dryRun });
    if (!response || !response.ok) {
      throw new Error((response && response.error) || "Could not process existing bookmarks");
    }
    const count = response.selected ?? response.queued ?? response.count;
    statusText.textContent = dryRun
      ? `Preview complete${count === undefined ? "." : `: ${count} bookmark(s) selected.`}`
      : `Existing bookmarks queued${count === undefined ? "." : `: ${count} bookmark(s).`}`;
  } finally {
    button.disabled = false;
  }
}

previewExistingButton.addEventListener("click", () => {
  importExistingBookmarks(true).catch((error) => {
    statusText.textContent = String(error && error.message ? error.message : error);
  });
});

importExistingButton.addEventListener("click", () => {
  importExistingBookmarks(false).catch((error) => {
    statusText.textContent = String(error && error.message ? error.message : error);
  });
});

loadSettings()
  .then(loadAgentSettings)
  .then(testNativeHost)
  .catch((error) => {
    statusText.textContent = String(error && error.message ? error.message : error);
  });
