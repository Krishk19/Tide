const { app, BrowserWindow, globalShortcut } = require('electron');
const path = require('path');

let mainWindow;

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 800,
    fullscreen: true,
    kiosk: true,
    frame: false,
    autoHideMenuBar: true,
    alwaysOnTop: true,
    webPreferences: {
      devTools: false, // Critical Chromium embed-level block
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js'),
    },
  });

  mainWindow.loadFile(path.join(__dirname, 'index.html'));

  // Disable right-click context menu (prevents Inspect Element)
  mainWindow.webContents.on('context-menu', (e) => {
    e.preventDefault();
  });

  // Block F12, Ctrl+Shift+I, Ctrl+Shift+J, Ctrl+Shift+C, Ctrl+R, etc.
  mainWindow.webContents.on('before-input-event', (event, input) => {
    const isDevToolsKey =
      input.key === 'F12' ||
      (input.control && input.shift && ['I', 'i', 'J', 'j', 'C', 'c'].includes(input.key));
    const isReloadKey =
      (input.control && ['r', 'R'].includes(input.key)) || input.key === 'F5';

    if (isDevToolsKey || isReloadKey) {
      event.preventDefault();
    }
  });

  // Re-force fullscreen if leave-full-screen fires (detection & mitigation)
  mainWindow.on('leave-full-screen', () => {
    mainWindow.webContents.send('telemetry-event', {
      type: 'fullscreen-exit',
      ts: new Date().toISOString(),
    });
    setTimeout(() => {
      if (mainWindow && !mainWindow.isDestroyed()) {
        mainWindow.setFullScreen(true);
      }
    }, 100);
  });

  // Window blur (focus lost)
  mainWindow.on('blur', () => {
    mainWindow.webContents.send('telemetry-event', {
      type: 'focus-lost',
      ts: new Date().toISOString(),
    });
  });

  // Window focus (focus regained)
  mainWindow.on('focus', () => {
    mainWindow.webContents.send('telemetry-event', {
      type: 'focus-regained',
      ts: new Date().toISOString(),
    });
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

app.whenReady().then(() => {
  createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});
