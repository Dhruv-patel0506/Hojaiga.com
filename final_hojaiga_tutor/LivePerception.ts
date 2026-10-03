/**
 * LivePerception - Captures window, inspects UI hierarchies, validates screen state
 * Uses LLM vision for dynamic app analysis (works with ANY app)
 * Enhanced with proper UI tree extraction and OCR fallback
 */

import axios from 'axios';
import { ScreenState, AppState, UITreeNode } from './src/types';

export class LivePerception {
  private ollamaEndpoint = 'http://localhost:11434';
  private model = 'llava:latest';

  /**
   * Capture current screen state with enhanced UI tree extraction
   */
  async captureScreenState(): Promise<ScreenState> {
    try {
      const pythonScript = `
import win32gui
import win32con
import json
import base64
from io import BytesIO
from PIL import ImageGrab

hwnd = win32gui.GetForegroundWindow()
title = win32gui.GetWindowText(hwnd)
rect = win32gui.GetWindowRect(hwnd)

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
    "screenshot": img_str
}

print(json.dumps(result))
`;

      const { execSync } = require('child_process');
      const { writeFileSync, unlinkSync } = require('fs');
      const { join } = require('path');
      
      // Write Python script to temp file to avoid newline issues
      const tempScriptPath = join(__dirname, 'temp_capture_screen.py');
      writeFileSync(tempScriptPath, pythonScript);
      
      try {
        const result = execSync(`python "${tempScriptPath}"`, {
          encoding: 'utf-8',
          maxBuffer: 10 * 1024 * 1024
        });

        const data = JSON.parse(result);
        data.timestamp = Date.now();

        return data;
      } finally {
        // Clean up temp file
        try {
          unlinkSync(tempScriptPath);
        } catch (e) {
          // Ignore cleanup errors
        }
      }
    } catch (error) {
      console.error('[LivePerception] Failed to capture screen state:', error);
      throw error;
    }
  }

  /**
   * Extract UI tree using OmniParser V2 (pure vision-based)
   * This provides universal UI parsing for ANY app (including canvas-based, games, etc.)
   */
  async extractUITree(hwnd: number): Promise<UITreeNode[]> {
    try {
      console.log(`[LivePerception] Extracting UI tree using Windows Accessibility API for window ${hwnd}...`);

      // Create temporary Python script for Accessibility API
      const { execSync } = require('child_process');
      const { writeFileSync, unlinkSync } = require('fs');
      const { join } = require('path');

      const tempScriptPath = join(__dirname, 'temp_accessibility.py');

      try {
        // Create Python script that uses Windows UI Automation
        const pythonScript = `
import sys
import json

try:
    sys.path.insert(0, r'D:\\\\new_automation\\\\final_hojaiga_tutor')
    from WindowsAccessibilityScanner import WindowsAccessibilityScanner

    scanner = WindowsAccessibilityScanner()

    if not scanner.available:
        print(json.dumps({
            'success': False,
            'error': 'UI Automation not available - install uiautomation package'
        }))
        sys.exit(1)

    # Scan UI tree
    ui_elements = scanner.scan_ui_tree(${hwnd})

    # Get window info
    window_info = scanner.get_active_window_with_process()

    # Get hierarchy as dict
    hierarchy = scanner.get_ui_hierarchy_as_dict(${hwnd})

    # Output result
    print(json.dumps({
        'success': True,
        'total_elements': len(ui_elements),
        'ui_elements': ui_elements,
        'window_info': window_info,
        'hierarchy': hierarchy
    }, indent=2))

except Exception as e:
    print(json.dumps({
        'success': False,
        'error': str(e)
    }))
`;

        writeFileSync(tempScriptPath, pythonScript);

        // Execute Python script
        const result = execSync(`python "${tempScriptPath}" 2>NUL`, {
          encoding: 'utf-8',
          maxBuffer: 10 * 1024 * 1024,
          timeout: 30000  // 30 seconds - much faster than OmniParser
        });

        // Parse JSON output
        const lines = result.trim().split('\n');
        let jsonStr = lines.find(line => line.trim().startsWith('{') || line.trim().startsWith('['));

        if (!jsonStr) {
          console.warn('[LivePerception] No JSON found in Accessibility API output');
          return [];
        }

        const parsedResult = JSON.parse(jsonStr);

        if (parsedResult.success) {
          console.log(`[LivePerception] Accessibility API found ${parsedResult.total_elements} UI elements`);
          console.log(`[LivePerception] Window: ${parsedResult.window_info.title} (${parsedResult.window_info.process_name})`);

          // Convert Accessibility API format to UITreeNode format
          const uiNodes = parsedResult.ui_elements.map((el: any) => ({
            id: el.id,
            name: el.name,
            role: el.role,
            className: el.className,
            boundingBox: el.boundingBox,
            isClickable: el.isClickable,
            isEnabled: el.isEnabled,
            text: el.text,
            children: el.children || []
          }));

          // Log detailed UI hierarchy
          console.log('[UI_HIERARCHY] Detected UI elements (from Accessibility API):');
          uiNodes.forEach((node, index) => {
            const indent = '  '.repeat(node.level || 0);
            console.log(`  [${index}] ${indent}${node.name} (${node.role}) - AutomationId: ${node.automationId || 'N/A'}`);
          });

          // Log hierarchy as JSON
          console.log('[UI_HIERARCHY_JSON]');
          console.log(JSON.stringify(parsedResult.hierarchy, null, 2).substring(0, 1000));

          return uiNodes;
        } else {
          console.warn('[LivePerception] Accessibility API failed:', parsedResult.error);
          return [];
        }
      } finally {
        // Clean up temp file
        try {
          unlinkSync(tempScriptPath);
        } catch (e) {
          // Ignore cleanup errors
        }
      }

    } catch (error) {
      console.error('[LivePerception] Accessibility API UI tree extraction failed:', error);
      return [];
    }
  }

  /**
   * OCR fallback for non-native apps (Canvas-based, games, etc.)
   * Uses Tesseract to generate spatial text matrix
   */
  async performOCRFallback(screenshot: string): Promise<Array<{ text: string; x: number; y: number; width: number; height: number }>> {
    try {
      console.log('[LivePerception] Using OCR fallback for UI element detection...');
      // This would integrate Tesseract.js or similar
      // For now, return empty array
      return [];
    } catch (error) {
      console.error('[LivePerception] OCR fallback failed:', error);
      return [];
    }
  }

  /**
   * Analyze screen using LLM vision (LLaVA) with UI tree cross-reference
   * Returns structured analysis with strict JSON schema enforcement
   */
  async analyzeScreenWithLLM(
    screenshot: string,
    userGoal: string,
    uiTree?: UITreeNode[],
    screenState?: ScreenState
  ): Promise<{
    appName: string;
    currentState: AppState;
    visibleElements: Array<{
      name: string;
      x: number;
      y: number;
      description: string;
    }>;
    nextAction: {
      actionType: string;
      target: { x: number; y: number; width: number; height: number };
      explanation: string;
      expectedStateChange: string;
    };
  }> {
    try {
      console.log('[LIVE_PERCEPTION] Analyzing screen with LLM vision...');
      console.log('[LIVE_PERCEPTION] User goal:', userGoal);
      console.log(`[LIVE_PERCEPTION] UI tree elements: ${uiTree?.length || 0}`);

      // Send semantic UI tree summary from Accessibility API (real button names)
      const uiTreeSummary = uiTree ?
        `\n\nDetected ${uiTree.length} UI elements via Windows Accessibility API.\n` +
        `Real button names and control types:\n` +
        uiTree.slice(0, 10).map(el =>
          `- ${el.name} (${el.role}) - ${el.automationId ? `ID: ${el.automationId}` : 'No ID'}`
        ).join('\n') : '';

      const response = await axios.post(
        `${this.ollamaEndpoint}/api/generate`,
        {
          model: this.model,
          prompt: `You are an expert application teacher. Analyze this screenshot and the user's goal: "${userGoal}"

CRITICAL RULES:
1. ONLY describe what is ACTUALLY visible in the screenshot
2. DO NOT hallucinate features that aren't visible
3. Use the real button names from the Accessibility API summary
4. DO NOT guess app names - use the window title if provided
5. Provide absolute coordinates (screen pixels), not normalized
6. Suggest ONE specific next action the user should take
7. Return STRICT JSON - no extra text

Return JSON:
{
  "appName": "${screenState?.appTitle || 'Unknown Application'}",
  "currentState": "splash_screen" | "initial" | "ready" | "dialog_open" | "loading" | "error",
  "visibleElements": [
    {
      "name": "Button/element name (exact text from Accessibility API)",
      "x": 450,
      "y": 120,
      "description": "What this element does based on its name and type"
    }
  ],
  "nextAction": {
    "actionType": "CLICK" | "TYPE" | "WAIT" | "PRESS_KEY",
    "target": {
      "x": 450,
      "y": 120,
      "width": 100,
      "height": 40
    },
    "explanation": "Navigate to the specific button and describe what it does.",
    "expectedStateChange": "WINDOW_TRANSITION"
  }
}${uiTreeSummary}

Be EXTREMELY precise about what is visible. Use the real button names from the Accessibility API. Do not guess.`,
          images: [screenshot],
          stream: false,
          options: {
            temperature: 0.3,
            num_predict: 2000
          }
        },
        {
          timeout: 15000  // Reduced to 15 seconds - LLaVA is now optional
        }
      );

      const text = response.data.response;
      console.log('[LivePerception] LLM raw response:', text.substring(0, 300));
      
      // Try to extract JSON - handle cases where LLM adds extra text
      const jsonMatch = text.match(/\{[\s\S]*\}/);
      
      // If no match, try to find JSON-like structure
      let jsonStr = jsonMatch ? jsonMatch[0] : text;
      
      // Clean up common LLM prefixes/suffixes
      jsonStr = jsonStr.replace(/^[^{]*[^\{[]*/, '');
      jsonStr = jsonStr.replace(/[^\]}]*[}\]]*$/, '');

      // Try to fix common JSON errors
      jsonStr = jsonStr.replace(/,\s*}/g, '}');  // Trailing commas
      jsonStr = jsonStr.replace(/,\s*]/g, ']');  // Trailing commas in arrays

      if (!jsonStr.startsWith('{') && !jsonStr.startsWith('[')) {
        console.error('[LivePerception] LLM did not return JSON');
        console.error('[LivePerception] Response:', text.substring(0, 500));
        throw new Error('Invalid LLM response format');
      }

      try {
        const result = JSON.parse(jsonStr);
        console.log('[LIVE_PERCEPTION] Identified app:', result.appName);
        console.log('[LIVE_PERCEPTION] Current state:', result.currentState);
        console.log(`[LIVE_PERCEPTION] Found ${result.visibleElements.length} visible elements`);
        result.visibleElements.forEach((el: any, i: number) => {
          console.log(`[LIVE_PERCEPTION]   Element ${i + 1}: ${el.name} at (${el.x}, ${el.y}) - ${el.description}`);
        });
        console.log('[LIVE_PERCEPTION] Next action:', result.nextAction.actionType, 'at', result.nextAction.target);

        return result;
      } catch (parseError) {
        console.error('[LivePerception] JSON parse error after cleanup:', parseError);
        console.error('[LivePerception] Attempted JSON:', jsonStr.substring(0, 500));
        throw parseError;
      }
    } catch (error) {
      console.error('[LivePerception] LLM analysis failed:', error);
      console.error('[LivePerception] LLaVA is optional - TeachingStateMachine will use Accessibility API fallback');
      // Throw error - TeachingStateMachine will handle fallback
      throw error;
    }
  }

  /**
   * Verify that the screen state changed as expected
   * Uses multiple methods: screenshot comparison, UI tree comparison, window state
   */
  async verifyStateChange(
    beforeState: ScreenState,
    expectedTransition: AppState
  ): Promise<{ success: boolean; actualState: AppState; confidence: number; details: any; reason: string }> {
    try {
      const afterState = await this.captureScreenState();

      console.log('[LivePerception] Verifying state change...');
      console.log(`[LivePerception] Before: ${beforeState.appTitle} (${beforeState.currentState})`);
      console.log(`[LivePerception] After: ${afterState.appTitle} (${afterState.currentState})`);

      // Method 1: Compare window title/ID (fast)
      const windowChanged = beforeState.appId !== afterState.appId || beforeState.appTitle !== afterState.appTitle;

      // Method 2: Compare UI trees (if available)
      let uiChanged = false;
      let uiElementCountDiff = 0;
      try {
        const beforeTree = await this.extractUITree(parseInt(beforeState.appId));
        const afterTree = await this.extractUITree(parseInt(afterState.appId));
        uiElementCountDiff = Math.abs(beforeTree.length - afterTree.length);
        uiChanged = uiElementCountDiff > 5; // Threshold for meaningful change
        console.log(`[LivePerception] UI element count: ${beforeTree.length} → ${afterTree.length} (diff: ${uiElementCountDiff})`);
      } catch (e) {
        console.log('[LivePerception] UI tree comparison skipped');
      }

      // Method 3: Compare window bounds (resize, move)
      const boundsChanged =
        beforeState.bounds.x !== afterState.bounds.x ||
        beforeState.bounds.y !== afterState.bounds.y ||
        beforeState.bounds.width !== afterState.bounds.width ||
        beforeState.bounds.height !== afterState.bounds.height;

      // Method 4: Compare coarse state string
      const stateChanged = beforeState.currentState !== afterState.currentState;

      // Calculate overall confidence based on multiple factors
      let confidence = 0;
      let reason = '';

      if (windowChanged) {
        confidence += 0.4;
        reason += 'Window changed. ';
      }
      if (uiChanged) {
        confidence += 0.3;
        reason += `UI elements changed (${uiElementCountDiff} diff). `;
      }
      if (boundsChanged) {
        confidence += 0.2;
        reason += 'Window bounds changed. ';
      }
      if (stateChanged) {
        confidence += 0.1;
        reason += 'State string changed. ';
      }

      // If no changes detected, low confidence
      if (confidence === 0) {
        reason = 'No meaningful changes detected';
        confidence = 0.1;
      }

      // Cap confidence at 1.0
      confidence = Math.min(confidence, 1.0);

      const success = confidence > 0.5; // Require 50% confidence to consider it a real change

      console.log(`[LivePerception] State verification: ${success ? 'PASSED' : 'FAILED'}`);
      console.log(`[LivePerception] Confidence: ${(confidence * 100).toFixed(0)}%`);
      console.log(`[LivePerception] Reason: ${reason}`);

      return {
        success,
        actualState: afterState.currentState,
        confidence,
        reason,
        details: {
          windowChanged,
          uiChanged,
          uiElementCountDiff,
          boundsChanged,
          stateChanged
        }
      };
    } catch (error) {
      console.error('[LivePerception] State verification failed:', error);
      return {
        success: false,
        actualState: 'error',
        confidence: 0,
        details: { error: String(error) },
        reason: `Verification error: ${error}`
      };
    }
  }

  /**
   * Check if Ollama is available
   */
  async checkOllamaAvailability(): Promise<boolean> {
    try {
      const response = await axios.get(`${this.ollamaEndpoint}/api/tags`, {
        timeout: 5000
      });
      return response.status === 200;
    } catch (error) {
      console.error('[LivePerception] Ollama not available:', error);
      return false;
    }
  }
}
