"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.GlobalPushToTalkShortcutMonitor = void 0;
const electron_1 = require("electron");
class GlobalPushToTalkShortcutMonitor {
    isListening = false;
    onTransitionCallback;
    start(onTransition) {
        this.onTransitionCallback = onTransition;
        electron_1.globalShortcut.unregisterAll();
        // Register Ctrl+Alt+Space on Windows
        electron_1.globalShortcut.register('CommandOrControl+Alt+Space', () => {
            if (!this.isListening) {
                this.isListening = true;
                this.onTransitionCallback?.('pressed');
            }
            else {
                this.isListening = false;
                this.onTransitionCallback?.('released');
            }
        });
    }
    resetState() {
        this.isListening = false;
    }
    stop() {
        electron_1.globalShortcut.unregisterAll();
        this.isListening = false;
    }
}
exports.GlobalPushToTalkShortcutMonitor = GlobalPushToTalkShortcutMonitor;
