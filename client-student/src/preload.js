const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  isElectron: true,
  onKioskEvent: (callback) => {
    ipcRenderer.on('kiosk-event', (_event, value) => callback(value));
  },
  exitApp: () => ipcRenderer.invoke('app-exit'),
  isFullScreen: () => ipcRenderer.invoke('is-fullscreen'),
  setFullScreen: () => ipcRenderer.invoke('set-fullscreen'),
  discoverServer: () => ipcRenderer.invoke('discover-server'),
});
