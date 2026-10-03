import { app, ipcMain, screen } from 'electron';
import { CompanionManager } from './CompanionManager';

const companionManager = new CompanionManager();

app.whenReady().then(() => {
  companionManager.start();
});

ipcMain.handle('submit-transcript', async (_, transcript: string) => {
  companionManager.shortcutMonitor.resetState();
  await companionManager.sendTranscriptToClaudeWithScreenshot(transcript, false);
});

ipcMain.on('clear-all-drawings', () => {
  companionManager.overlayWindowManager.broadcast('clear-drawings');
  companionManager.overlayWindowManager.broadcast('stop-tts-audio');
  companionManager.setVoiceState('idle');
});

ipcMain.on('replay-welcome', () => {
  const primaryWin = companionManager.overlayWindowManager.overlayWindowsByDisplayId.get(
    screen.getPrimaryDisplay().id
  );
  primaryWin?.webContents.send('trigger-welcome');
});

ipcMain.on('set-model', (_, modelName: string) => {
  companionManager.claudeAPI.model = modelName;
});

ipcMain.on('navigation-completed', () => {
  companionManager.anotherScreenNavigating = false;
});

ipcMain.on('tts-playback-ended', () => {
  companionManager.setVoiceState('idle');
});

ipcMain.on('quit-app', () => {
  app.quit();
});