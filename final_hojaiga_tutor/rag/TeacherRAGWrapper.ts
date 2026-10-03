/**
 * TeacherRAGWrapper - Operational wrapper for RAG-based teaching
 * Extracts relevant context from documentation, pairs it with live UI tree
 * Instructs local LLM to select exact target element without hallucinations
 */

import { AppKnowledgeRAG } from './AppKnowledgeRAG';
import { UIElementNode, TeacherStepDecision } from './types';

export class TeacherRAGWrapper {
  private ragEngine: AppKnowledgeRAG;
  private ollamaHost: string;
  private chatModel: string;

  constructor(
    ragEngine: AppKnowledgeRAG,
    ollamaHost: string = 'http://127.0.0.1:11434',
    chatModel: string = 'qwen2.5:7b'
  ) {
    this.ragEngine = ragEngine;
    this.ollamaHost = ollamaHost;
    this.chatModel = chatModel;
  }

  /**
   * Generate multiple sequential steps at once (for interactive tutor)
   * Returns an array of steps instead of a single step
   */
  public async determineNextSteps(
    appName: string,
    userGoal: string,
    visibleElements: UIElementNode[],
    numSteps: number = 3
  ): Promise<TeacherStepDecision[]> {
    // 1. Retrieve the exact paragraph from the local knowledge base
    const relevantDocs = await this.ragEngine.queryKnowledge(appName, userGoal, 3);
    
    // CRITICAL RUNTIME CHECK #3: Context-Prefixed RAG Chunks
    // The chunk content now includes [Section: ...] prefix for better vector search
    // We strip the prefix when displaying to the LLM to keep the prompt clean
    const manualContext = relevantDocs.map(d => {
      const cleanContent = d.chunk.content.replace(/^\[Section: [^\]]+\]\n?/, '');
      return `[Manual Topic: ${d.chunk.topic}]\n${cleanContent}`;
    }).join('\n\n');

    console.log(`[RAG] Retrieved ${relevantDocs.length} relevant documentation chunks for ${appName}`);

    // 2. Format a compact UI tree list (avoids token bloat for small 7B models)
    const uiList = visibleElements.slice(0, 45).map(el => 
      `- Name: "${el.name}" | Type: ${el.controlType} | AutomationId: "${el.automationId}"`
    ).join('\n');

    // 3. Interactive tutor prompt - generate JSON array of steps
    // STRICT: No conversational fluff, only JSON output
    const prompt = `You are a strict JSON data generator for OS automation. Do NOT include greetings, explanations, or markdown. Output ONLY a valid JSON array.

USER GOAL: "${userGoal}"
TARGET APP: "${appName}"

RELEVANT APP MANUAL:
${manualContext || "No documentation found. Rely strictly on UI element semantics."}

CURRENT VISIBLE UI CONTROLS ON SCREEN:
${uiList}

TASK:
Generate exactly ${numSteps} sequential steps to accomplish the goal. Each explanation must be 1-2 sentences maximum - concise and actionable. You MUST return a JSON ARRAY with ${numSteps} objects, not a single object. Output ONLY a valid JSON array starting with [ and ending with ].

EXAMPLE OUTPUT (copy this format exactly):
[
  {
    "explanation": "Click the File menu to open options",
    "actionType": "EXPAND",
    "targetAutomationId": "MenuBarItem",
    "targetName": "File",
    "inputValue": ""
  },
  {
    "explanation": "Select Save from the menu",
    "actionType": "INVOKE",
    "targetAutomationId": "SaveButton",
    "targetName": "Save",
    "inputValue": ""
  }
]

ACTION TYPES: INVOKE (click button), EXPAND (open menu), TYPE (enter text), WAIT (pause)
CRITICAL: Output MUST start with [ and end with ]. Do NOT output a single object.
`;

    console.log(`[RAG] Querying local LLM (${this.chatModel}) for sequential steps...`);

    const response = await fetch(`${this.ollamaHost}/api/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model: this.chatModel,
        prompt: prompt,
        format: 'json',
        stream: false,
        options: { 
          temperature: 0.0, // Zero temperature for deterministic output
          top_p: 0.9,
          num_predict: 500 // Limit output length
        }
      })
    });

    const data = await response.json();
    
    // Guard clause: Check if response exists and is a string
    if (!data.response || typeof data.response !== 'string') {
      console.error('[RAG] Invalid response from LLM:', data);
      throw new Error('LLM returned invalid response format');
    }
    
    // Try to parse as JSON array
    try {
      const decisions = JSON.parse(data.response) as TeacherStepDecision[];
      
      // Guard clause: Ensure we got an array
      if (!Array.isArray(decisions)) {
        console.error('[RAG] LLM did not return an array, got:', typeof decisions);
        // Try to wrap single object in array
        if (typeof decisions === 'object' && decisions !== null) {
          return [decisions as TeacherStepDecision];
        }
        throw new Error('LLM did not return a JSON array');
      }
      
      // Guard clause: Ensure array is not empty
      if (decisions.length === 0) {
        console.error('[RAG] LLM returned empty array');
        throw new Error('LLM returned empty step array');
      }
      
      console.log(`[RAG] LLM generated ${decisions.length} sequential steps`);
      return decisions;
    } catch (parseError) {
      console.error(`[RAG] Failed to parse LLM response as JSON: ${data.response}`);
      console.error('[RAG] Parse error:', parseError);
      
      // Fallback: Try to extract JSON from conversational text
      const jsonMatch = data.response.match(/\[[\s\S]*\]/);
      if (jsonMatch) {
        try {
          const extractedDecisions = JSON.parse(jsonMatch[0]) as TeacherStepDecision[];
          if (Array.isArray(extractedDecisions) && extractedDecisions.length > 0) {
            console.log('[RAG] Successfully extracted JSON from conversational response');
            return extractedDecisions;
          }
        } catch (extractError) {
          console.error('[RAG] Failed to extract JSON from response:', extractError);
        }
      }
      
      throw new Error(`LLM returned malformed JSON: ${data.response.substring(0, 200)}...`);
    }
  }

  /**
   * Determines the exact step by merging User Goal + RAG Manual + Visible UI Tree
   * Enhanced with live UI tree grounding and single-step constraint
   */
  public async determineNextStep(
    appName: string,
    userGoal: string,
    visibleElements: UIElementNode[],
    lastAction?: string
  ): Promise<TeacherStepDecision> {
    // 1. Retrieve the exact paragraph from the local knowledge base
    const relevantDocs = await this.ragEngine.queryKnowledge(appName, userGoal, 2);
    
    // CRITICAL RUNTIME CHECK #3: Context-Prefixed RAG Chunks
    // The chunk content now includes [Section: ...] prefix for better vector search
    // We strip the prefix when displaying to the LLM to keep the prompt clean
    const manualContext = relevantDocs.map(d => {
      // Remove the [Section: ...] prefix for display to LLM
      const cleanContent = d.chunk.content.replace(/^\[Section: [^\]]+\]\n?/, '');
      return `[Manual Topic: ${d.chunk.topic}]\n${cleanContent}`;
    }).join('\n\n');

    console.log(`[RAG] Retrieved ${relevantDocs.length} relevant documentation chunks for ${appName}`);

    // 2. Format a compact UI tree list (avoids token bloat for small 7B models)
    const uiList = visibleElements.slice(0, 45).map(el => 
      `- Name: "${el.name}" | Type: ${el.controlType} | AutomationId: "${el.automationId}"`
    ).join('\n');

    // 3. Extract just the element names for grounding
    const visibleElementNames = visibleElements.slice(0, 20).map(el => el.name).join(', ');

    // 4. Reactive single-step prompt with live UI grounding
    const prompt = `You are a reactive UI tutor. You guide the user exactly ONE step at a time based on what is currently visible on screen.

USER GOAL: "${userGoal}"
TARGET APP: "${appName}"

RELEVANT APP MANUAL:
${manualContext || "No documentation found. Rely strictly on UI element semantics."}

CURRENTLY VISIBLE BUTTONS: [${visibleElementNames}]

LAST ACTION TAKEN: ${lastAction || "None"}

RULE 1: ONLY explain and interact with elements strictly listed in CURRENTLY VISIBLE BUTTONS.
RULE 2: Do not explain features if they are not currently visible.
RULE 3: Output ONLY a single JSON object. Do not output an array.

TASK: Based on the LAST ACTION TAKEN and the CURRENTLY VISIBLE BUTTONS, what is the single next immediate action required?

Output ONLY a single JSON object matching this schema:
{
  "explanation": "Now that the Insert menu is open, let's click Table.",
  "actionType": "INVOKE",
  "targetAutomationId": "AutomationId from the list above",
  "targetName": "Name from the list above",
  "inputValue": ""
}

ACTION TYPES: INVOKE (click button), EXPAND (open menu), TYPE (enter text), WAIT (pause), ASK_USER (ask user for input)
If the goal is finished, set actionType to "COMPLETE".
`;

    console.log(`[RAG] Querying local LLM (${this.chatModel}) for decision...`);

    const response = await fetch(`${this.ollamaHost}/api/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model: this.chatModel,
        prompt: prompt,
        format: 'json',
        stream: false,
        options: { 
          temperature: 0.0, // Zero temperature for deterministic output
          top_p: 0.9,
          num_predict: 300 // Limit output length
        }
      })
    });

    const data = await response.json();
    
    // Guard clause: Check if response exists and is a string
    if (!data.response || typeof data.response !== 'string') {
      console.error('[RAG] Invalid response from LLM:', data);
      throw new Error('LLM returned invalid response format');
    }
    
    try {
      const decision = JSON.parse(data.response) as TeacherStepDecision;
      
      // Guard clause: Ensure decision has required fields
      if (!decision.actionType || !decision.targetName) {
        console.error('[RAG] LLM returned invalid decision structure:', decision);
        throw new Error('LLM returned decision missing required fields (actionType, targetName)');
      }
      
      console.log(`[RAG] LLM decision: ${decision.actionType} on ${decision.targetName}`);
      return decision;
    } catch (parseError) {
      console.error(`[RAG] Failed to parse LLM response as JSON: ${data.response}`);
      console.error('[RAG] Parse error:', parseError);
      
      // Fallback: Try to extract JSON from conversational text
      const jsonMatch = data.response.match(/\{[\s\S]*\}/);
      if (jsonMatch) {
        try {
          const extractedDecision = JSON.parse(jsonMatch[0]) as TeacherStepDecision;
          if (extractedDecision.actionType && extractedDecision.targetName) {
            console.log('[RAG] Successfully extracted JSON from conversational response');
            return extractedDecision;
          }
        } catch (extractError) {
          console.error('[RAG] Failed to extract JSON from response:', extractError);
        }
      }
      
      throw new Error(`LLM returned malformed JSON: ${data.response.substring(0, 200)}...`);
    }
  }
}
