import { BrowserWindow, screen } from 'electron';
import path from 'path';

export class OverlayWindowManager {
  public overlayWindowsByDisplayId = new Map<number, BrowserWindow>();
  public hasShownOverlayBefore = false;

  showOverlay() {
    this.hideOverlay();
    const isFirstAppearance = !this.hasShownOverlayBefore;
    this.hasShownOverlayBefore = true;

    const displays = screen.getAllDisplays();
    const primary = screen.getPrimaryDisplay();

    for (const display of displays) {
      const overlay = new BrowserWindow({
        x: display.bounds.x,
        y: display.bounds.y,
        width: display.bounds.width,
        height: display.bounds.height,
        transparent: true,
        frame: false,
        alwaysOnTop: true,
        skipTaskbar: true,
        hasShadow: false,
        focusable: false,
        resizable: false,
        movable: false,
        webPreferences: {
          nodeIntegration: true,
          contextIsolation: false,
        },
      });

      overlay.setAlwaysOnTop(true, 'screen-saver');
      overlay.setIgnoreMouseEvents(true, { forward: true });
      overlay.setContentProtection(false);
      overlay.loadFile(path.join(__dirname, '../public/overlay.html'));

      if (isFirstAppearance && display.id === primary.id) {
        overlay.webContents.once('did-finish-load', () => {
          overlay.webContents.send('trigger-welcome');
        });
      }

      this.overlayWindowsByDisplayId.set(display.id, overlay);
    }
  }

  hideOverlay() {
    for (const win of this.overlayWindowsByDisplayId.values()) {
      if (!win.isDestroyed()) win.close();
    }
    this.overlayWindowsByDisplayId.clear();
  }

  broadcast(channel: string, payload?: any) {
    for (const win of this.overlayWindowsByDisplayId.values()) {
      if (!win.isDestroyed()) {
        win.webContents.send(channel, payload);
      }
    }
  }
}