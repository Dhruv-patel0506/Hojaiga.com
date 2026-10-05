"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.DynamicAppTeacher = void 0;
class DynamicAppTeacher {
    env;
    llm;
    scanner;
    panelWindow;
    session = null;
    explorationQueue = [];
    visitedScreens = new Set();
    currentScreenId = '';
    isTeaching = false;
    maxExplorationDepth = 50;
    explorationDepth = 0;
    constructor(env, llm, scanner, panelWindow) {
        this.env = env;
        this.llm = llm;
        this.scanner = scanner;
        this.panelWindow = panelWindow;
    }
    /**
     * Start comprehensive teaching mode - teaches the entire app from scratch
     */
    async startComprehensiveTeaching() {
        console.log('[DynamicAppTeacher] Starting comprehensive teaching mode...');
        // Initialize Ollama first
        const ollamaInitialized = await this.llm.initialize();
        if (!ollamaInitialized) {
            console.error('[DynamicAppTeacher] Failed to initialize Ollama. Cannot proceed with teaching.');
            await this.sendToPanel('Ollama vision model is not available. Please run setup_ollama_d_drive.bat to install Ollama and LLaVA model.');
            return;
        }
        const appInfo = await this.env.getActiveWindowInfo();
        this.session = {
            appName: appInfo.processName,
            goal: 'Learn and teach the entire application',
            mode: 'comprehensive',
            currentStep: 0,
            navigationGraph: new Map(),
            discoveredFeatures: [],
            discoveredShortcuts: [],
        };
        this.isTeaching = true;
        this.explorationDepth = 0;
        // Announce teaching start
        await this.sendToPanel(`🎓 Starting comprehensive teaching of ${appInfo.processName}...`);
        await this.speak(`Starting comprehensive teaching of ${appInfo.processName}`);
        await new Promise(resolve => setTimeout(resolve, 2000));
        // Step 1: Pre-scan the app
        await this.preScanApplication();
        // Step 2: Detect and handle login/signup
        await this.handleLoginFlow();
        // Step 3: Start systematic exploration with actual clicking
        await this.exploreApplicationInteractive();
        // Step 4: Teach discovered features with bullet points
        await this.teachDiscoveredFeaturesStructured();
        console.log('[DynamicAppTeacher] Comprehensive teaching complete');
        this.isTeaching = false;
    }
    /**
     * Start specific feature teaching mode - teaches a specific feature
     */
    async startSpecificTeaching(feature) {
        console.log(`[DynamicAppTeacher] Starting specific teaching for: ${feature}`);
        // Initialize Ollama first
        const ollamaInitialized = await this.llm.initialize();
        if (!ollamaInitialized) {
            console.error('[DynamicAppTeacher] Failed to initialize Ollama. Cannot proceed with teaching.');
            await this.sendToPanel('Ollama vision model is not available. Please run setup_ollama_d_drive.bat to install Ollama and LLaVA model.');
            return;
        }
        const appInfo = await this.env.getActiveWindowInfo();
        this.session = {
            appName: appInfo.processName,
            goal: feature,
            mode: 'specific',
            currentStep: 0,
            navigationGraph: new Map(),
            discoveredFeatures: [],
            discoveredShortcuts: [],
        };
        this.isTeaching = true;
        // Announce teaching start
        await this.sendToPanel(`🎯 Teaching you how to: ${feature}`);
        await this.speak(`Teaching you how to ${feature}`);
        await new Promise(resolve => setTimeout(resolve, 2000));
        // Step 1: Pre-scan the app
        await this.preScanApplication();
        // Step 2: Ensure logged in
        await this.handleLoginFlow();
        // Step 3: Find and teach the specific feature with interaction
        await this.findAndTeachFeatureInteractive(feature);
        console.log('[DynamicAppTeacher] Specific teaching complete');
        this.isTeaching = false;
    }
    /**
     * Pre-scan the application to understand all UI elements before teaching
     */
    async preScanApplication() {
        console.log('[DynamicAppTeacher] Pre-scanning application...');
        await this.sendToPanel('🔍 Scanning the application to understand all buttons and features...');
        await this.speak('Scanning the application to understand all buttons and features');
        const screenshot = await this.env.captureScreen();
        const uiElements = await this.scanner.performOCR(screenshot);
        await this.sendToPanel(`✅ Found ${uiElements.length} UI elements on this screen`);
        await this.speak(`Found ${uiElements.length} UI elements on this screen`);
        // Use LLM to analyze and categorize all elements
        const analysis = await this.llm.analyzeScreen(screenshot, 'Analyze this screen and identify: 1) All button names and their purposes, 2) All menu items, 3) All input fields, 4) All navigation elements. Return as a structured list.');
        if (analysis.length > 0 && analysis[0].payload) {
            await this.sendToPanel(`📋 App Analysis:\n${analysis[0].payload}`);
            await new Promise(resolve => setTimeout(resolve, 3000));
        }
        console.log('[DynamicAppTeacher] Pre-scan complete');
    }
    /**
     * Detect and handle login/signup flow automatically
     */
    async handleLoginFlow() {
        console.log('[DynamicAppTeacher] Checking for login/signup flow...');
        const screenshot = await this.env.captureScreen();
        const uiElements = await this.scanner.performOCR(screenshot);
        // Use LLM to detect login/signup elements
        const loginCheck = await this.llm.analyzeScreen(screenshot, 'Is this a login or signup screen? Look for: username fields, password fields, login buttons, signup buttons, sign in forms. Return JSON: {"isLogin": true/false, "hasUsername": true/false, "hasPassword": true/false, "loginButton": "button text"}');
        if (loginCheck.length > 0 && loginCheck[0].payload?.includes('true')) {
            console.log('[DynamicAppTeacher] Login screen detected. Asking for credentials...');
            await this.sendToPanel('🔐 Login screen detected. Please enter your credentials manually, then I will continue.');
            await this.speak('Login screen detected. Please enter your credentials manually');
            await new Promise(resolve => setTimeout(resolve, 5000)); // Wait for user to login
        }
        else {
            console.log('[DynamicAppTeacher] No login screen detected, already logged in or not required.');
            await this.sendToPanel('✅ Already logged in or no login required');
        }
    }
    /**
     * Systematically explore the application by ACTUALLY clicking UI elements
     */
    async exploreApplicationInteractive() {
        console.log('[DynamicAppTeacher] Starting interactive exploration...');
        await this.sendToPanel('🖱️ Starting interactive exploration - I will click buttons to demonstrate functionality');
        await this.speak('Starting interactive exploration. I will click buttons to demonstrate functionality');
        while (this.isTeaching && this.explorationDepth < this.maxExplorationDepth) {
            const screenshot = await this.env.captureScreen();
            const uiElements = await this.scanner.performOCR(screenshot);
            // Generate screen ID
            const screenId = this.generateScreenId(screenshot);
            if (this.visitedScreens.has(screenId)) {
                console.log('[DynamicAppTeacher] Screen already visited, finding new path...');
                await this.backtrackToNewScreen();
                continue;
            }
            this.visitedScreens.add(screenId);
            this.currentScreenId = screenId;
            // Analyze current screen with LLM to get clickable elements with coordinates
            const screenAnalysis = await this.llm.analyzeScreen(screenshot, 'Analyze this application screen. Identify: 1) All clickable buttons/links with their approximate coordinates, 2) All menus, 3) All important UI elements. Return JSON array of actions: [{"actionType": "click", "targetText": "button text", "targetCoordinates": {"x": number, "y": number}}]');
            if (screenAnalysis.length === 0) {
                console.log('[DynamicAppTeacher] No actions found, exploration complete.');
                await this.sendToPanel('✅ Exploration complete - all main features discovered');
                break;
            }
            // Click top 2 buttons per screen to demonstrate
            for (const action of screenAnalysis.slice(0, 2)) {
                if (!this.isTeaching)
                    break;
                console.log(`[DynamicAppTeacher] Clicking: ${action.targetText}`);
                // Announce what we're about to do
                await this.sendToPanel(`👆 Clicking: "${action.targetText}" to demonstrate...`);
                await this.speak(`Clicking ${action.targetText} to demonstrate`);
                // Record before state
                const beforeScreenshot = await this.env.captureScreen();
                // ACTUALLY CLICK the button
                await this.env.executeAction(action);
                await new Promise(resolve => setTimeout(resolve, 2000));
                // Record after state
                const afterScreenshot = await this.env.captureScreen();
                // Verify action worked
                const actionWorked = await this.verifyAction(beforeScreenshot, afterScreenshot);
                if (actionWorked) {
                    // Add to navigation graph
                    this.addToNavigationGraph(screenId, action, afterScreenshot, uiElements);
                    // Explain what happened in bullet points
                    await this.sendToPanel(`✅ Successfully clicked "${action.targetText}"\n• Screen changed - this button opens a new section\n• This leads to additional features\n• You can explore this area further`);
                    await this.speak(`Successfully clicked ${action.targetText}. The screen changed, this button opens a new section.`);
                    this.explorationDepth++;
                    this.session?.discoveredFeatures.push(action.targetText || 'Unknown feature');
                    await new Promise(resolve => setTimeout(resolve, 3000));
                }
                else {
                    await this.sendToPanel(`⚠️ Clicking "${action.targetText}" didn't change the screen`);
                    await this.speak(`Clicking ${action.targetText} didn't change the screen. Let me try something else.`);
                }
            }
            // Try to go back
            await this.sendToPanel('⬅️ Going back to explore more options...');
            await this.speak('Going back to explore more options');
            await this.env.executeAction({
                actionType: 'type',
                payload: '{ESC}' // Try ESC to go back
            });
            await new Promise(resolve => setTimeout(resolve, 1500));
        }
    }
    /**
     * Find and teach a specific feature with actual interaction
     */
    async findAndTeachFeatureInteractive(feature) {
        console.log(`[DynamicAppTeacher] Finding feature: ${feature}`);
        const screenshot = await this.env.captureScreen();
        // Use LLM to find the feature with coordinates
        const featureActions = await this.llm.analyzeScreen(screenshot, `I need to find and use the feature: "${feature}". Look for related buttons, menus, or navigation with their coordinates. Return JSON array of actions: [{"actionType": "click", "targetText": "button text", "targetCoordinates": {"x": number, "y": number}}]`);
        if (featureActions.length === 0) {
            await this.sendToPanel(`❓ Couldn't find "${feature}" on current screen. Exploring to find it...`);
            await this.speak(`Couldn't find ${feature} on current screen. Exploring to find it.`);
            await this.exploreApplicationInteractive();
            return;
        }
        // Execute actions to reach the feature
        for (const action of featureActions) {
            await this.sendToPanel(`🎯 To access "${feature}", I'll click: ${action.targetText}`);
            await this.speak(`To access ${feature}, I'll click ${action.targetText}`);
            await this.env.executeAction(action);
            await new Promise(resolve => setTimeout(resolve, 2000));
        }
        // Once at the feature, teach how to use it with bullet points
        await this.teachCurrentScreenStructured(feature);
    }
    /**
     * Teach the current screen's functionality with structured bullet points
     */
    async teachCurrentScreenStructured(context) {
        const screenshot = await this.env.captureScreen();
        const uiElements = await this.scanner.performOCR(screenshot);
        await this.sendToPanel(`📚 Teaching about: ${context}`);
        await this.speak(`Teaching about ${context}`);
        const teaching = await this.llm.analyzeScreen(screenshot, `Teach the user about this screen: "${context}". Explain in bullet points: 1) What this screen does, 2) How to use each element, 3) What each button/option does. Return JSON array of explanations with actionType "explain".`);
        if (teaching.length > 0 && teaching[0].payload) {
            // Format as bullet points
            const explanation = teaching[0].payload
                .replace(/\n\n/g, '\n• ')
                .replace(/\. /g, '.\n• ');
            await this.sendToPanel(`📖 ${context}:\n\n• ${explanation}`);
            await this.speak(teaching[0].payload);
            await new Promise(resolve => setTimeout(resolve, 5000));
        }
    }
    /**
     * Teach all discovered features with structured bullet points
     */
    async teachDiscoveredFeaturesStructured() {
        console.log('[DynamicAppTeacher] Teaching discovered features...');
        await this.sendToPanel(`🎓 I've explored ${this.session?.discoveredFeatures.length} features of ${this.session?.appName}. Here's what I found:\n`);
        await this.speak(`I've explored ${this.session?.discoveredFeatures.length} features of ${this.session?.appName}. Here's what I found.`);
        let featureList = '';
        for (const feature of this.session?.discoveredFeatures || []) {
            featureList += `• ${feature}\n`;
        }
        await this.sendToPanel(featureList);
        await this.speak(featureList.replace(/•/g, '').replace(/\n/g, '. '));
        await new Promise(resolve => setTimeout(resolve, 3000));
        // Teach each feature in detail
        for (const feature of this.session?.discoveredFeatures || []) {
            await this.sendToPanel(`\n📌 Feature: ${feature}\n• This button/feature performs specific actions\n• Clicking it opens related functionality\n• You can use this to access additional options`);
            await this.speak(`Feature: ${feature}. This button performs specific actions and opens related functionality.`);
            await new Promise(resolve => setTimeout(resolve, 2000));
        }
    }
    /**
     * Verify if an action changed the screen
     */
    async verifyAction(before, after) {
        // Simple hash comparison (in real app, use perceptual hash)
        return before !== after;
    }
    /**
     * Add state to navigation graph
     */
    addToNavigationGraph(screenId, action, screenshot, elements) {
        const node = {
            id: screenId,
            screenshot,
            uiElements: elements,
            description: `Screen with ${elements.length} elements`,
            timestamp: Date.now(),
            transitions: []
        };
        this.session?.navigationGraph.set(screenId, node);
    }
    /**
     * Backtrack to find a new unvisited screen
     */
    async backtrackToNewScreen() {
        await this.env.executeAction({
            actionType: 'type',
            payload: '{ESC}'
        });
        await new Promise(resolve => setTimeout(resolve, 1000));
    }
    /**
     * Generate unique screen ID
     */
    generateScreenId(screenshot) {
        // Simple hash (in real app, use perceptual hash)
        let hash = 0;
        for (let i = 0; i < screenshot.length; i++) {
            const char = screenshot.charCodeAt(i);
            hash = ((hash << 5) - hash) + char;
            hash = hash & hash;
        }
        return Math.abs(hash).toString(36);
    }
    /**
     * Stop teaching
     */
    stopTeaching() {
        console.log('[DynamicAppTeacher] Stopping teaching...');
        this.isTeaching = false;
    }
    /**
     * Get current session status
     */
    getSessionStatus() {
        return this.session;
    }
    /**
     * Send message to panel window with formatted output
     */
    async sendToPanel(message) {
        console.log(`[TEACHER]: ${message}`);
        if (this.panelWindow) {
            try {
                await this.panelWindow.webContents.executeJavaScript(`
          if (typeof appendToTranscript === 'function') {
            appendToTranscript(\`${message.replace(/`/g, '\\`')}\`);
          } else {
            console.log('appendToTranscript not available');
          }
        `);
            }
            catch (error) {
                console.error('[DynamicAppTeacher] Failed to send to panel:', error);
            }
        }
    }
    /**
     * Speak the explanation using TTS
     */
    async speak(text) {
        console.log(`[TTS]: ${text}`);
        if (this.panelWindow) {
            try {
                await this.panelWindow.webContents.executeJavaScript(`
          if (typeof playEdgeTTS === 'function') {
            playEdgeTTS(\`${text.replace(/`/g, '\\`')}\`);
          } else {
            console.log('playEdgeTTS not available');
          }
        `);
            }
            catch (error) {
                console.error('[DynamicAppTeacher] Failed to speak:', error);
            }
        }
    }
}
exports.DynamicAppTeacher = DynamicAppTeacher;
