import { app, BrowserWindow, ipcMain, Menu, nativeImage, screen, Tray } from 'electron';
import * as fs from 'fs';
import * as path from 'path';

const getPanelStateFile = () => path.join(app.getPath('userData'), 'clicky-panel-state.json');

// Static drag handlers to avoid multiple registrations
let dragInstance: MenuBarPanelManager | null = null;

export function registerDragHandlers() {
  ipcMain.on('start-drag', () => {
    if (!dragInstance?.panelWindow) return;
    dragInstance.isDragging = true;
    const [x, y] = dragInstance.panelWindow.getPosition();
    dragInstance.dragOffset = { x, y };
  });

  ipcMain.on('end-drag', () => {
    if (dragInstance) dragInstance.isDragging = false;
  });
}

interface PanelState {
  x: number;
  y: number;
  isDrawerOpen: boolean;
}

export class MenuBarPanelManager {
  public panelWindow: BrowserWindow | null = null;
  public tray: Tray | null = null;
  public isDragging = false;
  public dragOffset = { x: 0, y: 0 };

  private loadPanelState(): PanelState {
    try {
      const panelStateFile = getPanelStateFile();
      if (fs.existsSync(panelStateFile)) {
        return JSON.parse(fs.readFileSync(panelStateFile, 'utf8'));
      }
    } catch {}
    return { x: 0, y: 0, isDrawerOpen: false };
  }

  private savePanelState(state: Partial<PanelState>) {
    try {
      const panelStateFile = getPanelStateFile();
      const current = this.loadPanelState();
      const updated = { ...current, ...state };
      fs.writeFileSync(panelStateFile, JSON.stringify(updated), 'utf8');
    } catch {}
  }

  createPanelAndTray(onDemoCommand: (prompt: string) => void) {
    dragInstance = this; // Set static instance for IPC handlers

    const primary = screen.getPrimaryDisplay();
    const savedState = this.loadPanelState();

    const defaultX = primary.workArea.x + primary.workArea.width - 350;
    const defaultY = primary.workArea.y + primary.workArea.height - 350;

    this.panelWindow = new BrowserWindow({
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
      if (!this.isDragging) return;
      const [x, y] = this.panelWindow!.getPosition();
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

    const icon = nativeImage.createEmpty();
    this.tray = new Tray(icon);
    this.tray.setToolTip('Clicky AI Companion');
    this.tray.setContextMenu(
      Menu.buildFromTemplate([
        {
          label: 'Toggle Clicky Panel',
          click: () => {
            if (this.panelWindow?.isVisible()) this.panelWindow.hide();
            else this.panelWindow?.show();
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
        { label: 'Quit Clicky', click: () => app.quit() },
      ])
    );
  }

  toggleDrawer() {
    if (!this.panelWindow) return;
    const [x, y] = this.panelWindow.getPosition();
    const currentHeight = this.panelWindow.getBounds().height;
    const targetHeight = currentHeight > 400 ? 330 : 530;

    this.panelWindow.setBounds({ x, y, width: 330, height: targetHeight });
    this.savePanelState({ isDrawerOpen: targetHeight > 400 });
  }
}
