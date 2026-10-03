import axios from 'axios';
import { AgentAction } from '../types';

export class OllamaVisionAPI {
  private endpoint: string = 'http://localhost:11434/api/generate';
  private model: string = 'llava'; // LLaVA is a vision model, can also use 'llama3.1-vision' if available
  private ollamaHome: string = 'D:\\Ollama'; // Default to D drive installation

  constructor(customEndpoint?: string, customModel?: string, customOllamaHome?: string) {
    if (customEndpoint) this.endpoint = customEndpoint;
    if (customModel) this.model = customModel;
    if (customOllamaHome) this.ollamaHome = customOllamaHome;
  }

  async analyzeScreen(screenshotBase64: string, instruction: string): Promise<AgentAction[]> {
    const prompt = `
You are a professional App Teacher AI. Analyze this UI screenshot.

User Goal: ${instruction}

Task: Determine the next step(s) to achieve this goal. Look at the UI and identify:
1. What UI elements are visible (buttons, menus, inputs, etc.)
2. What the user should click or type next
3. Provide a brief explanation before each action

Return ONLY a valid JSON array of actions. Format:
[
  {
    "actionType": "explain",
    "payload": "Brief explanation of what to do"
  },
  {
    "actionType": "click",
    "targetCoordinates": {"x": 100, "y": 200},
    "targetText": "Button label"
  }
]

If the goal appears complete, return an empty array.
`;

    try {
      const response = await axios.post(this.endpoint, {
        model: this.model,
        prompt: prompt,
        stream: false,
        images: [screenshotBase64],
      }, { timeout: 30000 });

      const responseText = response.data.response;
      console.log('[OllamaVision] Raw response:', responseText.substring(0, 200));

      // Extract JSON from response
      const jsonMatch = responseText.match(/\[.*\]/s);
      if (jsonMatch) {
        try {
          const actions = JSON.parse(jsonMatch[0]) as AgentAction[];
          console.log('[OllamaVision] Parsed actions:', actions);
          return actions;
        } catch (parseError) {
          console.error('[OllamaVision] JSON parse error:', parseError);
        }
      }

      // Fallback: try to parse entire response as JSON
      try {
        const actions = JSON.parse(responseText) as AgentAction[];
        return actions;
      } catch {
        console.warn('[OllamaVision] Could not parse actions from response');
      }

      return [];
    } catch (error) {
      console.error('[OllamaVision] API Error:', error);
      return [];
    }
  }

  async checkOllamaAvailable(): Promise<boolean> {
    try {
      await axios.get('http://localhost:11434/api/tags', { timeout: 2000 });
      return true;
    } catch {
      return false;
    }
  }

  async getAvailableModels(): Promise<string[]> {
    try {
      const response = await axios.get('http://localhost:11434/api/tags', { timeout: 2000 });
      return response.data.models?.map((m: any) => m.name) || [];
    } catch {
      return [];
    }
  }

  /**
   * Start Ollama server if not running
   * This is a helper method that can be called before using the vision API
   */
  async ensureOllamaRunning(): Promise<boolean> {
    // Check if already running
    if (await this.checkOllamaAvailable()) {
      console.log('[OllamaVision] Ollama server is already running');
      return true;
    }

    console.log('[OllamaVision] Ollama server not running, attempting to start...');

    try {
      const { exec } = require('child_process');
      const { promisify } = require('util');
      const execAsync = promisify(exec);

      // Start Ollama server from D drive
      const ollamaPath = this.ollamaHome + '\\ollama.exe';

      // Start server in background
      exec(`"${ollamaPath}" serve`, (error: any) => {
        if (error) {
          console.error('[OllamaVision] Failed to start Ollama server:', error);
        }
      });

      // Wait for server to start
      console.log('[OllamaVision] Waiting for Ollama server to start...');
      await new Promise(resolve => setTimeout(resolve, 5000));

      // Check if it's running now
      if (await this.checkOllamaAvailable()) {
        console.log('[OllamaVision] Ollama server started successfully');
        return true;
      } else {
        console.error('[OllamaVision] Ollama server failed to start');
        return false;
      }
    } catch (error) {
      console.error('[OllamaVision] Error starting Ollama:', error);
      return false;
    }
  }

  /**
   * Pull LLaVA model if not already downloaded
   */
  async ensureModelDownloaded(): Promise<boolean> {
    const models = await this.getAvailableModels();
    const hasLlava = models.some(m => m.includes('llava'));

    if (hasLlava) {
      console.log('[OllamaVision] LLaVA model already downloaded');
      return true;
    }

    console.log('[OllamaVision] LLaVA model not found, downloading...');

    try {
      const { exec } = require('child_process');
      const { promisify } = require('util');
      const execAsync = promisify(exec);

      const ollamaPath = this.ollamaHome + '\\ollama.exe';

      await execAsync(`"${ollamaPath}" pull llava`);
      console.log('[OllamaVision] LLaVA model downloaded successfully');
      return true;
    } catch (error) {
      console.error('[OllamaVision] Failed to download LLaVA model:', error);
      return false;
    }
  }

  /**
   * Initialize Ollama (check server, start if needed, download model if needed)
   */
  async initialize(): Promise<boolean> {
    console.log('[OllamaVision] Initializing Ollama...');

    // Ensure server is running
    const serverRunning = await this.ensureOllamaRunning();
    if (!serverRunning) {
      console.error('[OllamaVision] Failed to start Ollama server');
      return false;
    }

    // Ensure model is downloaded
    const modelDownloaded = await this.ensureModelDownloaded();
    if (!modelDownloaded) {
      console.error('[OllamaVision] Failed to download LLaVA model');
      return false;
    }

    console.log('[OllamaVision] Ollama initialized successfully');
    return true;
  }
}
