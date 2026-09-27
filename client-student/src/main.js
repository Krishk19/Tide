const { app, BrowserWindow, ipcMain, globalShortcut } = require('electron');
const path = require('path');
const net = require('net');
const dns = require('dns');

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
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.setKiosk(false);
    mainWindow.setFullScreen(false);
    mainWindow.destroy();
  }
  app.exit(0);
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

// IPC Handler: UDP LAN Auto-Discovery
const dgram = require('dgram');
ipcMain.handle('discover-server', () => {
  return new Promise((resolve) => {
    try {
      const client = dgram.createSocket('udp4');
      let resolved = false;

      client.on('error', () => {
        try { client.close(); } catch (e) {}
        if (!resolved) { resolved = true; resolve(null); }
      });

      client.on('message', (msg) => {
        try {
          const payload = JSON.parse(msg.toString());
          if (payload.type === 'TIDE_SERVER_ANNOUNCE' && !resolved) {
            resolved = true;
            try { client.close(); } catch (e) {}
            resolve(payload);
          }
        } catch (e) {}
      });

      client.bind(() => {
        try {
          client.setBroadcast(true);
          const packet = Buffer.from('TIDE_DISCOVER_SERVER');
          client.send(packet, 0, packet.length, 8001, '255.255.255.255', (err) => {
            if (err && !resolved) {
              try { client.close(); } catch (e) {}
              resolved = true;
              resolve(null);
            }
          });
        } catch (e) {
          if (!resolved) { resolved = true; resolve(null); }
        }
      });

      setTimeout(() => {
        if (!resolved) {
          resolved = true;
          try { client.close(); } catch (e) {}
          resolve(null);
        }
      }, 2500);
    } catch (err) {
      resolve(null);
    }
  });
});

// Canary Probe for External Internet Connectivity
function probeExternalInternet() {
  return new Promise((resolve) => {
    const socket = new net.Socket();
    let hasResolved = false;

    socket.setTimeout(1200);

    socket.connect(53, '8.8.8.8', () => {
      if (!hasResolved) {
        hasResolved = true;
        try { socket.destroy(); } catch (e) {}
        resolve(true); // Public internet reachable
      }
    });

    socket.on('error', () => {
      if (!hasResolved) {
        hasResolved = true;
        try { socket.destroy(); } catch (e) {}
        dns.lookup('dns.google', (err) => {
          resolve(!err);
        });
      }
    });

    socket.on('timeout', () => {
      if (!hasResolved) {
        hasResolved = true;
        try { socket.destroy(); } catch (e) {}
        resolve(false);
      }
    });
  });
}

ipcMain.handle('check-internet', async () => {
  try {
    return await probeExternalInternet();
  } catch (e) {
    return false;
  }
});



