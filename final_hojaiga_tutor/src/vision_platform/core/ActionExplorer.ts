import { IPlatformEnv } from '../platform/PlatformWrapper';
import { OllamaVisionAPI } from '../llm/OllamaVision';
import { AppScanner } from '../engine/AppScanner';
import { AgentAction, UIElement } from '../types';
import { execFile } from 'child_process';
import { promisify } from 'util';

const execFileAsync = promisify(execFile);

export interface ClickType {
  type: 'left' | 'right' | 'double' | 'drag';
  description: string;
}

export interface DiscoveredAction {
  element: UIElement;
  clickType: ClickType;
  result: string;
  screenshot: string;
}

export class ActionExplorer {
  private discoveredActions: DiscoveredAction[] = [];
  private discoveredShortcuts: Map<string, string> = new Map(); // shortcut -> description

  constructor(
    private env: IPlatformEnv,
    private llm: OllamaVisionAPI,
    private scanner: AppScanner
  ) {}

  /**
   * Explore all UI elements by trying different click types
   */
  async exploreAllClickTypes(uiElements: UIElement[]): Promise<DiscoveredAction[]> {
    console.log('[ActionExplorer] Exploring all click types...');

    const results: DiscoveredAction[] = [];

    for (const element of uiElements.slice(0, 10)) { // Limit to 10 elements to avoid infinite loops
      console.log(`[ActionExplorer] Exploring element: ${element.text || element.type}`);

      // Try left click
      const leftClickResult = await this.tryClick(element, 'left');
      if (leftClickResult) results.push(leftClickResult);

      // Try right click (context menu)
      const rightClickResult = await this.tryClick(element, 'right');
      if (rightClickResult) results.push(rightClickResult);

      // Try double click
      const doubleClickResult = await this.tryClick(element, 'double');
      if (doubleClickResult) results.push(doubleClickResult);

      // Return to original state
      await this.env.executeAction({ actionType: 'type', payload: '{ESC}' });
      await new Promise(resolve => setTimeout(resolve, 500));
    }

    this.discoveredActions = results;
    return results;
  }

  /**
   * Try a specific click type on an element
   */
  private async tryClick(element: UIElement, clickType: ClickType['type']): Promise<DiscoveredAction | null> {
    const beforeScreenshot = await this.env.captureScreen();

    const center = this.scanner.getElementCenter(element);

    // Execute click
    switch (clickType) {
      case 'left':
        await this.executeLeftClick(center.x, center.y);
        break;
      case 'right':
        await this.executeRightClick(center.x, center.y);
        break;
      case 'double':
        await this.executeDoubleClick(center.x, center.y);
        break;
    }

    await new Promise(resolve => setTimeout(resolve, 1000));

    const afterScreenshot = await this.env.captureScreen();

    // Analyze what happened
    const analysis = await this.llm.analyzeScreen(afterScreenshot,
      `What happened after clicking "${element.text || element.type}" with ${clickType} click? Describe the result.`);

    const result = analysis[0]?.payload || 'No visible change';

    return {
      element,
      clickType: { type: clickType, description: `${clickType} click` },
      result,
      screenshot: afterScreenshot
    };
  }

  /**
   * Execute left click
   */
  private async executeLeftClick(x: number, y: number): Promise<void> {
    await this.env.executeAction({
      actionType: 'click',
      targetCoordinates: { x, y }
    });
  }

  /**
   * Execute right click (context menu)
   */
  private async executeRightClick(x: number, y: number): Promise<void> {
    // PowerShell right click
    const psScript = `
      Add-Type @"
        using System;
        using System.Runtime.InteropServices;
        public class MouseClick {
          [DllImport("user32.dll")]
          public static extern void mouse_event(uint dwFlags, uint dx, uint dy, uint cButtons, uint dwExtraInfo);
          public const uint MOUSEEVENTF_RIGHTDOWN = 0x08;
          public const uint MOUSEEVENTF_RIGHTUP = 0x10;
          public const uint MOUSEEVENTF_MOVE = 0x0001;
        }
"@
      [MouseClick]::mouse_event([MouseClick]::MOUSEEVENTF_MOVE, ${x}, ${y}, 0, 0);
      Start-Sleep -Milliseconds 50
      [MouseClick]::mouse_event([MouseClick]::MOUSEEVENTF_RIGHTDOWN, 0, 0, 0, 0);
      Start-Sleep -Milliseconds 50
      [MouseClick]::mouse_event([MouseClick]::MOUSEEVENTF_RIGHTUP, 0, 0, 0, 0);
    `;

    await execFileAsync('powershell.exe', ['-NoProfile', '-NonInteractive', '-Command', psScript]);
  }

  /**
   * Execute double click
   */
  private async executeDoubleClick(x: number, y: number): Promise<void> {
    await this.executeLeftClick(x, y);
    await new Promise(resolve => setTimeout(resolve, 100));
    await this.executeLeftClick(x, y);
  }

  /**
   * Explore empty regions (right-click to see context menu)
   */
  async exploreEmptyRegions(): Promise<void> {
    console.log('[ActionExplorer] Exploring empty regions with right-click...');

    // Get screen dimensions
    const screenshot = await this.env.captureScreen();
    const analysis = await this.llm.analyzeScreen(screenshot,
      'Identify 3 empty regions on this screen (areas with no UI elements). Return coordinates: [{"x": 100, "y": 200}, ...]');

    for (const action of analysis) {
      if (action.targetCoordinates) {
        const before = await this.env.captureScreen();
        await this.executeRightClick(action.targetCoordinates.x, action.targetCoordinates.y);
        await new Promise(resolve => setTimeout(resolve, 1000));

        const after = await this.env.captureScreen();
        const menuAnalysis = await this.llm.analyzeScreen(after,
          'What context menu appeared? List all menu items and their functions.');

        await this.env.executeAction({
          actionType: 'explain',
          payload: `Right-clicking at (${action.targetCoordinates.x}, ${action.targetCoordinates.y}) shows: ${menuAnalysis[0]?.payload || 'No menu'}`
        });

        await this.env.executeAction({ actionType: 'type', payload: '{ESC}' });
        await new Promise(resolve => setTimeout(resolve, 500));
      }
    }
  }

  /**
   * Discover keyboard shortcuts
   */
  async discoverShortcuts(): Promise<Map<string, string>> {
    console.log('[ActionExplorer] Discovering keyboard shortcuts...');

    const commonShortcuts = [
      { keys: 'Ctrl+C', description: 'Copy' },
      { keys: 'Ctrl+V', description: 'Paste' },
      { keys: 'Ctrl+X', description: 'Cut' },
      { keys: 'Ctrl+Z', description: 'Undo' },
      { keys: 'Ctrl+Y', description: 'Redo' },
      { keys: 'Ctrl+S', description: 'Save' },
      { keys: 'Ctrl+O', description: 'Open' },
      { keys: 'Ctrl+N', description: 'New' },
      { keys: 'Ctrl+F', description: 'Find' },
      { keys: 'Ctrl+A', description: 'Select All' },
      { keys: 'Ctrl+W', description: 'Close' },
      { keys: 'Ctrl+P', description: 'Print' },
      { keys: 'F1', description: 'Help' },
      { keys: 'F5', description: 'Refresh' },
      { keys: 'Delete', description: 'Delete' },
      { keys: 'Space', description: 'Play/Pause' },
    ];

    const screenshot = await this.env.captureScreen();

    // Use LLM to identify which shortcuts are relevant to this app
    const shortcutAnalysis = await this.llm.analyzeScreen(screenshot,
      `Analyze this application and identify which keyboard shortcuts are likely to work. Consider the app type (media player, editor, browser, etc.). Return JSON array: [{"keys": "Ctrl+S", "description": "Save", "relevant": true/false}]`);

    for (const action of shortcutAnalysis) {
      if (action.payload) {
        try {
          const shortcutData = JSON.parse(action.payload);
          if (shortcutData.relevant) {
            this.discoveredShortcuts.set(shortcutData.keys, shortcutData.description);
          }
        } catch {
          // Skip if JSON parse fails
        }
      }
    }

    console.log(`[ActionExplorer] Discovered ${this.discoveredShortcuts.size} shortcuts`);
    return this.discoveredShortcuts;
  }

  /**
   * Get all discovered actions
   */
  getDiscoveredActions(): DiscoveredAction[] {
    return this.discoveredActions;
  }

  /**
   * Get all discovered shortcuts
   */
  getDiscoveredShortcuts(): Map<string, string> {
    return this.discoveredShortcuts;
  }
}
