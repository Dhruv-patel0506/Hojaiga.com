"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.createTeacherAgent = createTeacherAgent;
exports.createDynamicAppTeacher = createDynamicAppTeacher;
exports.createActionExplorer = createActionExplorer;
exports.main = main;
const PlatformWrapper_1 = require("./platform/PlatformWrapper");
const OllamaVision_1 = require("./llm/OllamaVision");
const AppScanner_1 = require("./engine/AppScanner");
const TeacherAgent_1 = require("./core/TeacherAgent");
const DynamicAppTeacher_1 = require("./core/DynamicAppTeacher");
const ActionExplorer_1 = require("./core/ActionExplorer");
// Default Ollama installation directory (D drive)
const DEFAULT_OLLAMA_HOME = 'D:\\Ollama';
/**
 * Factory function to create a TeacherAgent with the appropriate environment
 */
async function createTeacherAgent(overlayWindow, // Electron BrowserWindow if available
isTestMode = false, ollamaHome) {
    // 1. Determine Environment Wrapper
    const envWrapper = isTestMode
        ? new PlatformWrapper_1.TestingEnvWrapper()
        : new PlatformWrapper_1.WindowsEnvWrapper(overlayWindow);
    // 2. Initialize Core Systems
    const llmEngine = new OllamaVision_1.OllamaVisionAPI(undefined, // default endpoint
    undefined, // default model
    ollamaHome || DEFAULT_OLLAMA_HOME);
    const appScanner = new AppScanner_1.AppScanner();
    // 3. Initialize OCR
    await appScanner.initializeOCR();
    // 4. Boot Agent
    const teacher = new TeacherAgent_1.TeacherAgent(envWrapper, llmEngine, appScanner);
    return teacher;
}
/**
 * Factory function to create a DynamicAppTeacher for comprehensive app teaching
 */
async function createDynamicAppTeacher(overlayWindow, isTestMode = false, ollamaHome) {
    const envWrapper = isTestMode
        ? new PlatformWrapper_1.TestingEnvWrapper()
        : new PlatformWrapper_1.WindowsEnvWrapper(overlayWindow);
    const llmEngine = new OllamaVision_1.OllamaVisionAPI(undefined, undefined, ollamaHome || DEFAULT_OLLAMA_HOME);
    const appScanner = new AppScanner_1.AppScanner();
    await appScanner.initializeOCR();
    return new DynamicAppTeacher_1.DynamicAppTeacher(envWrapper, llmEngine, appScanner, overlayWindow);
}
/**
 * Factory function to create an ActionExplorer for UI exploration
 */
async function createActionExplorer(overlayWindow, isTestMode = false, ollamaHome) {
    const envWrapper = isTestMode
        ? new PlatformWrapper_1.TestingEnvWrapper()
        : new PlatformWrapper_1.WindowsEnvWrapper(overlayWindow);
    const llmEngine = new OllamaVision_1.OllamaVisionAPI(undefined, undefined, ollamaHome || DEFAULT_OLLAMA_HOME);
    const appScanner = new AppScanner_1.AppScanner();
    await appScanner.initializeOCR();
    return new ActionExplorer_1.ActionExplorer(envWrapper, llmEngine, appScanner);
}
/**
 * Standalone entry point for testing the vision platform independently
 */
async function main() {
    console.log('=== Vision Platform Standalone Test ===');
    const teacher = await createTeacherAgent(undefined, true); // Test mode
    const userGoal = 'Show me how to add an audio track in Premiere Pro';
    console.log(`Starting lesson: ${userGoal}`);
    await teacher.startTeaching(userGoal);
}
// Uncomment to run standalone:
// main().catch(console.error);
