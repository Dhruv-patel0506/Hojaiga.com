"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.MenuBarPanelManager = void 0;
exports.registerDragHandlers = registerDragHandlers;
const electron_1 = require("electron");
const fs = __importStar(require("fs"));
const path = __importStar(require("path"));
const getPanelStateFile = () => path.join(electron_1.app.getPath('userData'), 'clicky-panel-state.json');
// Static drag handlers to avoid multiple registrations
let dragInstance = null;
function registerDragHandlers() {
    electron_1.ipcMain.on('start-drag', () => {
        if (!dragInstance?.panelWindow)
            return;
        dragInstance.isDragging = true;
        const [x, y] = dragInstance.panelWindow.getPosition();
        dragInstance.dragOffset = { x, y };
    });
    electron_1.ipcMain.on('end-drag', () => {
        if (dragInstance)
            dragInstance.isDragging = false;
    });
}
class MenuBarPanelManager {
    panelWindow = null;
    tray = null;
    isDragging = false;
    dragOffset = { x: 0, y: 0 };
    loadPanelState() {
        try {
            const panelStateFile = getPanelStateFile();
            if (fs.existsSync(panelStateFile)) {
                return JSON.parse(fs.readFileSync(panelStateFile, 'utf8'));
            }
        }
        catch { }
        return { x: 0, y: 0, isDrawerOpen: false };
    }
    savePanelState(state) {
        try {
            const panelStateFile = getPanelStateFile();
            const current = this.loadPanelState();
            const updated = { ...current, ...state };
            fs.writeFileSync(panelStateFile, JSON.stringify(updated), 'utf8');
        }
        catch { }
    }
    createPanelAndTray(onDemoCommand) {
        dragInstance = this; // Set static instance for IPC handlers
        const primary = electron_1.screen.getPrimaryDisplay();
        const savedState = this.loadPanelState();
        const defaultX = primary.workArea.x + primary.workArea.width - 350;
        const defaultY = primary.workArea.y + primary.workArea.height - 350;
        this.panelWindow = new electron_1.BrowserWindow({
            width: 330,
            height: savedState.isDrawerOpen ? 530 : 330,
            x: savedState.x || defaultX,
            y: savedState.y || defaultY,
            frame: false,
            transparent: true,
            alwaysOnTop: true,
            resizable: false,
            skipTaskbar: false,
            webPreferences: {
                nodeIntegration: true,
                contextIsolation: false,
            },
        });
        this.panelWindow.setContentProtection(false);
        this.panelWindow.loadFile(path.join(__dirname, '..', '..', 'public', 'panel.html'));
        // Implement draggable functionality
        this.panelWindow.on('move', () => {
            if (!this.isDragging)
                return;
            const [x, y] = this.panelWindow.getPosition();
            this.savePanelState({ x, y });
        });
        // Enable dragging from header
        this.panelWindow.webContents.on('did-finish-load', () => {
            this.panelWindow?.webContents.executeJavaScript(`
        document.querySelector('.header').style.cursor = 'move';
        document.querySelector('.header').addEventListener('mousedown', (e) => {
          if (e.target.tagName === 'BUTTON' || e.target.closest('button')) return;
          require('electron').ipcRenderer.send('start-drag');
        });
      `);
        });
        const icon = electron_1.nativeImage.createEmpty();
        this.tray = new electron_1.Tray(icon);
        this.tray.setToolTip('Clicky AI Companion');
        this.tray.setContextMenu(electron_1.Menu.buildFromTemplate([
            {
                label: 'Toggle Clicky Panel',
                click: () => {
                    if (this.panelWindow?.isVisible())
                        this.panelWindow.hide();
                    else
                        this.panelWindow?.show();
                },
            },
            {
                label: 'Plot log(x) and sin(x) Graph',
                click: () => onDemoCommand('draw a graph of logx and sine curve'),
            },
            {
                label: 'Draw Parallelogram + Circle',
                click: () => onDemoCommand('draw a parallelogram and a circle in it'),
            },
            {
                label: 'Draw Circle + Decagon',
                click: () => onDemoCommand('draw a circle and a decagon in it'),
            },
            { type: 'separator' },
            { label: 'Quit Clicky', click: () => electron_1.app.quit() },
        ]));
    }
    toggleDrawer() {
        if (!this.panelWindow)
            return;
        const [x, y] = this.panelWindow.getPosition();
        const currentHeight = this.panelWindow.getBounds().height;
        const targetHeight = currentHeight > 400 ? 330 : 530;
        this.panelWindow.setBounds({ x, y, width: 330, height: targetHeight });
        this.savePanelState({ isDrawerOpen: targetHeight > 400 });
    }
}
exports.MenuBarPanelManager = MenuBarPanelManager;
