const { app, BrowserWindow, ipcMain, globalShortcut } = require('electron');
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
    backgroundColor: '#09090b',
    webPreferences: {
      devTools: false, // Core Chromium embed block
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js'),
    },
  });

  mainWindow.loadFile(path.join(__dirname, 'index.html'));

  // Disable right-click context menu
  mainWindow.webContents.on('context-menu', (e) => {
    e.preventDefault();
  });

  // Block new window creation
  mainWindow.webContents.setWindowOpenHandler(() => {
    return { action: 'deny' };
  });

  // Shortcut blocking (F12, Ctrl+Shift+I/J/C, F5, Ctrl+R)
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

  // Telemetry: Fullscreen Exit Attempt
  mainWindow.on('leave-full-screen', () => {
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send('kiosk-event', {
        type: 'fullscreen-exit',
        ts: new Date().toISOString(),
      });
      // Re-force fullscreen after detection
      setTimeout(() => {
        if (mainWindow && !mainWindow.isDestroyed()) {
          mainWindow.setFullScreen(true);
        }
      }, 100);
    }
  });

  // Telemetry: Window Blur (Focus Lost / Alt-Tab)
  mainWindow.on('blur', () => {
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send('kiosk-event', {
        type: 'focus-lost',
        ts: new Date().toISOString(),
      });
    }
  });

  // Telemetry: Window Focus (Focus Regained)
  mainWindow.on('focus', () => {
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send('kiosk-event', {
        type: 'focus-regained',
        ts: new Date().toISOString(),
      });
    }
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

// Emergency Developer / Teacher Exit Shortcut: Ctrl+Alt+Shift+Q
app.whenReady().then(() => {
  createWindow();

  globalShortcut.register('CommandOrControl+Alt+Shift+Q', () => {
    if (mainWindow) {
      mainWindow.setKiosk(false);
      mainWindow.setFullScreen(false);
      app.quit();
    }
  });

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('will-quit', () => {
  globalShortcut.unregisterAll();
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

// IPC Handler to exit when test is submitted
ipcMain.handle('app-exit', () => {
  app.quit();
});

// IPC Handler to check fullscreen status
ipcMain.handle('is-fullscreen', () => {
  if (!mainWindow || mainWindow.isDestroyed()) return false;
  return mainWindow.isFullScreen() || mainWindow.isKiosk();
});

// IPC Handler to enforce fullscreen
ipcMain.handle('set-fullscreen', () => {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.setFullScreen(true);
    mainWindow.setKiosk(true);
    return true;
  }
  return false;
});

