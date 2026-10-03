"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.OverlayWindowManager = void 0;
const electron_1 = require("electron");
const path_1 = __importDefault(require("path"));
class OverlayWindowManager {
    overlayWindowsByDisplayId = new Map();
    hasShownOverlayBefore = false;
    isClickThrough = true;
    screenListenerRegistered = false;
    constructor() {
        // Screen listener will be registered in showOverlay when app is ready
    }
    registerScreenListener() {
        if (this.screenListenerRegistered)
            return;
        this.screenListenerRegistered = true;
        electron_1.screen.on('display-metrics-changed', () => this.syncWindowsToDisplays());
    }
    showOverlay() {
        this.registerScreenListener();
        this.hideOverlay();
        const isFirstAppearance = !this.hasShownOverlayBefore;
        this.hasShownOverlayBefore = true;
        const displays = electron_1.screen.getAllDisplays();
        const primary = electron_1.screen.getPrimaryDisplay();
        for (const display of displays) {
            const overlay = new electron_1.BrowserWindow({
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
                    // File 29: never throttle the renderer timers/RAF while unfocused -
                    // the overlay is unfocused by design (click-through).
                    backgroundThrottling: false,
                },
            });
            overlay.setAlwaysOnTop(true, 'screen-saver');
            overlay.setContentProtection(false);
            overlay.loadFile(path_1.default.join(__dirname, '../public/overlay.html'));
            this.applyClickThroughToWindow(overlay, this.isClickThrough);
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
            if (!win.isDestroyed())
                win.close();
        }
        this.overlayWindowsByDisplayId.clear();
    }
    /**
     * File 29 idea: OS-level mouse passthrough toggle (Ctrl+Shift+Space).
     * `enableClickThrough = true` = clicks pass through to apps underneath;
     * false = overlay becomes focusable so the in-overlay prompt bar works.
     * Applied to every display's overlay window.
     */
    setClickThrough(enableClickThrough) {
        this.isClickThrough = enableClickThrough;
        for (const win of this.overlayWindowsByDisplayId.values()) {
            this.applyClickThroughToWindow(win, enableClickThrough);
        }
        this.broadcast('overlay:click-through-changed', this.isClickThrough);
    }
    applyClickThroughToWindow(win, enableClickThrough) {
        if (win.isDestroyed())
            return;
        if (enableClickThrough) {
            win.setFocusable(false);
            win.setIgnoreMouseEvents(true, { forward: true });
        }
        else {
            win.setIgnoreMouseEvents(false);
            win.setFocusable(true);
            win.focus();
        }
    }
    syncWindowsToDisplays() {
        for (const [displayId, win] of this.overlayWindowsByDisplayId) {
            if (win.isDestroyed())
                continue;
            const display = electron_1.screen.getAllDisplays().find((d) => d.id === displayId);
            if (display)
                win.setBounds(display.bounds);
        }
    }
    broadcast(channel, payload) {
        for (const win of this.overlayWindowsByDisplayId.values()) {
            if (!win.isDestroyed()) {
                win.webContents.send(channel, payload);
            }
        }
    }
    /** Forwards a batch of animated overlay commands to one display's overlay. */
    renderCommands(displayId, commands, clearFirst = false, subtitle) {
        const win = this.overlayWindowsByDisplayId.get(displayId);
        if (!win || win.isDestroyed())
            return;
        win.webContents.send('overlay:draw', {
            commands,
            clear: clearFirst,
            subtitle,
        });
    }
    clearDrawings() {
        this.broadcast('overlay:clear');
    }
}
exports.OverlayWindowManager = OverlayWindowManager;
