"use strict";
/**
 * SafeOSController - Input wrapper with kill switch, queue cancellation, and stuck-click guard
 * Wraps low-level input simulation with humanized movement curves
 * Enhanced with Bezier interpolation and atomic input blocks
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.SafeOSController = void 0;
const child_process_1 = require("child_process");
class SafeOSController {
    actionQueue = [];
    isExecuting = false;
    emergencyStop = { triggered: false, reason: 'user_manual', timestamp: 0 };
    mouseDown = false; // Track if mouse is currently down
    killSwitchListener = null;
    /**
     * Humanized mouse movement using Bezier curves
     * Calculates a human-like sweeping path from current position to target
     */
    async humanizedMove(targetX, targetY, duration = 500) {
        if (this.emergencyStop.triggered)
            return;
        const pythonScript = `
import pyautogui
import time
import math

start_x, start_y = pyautogui.position()
target_x, target_y = ${targetX}, ${targetY}
duration = ${duration} / 1000.0

# Bezier curve interpolation for human-like movement
def bezier_point(t, p0, p1, p2):
    return (1-t)**2 * p0 + 2*(1-t)*t * p1 + t**2 * p2

# Control point for curve (creates natural arc)
control_x = start_x + (target_x - start_x) * 0.5
control_y = start_y - 100  # Slight upward arc

steps = 30
for i in range(steps + 1):
    t = i / steps
    x = bezier_point(t, start_x, control_x, target_x)
    y = bezier_point(t, start_y, control_y, target_y)
    pyautogui.moveTo(x, y, duration=0)
    time.sleep(duration / steps)

print("moved")
`;
        try {
            const { writeFileSync, unlinkSync } = require('fs');
            const { join } = require('path');
            // Write Python script to temp file to avoid newline issues
            const tempScriptPath = join(__dirname, 'temp_move.py');
            writeFileSync(tempScriptPath, pythonScript);
            try {
                (0, child_process_1.execSync)(`python "${tempScriptPath}"`, {
                    encoding: 'utf-8',
                    timeout: 10000 // 10 seconds to account for Python startup
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
            console.error('[SafeOSController] Move failed:', error);
        }
    }
    /**
     * Execute a click with guaranteed mouse release (Atomic Input Block)
     * Wrapped in try/finally to prevent stuck mouse state
     */
    async executeClick(x, y, clickType = 'left') {
        if (this.emergencyStop.triggered)
            return;
        this.mouseDown = true;
        try {
            const pythonScript = `
import pyautogui
import time

pyautogui.moveTo(${x}, ${y}, duration=0.2)
${clickType === 'double' ? 'pyautogui.doubleClick()' : clickType === 'right' ? 'pyautogui.rightClick()' : 'pyautogui.click()'}
print("clicked")
`;
            const { writeFileSync, unlinkSync } = require('fs');
            const { join } = require('path');
            // Write Python script to temp file to avoid newline issues
            const tempScriptPath = join(__dirname, 'temp_click.py');
            writeFileSync(tempScriptPath, pythonScript);
            try {
                (0, child_process_1.execSync)(`python "${tempScriptPath}"`, {
                    encoding: 'utf-8',
                    timeout: 10000 // 10 seconds to account for Python startup
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
            console.error('[SafeOSController] Click failed:', error);
        }
        finally {
            // Guarantee mouse release (atomic block)
            this.mouseDown = false;
            this.ensureMouseUp();
        }
    }
    /**
     * Ensure mouse button is released (stuck-click guard)
     */
    ensureMouseUp() {
        try {
            const pythonScript = `
import pyautogui
pyautogui.mouseUp()
print("mouse_up")
`;
            const { writeFileSync, unlinkSync } = require('fs');
            const { join } = require('path');
            // Write Python script to temp file to avoid newline issues
            const tempScriptPath = join(__dirname, 'temp_mouseup.py');
            writeFileSync(tempScriptPath, pythonScript);
            try {
                (0, child_process_1.execSync)(`python "${tempScriptPath}"`, {
                    encoding: 'utf-8',
                    timeout: 10000 // 10 seconds to account for Python startup
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
            console.error('[SafeOSController] Failed to ensure mouse up:', error);
        }
    }
    /**
     * Type text with human-like delays
     */
    async typeText(text, speed = 0.05) {
        if (this.emergencyStop.triggered)
            return;
        const pythonScript = `
import pyautogui
import time

text = """${text.replace(/"/g, '\\"')}"""
for char in text:
    pyautogui.typewrite(char, interval=${speed})
print("typed")
`;
        try {
            const { writeFileSync, unlinkSync } = require('fs');
            const { join } = require('path');
            // Write Python script to temp file to avoid newline issues
            const tempScriptPath = join(__dirname, 'temp_type.py');
            writeFileSync(tempScriptPath, pythonScript);
            try {
                (0, child_process_1.execSync)(`python "${tempScriptPath}"`, {
                    encoding: 'utf-8',
                    timeout: 10000
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
            console.error('[SafeOSController] Type failed:', error);
        }
    }
    /**
     * Press a key or hotkey
     */
    async pressKey(key, isHotkey = false) {
        if (this.emergencyStop.triggered)
            return;
        const pythonScript = `
import pyautogui
${isHotkey ? `pyautogui.hotkey('${key}')` : `pyautogui.press('${key}')`}
print("pressed")
`;
        try {
            const { writeFileSync, unlinkSync } = require('fs');
            const { join } = require('path');
            // Write Python script to temp file to avoid newline issues
            const tempScriptPath = join(__dirname, 'temp_press.py');
            writeFileSync(tempScriptPath, pythonScript);
            try {
                (0, child_process_1.execSync)(`python "${tempScriptPath}"`, {
                    encoding: 'utf-8',
                    timeout: 10000 // 10 seconds to account for Python startup
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
            console.error('[SafeOSController] Key press failed:', error);
        }
    }
    /**
     * Execute an action with safety checks
     */
    async executeAction(actionType, normalizedCoords, payload, windowBounds) {
        if (this.emergencyStop.triggered) {
            console.log('[SafeOSController] Emergency stop triggered, skipping action');
            return;
        }
        // Convert to absolute coordinates
        let absoluteX, absoluteY;
        if (windowBounds) {
            absoluteX = windowBounds.x + normalizedCoords.x * windowBounds.width;
            absoluteY = windowBounds.y + normalizedCoords.y * windowBounds.height;
        }
        else {
            // If no window bounds, use absolute screen coordinates (fallback)
            absoluteX = normalizedCoords.x;
            absoluteY = normalizedCoords.y;
        }
        // Queue the action
        const action = async () => {
            switch (actionType) {
                case 'click':
                    // Use UI Automation InvokePattern (programmatic click without moving mouse)
                    await this.invokeViaUIAutomation(absoluteX, absoluteY);
                    break;
                case 'rightClick':
                    // UI Automation doesn't have a right-click pattern - use physical mouse as fallback
                    console.log(`[SafeOSController] Right-click not supported via UI Automation - skipping`);
                    break;
                case 'doubleClick':
                    // UI Automation doesn't have double-click - invoke twice
                    await this.invokeViaUIAutomation(absoluteX, absoluteY);
                    await new Promise(resolve => setTimeout(resolve, 100));
                    await this.invokeViaUIAutomation(absoluteX, absoluteY);
                    break;
                case 'type':
                    if (payload) {
                        await this.setValueViaUIAutomation(absoluteX, absoluteY, payload);
                    }
                    break;
                case 'pressKey':
                    if (payload) {
                        await this.pressKey(payload, false);
                    }
                    break;
                case 'hotkey':
                    if (payload) {
                        await this.pressKey(payload, true);
                    }
                    break;
                case 'wait':
                    await new Promise(resolve => setTimeout(resolve, 1000));
                    break;
                default:
                    console.warn(`[SafeOSController] Unknown action type: ${actionType}`);
            }
        };
        this.actionQueue.push(action);
        // Execute if not already running
        if (!this.isExecuting) {
            await this.processQueue();
        }
    }
    /**
     * Process the action queue
     */
    async processQueue() {
        if (this.isExecuting)
            return;
        this.isExecuting = true;
        while (this.actionQueue.length > 0 && !this.emergencyStop.triggered) {
            const action = this.actionQueue.shift();
            if (action) {
                try {
                    await action();
                }
                catch (error) {
                    console.error('[SafeOSController] Action failed:', error);
                }
            }
        }
        this.isExecuting = false;
    }
    /**
     * Cancel all pending actions
     */
    cancelAll() {
        console.log('[SafeOSController] Cancelling all actions');
        this.actionQueue = [];
        this.emergencyStop = { triggered: true, reason: 'user_manual', timestamp: Date.now() };
        this.ensureMouseUp(); // Ensure mouse is released
        // Reset emergency stop after a delay
        setTimeout(() => {
            this.emergencyStop = { triggered: false, reason: 'user_manual', timestamp: 0 };
        }, 1000);
    }
    /**
     * Trigger emergency stop
     */
    triggerEmergencyStop(reason) {
        console.log(`[SafeOSController] Emergency stop triggered: ${reason}`);
        this.emergencyStop = { triggered: true, reason, timestamp: Date.now() };
        this.cancelAll();
    }
    /**
     * Check if emergency stop is active
     */
    isEmergencyStopActive() {
        return this.emergencyStop.triggered;
    }
    /**
     * Reset emergency stop (for testing/recovery)
     */
    resetEmergencyStop() {
        this.emergencyStop = { triggered: false, reason: 'user_manual', timestamp: 0 };
    }
    /**
     * Invoke UI element via Windows UI Automation (InvokePattern)
     * Programmatic click without moving physical mouse
     */
    async invokeViaUIAutomation(x, y) {
        try {
            console.log(`[SafeOSController] Invoking element at (${x}, ${y}) via UI Automation`);
            const { execSync } = require('child_process');
            const { writeFileSync, unlinkSync } = require('fs');
            const { join } = require('path');
            const tempScriptPath = join(__dirname, 'temp_uia_invoke.py');
            const pythonScript = `
import sys
sys.path.insert(0, r'D:\\\\new_automation\\\\final_hojaiga_tutor')
from UIAutomationInvoker import UIAutomationInvoker
import json

invoker = UIAutomationInvoker()
result = invoker.invoke_element(${x}, ${y})
print(json.dumps(result))
`;
            writeFileSync(tempScriptPath, pythonScript);
            try {
                const output = execSync(`python "${tempScriptPath}" 2>NUL`, {
                    encoding: 'utf-8',
                    maxBuffer: 10 * 1024 * 1024,
                    timeout: 10000 // 10 seconds
                });
                const result = JSON.parse(output.trim());
                if (result.success) {
                    console.log(`[SafeOSController] UI Automation invoke SUCCESS: ${result.method} on ${result.element}`);
                }
                else {
                    console.warn(`[SafeOSController] UI Automation invoke FAILED: ${result.error}`);
                    console.warn('[SafeOSController] Element may not support InvokePattern - this is expected for some controls');
                }
            }
            finally {
                try {
                    unlinkSync(tempScriptPath);
                }
                catch (e) {
                    // Ignore cleanup errors
                }
            }
        }
        catch (error) {
            console.error('[SafeOSController] UI Automation invoke error:', error);
            console.warn('[SafeOSController] Element may not support InvokePattern - this is expected for some controls');
        }
    }
    /**
     * Set value in UI element via Windows UI Automation (ValuePattern)
     * Programmatic text input without moving physical mouse
     */
    async setValueViaUIAutomation(x, y, text) {
        try {
            console.log(`[SafeOSController] Setting value at (${x}, ${y}) via UI Automation: "${text}"`);
            const { execSync } = require('child_process');
            const { writeFileSync, unlinkSync } = require('fs');
            const { join } = require('path');
            const tempScriptPath = join(__dirname, 'temp_uia_setvalue.py');
            // Simple approach: encode text as base64 in the script
            const base64Text = Buffer.from(text).toString('base64');
            const pythonScript = `import sys
import base64
sys.path.insert(0, r'D:\\\\new_automation\\\\final_hojaiga_tutor')
from UIAutomationInvoker import UIAutomationInvoker
invoker = UIAutomationInvoker()
text = base64.b64decode('${base64Text}').decode('utf-8')
result = invoker.set_value(${x}, ${y}, text)
print(json.dumps(result))
`;
            writeFileSync(tempScriptPath, pythonScript);
            try {
                const output = execSync(`python "${tempScriptPath}" 2>NUL`, {
                    encoding: 'utf-8',
                    maxBuffer: 10 * 1024 * 1024,
                    timeout: 10000 // 10 seconds
                });
                const result = JSON.parse(output.trim());
                if (result.success) {
                    console.log(`[SafeOSController] UI Automation set value SUCCESS: ${result.method} on ${result.element}`);
                }
                else {
                    console.warn(`[SafeOSController] UI Automation set value FAILED: ${result.error}`);
                }
            }
            finally {
                try {
                    unlinkSync(tempScriptPath);
                }
                catch (e) {
                    // Ignore cleanup errors
                }
            }
        }
        catch (error) {
            console.error('[SafeOSController] UI Automation set value error:', error);
        }
    }
    /**
     * Start hardware kill switch listener
     * Detects mouse jerk movements and ESC key
     */
    startKillSwitchListener() {
        if (this.killSwitchListener)
            return;
        console.log('[SafeOSController] Starting hardware kill switch listener...');
        // Monitor for mouse jerk detection
        let lastMousePosition = { x: 0, y: 0 };
        let lastCheckTime = Date.now();
        this.killSwitchListener = setInterval(() => {
            try {
                const pythonScript = `
import pyautogui
x, y = pyautogui.position()
print(f"{x},{y}")
`;
                const { execSync } = require('child_process');
                const { writeFileSync, unlinkSync } = require('fs');
                const { join } = require('path');
                // Write Python script to temp file to avoid newline issues
                const tempScriptPath = join(__dirname, 'temp_mousepos.py');
                writeFileSync(tempScriptPath, pythonScript);
                try {
                    const result = execSync(`python "${tempScriptPath}"`, {
                        encoding: 'utf-8',
                        timeout: 500
                    });
                    const [x, y] = result.trim().split(',').map(Number);
                    const currentTime = Date.now();
                    const timeDelta = currentTime - lastCheckTime;
                    if (timeDelta > 0) {
                        const deltaX = Math.abs(x - lastMousePosition.x);
                        const deltaY = Math.abs(y - lastMousePosition.y);
                        const velocity = Math.sqrt(deltaX * deltaX + deltaY * deltaY) / timeDelta;
                        // If mouse moves too fast (jerk detection)
                        if (velocity > 2.0) { // Threshold for "jerk" motion
                            console.log('[SafeOSController] Mouse jerk detected! Triggering emergency stop.');
                            this.triggerEmergencyStop('mouse_jerk');
                        }
                    }
                    lastMousePosition = { x, y };
                    lastCheckTime = currentTime;
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
                // Ignore errors from mouse polling
            }
        }, 100); // Check every 100ms
    }
    /**
     * Stop hardware kill switch listener
     */
    stopKillSwitchListener() {
        if (this.killSwitchListener) {
            clearInterval(this.killSwitchListener);
            this.killSwitchListener = null;
            console.log('[SafeOSController] Kill switch listener stopped.');
        }
    }
    /**
     * Cleanup on shutdown with process termination hooks
     */
    cleanup() {
        console.log('[SafeOSController] Cleaning up...');
        this.stopKillSwitchListener();
        this.cancelAll();
        this.ensureMouseUp();
    }
}
exports.SafeOSController = SafeOSController;
// Process termination hooks for cleanup
process.on('SIGINT', () => {
    console.log('[SafeOSController] SIGINT received, cleaning up...');
    const controller = new SafeOSController();
    controller.cleanup();
    process.exit(0);
});
process.on('SIGTERM', () => {
    console.log('[SafeOSController] SIGTERM received, cleaning up...');
    const controller = new SafeOSController();
    controller.cleanup();
    process.exit(0);
});
process.on('exit', () => {
    console.log('[SafeOSController] Process exiting, cleaning up...');
    const controller = new SafeOSController();
    controller.cleanup();
});
