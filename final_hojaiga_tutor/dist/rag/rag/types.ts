/**
 * RAG Types for Retrieval-Augmented Generation
 * Interfaces for documents, vectors, and query payloads
 */

export interface DocumentChunk {
  id: string;
  appName: string;
  topic: string;
  content: string;
  embedding?: number[];
}

export interface SearchResult {
  chunk: DocumentChunk;
  score: number;
}

export interface UIElementNode {
  name: string;
  automationId: string;
  controlType: string;
  bounds: { x: number; y: number; width: number; height: number };
}

export interface TeacherStepDecision {
  explanation: string;
  actionType: 'INVOKE' | 'EXPAND' | 'TYPE' | 'WAIT';
  targetAutomationId?: string;
  targetName?: string;
  inputValue?: string;
}
