"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.WindowPositionManager = void 0;
const electron_1 = require("electron");
class WindowPositionManager {
    static hasAccessibilityPermission() {
        return true; // Native on Windows
    }
    static hasScreenRecordingPermission() {
        return true; // Native via desktopCapturer on Windows
    }
    static openPrivacySettings() {
        electron_1.shell.openExternal('ms-settings:privacy-microphone');
    }
}
exports.WindowPositionManager = WindowPositionManager;
