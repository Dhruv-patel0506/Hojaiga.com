"use strict";
/**
 * WindowManager - Window bounds clamping & focus validation
 * Retrieves active app info and clamps coordinates to prevent taskbar misclicks
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.WindowManager = void 0;
const child_process_1 = require("child_process");
class WindowManager {
    activeWindow = null;
    lastKnownTargetHwnd = null; // Store last known target app HWND
    ignorePid = null; // PID to ignore (Clicky/Electron)
    /**
     * Set the PID to ignore (e.g., Clicky/Electron app)
     */
    setIgnorePid(pid) {
        this.ignorePid = pid;
        console.log(`[WindowManager] Set ignore PID: ${pid}`);
    }
    /**
     * Clear the ignore PID
     */
    clearIgnorePid() {
        this.ignorePid = null;
        console.log('[WindowManager] Cleared ignore PID');
    }
    /**
     * Get the active window information
     */
    getActiveWindow() {
        try {
            const ignorePidArg = this.ignorePid ? this.ignorePid : 'None';
            const lastKnownHwndArg = this.lastKnownTargetHwnd ? this.lastKnownTargetHwnd : 'None';
            const pythonScript = `
import win32gui
import win32con
import win32process
import json
import base64
import time
from io import BytesIO
from PIL import ImageGrab

# CRITICAL RUNTIME CHECK #2: Common Dialogs (#32770 Modal Windows)
# When Save As or Open is triggered, Windows spawns a separate Win32 modal dialog
# We need to detect and re-attach to the newly focused child modal HWND
# EDGE CASE FIX: Filter modal dialogs by process ID and owner HWND to prevent
# latching onto unrelated dialogs from other apps
# WINDOW HIJACKING FIX: Ignore Clicky/Electron process and restore focus to target

def get_foreground_window_with_modal_check(ignore_pid=None, last_known_hwnd=None):
    """Get foreground window, checking for modal dialogs (#32770)"""
    hwnd = win32gui.GetForegroundWindow()
    
    # Get target process ID for filtering
    target_tid, target_pid = win32process.GetWindowThreadProcessId(hwnd)
    
    # WINDOW HIJACKING FIX: If active window is ignored PID (Clicky), fallback to last known target
    if ignore_pid and target_pid == ignore_pid:
        print(f"DETECTED_IGNORED_PID: {target_pid} (Clicky/Electron)")
        if last_known_hwnd:
            print(f"RESTORING_FOCUS_TO_LAST_TARGET: {last_known_hwnd}")
            hwnd = last_known_hwnd
            win32gui.SetForegroundWindow(hwnd)
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            time.sleep(0.2)  # Wait for focus to settle
            target_tid, target_pid = win32process.GetWindowThreadProcessId(hwnd)
        else:
            print("WARNING: No last known target HWND available")
    
    # Check if this is a modal dialog (class name #32770)
    class_name = win32gui.GetClassName(hwnd)
    
    if class_name == "#32770":
        # This is a common dialog (Save As, Open, etc.)
        # Log that we detected a modal dialog
        print(f"DETECTED_MODAL_DIALOG: {class_name}")
        return hwnd, True
    
    # Check if there's a modal dialog as a child of the foreground window
    # Sometimes the dialog appears but doesn't get focus immediately
    # EDGE CASE FIX: Filter by process ID and owner HWND
    def enum_windows_callback(hwnd_candidate, result_list):
        if win32gui.IsWindowVisible(hwnd_candidate):
            if win32gui.GetClassName(hwnd_candidate) == "#32770":
                # Ensure the modal belongs to the same process or is owned by hwnd
                cand_tid, cand_pid = win32process.GetWindowThreadProcessId(hwnd_candidate)
                owner_hwnd = win32gui.GetWindow(hwnd_candidate, win32con.GW_OWNER)
                if cand_pid == target_pid or owner_hwnd == hwnd:
                    result_list.append(hwnd_candidate)
        return True
    
    modal_hwnds = []
    win32gui.EnumWindows(enum_windows_callback, modal_hwnds)
    
    if modal_hwnds:
        # Return the first modal dialog found (filtered by process/owner)
        print(f"DETECTED_CHILD_MODAL_DIALOG: {modal_hwnds[0]}")
        return modal_hwnds[0], True
    
    return hwnd, False

# Get ignore PID and last known HWND from arguments
ignore_pid = ${ignorePidArg}
last_known_hwnd = ${lastKnownHwndArg}

hwnd, is_modal = get_foreground_window_with_modal_check(ignore_pid, last_known_hwnd)
title = win32gui.GetWindowText(hwnd)
rect = win32gui.GetWindowRect(hwnd)

# Store this as the last known target for future calls
print(f"LAST_KNOWN_TARGET_HWND: {hwnd}")

# Log detected window for debugging
print(f"DETECTED_WINDOW: {title}")
print(f"WINDOW_RECT: {rect}")
print(f"WINDOW_HWND: {hwnd}")
print(f"IS_MODAL_DIALOG: {is_modal}")

# Force focus on this window to ensure correct targeting
win32gui.SetForegroundWindow(hwnd)
win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)

# Determine app state
placement = win32gui.GetWindowPlacement(hwnd)
show_cmd = placement[1]

if show_cmd == win32con.SW_SHOWMINIMIZED:
    state = 'splash_screen'
elif show_cmd == win32con.SW_SHOWMAXIMIZED:
    state = 'ready'
else:
    state = 'initial'

# Capture window area
screenshot = ImageGrab.grab(bbox=(rect[0], rect[1], rect[2], rect[3]))
buffered = BytesIO()
screenshot.save(buffered, format="PNG")
img_str = base64.b64encode(buffered.getvalue()).decode()

result = {
    "appId": str(hwnd),
    "appTitle": title,
    "bounds": {
        "x": rect[0],
        "y": rect[1],
        "width": rect[2] - rect[0],
        "height": rect[3] - rect[1]
    },
    "currentState": state,
    "timestamp": 0,
    "screenshot": img_str,
    "isModalDialog": is_modal
}

print(json.dumps(result))
`;
            const { writeFileSync, unlinkSync } = require('fs');
            const { join } = require('path');
            // Write Python script to temp file to avoid newline issues
            const tempScriptPath = join(__dirname, 'temp_window.py');
            writeFileSync(tempScriptPath, pythonScript);
            try {
                const result = (0, child_process_1.execSync)(`python "${tempScriptPath}"`, {
                    encoding: 'utf-8',
                    maxBuffer: 10 * 1024 * 1024
                });
                const data = JSON.parse(result);
                data.timestamp = Date.now();
                this.activeWindow = data;
                // Store the HWND as last known target for future calls
                this.lastKnownTargetHwnd = parseInt(data.appId);
                // CRITICAL RUNTIME CHECK #2: Log if we detected a modal dialog
                if (data.isModalDialog) {
                    console.log(`[WindowManager] Modal dialog detected: ${data.appTitle} (HWND: ${data.appId})`);
                    console.log('[WindowManager] Active window re-attached to modal dialog for UI Automation search');
                }
                return data;
            }
            finally {
                // Clean up temp file
                try {
                    unlinkSync(tempScriptPath);
                }
                catch (e) {
                    // Ignore cleanup errors
                }
            }
        }
        catch (error) {
            console.error('[WindowManager] Failed to get active window:', error);
            throw error;
        }
    }
    /**
     * Focus the active window
     */
    focusWindow() {
        try {
            const pythonScript = `
import win32gui
import win32con

hwnd = win32gui.GetForegroundWindow()
if win32gui.IsIconic(hwnd):
    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
win32gui.SetForegroundWindow(hwnd)
print("focused")
`;
            const { writeFileSync, unlinkSync } = require('fs');
            const { join } = require('path');
            // Write Python script to temp file to avoid newline issues
            const tempScriptPath = join(__dirname, 'temp_focus.py');
            writeFileSync(tempScriptPath, pythonScript);
            try {
                (0, child_process_1.execSync)(`python "${tempScriptPath}"`, {
                    encoding: 'utf-8'
                });
            }
            finally {
                // Clean up temp file
                try {
                    unlinkSync(tempScriptPath);
                }
                catch (e) {
                    // Ignore cleanup errors
                }
            }
        }
        catch (error) {
            console.error('[WindowManager] Failed to focus window:', error);
        }
    }
    /**
     * Convert normalized coordinates (0-1) to absolute screen coordinates
     * Strictly clamped to window bounds to prevent taskbar misclicks
     */
    normalizedToAbsolute(normalized, padding = 10) {
        if (!this.activeWindow) {
            throw new Error('No active window to calculate coordinates');
        }
        const { bounds } = this.activeWindow;
        // Clamp normalized coordinates to [0, 1]
        const clampedX = Math.max(0, Math.min(1, normalized.x));
        const clampedY = Math.max(0, Math.min(1, normalized.y));
        // Convert to absolute coordinates
        const absoluteX = bounds.x + clampedX * bounds.width;
        const absoluteY = bounds.y + clampedY * bounds.height;
        // Apply padding (stay away from window edges)
        const safeX = Math.max(bounds.x + padding, Math.min(bounds.x + bounds.width - padding, absoluteX));
        const safeY = Math.max(bounds.y + padding, Math.min(bounds.y + bounds.height - padding, absoluteY));
        return { x: Math.round(safeX), y: Math.round(safeY) };
    }
    /**
     * Check if coordinates are within window bounds
     */
    isWithinBounds(x, y) {
        if (!this.activeWindow)
            return false;
        const { bounds } = this.activeWindow;
        return (x >= bounds.x &&
            x <= bounds.x + bounds.width &&
            y >= bounds.y &&
            y <= bounds.y + bounds.height);
    }
    /**
     * Get window bounds for reference
     */
    getBounds() {
        if (!this.activeWindow) {
            throw new Error('No active window');
        }
        return this.activeWindow.bounds;
    }
    /**
     * Capture the active window (for state verification)
     */
    captureWindow() {
        if (!this.activeWindow) {
            throw new Error('No active window to capture');
        }
        try {
            const pythonScript = `
import win32gui
import win32con
import win32process
import base64
from io import BytesIO
from PIL import ImageGrab

# CRITICAL RUNTIME CHECK #2: Check for modal dialogs when capturing
# EDGE CASE FIX: Filter modal dialogs by process ID and owner HWND
def get_foreground_window_with_modal_check():
    """Get foreground window, checking for modal dialogs (#32770)"""
    hwnd = win32gui.GetForegroundWindow()
    
    # Get target process ID for filtering
    target_tid, target_pid = win32process.GetWindowThreadProcessId(hwnd)
    
    # Check if this is a modal dialog (class name #32770)
    class_name = win32gui.GetClassName(hwnd)
    
    if class_name == "#32770":
        # This is a common dialog (Save As, Open, etc.)
        return hwnd, True
    
    # Check if there's a modal dialog as a child of the foreground window
    # EDGE CASE FIX: Filter by process ID and owner HWND
    def enum_windows_callback(hwnd_candidate, result_list):
        if win32gui.IsWindowVisible(hwnd_candidate):
            if win32gui.GetClassName(hwnd_candidate) == "#32770":
                # Ensure the modal belongs to the same process or is owned by hwnd
                cand_tid, cand_pid = win32process.GetWindowThreadProcessId(hwnd_candidate)
                owner_hwnd = win32gui.GetWindow(hwnd_candidate, win32con.GW_OWNER)
                if cand_pid == target_pid or owner_hwnd == hwnd:
                    result_list.append(hwnd_candidate)
        return True
    
    modal_hwnds = []
    win32gui.EnumWindows(enum_windows_callback, modal_hwnds)
    
    if modal_hwnds:
        # Return the first modal dialog found (filtered by process/owner)
        return modal_hwnds[0], True
    
    return hwnd, False

hwnd, is_modal = get_foreground_window_with_modal_check()
rect = win32gui.GetWindowRect(hwnd)
screenshot = ImageGrab.grab(bbox=(rect[0], rect[1], rect[2], rect[3]))
buffered = BytesIO()
screenshot.save(buffered, format="PNG")
img_str = base64.b64encode(buffered.getvalue()).decode()
print(img_str)
`;
            const { writeFileSync, unlinkSync } = require('fs');
            const { join } = require('path');
            // Write Python script to temp file to avoid newline issues
            const tempScriptPath = join(__dirname, 'temp_capture.py');
            writeFileSync(tempScriptPath, pythonScript);
            try {
                const result = (0, child_process_1.execSync)(`python "${tempScriptPath}"`, {
                    encoding: 'utf-8',
                    maxBuffer: 10 * 1024 * 1024
                });
                // Update screenshot in active window state
                this.activeWindow.screenshot = result.trim();
                this.activeWindow.timestamp = Date.now();
                // CRITICAL RUNTIME CHECK #2: Re-attach to modal dialog if detected
                // The Python script now returns the modal dialog HWND if detected
                // We should refresh the active window info to ensure we're targeting the right window
                if (this.activeWindow.isModalDialog) {
                    console.log('[WindowManager] Modal dialog active during capture - ensuring UI Automation targets correct window');
                }
                return result.trim();
            }
            finally {
                // Clean up temp file
                try {
                    unlinkSync(tempScriptPath);
                }
                catch (e) {
                    // Ignore cleanup errors
                }
            }
        }
        catch (error) {
            console.error('[WindowManager] Failed to capture window:', error);
            throw error;
        }
    }
    /**
     * Get the current window title
     */
    getWindowTitle() {
        return this.activeWindow?.appTitle || 'Unknown';
    }
    /**
     * Get the current app state
     */
    getCurrentState() {
        return this.activeWindow?.currentState || 'unknown';
    }
}
exports.WindowManager = WindowManager;
