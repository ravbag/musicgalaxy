// Electron entry point: opens the MusicGalaxy page in a desktop window.
const { app, BrowserWindow } = require('electron');
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

app.whenReady().then(() => {
    createWindow();
    app.on('activate', () => {
        if (BrowserWindow.getAllWindows().length === 0) createWindow();
    });
});

app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') app.quit();
});
