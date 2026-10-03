export interface BoundingBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface UIElement {
  id: string;
  text?: string;
  type: 'button' | 'menu' | 'input' | 'canvas' | 'text' | 'unknown';
  bounds: BoundingBox;
  confidence?: number;
}

export interface ScreenState {
  screenshotBase64: string;
  elements: UIElement[];
  timestamp: number;
  appContext?: {
    processName?: string;
    windowTitle?: string;
  };
}

export interface AgentAction {
  actionType: 'click' | 'type' | 'drag' | 'explain' | 'wait' | 'highlight';
  targetText?: string;
  targetCoordinates?: { x: number; y: number };
  payload?: string; // Text to type or explanation to speak
  elementId?: string;
  priority?: number; // 1-10, higher = more important
}

export interface TeachingContext {
  goal: string;
  currentStep: number;
  totalSteps: number;
  isComplete: boolean;
  lastState?: ScreenState;
}
