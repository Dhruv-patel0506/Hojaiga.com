import { app, BrowserWindow, Menu, nativeImage, screen, Tray } from 'electron';
import path from 'path';

export class MenuBarPanelManager {
  public panelWindow: BrowserWindow | null = null;
  public tray: Tray | null = null;

  createPanelAndTray(onDemoCommand: (prompt: string) => void) {
    const primary = screen.getPrimaryDisplay();
    this.panelWindow = new BrowserWindow({
      width: 330,
      height: 330,
      x: primary.workArea.x + primary.workArea.width - 350,
      y: primary.workArea.y + primary.workArea.height - 350,
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
    this.panelWindow.loadFile(path.join(__dirname, '../public/panel.html'));

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
}