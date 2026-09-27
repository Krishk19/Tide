const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  isElectron: true,
  onKioskEvent: (callback) => {
    ipcRenderer.on('kiosk-event', (_event, value) => callback(value));
  },
  exitApp: () => ipcRenderer.invoke('app-exit'),
});
