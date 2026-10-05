import { IPlatformEnv } from '../platform/PlatformWrapper';
import { OllamaVisionAPI } from '../llm/OllamaVision';
import { AppScanner } from '../engine/AppScanner';
import { ScreenState, AgentAction, TeachingContext } from '../types';

export class TeacherAgent {
  private isMonitoring = false;
  private scanIntervalMs = 2000; // Watch screen every 2 seconds
  private maxSteps = 20; // Safety limit
  private stepCount = 0;
  private consecutiveEmptyActions = 0;
  private maxEmptyActions = 3; // Stop after 3 consecutive empty action responses

  constructor(
    private env: IPlatformEnv,
    private llm: OllamaVisionAPI,
    private scanner: AppScanner
  ) {}

  async startTeaching(goal: string): Promise<void> {
    this.isMonitoring = true;
    this.stepCount = 0;
    this.consecutiveEmptyActions = 0;

    console.log(`[TEACHER] Starting lesson: ${goal}`);

    // Check if Ollama is available
    const ollamaAvailable = await this.llm.checkOllamaAvailable();
    if (!ollamaAvailable) {
      console.error('[TEACHER] Ollama is not running. Please start Ollama with: ollama serve');
      console.error('[TEACHER] Then pull a vision model: ollama pull llava');
      this.isMonitoring = false;
      return;
    }

    console.log('[TEACHER] Ollama is available. Beginning teaching loop...');

    while (this.isMonitoring && this.stepCount < this.maxSteps) {
      try {
        // 1. Capture State
        const base64Img = await this.env.captureScreen();
        const appInfo = await this.env.getActiveWindowInfo();

        console.log(`[TEACHER] Step ${this.stepCount + 1}/${this.maxSteps} - App: ${appInfo.processName}`);

        // 2. OCR Backup (Optional, use if LLM vision fails to find exact coordinates)
        const uiElements = await this.scanner.performOCR(base64Img);
        const layoutState = await this.scanner.determineLayoutState(uiElements);

        console.log(`[TEACHER] Layout state: ${layoutState}, UI elements found: ${uiElements.length}`);

        const screenState: ScreenState = {
          screenshotBase64: base64Img,
          elements: uiElements,
          timestamp: Date.now(),
          appContext: appInfo
        };

        // 3. LLM Vision Analysis & Decision Making
        const actions = await this.llm.analyzeScreen(base64Img, goal);

        // 4. Action Execution
        if (actions.length === 0) {
          this.consecutiveEmptyActions++;
          console.log(`[TEACHER] No actions returned (${this.consecutiveEmptyActions}/${this.maxEmptyActions})`);

          if (this.consecutiveEmptyActions >= this.maxEmptyActions) {
            console.log('[TEACHER] Goal appears complete or blocked. Stopping.');
            this.isMonitoring = false;
            break;
          }
        } else {
          this.consecutiveEmptyActions = 0;
          this.stepCount++;

          for (const action of actions) {
            if (!this.isMonitoring) break;

            console.log(`[TEACHER] Executing action: ${action.actionType}`);

            if (action.actionType === 'explain') {
              // Speak to user before acting
              await this.env.executeAction(action);
              // Wait for user to absorb explanation
              await new Promise(resolve => setTimeout(resolve, 2000));
            } else if (action.actionType === 'click' || action.actionType === 'type') {
              // Execute UI automation
              await this.env.executeAction(action);
              // Wait for UI to change
              await new Promise(resolve => setTimeout(resolve, 1500));
            } else if (action.actionType === 'wait') {
              await this.env.executeAction(action);
            } else if (action.actionType === 'highlight') {
              await this.env.executeAction(action);
              await new Promise(resolve => setTimeout(resolve, 1000));
            }
          }
        }

        // Wait before next scan
        await new Promise(resolve => setTimeout(resolve, this.scanIntervalMs));

      } catch (error) {
        console.error('[TEACHER] Error in teaching loop:', error);
        await new Promise(resolve => setTimeout(resolve, 3000)); // Wait longer on error
      }
    }

    console.log('[TEACHER] Teaching session ended');
    this.scanner.cleanup();
  }

  stopTeaching(): void {
    console.log('[TEACHER] Stop requested');
    this.isMonitoring = false;
  }

  getStatus(): { isMonitoring: boolean; stepCount: number } {
    return {
      isMonitoring: this.isMonitoring,
      stepCount: this.stepCount
    };
  }
}
