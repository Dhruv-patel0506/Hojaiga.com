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
   * Determines the exact step by merging User Goal + RAG Manual + Visible UI Tree
   */
  public async determineNextStep(
    appName: string,
    userGoal: string,
    visibleElements: UIElementNode[]
  ): Promise<TeacherStepDecision> {
    // 1. Retrieve the exact paragraph from the local knowledge base
    const relevantDocs = await this.ragEngine.queryKnowledge(appName, userGoal, 2);
    const manualContext = relevantDocs.map(d => `[Manual Topic: ${d.chunk.topic}]\n${d.chunk.content}`).join('\n\n');

    console.log(`[RAG] Retrieved ${relevantDocs.length} relevant documentation chunks for ${appName}`);

    // 2. Format a compact UI tree list (avoids token bloat for small 7B models)
    const uiList = visibleElements.slice(0, 45).map(el => 
      `- Name: "${el.name}" | Type: ${el.controlType} | AutomationId: "${el.automationId}"`
    ).join('\n');

    // 3. Strict prompt forcing string matching between manual and accessibility tree
    const prompt = `You are a real-time software tutor.
USER GOAL: "${userGoal}"
TARGET APP: "${appName}"

RELEVANT APP MANUAL:
${manualContext || "No documentation found. Rely strictly on UI element semantics."}

CURRENT VISIBLE UI CONTROLS ON SCREEN:
${uiList}

TASK:
1. Identify the SINGLE immediate step required to advance toward the user's goal based on the manual.
2. Match that step to the exact button or menu available in CURRENT VISIBLE UI CONTROLS.
3. Return ONLY a valid JSON object matching this schema:
{
  "explanation": "Clear, friendly explanation of what you are doing (to be spoken by TTS)",
  "actionType": "INVOKE" | "EXPAND" | "TYPE" | "WAIT",
  "targetAutomationId": "AutomationId from the list above",
  "targetName": "Name from the list above",
  "inputValue": "Text to type if action is TYPE"
}`;

    console.log(`[RAG] Querying local LLM (${this.chatModel}) for decision...`);

    const response = await fetch(`${this.ollamaHost}/api/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model: this.chatModel,
        prompt: prompt,
        format: 'json',
        stream: false,
        options: { temperature: 0.1 } // Low temperature prevents hallucinations
      })
    });

    const data = await response.json();
    try {
      const decision = JSON.parse(data.response) as TeacherStepDecision;
      console.log(`[RAG] LLM decision: ${decision.actionType} on ${decision.targetName}`);
      return decision;
    } catch {
      console.error(`[RAG] LLM returned malformed JSON: ${data.response}`);
      throw new Error(`LLM returned malformed JSON: ${data.response}`);
    }
  }
}
