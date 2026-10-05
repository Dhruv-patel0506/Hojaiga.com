"use strict";
/**
 * Vision LLM Integration - Ollama LLaVA
 * Connects to Ollama for vision-based action planning
 */
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.OllamaVisionAPI = void 0;
const axios_1 = __importDefault(require("axios"));
class OllamaVisionAPI {
    endpoint;
    model;
    constructor(endpoint = 'http://localhost:11434', model = 'llava') {
        this.endpoint = endpoint;
        this.model = model;
    }
    async initialize() {
        try {
            const response = await axios_1.default.get(`${this.endpoint}/api/tags`);
            return response.status === 200;
        }
        catch (error) {
            console.error('[OllamaVision] Failed to connect:', error);
            return false;
        }
    }
    async analyzeScreen(screenshot, prompt) {
        try {
            const response = await axios_1.default.post(`${this.endpoint}/api/generate`, {
                model: this.model,
                prompt: prompt,
                images: [screenshot],
                stream: false
            }, {
                timeout: 120000 // 2 minutes
            });
            const result = response.data;
            const text = result.response;
            // Return raw text for comprehensive analysis
            return {
                nextAction: {
                    actionType: 'explain',
                    description: 'Analysis complete',
                    confidence: 0.9
                },
                explanation: text,
                confidence: 0.9
            };
        }
        catch (error) {
            console.error('[OllamaVision] Failed to analyze screen:', error);
            return {
                nextAction: {
                    actionType: 'explain',
                    description: 'Failed to analyze screen',
                    confidence: 0
                },
                explanation: 'Analysis failed',
                confidence: 0
            };
        }
    }
    async getNextAction(screenshot, userGoal, uiTree, previousActions) {
        const prompt = `You are an expert UI interaction agent. Given a screenshot and user goal, determine the SINGLE next action.

User Goal: ${userGoal}

Available UI Elements: ${JSON.stringify(uiTree.slice(0, 20))}

Previous Actions: ${JSON.stringify(previousActions.slice(-5))}

IMPORTANT: When you want to point to a UI element, use the EXACT format:
[POINT:x,y:label:screen0]

Where:
- x = X coordinate in pixels
- y = Y coordinate in pixels
- label = What this element is (e.g., "File menu", "Bold button")
- screen0 = Always use screen0 for single monitor

Example: "First, let's go to the [POINT:100,50:File menu:screen0] to open the menu."

Your response should be natural text with embedded POINT tags. The system will:
1. Extract POINT tags to move the virtual cursor
2. Remove POINT tags before sending to TTS
3. Speak the explanation to the user

Return JSON format:
{
  "nextAction": {
    "actionType": "click|rightClick|doubleClick|type|drag|scroll|wait|verify|explain",
    "target": {
      "nodeId": "UI element ID from tree",
      "name": "Button name",
      "coordinates": {"x": 123, "y": 456}
    },
    "payload": "text to type if typing",
    "description": "What this action does",
    "confidence": 0.95,
    "reasoning": "Why this action"
  },
  "explanation": "Your explanation with embedded POINT tags like [POINT:x,y:label:screen0]",
  "verificationCriteria": "What should change after this action",
  "confidence": 0.95
}

ALWAYS include POINT tags in your explanation when pointing to UI elements.
Use exact pixel coordinates based on the screenshot dimensions.
Be specific and precise in your response.`;
        return this.analyzeScreen(screenshot, prompt);
    }
}
exports.OllamaVisionAPI = OllamaVisionAPI;
