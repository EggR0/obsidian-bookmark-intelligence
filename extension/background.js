const EXTENSION_NAME = "obsidian-bookmark-intelligence";
const HOST_NAME = "obsidian_bookmark_agent";
const api = globalThis.browser || globalThis.chrome;
const isPromiseApi = Boolean(globalThis.browser);
const storageArea = api.storage && api.storage.local;

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
      extension: EXTENSION_NAME
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
    sendNativeRequest(message)
      .then((response) => {
        setLastStatus({
          ok: Boolean(response && response.ok),
          checkedAt: nowIso(),
          response: response || null
        });
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

  sendNativeRequest({
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
