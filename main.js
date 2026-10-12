// Electron entry point: opens the MusicGalaxy page in a desktop window.
const { app, BrowserWindow, session } = require('electron');
const path = require('path');

function createWindow() {
    const win = new BrowserWindow({
        width: 1400,
        height: 900,
        backgroundColor: '#020202',
        webPreferences: {
            // The page only needs web APIs; keep Node out of the renderer
            nodeIntegration: false,
            contextIsolation: true,
        },
    });
    win.loadFile(path.join(__dirname, 'index_fixed_working_v9.html'));
}

const USER_AGENT = 'MusicGalaxy/0.1 (https://github.com/ravbag/musicgalaxy)';

app.whenReady().then(() => {
    // Radio Browser asks clients to identify themselves; browsers can't set User-Agent from page code
    session.defaultSession.webRequest.onBeforeSendHeaders(
        { urls: ['https://*.radio-browser.info/*'] },
        (details, callback) => {
            details.requestHeaders['User-Agent'] = USER_AGENT;
            callback({ requestHeaders: details.requestHeaders });
        });
    createWindow();
    app.on('activate', () => {
        if (BrowserWindow.getAllWindows().length === 0) createWindow();
    });
});

app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') app.quit();
});
