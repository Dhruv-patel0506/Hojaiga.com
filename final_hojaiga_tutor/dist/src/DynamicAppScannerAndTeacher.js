"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.DynamicAppScannerAndTeacher = void 0;
const child_process_1 = require("child_process");
const util_1 = require("util");
const execFileAsync = (0, util_1.promisify)(child_process_1.execFile);
class DynamicAppScannerAndTeacher {
    static cache = new Map();
    static CACHE_TTL_MS = 4500;
    /**
     * Fast, deep Windows UI Automation tree scanner.
     * Extracts interactive buttons, tabs, sliders, and menu items with exact
     * screen coordinates via an in-memory BFS tree cache.
     */
    static async scanActiveOrNamedApp(targetAppName) {
        const cacheKey = (targetAppName || '__active__').toLowerCase();
        const cached = this.cache.get(cacheKey);
        if (cached && Date.now() - cached.scannedAt < this.CACHE_TTL_MS) {
            return cached;
        }
        const safeName = (targetAppName || '').replace(/[^a-zA-Z0-9 ]/g, '');
        const filterClause = targetAppName
            ? `$proc = Get-Process | Where-Object { $_.MainWindowTitle -match "${safeName}" -or $_.ProcessName -match "${safeName}" } | Select-Object -First 1`
            : `Add-Type @"
         using System;
         using System.Runtime.InteropServices;
         public class WinFg { [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow(); }
"@
         $hwnd = [WinFg]::GetForegroundWindow()
         $proc = Get-Process | Where-Object { $_.MainWindowHandle -eq $hwnd } | Select-Object -First 1`;
        const psScript = `
      Add-Type -AssemblyName UIAutomationClient
      Add-Type -AssemblyName UIAutomationTypes
      ${filterClause}
      if (-not $proc -or $proc.MainWindowHandle -eq 0) {
        Write-Output "NONE|Desktop"
        exit
      }
      $root = [System.Windows.Automation.AutomationElement]::FromHandle($proc.MainWindowHandle)
      Write-Output "$($proc.ProcessName)|$($proc.MainWindowTitle)"

      $walker = [System.Windows.Automation.TreeWalker]::ControlViewWalker
      $queue = New-Object System.Collections.Generic.Queue[System.Windows.Automation.AutomationElement]
      $queue.Enqueue($root)
      $count = 0

      while ($queue.Count -gt 0 -and $count -lt 65) {
        $el = $queue.Dequeue()
        try {
          $name = $el.Current.Name
          $type = $el.Current.ControlType.ProgrammaticName -replace "ControlType\\.", ""
          $id = $el.Current.AutomationId
          $rect = $el.Current.BoundingRectangle
          if ($name -and $rect.Width -gt 8 -and $rect.Height -gt 8 -and $rect.Width -lt 1600) {
            $cleanName = $name -replace "[\\r\\n\\|]", " "
            Write-Output "EL|$cleanName|$type|$id|$([int]$rect.Left)|$([int]$rect.Top)|$([int]$rect.Width)|$([int]$rect.Height)"
            $count++
          }
          $child = $walker.GetFirstChild($el)
          $depthCount = 0
          while ($child -ne $null -and $depthCount -lt 25) {
            $queue.Enqueue($child)
            $child = $walker.GetNextSibling($child)
            $depthCount++
          }
        } catch {}
      }
    `;
        const elements = [];
        let processName = targetAppName || 'ActiveApp';
        let windowTitle = targetAppName || 'Application Window';
        try {
            const { stdout } = await execFileAsync('powershell.exe', [
                '-NoProfile',
                '-NonInteractive',
                '-Command',
                psScript,
            ], { timeout: 3500 });
            const lines = (stdout || '').split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
            if (lines.length > 0 && !lines[0].startsWith('EL|')) {
                const [pName, wTitle] = lines[0].split('|');
                processName = pName || processName;
                windowTitle = wTitle || windowTitle;
            }
            for (const line of lines) {
                if (!line.startsWith('EL|'))
                    continue;
                const [, name, controlType, automationId, x, y, width, height] = line.split('|');
                elements.push({
                    name: name.slice(0, 42),
                    controlType,
                    automationId: automationId || '',
                    x: Number(x) || 100,
                    y: Number(y) || 100,
                    width: Number(width) || 80,
                    height: Number(height) || 30,
                });
            }
        }
        catch {
            // Fallback if the UIA tree is locked or the target is elevated.
        }
        const snapshot = { processName, windowTitle, scannedAt: Date.now(), elements };
        this.cache.set(cacheKey, snapshot);
        return snapshot;
    }
    /**
     * Builds a visual guide over the exact scanned UI controls.
     *
     * Deviation from the original: highlighted controls use the new UIRECT type
     * (absolute screen coordinates, never clamped into the left diagram zone) -
     * the original emitted [BOX] which our layout engine rightfully repositions
     * into the diagram zone, defeating the point of pointing at a real control.
     * Per-control instructions live in the UIRECT label pill instead of WRITE
     * cards, so right-side controls can never collide with the note column.
     */
    static async buildInteractiveAppLesson(userPrompt) {
        const appMatch = userPrompt.match(/\b(?:teach|scan|explain|use|in|open)\s+([a-zA-Z0-9_.\s]{2,25})/i);
        const targetApp = appMatch ? appMatch[1].trim() : undefined;
        const snap = await this.scanActiveOrNamedApp(targetApp);
        const commands = [
            {
                type: 'BOARD',
                label: `AppScanner Deep Guide • ${snap.windowTitle} (${snap.elements.length} Controls Indexed)`,
            },
        ];
        const keywords = userPrompt.toLowerCase().split(/\W+/).filter((w) => w.length > 2);
        const scored = snap.elements
            .map((el) => {
            const nameLower = el.name.toLowerCase();
            const score = keywords.reduce((acc, kw) => acc + (nameLower.includes(kw) ? 10 : 0), 0);
            return { el, score };
        })
            .sort((a, b) => b.score - a.score);
        const picked = scored.slice(0, 4).map((s) => s.el);
        if (picked.length > 0) {
            picked.forEach((el, idx) => {
                const colors = ['cyan', 'yellow', 'green', 'orange'];
                commands.push({
                    type: 'UIRECT',
                    x: el.x,
                    y: el.y,
                    w: el.width,
                    h: el.height,
                    label: `Step ${idx + 1}: Click "${el.name}" [${el.controlType}]`,
                    color: colors[idx % colors.length],
                });
            });
        }
        else {
            commands.push({ type: 'WRITE', label: `AppScanner Target: ${snap.windowTitle}`, color: 'cyan' }, { type: 'WRITE', label: '1. Top Menu / Ribbon: File, Edit, View & Project Settings', color: 'yellow' }, { type: 'WRITE', label: '2. Primary Workspace Canvas: Main editing & creation viewport', color: 'green' }, { type: 'WRITE', label: '3. Inspector / Properties Panel: Fine-tune active tool parameters', color: 'orange' });
        }
        return commands;
    }
}
exports.DynamicAppScannerAndTeacher = DynamicAppScannerAndTeacher;
