const EXTENSION_NAME = "obsidian-bookmark-intelligence";
const HOST_NAME = "obsidian_bookmark_agent";
const api = globalThis.browser || globalThis.chrome;
const isPromiseApi = Boolean(globalThis.browser);
const storageArea = api.storage && api.storage.local;
const ACTIVITY_ALARM = "bookmark-agent-activity-poll";
const DEFAULT_AGENT_DOWNLOAD_URL = "https://github.com/EggR0/obsidian-bookmark-intelligence/releases/latest";
const DEFAULT_SETTINGS = {
  agentDownloadUrl: DEFAULT_AGENT_DOWNLOAD_URL,
  notificationsEnabled: true,
  notifyQueued: true,
  notifySucceeded: true,
  notifyFailed: true,
  activityPollingEnabled: true,
  pollIntervalMinutes: 1
};

function nowIso() {
  return new Date().toISOString();
}

function detectBrowser() {
  const userAgent = navigator.userAgent.toLowerCase();
  if (userAgent.includes("firefox")) return "firefox";
  if (userAgent.includes("edg/")) return "edge";
  if (userAgent.includes("chrome")) return "chrome";
  return "unknown";
}

function randomId() {
  if (globalThis.crypto && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return `profile-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function getStorage(keys) {
  if (!storageArea) return Promise.resolve({});
  if (isPromiseApi) {
    return storageArea.get(keys);
  }

  return new Promise((resolve) => {
    storageArea.get(keys, resolve);
  });
}

function setStorage(values) {
  if (!storageArea) return Promise.resolve();
  if (isPromiseApi) {
    return storageArea.set(values);
  }

  return new Promise((resolve) => {
    storageArea.set(values, resolve);
  });
}

async function getProfileId() {
  const data = await getStorage(["profileId"]);
  if (data && data.profileId) {
    return data.profileId;
  }
  const profileId = randomId();
  await setStorage({ profileId });
  return profileId;
}

async function getSettings() {
  const data = await getStorage(["settings"]);
  return {
    ...DEFAULT_SETTINGS,
    ...((data && data.settings) || {})
  };
}

async function saveSettings(settings) {
  await setStorage({
    settings: {
      ...DEFAULT_SETTINGS,
      ...(settings || {})
    }
  });
  await configureActivityAlarm();
}

function createNotification(title, message) {
  if (!api.notifications) return Promise.resolve();
  return getSettings().then((settings) => {
    if (!settings.notificationsEnabled) return null;
    const notificationId = `obi-${Date.now()}-${Math.random().toString(16).slice(2)}`;
    const options = {
      type: "basic",
      iconUrl: api.runtime.getURL("icon128.png"),
      title,
      message
    };

    if (isPromiseApi) {
      return api.notifications.create(notificationId, options);
    }

    return new Promise((resolve) => {
      api.notifications.create(notificationId, options, resolve);
    });
  });
}

async function notifyQueued(response, eventType) {
  const settings = await getSettings();
  if (!settings.notifyQueued || eventType === "removed") return;
  if (!response || !response.ok || !response.resource_id) return;
  if (response.process_status && response.process_status !== "pending") return;
  await createNotification(
    "Bookmark queued",
    `Saved to queue for ${response.resource_type || "resource"} processing.`
  );
}

function activityNotification(entry) {
  const title = entry.title || entry.resource_title || "Bookmark Agent";
  if (entry.event_type === "processing_succeeded") {
    return {
      title: "Bookmark summary complete",
      message: `${title} was saved to Obsidian.`
    };
  }
  if (entry.event_type === "processing_failed") {
    return {
      title: "Bookmark processing failed",
      message: entry.error || entry.message || title
    };
  }
  return null;
}

async function configureActivityAlarm() {
  if (!api.alarms) return;
  const settings = await getSettings();
  if (api.alarms.clear) {
    if (isPromiseApi) {
      await api.alarms.clear(ACTIVITY_ALARM);
    } else {
      await new Promise((resolve) => api.alarms.clear(ACTIVITY_ALARM, resolve));
    }
  }
  if (!settings.activityPollingEnabled || !settings.notificationsEnabled) return;
  api.alarms.create(ACTIVITY_ALARM, {
    delayInMinutes: Math.max(1, Number(settings.pollIntervalMinutes) || 1),
    periodInMinutes: Math.max(1, Number(settings.pollIntervalMinutes) || 1)
  });
}

async function pollRecentActivity() {
  const settings = await getSettings();
  if (!settings.activityPollingEnabled || !settings.notificationsEnabled) return;

  const stored = await getStorage(["lastActivityTimestamp"]);
  const after = stored.lastActivityTimestamp;
  if (!after) {
    await setStorage({ lastActivityTimestamp: nowIso() });
    return;
  }

  let response;
  try {
    response = await sendNativeRequest(
      await withProfileId({
        schema_version: 1,
        command: "recent-activity",
        after,
        limit: 20,
        source: {
          browser: detectBrowser(),
          extension: EXTENSION_NAME
        },
        event: {
          type: "recent-activity",
          timestamp: nowIso()
        }
      })
    );
  } catch (error) {
    return;
  }

  const entries = response && Array.isArray(response.entries) ? response.entries : [];
  let latest = after;
  for (const entry of entries) {
    if (entry.timestamp && entry.timestamp > latest) latest = entry.timestamp;
    if (entry.event_type === "processing_succeeded" && !settings.notifySucceeded) continue;
    if (entry.event_type === "processing_failed" && !settings.notifyFailed) continue;
    const notification = activityNotification(entry);
    if (notification) {
      await createNotification(notification.title, notification.message);
    }
  }
  if (latest !== after) {
    await setStorage({ lastActivityTimestamp: latest });
  }
}

function compactBookmark(node) {
  if (!node) return {};
  return {
    id: node.id,
    parentId: node.parentId || null,
    index: Number.isInteger(node.index) ? node.index : null,
    title: node.title || "",
    url: node.url || null,
    dateAdded: node.dateAdded || null
  };
}

function eventEnvelope(type, bookmark, change = {}) {
  return {
    schema_version: 1,
    source: {
      browser: detectBrowser(),
      extension: EXTENSION_NAME,
      profile_id: null
    },
    event: {
      type,
      timestamp: nowIso()
    },
    bookmark: compactBookmark(bookmark),
    change
  };
}

function setLastStatus(status) {
  if (!storageArea) return;
  try {
    storageArea.set({ lastStatus: status });
  } catch (error) {
    console.warn("Could not store status:", error);
  }
}

function sendNativeRequest(message) {
  if (isPromiseApi) {
    return api.runtime.sendNativeMessage(HOST_NAME, message);
  }

  return new Promise((resolve, reject) => {
    api.runtime.sendNativeMessage(HOST_NAME, message, (response) => {
      const lastError = api.runtime.lastError;
      if (lastError) {
        reject(new Error(lastError.message));
        return;
      }
      resolve(response);
    });
  });
}

function sendNativeMessage(message) {
  try {
    withProfileId(message)
      .then(sendNativeRequest)
      .then((response) => {
        setLastStatus({
          ok: Boolean(response && response.ok),
          checkedAt: nowIso(),
          response: response || null
        });
        notifyQueued(response, message.event && message.event.type).catch(() => {});
      })
      .catch((error) => {
        console.warn("Native message failed:", error);
        setLastStatus({
          ok: false,
          checkedAt: nowIso(),
          error: String(error && error.message ? error.message : error)
        });
      });
  } catch (error) {
    console.warn("Native message failed:", error);
    setLastStatus({
      ok: false,
      checkedAt: nowIso(),
      error: String(error && error.message ? error.message : error)
    });
  }
}

async function withProfileId(message) {
  const profileId = await getProfileId();
  return {
    ...message,
    source: {
      ...(message.source || {}),
      profile_id: profileId
    }
  };
}

function getBookmark(id) {
  if (isPromiseApi) {
    return api.bookmarks.get(id).then((nodes) => (Array.isArray(nodes) ? nodes[0] : null));
  }

  return new Promise((resolve) => {
    api.bookmarks.get(id, (nodes) => {
      const lastError = api.runtime.lastError;
      if (lastError) {
        console.warn("Could not read bookmark:", lastError.message);
        resolve(null);
        return;
      }
      resolve(Array.isArray(nodes) ? nodes[0] : null);
    });
  });
}

api.bookmarks.onCreated.addListener((id, bookmark) => {
  sendNativeMessage(eventEnvelope("created", bookmark));
});

api.bookmarks.onChanged.addListener((id, changeInfo) => {
  getBookmark(id).then((bookmark) => {
    sendNativeMessage(eventEnvelope("changed", bookmark, changeInfo));
  });
});

api.bookmarks.onMoved.addListener((id, moveInfo) => {
  getBookmark(id).then((bookmark) => {
    sendNativeMessage(eventEnvelope("moved", bookmark, moveInfo));
  });
});

api.bookmarks.onRemoved.addListener((id, removeInfo) => {
  const removedNode = removeInfo && removeInfo.node ? removeInfo.node : { id };
  sendNativeMessage(eventEnvelope("removed", removedNode, removeInfo || {}));
});

api.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (!message || message.type !== "ping-native-host") {
    return false;
  }

  withProfileId({
    schema_version: 1,
    command: "ping",
    source: {
      browser: detectBrowser(),
      extension: EXTENSION_NAME
    },
    event: {
      type: "ping",
      timestamp: nowIso()
    }
  })
    .then(sendNativeRequest)
    .then((response) => {
      const status = {
        ok: Boolean(response && response.ok),
        checkedAt: nowIso(),
        response: response || null
      };
      setLastStatus(status);
      sendResponse(status);
    })
    .catch((error) => {
      const status = {
        ok: false,
        checkedAt: nowIso(),
        error: String(error && error.message ? error.message : error)
      };
      setLastStatus(status);
      sendResponse(status);
    });

  return true;
});

api.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (!message || message.type !== "import-bookmarks-index") {
    return false;
  }

  withProfileId({
    schema_version: 1,
    command: "import-bookmarks",
    mode: "index",
    dry_run: Boolean(message.dryRun),
    source: {
      browser: detectBrowser(),
      extension: EXTENSION_NAME
    },
    event: {
      type: "import-bookmarks",
      timestamp: nowIso()
    }
  })
    .then(sendNativeRequest)
    .then((response) => {
      const status = {
        ok: Boolean(response && response.ok),
        checkedAt: nowIso(),
        response: response || null
      };
      setLastStatus(status);
      sendResponse(status);
    })
    .catch((error) => {
      const status = {
        ok: false,
        checkedAt: nowIso(),
        error: String(error && error.message ? error.message : error)
      };
      setLastStatus(status);
      sendResponse(status);
    });

  return true;
});

api.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (!message || message.type !== "get-extension-settings") {
    return false;
  }

  Promise.all([getSettings(), getProfileId()])
    .then(([settings, profileId]) => {
      sendResponse({
        ok: true,
        settings,
        profileId,
        defaultAgentDownloadUrl: DEFAULT_AGENT_DOWNLOAD_URL
      });
    })
    .catch((error) => {
      sendResponse({
        ok: false,
        error: String(error && error.message ? error.message : error)
      });
    });
  return true;
});

api.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (!message || message.type !== "save-extension-settings") {
    return false;
  }

  saveSettings(message.settings)
    .then(() => sendResponse({ ok: true }))
    .catch((error) => {
      sendResponse({
        ok: false,
        error: String(error && error.message ? error.message : error)
      });
    });
  return true;
});

api.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (!message || message.type !== "poll-recent-activity") {
    return false;
  }

  pollRecentActivity()
    .then(() => sendResponse({ ok: true }))
    .catch((error) => {
      sendResponse({
        ok: false,
        error: String(error && error.message ? error.message : error)
      });
    });
  return true;
});

api.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (!message || message.type !== "get-agent-settings") {
    return false;
  }

  withProfileId({
    schema_version: 1,
    command: "get-agent-settings",
    source: {
      browser: detectBrowser(),
      extension: EXTENSION_NAME
    },
    event: {
      type: "get-agent-settings",
      timestamp: nowIso()
    }
  })
    .then(sendNativeRequest)
    .then((response) => sendResponse(response || { ok: false, error: "Empty native response" }))
    .catch((error) => {
      sendResponse({
        ok: false,
        error: String(error && error.message ? error.message : error)
      });
    });
  return true;
});

api.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (!message || message.type !== "save-agent-settings") {
    return false;
  }

  withProfileId({
    schema_version: 1,
    command: "save-agent-settings",
    summary_prompt: message.summaryPrompt || "",
    source: {
      browser: detectBrowser(),
      extension: EXTENSION_NAME
    },
    event: {
      type: "save-agent-settings",
      timestamp: nowIso()
    }
  })
    .then(sendNativeRequest)
    .then((response) => sendResponse(response || { ok: false, error: "Empty native response" }))
    .catch((error) => {
      sendResponse({
        ok: false,
        error: String(error && error.message ? error.message : error)
      });
    });
  return true;
});

if (api.alarms && api.alarms.onAlarm) {
  api.alarms.onAlarm.addListener((alarm) => {
    if (alarm && alarm.name === ACTIVITY_ALARM) {
      pollRecentActivity().catch(() => {});
    }
  });
}

if (api.runtime.onInstalled) {
  api.runtime.onInstalled.addListener(() => {
    configureActivityAlarm().catch(() => {});
  });
}

if (api.runtime.onStartup) {
  api.runtime.onStartup.addListener(() => {
    configureActivityAlarm().catch(() => {});
  });
}

configureActivityAlarm().catch(() => {});
