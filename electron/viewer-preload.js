const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("yizhiViewer", {
  openWithSystem(relPath, filename) {
    return ipcRenderer.invoke("open-asset-system", { path: relPath, filename });
  },
});
