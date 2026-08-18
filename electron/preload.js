const { contextBridge, ipcRenderer } = require("electron");

const PORT = process.env.MYKNOWLEDGE_PORT || "18765";

let deviceId = "";
try {
  deviceId = require("./device-id").computeDeviceId();
} catch {
  deviceId = "";
}

const pkg = require("./package.json");

contextBridge.exposeInMainWorld("myknowledge", {
  apiBase: `http://127.0.0.1:${PORT}`,
  deviceId,
  appVersion: pkg.version || "0.0.0",
  getAppInfo() {
    return ipcRenderer.invoke("get-app-info");
  },
  ensureFileViewer() {
    return ipcRenderer.invoke("ensure-file-viewer");
  },
  openAssetViewer(path, filename, page) {
    return ipcRenderer.invoke("open-asset-viewer", { path, filename, page: page || 0 });
  },
  pickDirectory() {
    return ipcRenderer.invoke("pick-directory");
  },
  openExternal(url) {
    return ipcRenderer.invoke("open-external", url);
  },
});
