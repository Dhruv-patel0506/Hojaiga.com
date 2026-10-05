"use strict";
/**
 * OverlayEngine - Focus-free rendering with visual anchoring
 * Draws high-visibility SVG pulse rings and fake cursor at target coordinates
 * Never occludes workspace or steals window focus
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.OverlayEngine = void 0;
const electron_1 = require("electron");
const path_1 = require("path");
class OverlayEngine {
    overlayWindow = null;
    isVisible = false;
    virtualCursor = {
        isDetached: false,
        mode: 'idle',
        color: '#FFFFFF', // White when following physical mouse
        position: { x: 0, y: 0 }
    };
    /**
     * Initialize the overlay window
     * Focus-free: transparent, frameless, always-on-top, ignores mouse events
     */
    initializeOverlay() {
        if (this.overlayWindow) {
            console.log('[OverlayEngine] Overlay already initialized');
            return;
        }
        console.log('[OverlayEngine] Initializing focus-free overlay...');
        this.overlayWindow = new electron_1.BrowserWindow({
            width: 1920,
            height: 1080,
            x: 0,
            y: 0,
            transparent: true,
            frame: false,
            alwaysOnTop: true,
            skipTaskbar: true,
            resizable: false,
            movable: false,
            webPreferences: {
                nodeIntegration: true,
                contextIsolation: false
            }
        });
        // Make window click-through (ignores mouse events)
        this.overlayWindow.setIgnoreMouseEvents(true);
        // Load overlay content - use absolute path from project root
        const overlayPath = (0, path_1.join)(__dirname, '..', 'public', 'overlay.html');
        this.overlayWindow.loadFile(overlayPath);
        this.overlayWindow.on('ready-to-show', () => {
            console.log('[OverlayEngine] Overlay ready');
        });
        this.overlayWindow.on('closed', () => {
            this.overlayWindow = null;
            this.isVisible = false;
        });
    }
    /**
     * Show the overlay
     */
    showOverlay() {
        if (!this.overlayWindow) {
            this.initializeOverlay();
        }
        if (this.overlayWindow && !this.isVisible) {
            this.overlayWindow.show();
            this.isVisible = true;
            console.log('[OverlayEngine] Overlay shown');
        }
    }
    /**
     * Hide the overlay
     */
    hideOverlay() {
        if (this.overlayWindow && this.isVisible) {
            this.overlayWindow.hide();
            this.isVisible = false;
            console.log('[OverlayEngine] Overlay hidden');
        }
    }
    /**
     * Draw a pulse ring at target coordinates
     * Visual anchoring for the target element (enhanced mode)
     */
    drawPulseRing(x, y, label) {
        if (!this.overlayWindow) {
            console.warn('[OverlayEngine] Overlay not initialized');
            return;
        }
        this.overlayWindow.webContents.send('draw-pulse-ring-enhanced', { x, y, label });
        console.log(`[OverlayEngine] Drawing enhanced pulse ring at (${x}, ${y}): ${label}`);
    }
    /**
     * Draw a fake cursor (Clicky-style blue cursor) - enhanced mode
     * Visual indicator for where the action will occur
     */
    drawFakeCursor(x, y, label) {
        if (!this.overlayWindow) {
            console.warn('[OverlayEngine] Overlay not initialized');
            return;
        }
        this.overlayWindow.webContents.send('draw-fake-cursor-enhanced', { x, y, label });
        console.log(`[OverlayEngine] Drawing enhanced fake cursor at (${x}, ${y}): ${label}`);
    }
    /**
     * Clear enhanced drawings only (doesn't affect existing Clicky drawings)
     */
    clearDrawings() {
        if (!this.overlayWindow) {
            console.warn('[OverlayEngine] Overlay not initialized');
            return;
        }
        this.overlayWindow.webContents.send('clear-enhanced-drawings');
        console.log('[OverlayEngine] Cleared enhanced drawings only');
    }
    /**
     * Animate cursor movement from start to end
     * Bezier curve animation for visual feedback
     */
    animateCursorMovement(startX, startY, endX, endY, duration = 500) {
        if (!this.overlayWindow) {
            console.warn('[OverlayEngine] Overlay not initialized');
            return;
        }
        this.overlayWindow.webContents.send('animate-cursor', {
            startX,
            startY,
            endX,
            endY,
            duration
        });
        console.log(`[OverlayEngine] Animating cursor from (${startX}, ${startY}) to (${endX}, ${endY})`);
    }
    /**
     * Update overlay position (for multi-monitor setups)
     */
    updateOverlayPosition(x, y) {
        if (!this.overlayWindow) {
            console.warn('[OverlayEngine] Overlay not initialized');
            return;
        }
        this.overlayWindow.setPosition(x, y);
        console.log(`[OverlayEngine] Overlay position updated to (${x}, ${y})`);
    }
    /**
     * Get overlay visibility
     */
    isOverlayVisible() {
        return this.isVisible;
    }
    /**
     * Cleanup overlay
     */
    cleanup() {
        console.log('[OverlayEngine] Cleaning up overlay...');
        if (this.overlayWindow) {
            this.overlayWindow.close();
            this.overlayWindow = null;
            this.isVisible = false;
        }
    }
    /**
     * Detach virtual cursor - Clicky works independently (magenta)
     */
    detachVirtualCursor() {
        this.virtualCursor.isDetached = true;
        this.virtualCursor.mode = 'teaching';
        this.virtualCursor.color = '#FF00FF'; // Magenta
        console.log('[OverlayEngine] Virtual cursor DETACHED (magenta) - Clicky working independently');
        this.sendCursorState();
    }
    /**
     * Attach virtual cursor - Follow physical mouse (white)
     */
    attachVirtualCursor() {
        this.virtualCursor.isDetached = false;
        this.virtualCursor.mode = 'idle';
        this.virtualCursor.color = '#FFFFFF'; // White
        console.log('[OverlayEngine] Virtual cursor ATTACHED (white) - Following physical mouse');
        this.sendCursorState();
    }
    /**
     * Update virtual cursor position
     */
    updateVirtualCursor(x, y) {
        this.virtualCursor.position = { x, y };
        this.sendCursorState();
    }
    /**
     * Send cursor state to overlay
     */
    sendCursorState() {
        if (!this.overlayWindow)
            return;
        this.overlayWindow.webContents.send('cursor-state', this.virtualCursor);
    }
    /**
     * Get current cursor state
     */
    getCursorState() {
        return this.virtualCursor;
    }
}
exports.OverlayEngine = OverlayEngine;
