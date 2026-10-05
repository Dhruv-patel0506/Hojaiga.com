/**
 * Core Types for Live Interactive Teaching Engine
 * State definitions, bounds, action payloads, safety constraints
 */

// ============================================================================
// STATE DEFINITIONS
// ============================================================================

export type AppState = 'unknown' | 'splash_screen' | 'initial' | 'ready' | 'dialog_open' | 'loading' | 'error';

export interface WindowBounds {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface NormalizedCoordinates {
  x: number; // 0.0 to 1.0 (relative to window)
  y: number; // 0.0 to 1.0 (relative to window)
}

export interface ScreenState {
  appId: string;
  appTitle: string;
  bounds: WindowBounds;
  currentState: AppState;
  timestamp: number;
  screenshot: string; // base64
  isModalDialog?: boolean; // CRITICAL RUNTIME CHECK #2: True if window is a #32770 modal dialog
}

// ============================================================================
// ACTION PAYLOADS
// ============================================================================

export type ActionType = 'click' | 'rightClick' | 'doubleClick' | 'type' | 'drag' | 'scroll' | 'wait' | 'pressKey' | 'hotkey';

export interface TeachingAction {
  id: string;
  actionType: ActionType;
  targetName: string;
  normalizedCoords: NormalizedCoordinates;
  payload?: string; // text to type, key to press, etc.
  description: string; // What this action does (for TTS)
  expectedTransition: AppState; // What state we expect after this action
  confidence: number; // 0-1
}

export interface ActionStep {
  stepNumber: number;
  action: TeachingAction;
  explanation: string;
  verificationCriteria: string;
}

// ============================================================================
// SAFETY CONSTRAINTS
// ============================================================================

export interface SafetyConfig {
  maxActionsPerSession: number;
  maxActionDuration: number; // milliseconds
  stateVerificationTimeout: number; // milliseconds
  inputBoundaryPadding: number; // pixels from window edge
  enableKillSwitch: boolean;
  killSwitchZones: Array<{ x: number; y: number; width: number; height: number }>;
  blocklistApps: string[];
  requireConfirmationFor: ActionType[];
}

export interface EmergencyStopSignal {
  triggered: boolean;
  reason: 'mouse_jerk' | 'escape_key' | 'timeout' | 'user_manual' | 'queue_full';
  timestamp: number;
}

// ============================================================================
// VERIFICATION RESULTS
// ============================================================================

export interface StateVerification {
  beforeState: ScreenState;
  afterState: ScreenState;
  expectedTransition: AppState;
  actualTransition: AppState;
  success: boolean;
  confidence: number;
  reason: string;
  details?: any;  // Additional verification details (windowChanged, uiChanged, etc.)
}

// ============================================================================
// EVENTS
// ============================================================================

export type TeachingEvent =
  | { type: 'stepStart'; step: ActionStep }
  | { type: 'stepComplete'; step: ActionStep; verification: StateVerification }
  | { type: 'stepFailed'; step: ActionStep; error: string }
  | { type: 'stateVerification'; verification: StateVerification }
  | { type: 'emergencyStop'; signal: EmergencyStopSignal }
  | { type: 'sessionComplete'; totalSteps: number }
  | { type: 'error'; error: Error; context: string };

export type EventListener = (event: TeachingEvent) => void;

// ============================================================================
// LEGACY TYPES FOR CLICKY COMPATIBILITY
// ============================================================================

export type CompanionVoiceState = 'idle' | 'listening' | 'processing' | 'speaking' | 'responding';

export interface CompanionScreenCapture {
  base64?: string;
  imageDataBase64?: string;
  timestamp?: number;
  screenshotWidthInPixels?: number;
  screenshotHeightInPixels?: number;
  displayWidthInPoints?: number;
  displayHeightInPoints?: number;
  displayId?: number;
  isCursorScreen?: boolean;
  label?: string;
  displayFrame?: { x: number; y: number; width: number; height: number };
  windowInfo?: {
    title: string;
    bounds: { x: number; y: number; width: number; height: number };
  };
}

export type DrawShapeType = 'circle' | 'arrow' | 'rect' | 'line' | 'text';

export interface DrawCommand {
  type: DrawShapeType;
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  color?: string;
  text?: string;
  duration?: number;
  coords?: number[];
  label?: string;
}

export interface PointingParseResult {
  points?: Array<{ x: number; y: number; label: string }>;
  cleanedText?: string;
  spokenText?: string;
  coordinate?: { x: number; y: number };
  elementLabel?: string;
  screenNumber?: number;
  drawCommands?: DrawCommand[];
}

// ============================================================================
// UI TREE NODE (from Windows Accessibility API)
// ============================================================================

export interface UITreeNode {
  id?: string;
  name: string;
  role?: string;
  className?: string;
  automationId?: string;  // Windows UI Automation ID
  boundingBox?: { x: number; y: number; width: number; height: number };
  isClickable?: boolean;
  isEnabled?: boolean;
  text?: string;
  level?: number;  // Hierarchy depth
  parentId?: string;  // Parent element ID
  children?: UITreeNode[];
}

// ============================================================================
// APP KNOWLEDGE BASE
// ============================================================================

export interface ButtonKnowledge {
  id: string;
  name: string;
  semanticLabel: string; // "Create new document", "Save", "Delete", etc.
  description: string; // What this button does
  category: string; // "File", "Edit", "View", "Tools", etc.
  position: { x: number; y: number; width: number; height: number };
  shortcut?: string; // Ctrl+S, Ctrl+N, etc.
  leadsTo?: string; // What screen/dialog this button opens
  confidence: number; // 0-1
}

export interface AppKnowledge {
  appId: string;
  appName: string;
  appType: string; // "Word Processor", "Spreadsheet", "Browser", etc.
  buttons: Map<string, ButtonKnowledge>;
  workflows: Array<{
    name: string;
    steps: Array<{ buttonId: string; action: string }>;
  }>;
  lastScanned: number;
  version: number;
}

export interface VirtualCursorState {
  isDetached: boolean; // true when Clicky is working independently
  mode: 'idle' | 'teaching' | 'executing';
  color: string; // 'magenta' when detached, follows physical mouse when idle
  position: { x: number; y: number };
}
