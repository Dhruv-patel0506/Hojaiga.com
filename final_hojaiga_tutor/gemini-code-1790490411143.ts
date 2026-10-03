export type CompanionVoiceState = 'idle' | 'listening' | 'processing' | 'responding';

export interface CompanionScreenCapture {
  imageDataBase64: string;
  label: string;
  isCursorScreen: boolean;
  displayId: number;
  displayWidthInPoints: number;
  displayHeightInPoints: number;
  displayFrame: { x: number; y: number; width: number; height: number };
  screenshotWidthInPixels: number;
  screenshotHeightInPixels: number;
}

export interface PointingParseResult {
  spokenText: string;
  coordinate: { x: number; y: number } | null;
  elementLabel: string | null;
  screenNumber: number | null;
}

export interface AppStatusPayload {
  voiceState: CompanionVoiceState;
  selectedModel: string;
  isOverlayVisible: boolean;
  hasCompletedOnboarding: boolean;
  lastTranscript: string;
}