import {
  app,
  BrowserWindow,
  globalShortcut,
  ipcMain,
  Menu,
  nativeImage,
  screen,
  Tray,
} from 'electron';
import path from 'path';
import { CompanionScreenCaptureUtility } from './screenCapture';
import { CompanionAIService } from './aiService';
import { FreeTTSClient } from './ttsService';
import { CompanionVoiceState } from './types';

let overlayWindowsByDisplayId = new Map<number, BrowserWindow>();
let panelWindow: BrowserWindow | null = null;
let tray: Tray | null = null;

const aiService = new CompanionAIService();
const ttsClient = new FreeTTSClient();

let voiceState: CompanionVoiceState = 'idle';
let isListeningToggle = false;
let anotherScreenNavigating = false;
const conversationHistory: { userTranscript: string; assistantResponse: string }[] = [];

function setVoiceState(newState: CompanionVoiceState) {
  voiceState = newState;
  for (const win of overlayWindowsByDisplayId.values()) {
    if (!win.isDestroyed()) {
      win.webContents.send('voice-state', newState);
    }
  }
  if (panelWindow && !panelWindow.isDestroyed()) {
    panelWindow.webContents.send('status-update', newState);
  }
}

function createOverlaysForAllDisplays() {
  for (const win of overlayWindowsByDisplayId.values()) {
    if (!win.isDestroyed()) win.close();
  }
  overlayWindowsByDisplayId.clear();

  const displays = screen.getAllDisplays();

  for (const display of displays) {
    const overlay = new BrowserWindow({
      x: display.bounds.x,
      y: display.bounds.y,
      width: display.bounds.width,
      height: display.bounds.height,
      transparent: true,
      frame: false,
      alwaysOnTop: true,
      skipTaskbar: true,
      hasShadow: false,
      focusable: false,
      resizable: false,
      movable: false,
      webPreferences: {
        nodeIntegration: true,
        contextIsolation: false,
      },
    });

    overlay.setAlwaysOnTop(true, 'screen-saver');
    overlay.setIgnoreMouseEvents(true, { forward: true });
    // Exclude overlay from screenshots on Windows (matches SCContentFilter on macOS)
    overlay.setContentProtection(true);
    overlay.loadFile(path.join(__dirname, '../public/overlay.html'));

    overlay.webContents.once('did-finish-load', () => {
      const primary = screen.getPrimaryDisplay();
      if (display.id === primary.id) {
        overlay.webContents.send('trigger-welcome');
      }
    });

    overlayWindowsByDisplayId.set(display.id, overlay);
  }
}

function createControlPanelWindow() {
  const primary = screen.getPrimaryDisplay();
  panelWindow = new BrowserWindow({
    width: 320,
    height: 270,
    x: primary.workArea.x + primary.workArea.width - 340,
    y: primary.workArea.y + primary.workArea.height - 290,
    frame: false,
    transparent: true,
    alwaysOnTop: true,
    resizable: false,
    skipTaskbar: false,
    webPreferences: {
      nodeIntegration: true,
      contextIsolation: false,
    },
  });

  panelWindow.setContentProtection(true);
  panelWindow.loadFile(path.join(__dirname, '../public/panel.html'));
}

function startCursorTrackingLoop() {
  // 60 FPS cursor tracking across all monitors (matches 0.016s Timer in OverlayWindow.swift)
  setInterval(() => {
    const mousePt = screen.getCursorScreenPoint();
    const displays = screen.getAllDisplays();

    for (const display of displays) {
      const win = overlayWindowsByDisplayId.get(display.id);
      if (!win || win.isDestroyed()) continue;

      const isCursorOnThisScreen =
        mousePt.x >= display.bounds.x &&
        mousePt.x <= display.bounds.x + display.bounds.width &&
        mousePt.y >= display.bounds.y &&
        mousePt.y <= display.bounds.y + display.bounds.height;

      win.webContents.send('cursor-tick', {
        isCursorOnThisScreen,
        anotherScreenNavigating,
        localX: mousePt.x - display.bounds.x,
        localY: mousePt.y - display.bounds.y,
      });
    }
  }, 16);
}

async function processUserTranscript(transcript: string, isDemo = false) {
  if (!transcript || !transcript.trim()) {
    setVoiceState('idle');
    return;
  }

  setVoiceState('processing');

  try {
    const screenCaptures = await CompanionScreenCaptureUtility.captureAllScreensAsJPEG();
    const systemPrompt = isDemo
      ? CompanionAIService.onboardingDemoSystemPrompt
      : CompanionAIService.companionVoiceResponseSystemPrompt;

    const fullResponseText = await aiService.analyzeImage(
      screenCaptures,
      systemPrompt,
      conversationHistory,
      transcript
    );

    const parseResult = CompanionAIService.parsePointingCoordinates(fullResponseText);
    const spokenText = parseResult.spokenText;

    if (!isDemo) {
      conversationHistory.push({
        userTranscript: transcript,
        assistantResponse: spokenText,
      });
      if (conversationHistory.length > 10) {
        conversationHistory.shift();
      }
    }

    // Coordinate scaling & multi-monitor target selection from CompanionManager.swift
    if (parseResult.coordinate) {
      setVoiceState('idle');

      const targetCapture =
        (parseResult.screenNumber &&
        parseResult.screenNumber >= 1 &&
        parseResult.screenNumber <= screenCaptures.length
          ? screenCaptures[parseResult.screenNumber - 1]
          : screenCaptures.find((c) => c.isCursorScreen)) || screenCaptures[0];

      const clampedX = Math.max(
        0,
        Math.min(parseResult.coordinate.x, targetCapture.screenshotWidthInPixels)
      );
      const clampedY = Math.max(
        0,
        Math.min(parseResult.coordinate.y, targetCapture.screenshotHeightInPixels)
      );

      const displayLocalX =
        clampedX * (targetCapture.displayWidthInPoints / targetCapture.screenshotWidthInPixels);
      const displayLocalY =
        clampedY * (targetCapture.displayHeightInPoints / targetCapture.screenshotHeightInPixels);

      const targetWindow = overlayWindowsByDisplayId.get(targetCapture.displayId);
      if (targetWindow && !targetWindow.isDestroyed()) {
        anotherScreenNavigating = true;
        targetWindow.webContents.send('navigate-to-element', {
          localX: displayLocalX,
          localY: displayLocalY,
          bubbleText: isDemo ? spokenText : parseResult.elementLabel,
        });
      }
    }

    // Play spoken response via Free Neural TTS
    if (spokenText && !isDemo) {
      const audioBase64 = await ttsClient.synthesizeSpeechBase64(spokenText);
      setVoiceState('responding');
      const primaryWin = overlayWindowsByDisplayId.get(screen.getPrimaryDisplay().id);
      primaryWin?.webContents.send('play-tts-audio', {
        audioBase64,
        spokenText,
      });
    } else {
      setVoiceState('idle');
    }
  } catch (err) {
    console.error('⚠️ Companion response error:', err);
    setVoiceState('idle');
  }
}

app.whenReady().then(() => {
  createOverlaysForAllDisplays();
  createControlPanelWindow();
  startCursorTrackingLoop();

  // Global Push-to-Talk Hotkey (Ctrl+Alt+Space toggles listening start/stop cleanly on Windows)
  globalShortcut.register('CommandOrControl+Alt+Space', () => {
    const primaryWin = overlayWindowsByDisplayId.get(screen.getPrimaryDisplay().id);
    if (!isListeningToggle) {
      isListeningToggle = true;
      setVoiceState('listening');
      primaryWin?.webContents.send('start-listening');
    } else {
      isListeningToggle = false;
      setVoiceState('processing');
      primaryWin?.webContents.send('stop-listening');
    }
  });

  // System Tray icon
  const icon = nativeImage.createEmpty();
  tray = new Tray(icon);
  tray.setToolTip('Clicky Companion');
  tray.setContextMenu(
    Menu.buildFromTemplate([
      {
        label: 'Toggle Clicky Panel',
        click: () => {
          if (panelWindow?.isVisible()) panelWindow.hide();
          else panelWindow?.show();
        },
      },
      {
        label: 'Point at Something on Screen',
        click: () =>
          processUserTranscript(
            'look around my screen and find something interesting to point at',
            true
          ),
      },
      { type: 'separator' },
      { label: 'Quit Clicky', click: () => app.quit() },
    ])
  );
});

ipcMain.handle('submit-transcript', async (_, transcript: string) => {
  isListeningToggle = false;
  await processUserTranscript(transcript, false);
});

ipcMain.on('trigger-onboarding-demo', () => {
  processUserTranscript(
    'look around my screen and find something interesting to point at',
    true
  );
});

ipcMain.on('replay-welcome', () => {
  const primaryWin = overlayWindowsByDisplayId.get(screen.getPrimaryDisplay().id);
  primaryWin?.webContents.send('trigger-welcome');
});

ipcMain.on('set-model', (_, modelName: string) => {
  aiService.model = modelName;
});

ipcMain.on('navigation-completed', () => {
  anotherScreenNavigating = false;
});

ipcMain.on('tts-playback-ended', () => {
  setVoiceState('idle');
});

ipcMain.on('quit-app', () => {
  app.quit();
});