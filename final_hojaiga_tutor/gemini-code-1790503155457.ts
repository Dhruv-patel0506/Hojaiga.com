import { screen } from 'electron';
import { ClaudeAPI } from './ClaudeAPI';
import { ElevenLabsTTSClient } from './ElevenLabsTTSClient';
import { CompanionScreenCaptureUtility } from './CompanionScreenCaptureUtility';
import { OverlayWindowManager } from './OverlayWindowManager';
import { MenuBarPanelManager } from './MenuBarPanelManager';
import { GlobalPushToTalkShortcutMonitor, ShortcutTransition } from './GlobalPushToTalkShortcutMonitor';
import { BuddyDictationManager } from './BuddyDictationManager';
import { ClickyAnalytics } from './ClickyAnalytics';
import { CompanionVoiceState } from './types';

export class CompanionManager {
  public voiceState: CompanionVoiceState = 'idle';
  public anotherScreenNavigating = false;

  public readonly claudeAPI = new ClaudeAPI();
  public readonly elevenLabsTTSClient = new ElevenLabsTTSClient();
  public readonly overlayWindowManager = new OverlayWindowManager();
  public readonly menuBarPanelManager = new MenuBarPanelManager();
  public readonly shortcutMonitor = new GlobalPushToTalkShortcutMonitor();
  public readonly buddyDictationManager = new BuddyDictationManager();

  private conversationHistory: { userTranscript: string; assistantResponse: string }[] = [];
  private requestCounter = 0;

  start() {
    this.overlayWindowManager.showOverlay();
    this.menuBarPanelManager.createPanelAndTray((prompt) => {
      this.sendTranscriptToClaudeWithScreenshot(prompt, false);
    });

    this.shortcutMonitor.start((transition) => this.handleShortcutTransition(transition));
    this.startCursorTrackingLoop();
  }

  private handleShortcutTransition(transition: ShortcutTransition) {
    const primaryWin = this.overlayWindowManager.overlayWindowsByDisplayId.get(
      screen.getPrimaryDisplay().id
    );
    if (transition === 'pressed') {
      ClickyAnalytics.trackPushToTalkStarted();
      this.overlayWindowManager.broadcast('stop-tts-audio');
      this.setVoiceState('listening');
      primaryWin?.webContents.send('start-listening');
    } else if (transition === 'released') {
      ClickyAnalytics.trackPushToTalkReleased();
      this.setVoiceState('processing');
      primaryWin?.webContents.send('stop-listening');
    }
  }

  public setVoiceState(newState: CompanionVoiceState) {
    this.voiceState = newState;
    this.overlayWindowManager.broadcast('voice-state', newState);
    if (
      this.menuBarPanelManager.panelWindow &&
      !this.menuBarPanelManager.panelWindow.isDestroyed()
    ) {
      this.menuBarPanelManager.panelWindow.webContents.send('status-update', newState);
    }
  }

  private startCursorTrackingLoop() {
    setInterval(() => {
      const mousePt = screen.getCursorScreenPoint();
      const displays = screen.getAllDisplays();

      for (const display of displays) {
        const win = this.overlayWindowManager.overlayWindowsByDisplayId.get(display.id);
        if (!win || win.isDestroyed()) continue;

        const isCursorOnThisScreen =
          mousePt.x >= display.bounds.x &&
          mousePt.x <= display.bounds.x + display.bounds.width &&
          mousePt.y >= display.bounds.y &&
          mousePt.y <= display.bounds.y + display.bounds.height;

        win.webContents.send('cursor-tick', {
          isCursorOnThisScreen,
          anotherScreenNavigating: this.anotherScreenNavigating,
          localX: mousePt.x - display.bounds.x,
          localY: mousePt.y - display.bounds.y,
        });
      }
    }, 16);
  }

  async sendTranscriptToClaudeWithScreenshot(transcript: string, isDemo = false) {
    if (!transcript || !transcript.trim()) {
      this.setVoiceState('idle');
      return;
    }

    // Increment request ID and stop any previous TTS playback immediately so voices NEVER overlap!
    const currentRequestId = ++this.requestCounter;
    this.overlayWindowManager.broadcast('stop-tts-audio');

    ClickyAnalytics.trackUserMessageSent(transcript);
    this.setVoiceState('processing');

    try {
      const screenCaptures = await CompanionScreenCaptureUtility.captureAllScreensAsJPEG();
      if (currentRequestId !== this.requestCounter) return;

      const systemPrompt = isDemo
        ? ClaudeAPI.onboardingDemoSystemPrompt
        : ClaudeAPI.companionVoiceResponseSystemPrompt;

      const fullResponseText = await this.claudeAPI.analyzeImageStreaming(
        screenCaptures,
        systemPrompt,
        this.conversationHistory,
        transcript
      );
      if (currentRequestId !== this.requestCounter) return;

      const parseResult = ClaudeAPI.parseResponseAndDrawings(fullResponseText);
      const spokenText = ElevenLabsTTSClient.sanitizeSpokenText(parseResult.spokenText);

      if (!isDemo && spokenText) {
        this.conversationHistory.push({
          userTranscript: transcript,
          assistantResponse: spokenText,
        });
        if (this.conversationHistory.length > 10) {
          this.conversationHistory.shift();
        }
      }

      const targetCapture =
        (parseResult.screenNumber &&
        parseResult.screenNumber >= 1 &&
        parseResult.screenNumber <= screenCaptures.length
          ? screenCaptures[parseResult.screenNumber - 1]
          : screenCaptures.find((c) => c.isCursorScreen)) || screenCaptures[0];

      const scaleX = targetCapture.displayWidthInPoints / targetCapture.screenshotWidthInPixels;
      const scaleY = targetCapture.displayHeightInPoints / targetCapture.screenshotHeightInPixels;
      const targetWindow = this.overlayWindowManager.overlayWindowsByDisplayId.get(
        targetCapture.displayId
      );

      if (parseResult.drawCommands.length > 0 && targetWindow && !targetWindow.isDestroyed()) {
        targetWindow.webContents.send('render-drawings', {
          drawCommands: parseResult.drawCommands,
          scaleX,
          scaleY,
        });
      }

      if (parseResult.coordinate && targetWindow && !targetWindow.isDestroyed()) {
        this.setVoiceState('idle');
        const clampedX = Math.max(
          0,
          Math.min(parseResult.coordinate.x, targetCapture.screenshotWidthInPixels)
        );
        const clampedY = Math.max(
          0,
          Math.min(parseResult.coordinate.y, targetCapture.screenshotHeightInPixels)
        );

        this.anotherScreenNavigating = true;
        ClickyAnalytics.trackElementPointed(parseResult.elementLabel);
        targetWindow.webContents.send('navigate-to-element', {
          localX: clampedX * scaleX,
          localY: clampedY * scaleY,
          bubbleText: isDemo ? spokenText : parseResult.elementLabel,
        });
      }

      if (spokenText && !isDemo) {
        const audioBase64 = await this.elevenLabsTTSClient.speakText(spokenText);
        if (currentRequestId !== this.requestCounter) return;

        this.setVoiceState('responding');
        ClickyAnalytics.trackAIResponseReceived(spokenText);
        const primaryWin = this.overlayWindowManager.overlayWindowsByDisplayId.get(
          screen.getPrimaryDisplay().id
        );
        primaryWin?.webContents.send('play-tts-audio', {
          audioBase64,
          spokenText,
        });
      } else {
        this.setVoiceState('idle');
      }
    } catch (err: any) {
      ClickyAnalytics.trackResponseError(String(err));
      this.setVoiceState('idle');
    }
  }
}