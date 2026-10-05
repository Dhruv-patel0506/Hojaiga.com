/**
 * TeachingStateMachine - The step-verify-proceed event loop
 * State machine that executes teaching steps with verification
 * Enhanced with OverlayEngine for visual anchoring
 * Enhanced with RAG for documentation-based teaching
 */

import { WindowManager } from './WindowManager';
import { SafeOSController } from './SafeOSController';
import { LivePerception } from './LivePerception';
import { OverlayEngine } from './OverlayEngine';
import { AppKnowledgeManager } from './AppKnowledgeManager';
import { AppKnowledgeRAG } from './rag/AppKnowledgeRAG';
import { TeacherRAGWrapper } from './rag/TeacherRAGWrapper';
import {
  TeachingAction,
  ActionStep,
  ScreenState,
  StateVerification,
  TeachingEvent,
  EventListener,
  EmergencyStopSignal,
  SafetyConfig
} from './src/types';

export class TeachingStateMachine {
  private windowManager: WindowManager;
  private osController: SafeOSController;
  private perception: LivePerception;
  private overlayEngine: OverlayEngine;
  private appKnowledge: AppKnowledgeManager;
  private ragEngine: AppKnowledgeRAG;
  private ragWrapper: TeacherRAGWrapper;
  private eventListeners: EventListener[] = [];
  private isRunning = false;
  private safetyConfig: SafetyConfig;
  private useRAG: boolean = false;  // Flag to enable/disable RAG

  constructor(safetyConfig?: Partial<SafetyConfig>, useRAG: boolean = false) {
    this.windowManager = new WindowManager();
    this.osController = new SafeOSController();
    this.perception = new LivePerception();
    this.overlayEngine = new OverlayEngine();
    this.appKnowledge = new AppKnowledgeManager();
    this.useRAG = useRAG;

    // Initialize RAG if enabled
    if (useRAG) {
      this.ragEngine = new AppKnowledgeRAG();
      this.ragWrapper = new TeacherRAGWrapper(this.ragEngine, 'http://127.0.0.1:11434', 'qwen2.5:7b');
      console.log('[TeachingStateMachine] RAG enabled - will use documentation for teaching');
    }

    this.safetyConfig = {
      maxActionsPerSession: 50,
      maxActionDuration: 5000,
      stateVerificationTimeout: 3000,
      inputBoundaryPadding: 20,
      enableKillSwitch: true,
      killSwitchZones: [
        { x: 0, y: 0, width: 50, height: 50 }, // Top-left corner
        { x: 0, y: 0, width: 50, height: 50 }, // Top-right corner
        { x: 0, y: 0, width: 50, height: 50 }, // Bottom-left corner
        { x: 0, y: 0, width: 50, height: 50 }  // Bottom-right corner
      ],
      blocklistApps: ['System', 'Windows Security', 'Task Manager'],
      requireConfirmationFor: ['hotkey', 'pressKey'],
      ...safetyConfig
    };
  }

  /**
   * Add event listener
   */
  on(listener: EventListener): void {
    this.eventListeners.push(listener);
  }

  /**
   * Emit event to all listeners
   */
  private emit(event: TeachingEvent): void {
    this.eventListeners.forEach(listener => listener(event));
  }

  /**
   * Load app documentation into RAG knowledge base
   */
  async loadAppDocumentation(appName: string, docPath: string): Promise<void> {
    if (!this.useRAG || !this.ragEngine) {
      console.warn('[TeachingStateMachine] RAG not enabled - cannot load documentation');
      return;
    }

    try {
      console.log(`[TeachingStateMachine] Loading documentation for ${appName} from ${docPath}`);
      await this.ragEngine.ingestMarkdownFile(appName, docPath);
      console.log(`[TeachingStateMachine] Documentation loaded successfully for ${appName}`);
    } catch (error) {
      console.error(`[TeachingStateMachine] Failed to load documentation: ${error}`);
      throw error;
    }
  }

  /**
   * Start interactive teaching session
   */
  async startTeaching(userGoal: string): Promise<void> {
    console.log(`[TeachingStateMachine] Starting teaching: ${userGoal}`);

    // Check Ollama availability
    const ollamaAvailable = await this.perception.checkOllamaAvailability();
    if (!ollamaAvailable) {
      this.emit({
        type: 'error',
        error: new Error('Ollama not available'),
        context: 'Cannot start teaching without Ollama'
      });
      return;
    }

    // Initialize overlay
    this.overlayEngine.initializeOverlay();
    this.overlayEngine.showOverlay();

    // Start kill switch listener
    this.osController.startKillSwitchListener();

    this.isRunning = true;
    let actionCount = 0;
    let steps: ActionStep[] = [];
    let discoveredElements: Array<{ name: string; description: string }> = [];

    try {
      // Focus the active window
      this.windowManager.focusWindow();

      // Initial screen capture
      const initialState = await this.perception.captureScreenState();
      console.log(`[TeachingStateMachine] Initial state: ${initialState.currentState}`);
      console.log(`[TeachingStateMachine] Window: ${initialState.appTitle}`);

      // Extract UI tree using Windows Accessibility API (replaces OmniParser)
      const uiTree = await this.perception.extractUITree(parseInt(initialState.appId));
      console.log(`[TeachingStateMachine] UI tree extracted: ${uiTree.length} nodes via Accessibility API`);

      // Build app knowledge - learn what buttons do
      console.log(`[TeachingStateMachine] Building knowledge for app: ${initialState.appTitle}`);
      const appKnowledge = this.appKnowledge.addButtonKnowledge(
        initialState.appId,
        uiTree,
        initialState.appTitle
      );
      console.log(`[TeachingStateMachine] App type: ${appKnowledge.appType}`);
      console.log(`[TeachingStateMachine] Buttons with semantic labels: ${appKnowledge.buttons.size}`);
      console.log(`[TeachingStateMachine] Window bounds: ${JSON.stringify(initialState.bounds)}`);

      // Small delay to reduce initial system load
      await this.sleep(1000);

      // Main teaching loop
      while (this.isRunning && actionCount < this.safetyConfig.maxActionsPerSession) {
        // Capture current state
        const currentState = await this.perception.captureScreenState();
        console.log(`[TeachingStateMachine] Current window: ${currentState.appTitle} (id: ${currentState.appId})`);

        // Analyze with LLM to get next action (with UI tree cross-reference)
        // Priority: RAG (documentation) > LLaVA (vision) > Accessibility API (fallback)
        let analysis;
        try {
          if (this.useRAG && this.ragWrapper && uiTree.length > 0) {
            // Use RAG with documentation
            console.log('[TeachingStateMachine] Using RAG for documentation-based teaching');
            
            // Convert UI tree to RAG format
            const uiElements = uiTree.map(el => ({
              name: el.name,
              automationId: el.automationId || '',
              controlType: el.role || 'Unknown',
              bounds: el.boundingBox || { x: 0, y: 0, width: 0, height: 0 }
            }));

            const ragDecision = await this.ragWrapper.determineNextStep(
              currentState.appTitle,
              userGoal,
              uiElements
            );

            // Guard clause: Ensure ragDecision is valid
            if (!ragDecision || !ragDecision.actionType) {
              console.error('[TeachingStateMachine] Invalid RAG decision received');
              console.error('[TeachingStateMachine] ragDecision:', ragDecision);
              throw new Error('Invalid RAG decision - missing actionType');
            }

            // Convert RAG decision to analysis format
            analysis = {
              appName: currentState.appTitle,
              currentState: currentState.currentState,
              visibleElements: uiElements.slice(0, 5).map(el => ({
                name: el.name,
                x: el.bounds.x,
                y: el.bounds.y,
                description: `${el.controlType} - ${el.automationId || 'No ID'}`
              })),
              nextAction: {
                actionType: ragDecision.actionType,
                target: {
                  x: uiElements[0]?.bounds.x || 0,
                  y: uiElements[0]?.bounds.y || 0,
                  width: uiElements[0]?.bounds.width || 100,
                  height: uiElements[0]?.bounds.height || 40
                },
                explanation: ragDecision.explanation,
                expectedStateChange: 'INTERACTION'
              }
            };

            console.log('[TeachingStateMachine] RAG decision successful');
          } else if (uiTree.length === 0) {
            console.warn('[TeachingStateMachine] No UI tree available - using fallback');
            analysis = this.generateFallbackAnalysis(uiTree, currentState, userGoal);
          } else {
            // Fallback to LLaVA vision model
            try {
              analysis = await this.perception.analyzeScreenWithLLM(
                currentState.screenshot,
                userGoal,
                uiTree,
                currentState
              );
              console.log('[TeachingStateMachine] LLM analysis successful');
            } catch (llmError) {
              console.warn('[TeachingStateMachine] LLM analysis failed - using Accessibility API fallback');
              console.warn('[TeachingStateMachine] LLaVA is optional - continuing with API-based analysis');
              analysis = this.generateFallbackAnalysis(uiTree, currentState, userGoal);
            }
          }
        } catch (fallbackError) {
          console.error('[TeachingStateMachine] Both RAG, LLM and fallback failed - stopping');
          this.emit({
            type: 'error',
            error: fallbackError as Error,
            context: 'Failed to generate action'
          });
          break;
        }

        // Store discovered elements
        analysis.visibleElements.forEach((el: any) => {
          if (!discoveredElements.find(e => e.name === el.name)) {
            discoveredElements.push({ name: el.name, description: el.description });
          }
        });

        // Create action step
        const action: TeachingAction = {
          id: `action_${actionCount}`,
          actionType: (analysis.nextAction.actionType.toLowerCase()) as any,
          targetName: analysis.visibleElements[0]?.name || `Element at (${analysis.nextAction.target.x}, ${analysis.nextAction.target.y})`,
          normalizedCoords: {
            x: analysis.nextAction.target.x / currentState.bounds.width,
            y: analysis.nextAction.target.y / currentState.bounds.height
          },
          description: analysis.nextAction.explanation,
          expectedTransition: analysis.nextAction.expectedStateChange as any,
          confidence: 0.8
        };

        const step: ActionStep = {
          stepNumber: actionCount + 1,
          action,
          explanation: analysis.nextAction.explanation,
          verificationCriteria: `State should transition to ${analysis.nextAction.expectedStateChange}`
        };

        this.emit({ type: 'stepStart', step });

        // Detach virtual cursor - Clicky works independently (magenta)
        this.overlayEngine.detachVirtualCursor();

        // Draw visual anchoring (pulse ring or fake cursor)
        this.overlayEngine.drawFakeCursor(
          analysis.nextAction.target.x,
          analysis.nextAction.target.y,
          analysis.nextAction.explanation
        );

        // Execute the action with window bounds for coordinate mapping
        await this.executeAction(action, currentState, currentState.bounds);

        // Clear overlay after action
        await this.sleep(500);
        this.overlayEngine.clearDrawings();

        // Wait for state transition
        await this.sleep(2000);  // Increased to reduce system load

        // Verify state change
        const verification = await this.verifyStateChange(currentState, action.expectedTransition);

        this.emit({ type: 'stepComplete', step, verification });

        if (!verification.success) {
          console.warn(`[TeachingStateMachine] State verification failed: ${verification.reason}`);
          console.warn(`[TeachingStateMachine] Confidence: ${(verification.confidence * 100).toFixed(0)}%`);
          if (verification.details) {
            console.warn(`[TeachingStateMachine] Details:`, verification.details);
          }

          // If confidence is very low (< 20%), stop to prevent useless retries
          if (verification.confidence < 0.2) {
            console.error('[TeachingStateMachine] ABORTING: Confidence too low - action likely ineffective');
            this.emit({
              type: 'stepFailed',
              step,
              error: `Low confidence (${(verification.confidence * 100).toFixed(0)}%) - ${verification.reason}`
            });
            break;
          }

          // If confidence is moderate (20-50%), warn but continue
          console.warn('[TeachingStateMachine] Continuing despite low confidence - action may have partial effect');
          this.emit({
            type: 'stepFailed',
            step,
            error: `Low confidence (${(verification.confidence * 100).toFixed(0)}%) - ${verification.reason}`
          });
          // Continue anyway
        } else {
          console.log(`[TeachingStateMachine] State verification PASSED: ${verification.reason}`);
        }

        actionCount++;
        steps.push(step);

        // Small delay between steps
        await this.sleep(500);
      }

      // Log summary at the end
      console.log(`\n[TeachingStateMachine] Teaching complete! Total steps: ${actionCount}`);
      console.log(`[TeachingStateMachine] Discovered ${discoveredElements.length} features:`);
      discoveredElements.forEach((el, i) => {
        console.log(`[TeachingStateMachine]   ${i + 1}. ${el.name} - ${el.description}`);
      });

      // Reattach virtual cursor after entire teaching session
      this.overlayEngine.attachVirtualCursor();

      this.emit({ type: 'sessionComplete', totalSteps: actionCount });

    } catch (error) {
      console.error('[TeachingStateMachine] Teaching failed:', error);
      this.emit({
        type: 'error',
        error: error as Error,
        context: 'Teaching session'
      });
    } finally {
      this.isRunning = false;
      this.osController.stopKillSwitchListener();
      this.osController.cleanup();
      this.overlayEngine.cleanup();
      this.overlayEngine.attachVirtualCursor(); // Ensure cursor reattaches on cleanup
    }
  }

  /**
   * Generate fallback analysis using Accessibility API (no LLM)
   * Uses real button names and control types from Windows UI Automation
   */
  private generateFallbackAnalysis(
    uiTree: any[],
    currentState: ScreenState,
    userGoal: string
  ): any {
    console.log('[TeachingStateMachine] Generating fallback analysis from Accessibility API');

    // Find the most important clickable elements
    const clickableElements = uiTree.filter(el =>
      el.isClickable && el.isEnabled && el.boundingBox
    );

    if (clickableElements.length === 0) {
      throw new Error('No clickable elements found via Accessibility API');
    }

    // Prioritize: buttons > menu items > others
    const priorityOrder = ['button', 'menuitem', 'menu', 'hyperlink'];
    clickableElements.sort((a, b) => {
      const aPriority = priorityOrder.indexOf(a.role || '');
      const bPriority = priorityOrder.indexOf(b.role || '');
      return (aPriority === -1 ? 999 : aPriority) - (bPriority === -1 ? 999 : bPriority);
    });

    // Pick the highest priority element
    const targetElement = clickableElements[0];

    console.log(`[TeachingStateMachine] Selected target: ${targetElement.name} (${targetElement.role})`);

    return {
      appName: currentState.appTitle,
      currentState: currentState.currentState,
      visibleElements: clickableElements.slice(0, 5).map(el => ({
        name: el.name,
        x: el.boundingBox?.x || 0,
        y: el.boundingBox?.y || 0,
        description: `${el.role} - ${el.automationId || 'No ID'}`
      })),
      nextAction: {
        actionType: 'CLICK',
        target: {
          x: targetElement.boundingBox?.x || 0,
          y: targetElement.boundingBox?.y || 0,
          width: targetElement.boundingBox?.width || 100,
          height: targetElement.boundingBox?.height || 40
        },
        explanation: `Click on the ${targetElement.name} ${targetElement.role} to interact with ${currentState.appTitle}`,
        expectedStateChange: 'INTERACTION'
      }
    };
  }

  /**
   * Execute a single action with safety checks
   */
  private async executeAction(action: TeachingAction, currentState: ScreenState, windowBounds?: { x: number; y: number; width: number; height: number }): Promise<void> {
    console.log(`[TeachingStateMachine] Executing action: ${action.actionType} on ${action.targetName}`);
    console.log(`[TeachingStateMachine] Window bounds: ${JSON.stringify(windowBounds)}`);
    console.log(`[TeachingStateMachine] Target coords: (${action.normalizedCoords.x}, ${action.normalizedCoords.y})`);

    // Check if app is blocklisted
    if (this.safetyConfig.blocklistApps.includes(currentState.appTitle)) {
      console.warn(`[TeachingStateMachine] App is blocklisted: ${currentState.appTitle}`);
      return;
    }

    // Check if confirmation is required
    if (this.safetyConfig.requireConfirmationFor.includes(action.actionType)) {
      console.log(`[TeachingStateMachine] Confirmation required for ${action.actionType}`);
      // In production, would wait for user confirmation
    }

    // Log the action being performed
    switch (action.actionType) {
      case 'click':
        console.log(`[CLICKING]: ${action.targetName} at (${action.normalizedCoords.x.toFixed(2)}, ${action.normalizedCoords.y.toFixed(2)})`);
        break;
      case 'rightClick':
        console.log(`[RIGHT-CLICKING]: ${action.targetName} at (${action.normalizedCoords.x.toFixed(2)}, ${action.normalizedCoords.y.toFixed(2)})`);
        break;
      case 'doubleClick':
        console.log(`[DOUBLE-CLICKING]: ${action.targetName} at (${action.normalizedCoords.x.toFixed(2)}, ${action.normalizedCoords.y.toFixed(2)})`);
        break;
      case 'type':
        console.log(`[TYPING]: "${action.payload}"`);
        break;
      case 'pressKey':
        console.log(`[PRESSING KEY]: ${action.payload}`);
        break;
      case 'hotkey':
        console.log(`[PRESSING HOTKEY]: ${action.payload}`);
        break;
      default:
        console.log(`[ACTION]: ${action.actionType}`);
    }

    // Execute action with boundary clamping
    await this.osController.executeAction(
      action.actionType,
      action.normalizedCoords,
      action.payload,
      currentState.bounds
    );
  }

  /**
   * Verify that the state changed as expected
   */
  private async verifyStateChange(
    beforeState: ScreenState,
    expectedTransition: string
  ): Promise<StateVerification> {
    try {
      const result = await this.perception.verifyStateChange(beforeState, expectedTransition as any);

      return {
        beforeState,
        afterState: await this.perception.captureScreenState(),
        expectedTransition: expectedTransition as any,
        actualTransition: result.actualState,
        success: result.success,
        confidence: result.confidence,
        reason: result.reason || (result.success ? 'State changed as expected' : 'State did not change'),
        details: result.details
      };
    } catch (error) {
      return {
        beforeState,
        afterState: beforeState,
        expectedTransition: expectedTransition as any,
        actualTransition: 'error',
        success: false,
        confidence: 0,
        reason: `Verification failed: ${error}`,
        details: { error: String(error) }
      };
    }
  }

  /**
   * Stop teaching
   */
  stopTeaching(): void {
    console.log('[TeachingStateMachine] Stopping teaching...');
    this.isRunning = false;
    this.osController.cancelAll();
  }

  /**
   * Trigger emergency stop
   */
  triggerEmergencyStop(reason: EmergencyStopSignal['reason']): void {
    console.log(`[TeachingStateMachine] Emergency stop: ${reason}`);
    this.stopTeaching();
    this.osController.triggerEmergencyStop(reason);
    this.emit({
      type: 'emergencyStop',
      signal: { triggered: true, reason, timestamp: Date.now() }
    });
  }

  /**
   * Sleep helper
   */
  private sleep(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms));
  }
}
