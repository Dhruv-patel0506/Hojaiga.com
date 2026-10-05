import { WindowsEnvWrapper, TestingEnvWrapper } from './platform/PlatformWrapper';
import { OllamaVisionAPI } from './llm/OllamaVision';
import { AppScanner } from './engine/AppScanner';
import { TeacherAgent } from './core/TeacherAgent';
import { DynamicAppTeacher } from './core/DynamicAppTeacher';
import { ActionExplorer } from './core/ActionExplorer';

// Default Ollama installation directory (D drive)
const DEFAULT_OLLAMA_HOME = 'D:\\Ollama';

/**
 * Factory function to create a TeacherAgent with the appropriate environment
 */
export async function createTeacherAgent(
  overlayWindow?: any, // Electron BrowserWindow if available
  isTestMode: boolean = false,
  ollamaHome?: string
): Promise<TeacherAgent> {
  // 1. Determine Environment Wrapper
  const envWrapper = isTestMode
    ? new TestingEnvWrapper()
    : new WindowsEnvWrapper(overlayWindow);

  // 2. Initialize Core Systems
  const llmEngine = new OllamaVisionAPI(
    undefined, // default endpoint
    undefined, // default model
    ollamaHome || DEFAULT_OLLAMA_HOME
  );
  const appScanner = new AppScanner();

  // 3. Initialize OCR
  await appScanner.initializeOCR();

  // 4. Boot Agent
  const teacher = new TeacherAgent(envWrapper, llmEngine, appScanner);

  return teacher;
}

/**
 * Factory function to create a DynamicAppTeacher for comprehensive app teaching
 */
export async function createDynamicAppTeacher(
  overlayWindow?: any,
  isTestMode: boolean = false,
  ollamaHome?: string
): Promise<DynamicAppTeacher> {
  const envWrapper = isTestMode
    ? new TestingEnvWrapper()
    : new WindowsEnvWrapper(overlayWindow);

  const llmEngine = new OllamaVisionAPI(
    undefined,
    undefined,
    ollamaHome || DEFAULT_OLLAMA_HOME
  );
  const appScanner = new AppScanner();

  await appScanner.initializeOCR();

  return new DynamicAppTeacher(envWrapper, llmEngine, appScanner, overlayWindow);
}

/**
 * Factory function to create an ActionExplorer for UI exploration
 */
export async function createActionExplorer(
  overlayWindow?: any,
  isTestMode: boolean = false,
  ollamaHome?: string
): Promise<ActionExplorer> {
  const envWrapper = isTestMode
    ? new TestingEnvWrapper()
    : new WindowsEnvWrapper(overlayWindow);

  const llmEngine = new OllamaVisionAPI(
    undefined,
    undefined,
    ollamaHome || DEFAULT_OLLAMA_HOME
  );
  const appScanner = new AppScanner();

  await appScanner.initializeOCR();

  return new ActionExplorer(envWrapper, llmEngine, appScanner);
}

/**
 * Standalone entry point for testing the vision platform independently
 */
export async function main(): Promise<void> {
  console.log('=== Vision Platform Standalone Test ===');

  const teacher = await createTeacherAgent(undefined, true); // Test mode

  const userGoal = 'Show me how to add an audio track in Premiere Pro';
  console.log(`Starting lesson: ${userGoal}`);

  await teacher.startTeaching(userGoal);
}

// Uncomment to run standalone:
// main().catch(console.error);
