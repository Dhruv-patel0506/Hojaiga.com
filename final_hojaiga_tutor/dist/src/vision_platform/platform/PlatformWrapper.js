"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.TestingEnvWrapper = exports.WindowsEnvWrapper = void 0;
const child_process_1 = require("child_process");
const util_1 = require("util");
const execFileAsync = (0, util_1.promisify)(child_process_1.execFile);
// Windows Implementation using PowerShell + Electron screen capture
class WindowsEnvWrapper {
    overlayWindow;
    constructor(overlayWindow) {
        this.overlayWindow = overlayWindow;
    }
    async captureScreen(displayId) {
        try {
            // Use Electron's screen capture via the overlay window
            if (this.overlayWindow) {
                const result = await this.overlayWindow.webContents.executeJavaScript(`
          new Promise((resolve) => {
            const desktopCapturer = require('electron').desktopCapturer;
            desktopCapturer.getSources({ types: ['screen'] }).then(async (sources) => {
              const source = sources[0];
              const stream = await navigator.mediaDevices.getUserMedia({
                audio: false,
                video: {
                  mandatory: {
                    chromeMediaSource: 'desktop',
                    chromeMediaSourceId: source.id,
                    minWidth: 1920,
                    maxWidth: 1920,
                    minHeight: 1080,
                    maxHeight: 1080
                  }
                }
              });
              const video = document.createElement('video');
              video.srcObject = stream;
              video.onloadedmetadata = () => {
                video.play();
                const canvas = document.createElement('canvas');
                canvas.width = 1920;
                canvas.height = 1080;
                const ctx = canvas.getContext('2d');
                ctx.drawImage(video, 0, 0, 1920, 1080);
                const dataUrl = canvas.toDataURL('image/png');
                stream.getTracks().forEach(track => track.stop());
                resolve(dataUrl);
              };
            });
          });
        `);
                // Remove data URL prefix
                return result.replace(/^data:image\/png;base64,/, '');
            }
            // Fallback: Use PowerShell to capture screen
            const psScript = `
        Add-Type -AssemblyName System.Windows.Forms
        Add-Type -AssemblyName System.Drawing
        $screen = [System.Windows.Forms.Screen]::PrimaryScreen
        $bitmap = New-Object System.Drawing.Bitmap $screen.Bounds.Width, $screen.Bounds.Height
        $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
        $graphics.CopyFromScreen($screen.Bounds.X, $screen.Bounds.Y, 0, 0, $screen.Bounds.Size)
        $memoryStream = New-Object System.IO.MemoryStream
        $bitmap.Save($memoryStream, [System.Drawing.Imaging.ImageFormat]::Png)
        $base64 = [Convert]::ToBase64String($memoryStream.ToArray())
        $graphics.Dispose()
        $bitmap.Dispose()
        Write-Output $base64
      `;
            const { stdout } = await execFileAsync('powershell.exe', [
                '-NoProfile',
                '-NonInteractive',
                '-Command',
                psScript,
            ], { timeout: 5000 });
            return stdout.trim();
        }
        catch (error) {
            console.error('[WindowsEnvWrapper] Screen capture failed:', error);
            throw error;
        }
    }
    async executeAction(action) {
        switch (action.actionType) {
            case 'click':
                if (action.targetCoordinates) {
                    await this.clickAt(action.targetCoordinates.x, action.targetCoordinates.y);
                }
                break;
            case 'type':
                if (action.payload) {
                    await this.typeText(action.payload);
                }
                break;
            case 'explain':
                console.log(`[TEACHER SAYS]: ${action.payload}`);
                // TTS integration would go here
                break;
            case 'highlight':
                console.log(`[HIGHLIGHT]: ${action.targetText} at ${JSON.stringify(action.targetCoordinates)}`);
                break;
            case 'wait':
                await new Promise(resolve => setTimeout(resolve, action.payload ? parseInt(action.payload) : 1000));
                break;
        }
    }
    async clickAt(x, y) {
        const psScript = `
      Add-Type @"
        using System;
        using System.Runtime.InteropServices;
        public class MouseClick {
          [DllImport("user32.dll")]
          public static extern void mouse_event(uint dwFlags, uint dx, uint dy, uint cButtons, uint dwExtraInfo);
          public const uint MOUSEEVENTF_LEFTDOWN = 0x02;
          public const uint MOUSEEVENTF_LEFTUP = 0x04;
          public const uint MOUSEEVENTF_MOVE = 0x0001;
        }
"@
      [MouseClick]::mouse_event([MouseClick]::MOUSEEVENTF_MOVE, ${x}, ${y}, 0, 0);
      Start-Sleep -Milliseconds 50
      [MouseClick]::mouse_event([MouseClick]::MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0);
      Start-Sleep -Milliseconds 50
      [MouseClick]::mouse_event([MouseClick]::MOUSEEVENTF_LEFTUP, 0, 0, 0, 0);
    `;
        await execFileAsync('powershell.exe', ['-NoProfile', '-NonInteractive', '-Command', psScript]);
    }
    async typeText(text) {
        const psScript = `
      Add-Type -AssemblyName System.Windows.Forms
      $wsh = New-Object -ComObject WScript.Shell
      "$text" | ForEach-Object {
        $wsh.SendKeys($_)
        Start-Sleep -Milliseconds 10
      }
    `.replace('$text', text.replace(/"/g, '`"'));
        await execFileAsync('powershell.exe', ['-NoProfile', '-NonInteractive', '-Command', psScript]);
    }
    async getActiveWindowInfo() {
        const psScript = `
      Add-Type @"
        using System;
        using System.Runtime.InteropServices;
        public class WinFg {
          [DllImport("user32.dll")]
          public static extern IntPtr GetForegroundWindow();
        }
"@
      $hwnd = [WinFg]::GetForegroundWindow()
      $proc = Get-Process | Where-Object { $_.MainWindowHandle -eq $hwnd } | Select-Object -First 1
      if ($proc) {
        Write-Output "$($proc.ProcessName)|$($proc.MainWindowTitle)"
      } else {
        Write-Output "Unknown|Desktop"
      }
    `;
        try {
            const { stdout } = await execFileAsync('powershell.exe', [
                '-NoProfile',
                '-NonInteractive',
                '-Command',
                psScript,
            ]);
            const [processName, windowTitle] = stdout.trim().split('|');
            return { processName, windowTitle };
        }
        catch {
            return { processName: 'Unknown', windowTitle: 'Desktop' };
        }
    }
}
exports.WindowsEnvWrapper = WindowsEnvWrapper;
// Test Wrapper for CI/CD or dry-run testing
class TestingEnvWrapper {
    mockScreenshotBase64 = 'mock_base64_data';
    async captureScreen() {
        console.log('[TEST ENV] Mock screen captured.');
        return this.mockScreenshotBase64;
    }
    async executeAction(action) {
        console.log(`[TEST ENV] Simulating Action: ${JSON.stringify(action)}`);
        await new Promise(resolve => setTimeout(resolve, 500));
    }
    async getActiveWindowInfo() {
        return { processName: 'TestApp', windowTitle: 'Test Window' };
    }
}
exports.TestingEnvWrapper = TestingEnvWrapper;
