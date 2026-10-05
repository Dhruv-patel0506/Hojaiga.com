/**
 * Bulletproof Interactive Tutor Wrapper - Reactive State Machine
 * BULLETPROOF JSON EXTRACTOR + SENSORY GATE LOOP
 * Never crashes on undefined, detects manual intervention, physically moves mouse
 */

import { TeacherRAGWrapper } from './rag/TeacherRAGWrapper';
import { WindowManager } from './WindowManager';
import { SafeOSController } from './SafeOSController';
import { LivePerception } from './LivePerception';
import { UIElementNode } from './rag/types';
import { InteractiveInputHandler, QuestionAskedEvent, ResponseReceivedEvent } from './InteractiveInputHandler';
import { exec } from 'child_process';
import { promisify } from 'util';

const execAsync = promisify(exec);

export interface TeachingStep {
  explanation: string;
  actionType: 'INVOKE' | 'EXPAND' | 'TYPE' | 'WAIT' | 'ASK_USER' | 'COMPLETE';
  targetAutomationId: string;
  targetName: string;
  inputValue?: string;
}

export interface UserQuestion {
  question: string;
  timestamp: number;
}

export class InteractiveTutorWrapper {
  private ragWrapper: TeacherRAGWrapper;
  private windowManager: WindowManager;
  private osController: SafeOSController;
  private perception: LivePerception;
  private inputHandler: InteractiveInputHandler;
  private isPlaying: boolean = false;
  private isPaused: boolean = false;
  private currentAppName: string = '';
  private questionQueue: UserQuestion[] = [];
  private pollingPaused: boolean = false;
  private lastUiTreeHash: string = '';
  private usePhysicalMouse: boolean = true;

  constructor(
    ragWrapper: TeacherRAGWrapper,
    windowManager: WindowManager,
    osController: SafeOSController,
    perception: LivePerception,
    usePhysicalMouse: boolean = true
  ) {
    this.ragWrapper = ragWrapper;
    this.windowManager = windowManager;
    this.osController = osController;
    this.perception = perception;
    this.inputHandler = new InteractiveInputHandler();
    this.usePhysicalMouse = usePhysicalMouse;

    this.inputHandler.on('question-asked', (data: QuestionAskedEvent) => {
      console.log(`[InteractiveTutor] UI should show input field for: "${data.question}"`);
    });
    this.inputHandler.on('response-received', (data: ResponseReceivedEvent) => {
      console.log(`[InteractiveTutor] User responded: "${data.response}"`);
    });
  }

  setIgnorePid(pid: number): void {
    this.windowManager.setIgnorePid(pid);
  }

  clearIgnorePid(): void {
    this.windowManager.clearIgnorePid();
  }

  pauseBackgroundPolling(): void {
    this.pollingPaused = true;
    console.log('[InteractiveTutor] Background UI polling paused');
  }

  resumeBackgroundPolling(): void {
    this.pollingPaused = false;
    console.log('[InteractiveTutor] Background UI polling resumed');
  }

  stopInteraction(): void {
    this.isPlaying = false;
    console.log('[InteractiveTutor] Interaction stopped');
  }

  addUserQuestion(question: string): void {
    this.questionQueue.push({ question, timestamp: Date.now() });
    console.log(`[InteractiveTutor] User question queued: "${question}"`);
  }

  handleUserInput(input: string): void {
    if (this.inputHandler.getCurrentQuestion()) {
      this.inputHandler.handleResponse(input);
    } else {
      this.addUserQuestion(input);
    }
  }

  private async processUserQuestions(): Promise<void> {
    while (this.questionQueue.length > 0 && this.isPlaying) {
      const userQuestion = this.questionQueue.shift();
      if (!userQuestion) continue;

      console.log(`[InteractiveTutor] Processing user question: "${userQuestion.question}"`);

      const currentState = this.windowManager.getActiveWindow();
      const uiTree = await this.perception.extractUITree(parseInt(currentState.appId));
      const uiElements = uiTree.map(el => ({
        name: el.name,
        automationId: el.automationId || '',
        controlType: el.role || 'Unknown',
        bounds: el.boundingBox || { x: 0, y: 0, width: 0, height: 0 }
      }));

      try {
        const answerStep = await this.ragWrapper.determineNextStep(
          currentState.appTitle,
          userQuestion.question,
          uiElements,
          "User asked a question"
        );

        console.log(`[InteractiveTutor] Answer: ${answerStep.explanation}`);

        if (answerStep.actionType !== 'WAIT') {
          await this.executeStep(answerStep, currentState);
        }
      } catch (error) {
        console.error('[InteractiveTutor] Failed to answer user question:', error);
      }

      await new Promise(resolve => setTimeout(resolve, 1000));
    }
  }

  /**
   * BULLETPROOF JSON EXTRACTOR
   * Prevents the app from crashing even if the LLM hallucinates text around the JSON
   */
  private extractJSON(text: string): TeachingStep | null {
    try {
      return JSON.parse(text);
    } catch (e) {
      const match = text.match(/\{[\s\S]*\}/);
      if (match) {
        try {
          return JSON.parse(match[0]);
        } catch (e2) {
          console.error('[InteractiveTutor] Failed to parse extracted JSON:', e2);
          return null;
        }
      }
      console.error('[InteractiveTutor] No JSON found in LLM output');
      return null;
    }
  }

  private async generateNextImmediateStep(
    userGoal: string,
    appName: string,
    lastAction: string
  ): Promise<TeachingStep> {
    console.log(`[InteractiveTutor] Generating next immediate step for: ${userGoal}`);
    console.log(`[InteractiveTutor] Last action: ${lastAction}`);

    try {
      const currentState = this.windowManager.getActiveWindow();
      const uiTree = await this.perception.extractUITree(parseInt(currentState.appId));
      const uiElements = uiTree.map(el => ({
        name: el.name,
        automationId: el.automationId || '',
        controlType: el.role || 'Unknown',
        bounds: el.boundingBox || { x: 0, y: 0, width: 0, height: 0 }
      }));

      const step = await this.ragWrapper.determineNextStep(appName, userGoal, uiElements, lastAction);

      const teachingStep: TeachingStep = {
        explanation: step.explanation || 'Perform action',
        actionType: step.actionType || 'INVOKE',
        targetAutomationId: step.targetAutomationId || '',
        targetName: step.targetName || 'Unknown',
        inputValue: step.inputValue
      };

      return teachingStep;
    } catch (error) {
      console.error('[InteractiveTutor] Failed to generate immediate step:', error);
      throw error;
    }
  }

  private async executeStepWithPhysicalMouse(step: TeachingStep, currentState: any): Promise<void> {
    console.log(`[InteractiveTutor] Executing with physical mouse: ${step.actionType} on ${step.targetName}`);

    const uiTree = await this.perception.extractUITree(parseInt(currentState.appId));
    const targetElement = uiTree.find(el =>
      el.automationId === step.targetAutomationId ||
      el.name === step.targetName
    );

    if (!targetElement || !targetElement.boundingBox) {
      console.warn(`[InteractiveTutor] Target element not found: ${step.targetName}`);
      return;
    }

    const bounds = targetElement.boundingBox;
    const absoluteX = Math.round(bounds.x + bounds.width / 2);
    const absoluteY = Math.round(bounds.y + bounds.height / 2);

    try {
      const scriptPath = 'D:\\new_automation\\final_hojaiga_tutor\\physical_mouse_driver.py';
      const { stdout, stderr } = await execAsync(
        `python "${scriptPath}" click ${absoluteX} ${absoluteY} 0.8`
      );

      console.log(`[InteractiveTutor] Physical mouse output: ${stdout}`);
      if (stderr) {
        console.warn(`[InteractiveTutor] Physical mouse stderr: ${stderr}`);
      }
      console.log(`[InteractiveTutor] Physical mouse click executed at (${absoluteX}, ${absoluteY})`);
    } catch (error) {
      console.error(`[InteractiveTutor] Failed to execute physical mouse step: ${error}`);
      console.log(`[InteractiveTutor] Falling back to programmatic UI Automation`);
      await this.executeStepWithProgrammatic(step, currentState);
    }
  }

  private async executeStepWithProgrammatic(step: TeachingStep, currentState: any): Promise<void> {
    console.log(`[InteractiveTutor] Executing programmatically: ${step.actionType} on ${step.targetName}`);

    const uiTree = await this.perception.extractUITree(parseInt(currentState.appId));
    const targetElement = uiTree.find(el =>
      el.automationId === step.targetAutomationId ||
      el.name === step.targetName
    );

    if (!targetElement || !targetElement.boundingBox) {
      console.warn(`[InteractiveTutor] Target element not found: ${step.targetName}`);
      return;
    }

    const bounds = targetElement.boundingBox;
    const absoluteX = bounds.x + bounds.width / 2;
    const absoluteY = bounds.y + bounds.height / 2;

    try {
      if (step.actionType === 'INVOKE') {
        console.log(`[InteractiveTutor] Invoking element programmatically at (${absoluteX}, ${absoluteY})`);
        await this.osController.executeAction(
          'click',
          { x: bounds.x / currentState.bounds.width, y: bounds.y / currentState.bounds.height },
          undefined,
          currentState.bounds
        );
      } else if (step.actionType === 'EXPAND') {
        console.log(`[InteractiveTutor] Expanding menu programmatically at (${absoluteX}, ${absoluteY})`);
        await this.osController.executeAction(
          'click',
          { x: bounds.x / currentState.bounds.width, y: bounds.y / currentState.bounds.height },
          undefined,
          currentState.bounds
        );
      } else if (step.actionType === 'TYPE') {
        if (step.inputValue) {
          console.log(`[InteractiveTutor] Typing: "${step.inputValue}" programmatically`);
          await this.osController.executeAction(
            'type',
            { x: bounds.x / currentState.bounds.width, y: bounds.y / currentState.bounds.height },
            step.inputValue,
            currentState.bounds
          );
        }
      }
    } catch (error) {
      console.error(`[InteractiveTutor] Failed to execute step: ${error}`);
    }
  }

  private async executeStep(step: TeachingStep, currentState: any): Promise<void> {
    if (this.usePhysicalMouse) {
      await this.executeStepWithPhysicalMouse(step, currentState);
    } else {
      await this.executeStepWithProgrammatic(step, currentState);
    }
  }

  private async askUserQuestion(question: string): Promise<string> {
    console.log(`[InteractiveTutor] Asking user: "${question}"`);
    return await this.inputHandler.askQuestion(question, 30000);
  }

  /**
   * THE SENSORY GATE LOOP: ONE STEP AT A TIME
   * BULLETPROOF - Never crashes, detects manual intervention, physically moves mouse
   */
  public async startLiveInteraction(userGoal: string, appName: string): Promise<void> {
    this.isPlaying = true;
    this.isPaused = false;
    this.currentAppName = appName;

    console.log(`[InteractiveTutor] Starting BULLETPROOF reactive live interaction for: ${appName}`);
    console.log(`[InteractiveTutor] Goal: ${userGoal}`);
    console.log(`[InteractiveTutor] Physical mouse: ${this.usePhysicalMouse ? 'ENABLED' : 'DISABLED'}`);

    try {
      this.windowManager.focusWindow();
      await new Promise(resolve => setTimeout(resolve, 500));

      let goalAchieved = false;
      let lastAction = "Just started.";
      let stepCount = 0;
      const maxSteps = 50;

      while (this.isPlaying && !goalAchieved && stepCount < maxSteps) {
        if (this.isPaused) {
          console.log('[InteractiveTutor] Paused, waiting...');
          await new Promise(resolve => setTimeout(resolve, 1000));
          continue;
        }

        console.log(`[InteractiveTutor] Step ${stepCount + 1}: Sensing UI...`);
        const currentState = this.windowManager.getActiveWindow();
        const uiTree = await this.perception.extractUITree(parseInt(currentState.appId));

        const liveUIElements = uiTree.slice(0, 20).map(el => ({
          name: el.name,
          automationId: el.automationId,
          controlType: el.role || 'Unknown',
          bounds: el.boundingBox || { x: 0, y: 0, width: 0, height: 0 }
        }));

        const currentUiHash = JSON.stringify(liveUIElements);

        if (this.lastUiTreeHash && this.lastUiTreeHash !== currentUiHash) {
          console.log('[InteractiveTutor] UI state changed - possible manual user intervention detected');
          console.log('[InteractiveTutor] Abandoning previous script, regenerating based on new UI state');
          lastAction = "User manually clicked an element. Screen changed.";
        }
        this.lastUiTreeHash = currentUiHash;

        const visibleElementNames = liveUIElements.map(el => el.name).join(', ');
        console.log(`[InteractiveTutor] Visible elements: ${visibleElementNames}`);

        console.log(`[InteractiveTutor] Planning next step...`);
        const rawLLMOutput = await this.ragWrapper.determineNextStep(appName, userGoal, liveUIElements, lastAction);
        const nextStep = this.extractJSON(JSON.stringify(rawLLMOutput));

        if (!nextStep) {
          console.error('[InteractiveTutor] LLM hallucinated. Retrying silently...');
          await new Promise(resolve => setTimeout(resolve, 1000));
          continue;
        }

        if (nextStep.actionType === 'COMPLETE') {
          console.log(`[InteractiveTutor] Goal achieved: ${nextStep.explanation}`);
          console.log(`[TTS] "${nextStep.explanation}"`);
          goalAchieved = true;
          break;
        }

        if (nextStep.actionType === 'ASK_USER') {
          console.log(`[InteractiveTutor] Asking user for input...`);
          try {
            const userResponse = await this.askUserQuestion(nextStep.explanation);
            console.log(`[InteractiveTutor] User requested: ${userResponse}`);
            userGoal = userResponse;
            lastAction = "User requested new goal";
            console.log(`[InteractiveTutor] New goal: ${userGoal}`);
            continue;
          } catch (error) {
            console.warn('[InteractiveTutor] User question failed or timed out, continuing...');
            lastAction = "User question timed out";
          }
        }

        const cleanExplanation = nextStep.explanation.replace(/<[^>]*>/g, '').trim();
        console.log(`[TTS] "${cleanExplanation}"`);

        const newUIElements = await this.perception.extractUITree(parseInt(currentState.appId));
        const newLiveUIElements = newUIElements.slice(0, 20).map(el => ({
          name: el.name,
          automationId: el.automationId,
          controlType: el.role || 'Unknown',
          bounds: el.boundingBox || { x: 0, y: 0, width: 0, height: 0 }
        }));
        const uiChanged = JSON.stringify(liveUIElements) !== JSON.stringify(newLiveUIElements);

        if (uiChanged) {
          console.log('[InteractiveTutor] User manually advanced the UI. Recalculating next step...');
          lastAction = "User manually clicked an element. Screen changed.";
          this.lastUiTreeHash = JSON.stringify(newLiveUIElements);
          continue;
        }

        this.pauseBackgroundPolling();

        try {
          await this.executeStep(nextStep, currentState);
          lastAction = `${nextStep.actionType} on ${nextStep.targetName}`;
        } catch (error) {
          console.error(`[InteractiveTutor] Failed to execute step: ${error}`);
        } finally {
          this.resumeBackgroundPolling();
        }

        await new Promise(resolve => setTimeout(resolve, 1500));
        stepCount++;
      }

      console.log(`[InteractiveTutor] Session complete. Total steps: ${stepCount}`);
    } catch (error) {
      console.error('[InteractiveTutor] Session failed:', error);
    } finally {
      this.isPlaying = false;
    }
  }
}
