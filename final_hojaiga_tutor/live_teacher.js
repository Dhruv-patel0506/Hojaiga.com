"use strict";
/**
 * Live Teacher - Main Stateful Loop with Virtual Cursor (Clicky-style)
 * Wires Observation, LLM planning, TTS explanation, and Virtual Cursor Execution
 * Physical mouse remains independent - user can do their own tasks
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.LiveTeacher = void 0;
const virtual_cursor_controller_1 = require("./virtual_cursor_controller");
const vision_llm_1 = require("./vision_llm");
class LiveTeacher {
    virtualCursor;
    visionLLM;
    session = null;
    isRunning = false;
    killSwitchActive = false;
    constructor() {
        this.virtualCursor = new virtual_cursor_controller_1.VirtualCursorController();
        this.visionLLM = new vision_llm_1.OllamaVisionAPI();
        this.virtualCursor.initializeOverlay();
    }
    /**
     * Start teaching session
     */
    async startTeaching(userGoal) {
        console.log('[LiveTeacher] Starting teaching session...');
        console.log(`[LiveTeacher] User Goal: ${userGoal}`);
        // Initialize Ollama
        const ollamaReady = await this.visionLLM.initialize();
        if (!ollamaReady) {
            console.error('[LiveTeacher] Ollama not available. Cannot start teaching.');
            return;
        }
        // Create session
        this.session = {
            id: Date.now().toString(),
            userGoal,
            startTime: Date.now(),
            status: 'running',
            currentStep: 0,
            totalSteps: 0,
            actionsExecuted: []
        };
        this.isRunning = true;
        this.killSwitchActive = false;
        // Start the main loop
        await this.teachingLoop();
    }
    /**
     * Main teaching loop - LISTEN → OBSERVE → THINK → TEACH → ACT → VERIFY
     * Uses virtual cursor (Clicky-style) - physical mouse independent
     */
    async teachingLoop() {
        console.log('[LiveTeacher] Starting main loop with virtual cursor...');
        while (this.isRunning && !this.killSwitchActive) {
            try {
                // OBSERVE: Capture screen and UI tree
                console.log('[LiveTeacher] OBSERVE: Capturing screen and UI tree...');
                const screenshot = this.virtualCursor.captureScreen();
                const uiTreeData = this.virtualCursor.getUITree();
                const uiTree = uiTreeData.uiTree || [];
                if (!screenshot) {
                    console.error('[LiveTeacher] Failed to capture screen. Retrying...');
                    await this.sleep(2000);
                    continue;
                }
                // THINK: Get next action from LLM
                console.log('[LiveTeacher] THINK: Getting next action from Vision LLM...');
                const response = await this.visionLLM.getNextAction(screenshot, this.session.userGoal, uiTree, this.session.actionsExecuted);
                console.log('[LiveTeacher] LLM Response:', response.explanation);
                console.log('[LiveTeacher] Next Action:', response.nextAction);
                // PARSE POINT TAGS (Clicky-style)
                console.log('[LiveTeacher] Parsing POINT tags from LLM response...');
                const pointTags = this.virtualCursor.parsePointTags(response.explanation);
                console.log('[LiveTeacher] Found POINT tags:', pointTags);
                // MOVE VIRTUAL CURSOR to each point
                for (const point of pointTags) {
                    console.log(`[LiveTeacher] Moving virtual cursor to (${point.x}, ${point.y}): ${point.label}`);
                    this.virtualCursor.showVirtualCursor();
                    this.virtualCursor.moveVirtualCursor(point.x, point.y, point.label, { duration: 800, click: true });
                    await this.sleep(1000);
                }
                // TEACH: Speak explanation (POINT tags removed)
                console.log('[LiveTeacher] TEACH: Speaking explanation (POINT tags removed)...');
                const cleanExplanation = this.virtualCursor.removePointTags(response.explanation);
                await this.speak(cleanExplanation);
                // ACT: Execute the action (using virtual cursor, not physical mouse)
                console.log('[LiveTeacher] ACT: Executing action with virtual cursor...');
                await this.executeAction(response.nextAction);
                // Record action
                this.session.actionsExecuted.push(response.nextAction);
                this.session.currentStep++;
                // VERIFY: Check if action succeeded
                console.log('[LiveTeacher] VERIFY: Checking if action succeeded...');
                const success = await this.verifyAction(response.nextAction, response.verificationCriteria);
                if (success) {
                    console.log('[LiveTeacher] Action succeeded. Continuing...');
                    await this.sleep(2000);
                }
                else {
                    console.log('[LiveTeacher] Action failed. Retrying...');
                    await this.sleep(1000);
                }
                // Safety check
                if (this.session.currentStep >= 50) {
                    console.log('[LiveTeacher] Reached max steps. Stopping.');
                    this.isRunning = false;
                }
            }
            catch (error) {
                console.error('[LiveTeacher] Error in loop:', error);
                await this.sleep(2000);
            }
        }
        console.log('[LiveTeacher] Teaching loop complete.');
        this.virtualCursor.hideVirtualCursor();
        this.session.status = 'complete';
    }
    /**
     * Execute an action using virtual cursor with actual OS interaction
     * Shows virtual cursor AND actually clicks/interacts
     */
    async executeAction(action) {
        const { actionType, target, payload } = action;
        switch (actionType) {
            case 'click':
                if (target?.coordinates) {
                    console.log(`[LiveTeacher] Clicking at (${target.coordinates.x}, ${target.coordinates.y})`);
                    this.virtualCursor.showVirtualCursor();
                    this.virtualCursor.clickAt(target.coordinates.x, target.coordinates.y);
                }
                break;
            case 'rightClick':
                if (target?.coordinates) {
                    console.log(`[LiveTeacher] Right-clicking at (${target.coordinates.x}, ${target.coordinates.y})`);
                    this.virtualCursor.showVirtualCursor();
                    this.virtualCursor.rightClickAt(target.coordinates.x, target.coordinates.y);
                }
                break;
            case 'doubleClick':
                if (target?.coordinates) {
                    console.log(`[LiveTeacher] Double-clicking at (${target.coordinates.x}, ${target.coordinates.y})`);
                    this.virtualCursor.showVirtualCursor();
                    this.virtualCursor.doubleClickAt(target.coordinates.x, target.coordinates.y);
                }
                break;
            case 'type':
                if (payload) {
                    console.log(`[LiveTeacher] Typing: ${payload}`);
                    this.virtualCursor.typeText(payload);
                }
                break;
            case 'press':
                if (payload) {
                    console.log(`[LiveTeacher] Pressing key: ${payload}`);
                    this.virtualCursor.pressKey(payload);
                }
                break;
            case 'hotkey':
                if (payload) {
                    console.log(`[LiveTeacher] Pressing hotkey: ${payload}`);
                    this.virtualCursor.hotkey(payload);
                }
                break;
            case 'wait':
                const duration = parseInt(payload || '1000');
                await this.sleep(duration);
                break;
            case 'explain':
                // Just wait - already spoke the explanation
                await this.sleep(1000);
                break;
            default:
                console.log(`[LiveTeacher] Unknown action type: ${actionType}`);
        }
    }
    /**
     * Verify if an action succeeded
     */
    async verifyAction(action, criteria) {
        // Simple verification: capture screen and check if it changed
        // In production, use perceptual hash or specific UI element checks
        await this.sleep(500);
        return true; // Simplified for now
    }
    /**
     * Speak text using TTS (simplified - using system speech)
     */
    async speak(text) {
        console.log(`[TTS]: ${text}`);
        // In production, integrate with Edge TTS or system TTS
        // For now, just log it
    }
    /**
     * Sleep helper
     */
    sleep(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }
    /**
     * Stop teaching
     */
    stopTeaching() {
        console.log('[LiveTeacher] Stopping teaching...');
        this.isRunning = false;
        if (this.session) {
            this.session.status = 'stopped';
        }
    }
    /**
     * Activate kill switch
     */
    activateKillSwitch() {
        console.log('[LiveTeacher] Kill switch activated!');
        this.killSwitchActive = true;
    }
    /**
     * Get session status
     */
    getSessionStatus() {
        return this.session;
    }
}
exports.LiveTeacher = LiveTeacher;
// CLI Interface
if (require.main === module) {
    const teacher = new LiveTeacher();
    console.log('=== Universal App Teacher ===');
    console.log('Type your goal to start teaching (e.g., "How do I apply gaussian blur in Photoshop?")');
    console.log('Press Ctrl+C to stop\n');
    const readline = require('readline');
    const rl = readline.createInterface({
        input: process.stdin,
        output: process.stdout
    });
    rl.question('Your goal: ', (answer) => {
        rl.close();
        if (answer.trim()) {
            teacher.startTeaching(answer.trim()).catch(console.error);
        }
        else {
            console.log('No goal provided. Exiting.');
        }
    });
    // Handle Ctrl+C
    process.on('SIGINT', () => {
        console.log('\nStopping...');
        teacher.stopTeaching();
        process.exit(0);
    });
}
