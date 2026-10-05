/**
 * Core Types for Universal App Teacher
 * Defines all interfaces for UI nodes, screen state, actions, and events
 */

// ============================================================================
// UI ELEMENT TYPES
// ============================================================================

export interface UINode {
  id: string;
  name: string;
  role: string; // button, text, menu, slider, etc.
  bounds: BoundingBox;
  parent?: string;
  children?: UINode[];
  properties?: Record<string, any>;
  accessibleText?: string;
  isInteractable: boolean;
  isVisible: boolean;
}

export interface BoundingBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface ScreenState {
  screenshot: string; // base64 encoded
  timestamp: number;
  uiTree: UINode[];
  activeWindow: {
    title: string;
    processName: string;
    bounds: BoundingBox;
  };
  cursorPosition: { x: number; y: number };
}

// ============================================================================
// ACTION TYPES
// ============================================================================

export type ActionType = 'click' | 'rightClick' | 'doubleClick' | 'type' | 'drag' | 'scroll' | 'wait' | 'verify' | 'explain';

export interface AgentAction {
  actionType: ActionType;
  target?: {
    nodeId?: string;
    name?: string;
    coordinates?: { x: number; y: number };
  };
  payload?: string; // text to type, value to scroll, etc.
  description: string; // What this action does (for TTS)
  confidence: number; // 0-1
  reasoning?: string; // Why this action was chosen
}

export interface ActionPlan {
  actions: AgentAction[];
  reasoning: string;
  expectedOutcome: string;
  estimatedSteps: number;
}

// ============================================================================
// LLM TYPES
// ============================================================================

export interface VisionLLMRequest {
  screenshot: string;
  userGoal: string;
  currentState: ScreenState;
  previousActions: AgentAction[];
  context: string;
}

export interface VisionLLMResponse {
  nextAction: AgentAction;
  explanation: string;
  verificationCriteria?: string;
  confidence: number;
}

export interface LLMConfig {
  provider: 'anthropic' | 'openai' | 'ollama';
  model: string;
  apiKey?: string;
  endpoint?: string;
  maxTokens?: number;
  temperature?: number;
}

// ============================================================================
// OS WRAPPER TYPES
// ============================================================================

export interface OSControlCapabilities {
  mouseMove: boolean;
  mouseClick: boolean;
  keyboardInput: boolean;
  screenCapture: boolean;
  uiTreeExtraction: boolean;
  dragAndDrop: boolean;
}

export interface MouseMovementOptions {
  curve: 'linear' | 'bezier' | 'easeInEaseOut';
  duration: number; // milliseconds
  showCursor: boolean;
}

export interface KeyboardInputOptions {
  typingSpeed: number; // milliseconds per character
  useClipboard: boolean;
}

// ============================================================================
// TEACHING TYPES
// ============================================================================

export interface TeachingSession {
  id: string;
  userGoal: string;
  startTime: number;
  status: 'idle' | 'listening' | 'observing' | 'thinking' | 'teaching' | 'acting' | 'verifying' | 'complete' | 'error';
  currentStep: number;
  totalSteps: number;
  actionsExecuted: AgentAction[];
  verificationResults: VerificationResult[];
}

export interface VerificationResult {
  action: AgentAction;
  screenshotBefore: string;
  screenshotAfter: string;
  expectedChange: string;
  actualChange: string;
  success: boolean;
  confidence: number;
}

export interface TTSConfig {
  provider: 'edge' | 'system' | 'elevenlabs';
  voice?: string;
  rate: number;
  pitch: number;
}

export interface OverlayConfig {
  showCursor: boolean;
  showHighlight: boolean;
  showTooltip: boolean;
  cursorColor: string;
  highlightColor: string;
}

// ============================================================================
// EVENT TYPES
// ============================================================================

export type TeacherEvent =
  | { type: 'sessionStart'; session: TeachingSession }
  | { type: 'sessionEnd'; session: TeachingSession }
  | { type: 'actionStart'; action: AgentAction }
  | { type: 'actionComplete'; action: AgentAction; result: VerificationResult }
  | { type: 'explanationStart'; text: string }
  | { type: 'explanationComplete'; text: string }
  | { type: 'error'; error: Error; context: string }
  | { type: 'abort'; reason: string };

export type EventListener = (event: TeacherEvent) => void;

// ============================================================================
// KILL SWITCH TYPES
// ============================================================================

export interface KillSwitchConfig {
  enabled: boolean;
  trigger: 'mouseMove' | 'keyboard' | 'voice' | 'manual';
  hotkey?: string;
  mouseZone?: { x: number; y: number; width: number; height: number };
}

export interface SafetyConfig {
  maxActionsPerSession: number;
  maxActionDuration: number;
  requireConfirmationFor: ActionType[];
  blocklistApps: string[];
  allowlistApps?: string[];
}
