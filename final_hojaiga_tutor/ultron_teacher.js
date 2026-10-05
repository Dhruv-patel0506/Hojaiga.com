"use strict";
/**
 * Enhanced App Teacher - Ultron/Jarvis-Level Intelligence
 * Integrated with Clicky's Electron panel
 * Knows EVERY button, explains like it created the app
 * Systematically interacts with ALL UI elements
 * Writes professional documents, creates resumes, teaches multi-app workflows
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.UltronLevelTeacher = void 0;
const virtual_cursor_controller_1 = require("./virtual_cursor_controller");
const vision_llm_1 = require("./vision_llm");
class UltronLevelTeacher {
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
     * Start comprehensive app teaching - Ultron/Jarvis level
     */
    async startComprehensiveTeaching() {
        console.log('[UltronTeacher] Starting comprehensive teaching with Ultron-level intelligence...');
        // Initialize Ollama
        const ollamaReady = await this.visionLLM.initialize();
        if (!ollamaReady) {
            console.error('[UltronTeacher] Ollama not available. Cannot start teaching.');
            return;
        }
        // Create session
        this.session = {
            id: Date.now().toString(),
            userGoal: 'Explain this application completely',
            startTime: Date.now(),
            status: 'running',
            currentStep: 0,
            totalSteps: 0,
            actionsExecuted: []
        };
        this.isRunning = true;
        this.killSwitchActive = false;
        // Start the main loop
        await this.ultronTeachingLoop();
    }
    /**
     * Write professional document (report, email, paragraph)
     */
    async writeProfessionalDocument(topic, documentType) {
        console.log(`[UltronTeacher] Writing professional ${documentType} about: ${topic}`);
        const screenshot = this.virtualCursor.captureScreen();
        const documentPrompt = `You are an expert professional writer with human-like but highly formal writing style. Write a ${documentType} about: ${topic}

Requirements:
1. Professional and formal tone
2. Human-like (not robotic AI-sounding)
3. Detailed and comprehensive
4. Well-structured with clear sections
5. Proper formatting and flow
6. Industry-standard terminology
7. For resumes: High ATS score optimization with keywords
8. For reports: Executive summary, body, conclusions
9. For emails: Professional greeting, body, closing
10. For paragraphs: Clear topic sentence, supporting details, conclusion

${documentType === 'resume' ? `
Additional for resume:
- Include industry-specific keywords for ATS
- Quantifiable achievements
- Action verbs
- Professional summary
- Skills section with relevant keywords
- Clean formatting
` : ''}

Return the document content to be typed into the active application.`;
        const response = await this.visionLLM.analyzeScreen(screenshot, documentPrompt);
        // Move to document area and type the professional content
        this.virtualCursor.showVirtualCursor();
        this.virtualCursor.moveVirtualCursor(500, 400, "Document area", { duration: 500, click: true });
        await this.sleep(500);
        // Type the document character by character for realism
        const documentContent = response.explanation;
        await this.virtualCursor.typeText(documentContent, { speed: 0.03 });
        await this.speak(`I've written a professional ${documentType} about ${topic}. The content is detailed, formal, and human-like.`);
    }
    /**
     * Detect and teach multiple open applications
     */
    async teachMultipleApps() {
        console.log('[UltronTeacher] Detecting and teaching multiple open applications...');
        // Detect all open windows
        const screenshot = this.virtualCursor.captureScreen();
        const multiAppPrompt = `You are Ultron-level AI. Analyze this screenshot to identify ALL open applications/windows.

For EACH application/window visible:
1. Application name
2. Window title
3. Approximate position (x, y)
4. Purpose based on visible content

Return JSON:
{
  "applications": [
    {
      "name": "Application name",
      "title": "Window title",
      "x": 123,
      "y": 456,
      "purpose": "What this app is being used for"
    }
  ]
}`;
        const response = await this.visionLLM.analyzeScreen(screenshot, multiAppPrompt);
        const apps = this.parseApplicationsFromResponse(response.explanation);
        console.log(`[UltronTeacher] Found ${apps.length} open applications`);
        // Teach each application
        for (const app of apps) {
            if (!this.isRunning || this.killSwitchActive)
                break;
            console.log(`[UltronTeacher] Teaching ${app.name}...`);
            // Focus the app window
            this.virtualCursor.moveVirtualCursor(app.x, app.y, app.name, { duration: 500, click: true });
            await this.sleep(1000);
            // Teach this app
            await this.teachSingleApp(app.name);
            await this.sleep(2000);
        }
        // Ask about interconnections
        await this.askAboutInterconnections(apps);
    }
    /**
     * Teach a single application
     */
    async teachSingleApp(appName) {
        console.log(`[UltronTeacher] Teaching ${appName}...`);
        const screenshot = this.virtualCursor.captureScreen();
        const appPrompt = `You are Ultron-level AI. Teach me about ${appName} comprehensively.

Provide:
1. What this application does
2. Key features and capabilities
3. ALL visible UI elements with expert explanations
4. Professional workflows
5. Expert tips and tricks
6. Common mistakes to avoid

For each UI element, provide coordinates (x, y) so I can click it.

Return detailed explanation.`;
        const response = await this.visionLLM.analyzeScreen(screenshot, appPrompt);
        await this.speak(response.explanation);
    }
    /**
     * Ask user about app interconnections
     */
    async askAboutInterconnections(apps) {
        console.log('[UltronTeacher] Asking about app interconnections...');
        const appNames = apps.map(a => a.name).join(', ');
        await this.speak(`I've taught you about ${appNames}. Would you like to learn how these applications can work together?`);
        // In production, would wait for user input
        // For now, auto-detect and suggest interconnections
        const screenshot = this.virtualCursor.captureScreen();
        const interconnectionPrompt = `You are Ultron-level AI. Analyze these applications: ${appNames}

Can these applications be interconnected? If yes, explain:
1. How they can work together
2. Common workflows between them
3. Data transfer possibilities
4. Automation opportunities
5. Professional workflows that use multiple apps

If no interconnection is possible, explain why.

Provide step-by-step implementation that I can demonstrate on screen.`;
        const response = await this.visionLLM.analyzeScreen(screenshot, interconnectionPrompt);
        if (response.explanation.toLowerCase().includes('yes') || response.explanation.toLowerCase().includes('can')) {
            await this.speak('Yes, these applications can work together! Let me show you how to interconnect them.');
            await this.demonstrateInterconnection(response.explanation);
        }
        else {
            await this.speak('These applications cannot be directly interconnected. However, I can teach you each one individually.');
        }
    }
    /**
     * Demonstrate app interconnection with actual implementation
     */
    async demonstrateInterconnection(interconnectionPlan) {
        console.log('[UltronTeacher] Demonstrating app interconnection...');
        await this.speak('I will now demonstrate how to interconnect these applications with actual implementation on screen.');
        // Parse the interconnection plan and execute it
        // This would involve:
        // 1. Moving between apps
        // 2. Copying data from one app
        // 3. Pasting into another app
        // 4. Showing the workflow
        // 5. Explaining each step
        // For now, speak the plan
        await this.speak(interconnectionPlan);
    }
    /**
     * Ultron-level teaching loop - knows EVERY button like it created the app
     */
    async ultronTeachingLoop() {
        console.log('[UltronTeacher] Starting Ultron-level teaching loop...');
        // Step 1: Deep scan to understand the entire app
        await this.deepAppAnalysis();
        // Step 2: Teach each UI element systematically
        await this.teachAllUIElements();
        // Step 3: Teach workflows and connections
        await this.teachWorkflows();
        console.log('[UltronTeacher] Ultron-level teaching complete.');
        this.session.status = 'complete';
        this.virtualCursor.hideVirtualCursor();
    }
    /**
     * Deep app analysis - understand EVERYTHING about the app
     */
    async deepAppAnalysis() {
        console.log('[UltronTeacher] Performing deep app analysis...');
        const screenshot = this.virtualCursor.captureScreen();
        const uiTreeData = this.virtualCursor.getUITree();
        const uiTree = uiTreeData.uiTree || [];
        console.log('[UltronTeacher] Analyzing app structure and purpose...');
        // Use LLaVA to understand the app deeply
        const analysisPrompt = `You are Ultron-level AI with complete knowledge of this application. Analyze this screenshot EXTREMELY THOROUGHLY.

I need you to explain this application as if you created it yourself and know every detail:

1. **App Identity**: What is this application? What is its primary purpose?
2. **UI Structure**: How is the interface organized? What are the main sections?
3. **All Visible Elements**: List EVERY visible button, menu, input, and control with:
   - Exact name/text
   - Purpose and functionality
   - How it connects to other features
   - Best practices for using it
4. **Workflow Understanding**: What are the common workflows users perform?
5. **Expert Tips**: What would an expert know that a beginner wouldn't?

Return JSON:
{
  "appName": "Application name",
  "appPurpose": "Detailed purpose",
  "uiStructure": "How the UI is organized",
  "elements": [
    {
      "name": "Element name",
      "type": "button/menu/input/etc",
      "x": 123,
      "y": 456,
      "purpose": "Detailed purpose",
      "expertTip": "Expert knowledge about this element",
      "connections": "How it connects to other features"
    }
  ],
  "workflows": ["Common workflow 1", "Common workflow 2"],
  "expertTips": ["Expert tip 1", "Expert tip 2"]
}

Be EXTREMELY thorough. I want to know EVERYTHING about this app.`;
        const analysis = await this.visionLLM.analyzeScreen(screenshot, analysisPrompt);
        console.log('[UltronTeacher] Deep analysis complete:', analysis.explanation);
        // Speak the analysis
        await this.speak(analysis.explanation);
    }
    /**
     * Teach ALL UI elements systematically
     */
    async teachAllUIElements() {
        console.log('[UltronTeacher] Teaching ALL UI elements systematically...');
        const screenshot = this.virtualCursor.captureScreen();
        // Get all UI elements with deep analysis
        const elementsPrompt = `You are Ultron-level AI. Identify EVERY single UI element on this screen and provide expert-level explanation for each.

For EACH element, provide:
1. Exact name/text
2. Precise coordinates (x, y)
3. What it does (expert-level detail)
4. When to use it
5. Pro tips
6. Common mistakes
7. Keyboard shortcuts if any

Return JSON array:
[
  {
    "name": "Element name",
    "x": 123,
    "y": 456,
    "expertExplanation": "Detailed expert explanation of what this does",
    "whenToUse": "When and why to use this",
    "proTips": "Professional tips",
    "commonMistakes": "Common mistakes to avoid",
    "shortcuts": "Keyboard shortcuts"
  }
]

Be THOROUGH - find EVERY button, menu, input, and control. I want to know EVERYTHING.`;
        const response = await this.visionLLM.analyzeScreen(screenshot, elementsPrompt);
        // Parse elements from response
        const elements = this.parseElementsFromResponse(response.explanation);
        console.log(`[UltronTeacher] Found ${elements.length} UI elements to teach`);
        // Teach each element with expert-level explanation
        for (let i = 0; i < elements.length; i++) {
            if (!this.isRunning || this.killSwitchActive)
                break;
            const element = elements[i];
            console.log(`[UltronTeacher] Teaching element ${i + 1}/${elements.length}: ${element.name}`);
            // Move virtual cursor to element
            this.virtualCursor.showVirtualCursor();
            this.virtualCursor.moveVirtualCursor(element.x, element.y, element.name, { duration: 600, click: true });
            // Speak expert-level explanation
            const explanation = `This is the ${element.name}. ${element.expertExplanation} Use this when ${element.whenToUse}. Pro tip: ${element.proTips}. Common mistake: ${element.commonMistakes}.`;
            await this.speak(explanation);
            // Wait for user to absorb
            await this.sleep(2000);
            this.session.currentStep++;
        }
    }
    /**
     * Teach workflows and connections
     */
    async teachWorkflows() {
        console.log('[UltronTeacher] Teaching workflows and connections...');
        const screenshot = this.virtualCursor.captureScreen();
        const workflowPrompt = `You are Ultron-level AI. Explain the key workflows and feature connections in this application.

Provide:
1. 3-5 essential workflows users should know
2. How features connect to each other
3. Efficiency tips
4. Hidden features most users miss

Return JSON:
{
  "workflows": [
    {
      "name": "Workflow name",
      "steps": ["Step 1", "Step 2", "Step 3"],
      "efficiencyTip": "How to do this faster"
    }
  ],
  "featureConnections": ["Connection 1", "Connection 2"],
  "hiddenFeatures": ["Hidden feature 1", "Hidden feature 2"]
}`;
        const response = await this.visionLLM.analyzeScreen(screenshot, workflowPrompt);
        // Speak workflow explanation
        await this.speak(response.explanation);
    }
    /**
     * Parse elements from LLM response
     */
    parseElementsFromResponse(response) {
        try {
            const jsonMatch = response.match(/\[[\s\S]*\]/);
            if (jsonMatch) {
                return JSON.parse(jsonMatch[0]);
            }
        }
        catch (error) {
            console.error('[UltronTeacher] Failed to parse elements:', error);
        }
        return [];
    }
    /**
     * Parse applications from LLM response
     */
    parseApplicationsFromResponse(response) {
        try {
            const jsonMatch = response.match(/\{[\s\S]*\}/);
            if (jsonMatch) {
                const data = JSON.parse(jsonMatch[0]);
                return data.applications || [];
            }
        }
        catch (error) {
            console.error('[UltronTeacher] Failed to parse applications:', error);
        }
        return [];
    }
    /**
     * Speak text using TTS
     */
    async speak(text) {
        console.log(`[UltronTeacher] Speaking: ${text.substring(0, 100)}...`);
        // In production, integrate with Edge TTS or system TTS
        // For now, just log it
        await this.sleep(100);
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
        console.log('[UltronTeacher] Stopping teaching...');
        this.isRunning = false;
        if (this.session) {
            this.session.status = 'stopped';
        }
        this.virtualCursor.hideVirtualCursor();
    }
    /**
     * Activate kill switch
     */
    activateKillSwitch() {
        console.log('[UltronTeacher] Kill switch activated!');
        this.killSwitchActive = true;
    }
    /**
     * Get session status
     */
    getSessionStatus() {
        return this.session;
    }
}
exports.UltronLevelTeacher = UltronLevelTeacher;
