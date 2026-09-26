const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  onTelemetryEvent: (callback) => ipcRenderer.on('telemetry-event', (_event, value) => callback(value)),
});
