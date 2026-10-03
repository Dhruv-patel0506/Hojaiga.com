import { app, globalShortcut, ipcMain, screen } from 'electron';
import { CompanionManager, routeSpecializedEngines, ParsedOverlayCommand } from './CompanionManager';
import { registerDragHandlers } from './MenuBarPanelManager';

let companionManager: CompanionManager | null = null;

function clearAllDrawings(): void {
  if (!companionManager) return;
  companionManager.overlayWindowManager.broadcast('stop-tts-audio');
  companionManager.notifyTtsEnded();
  companionManager.overlayWindowManager.clearDrawings();
  companionManager.setVoiceState('idle');
}

// Add error handling
process.on('uncaughtException', (error) => {
  console.error('[MAIN] Uncaught Exception:', error);
});

process.on('unhandledRejection', (reason, promise) => {
  console.error('[MAIN] Unhandled Rejection:', reason);
});

// Defer Electron access to avoid module load time issues
if (typeof app !== 'undefined') {
  console.log('[MAIN] App is defined, waiting for ready...');

  app.whenReady().then(() => {
    console.log('[MAIN] App is ready, initializing...');

    try {
      // Single-instance lock - must be called at app ready
      const gotTheLock = app.requestSingleInstanceLock();
      console.log('[MAIN] Single-instance lock:', gotTheLock);

      if (!gotTheLock) {
        console.log('[MAIN] Another instance is running, quitting...');
        app.quit();
      } else {
        app.on('second-instance', () => {
          console.log('[MAIN] Second instance detected, focusing panel...');
          const panel = companionManager?.menuBarPanelManager?.panelWindow;
          if (panel) {
            if (panel.isMinimized()) panel.restore();
            panel.show();
            panel.focus();
          }
        });

        console.log('[MAIN] Creating CompanionManager...');
        companionManager = new CompanionManager();
        console.log('[MAIN] CompanionManager created successfully');

        // IPC handlers - register inside app.whenReady
        ipcMain.handle('submit-transcript', async (_, transcript: string) => {
          if (!companionManager) return;
          companionManager.shortcutMonitor.resetState();
          await companionManager.sendTranscriptToClaudeWithScreenshot(transcript, false);
        });

        ipcMain.handle('user-input', async (_, input: string) => {
          console.log(`[MAIN] Received user input: "${input}"`);
          // Forward to interactive tutor if it's running
          // This will be handled by the teaching machine when active
          return { success: true };
        });

        ipcMain.handle('start-app-teaching', async () => {
          console.log('[MAIN] Starting live interactive teaching...');
          try {
            // Import the new reactive interactive tutor wrapper
            const { InteractiveTutorWrapper } = require('../InteractiveTutorWrapper');
            const { WindowManager } = require('../WindowManager');
            const { SafeOSController } = require('../SafeOSController');
            const { LivePerception } = require('../LivePerception');
            const { AppKnowledgeRAG } = require('../rag/AppKnowledgeRAG');
            const { TeacherRAGWrapper } = require('../rag/TeacherRAGWrapper');

            // Initialize components
            const windowManager = new WindowManager();
            const osController = new SafeOSController();
            const perception = new LivePerception();
            const ragEngine = new AppKnowledgeRAG();
            const ragWrapper = new TeacherRAGWrapper(ragEngine, 'http://127.0.0.1:11434', 'qwen2.5:7b');

            // Create the interactive tutor wrapper (it creates its own input handler)
            // usePhysicalMouse: true = use PyAutoGUI to physically move the OS cursor
            // usePhysicalMouse: false = use programmatic UI Automation (no mouse movement)
            const tutorWrapper = new InteractiveTutorWrapper(
              ragWrapper,
              windowManager,
              osController,
              perception,
              true  // Enable physical mouse movement
            );

            // Load documentation for common apps (if available)
            const { path } = require('path');
            const { app } = require('electron');
            
            // Guard clause: Ensure app is available
            if (!app || !app.getAppPath) {
              console.error('[MAIN] Electron app not available, using fallback path');
              const fallbackPath = path.join(__dirname, '../docs');
              
              try {
                const notepadDoc = path.join(fallbackPath, 'notepad.md');
                if (require('fs').existsSync(notepadDoc)) {
                  await ragEngine.ingestMarkdownFile('Notepad', notepadDoc);
                }
              } catch (e) {
                console.log('[MAIN] No documentation found for Notepad - will use live UI only');
              }
            } else {
              const docsPath = path.join(app.getAppPath(), 'docs');
              
              try {
                // Try to load Notepad documentation
                const notepadDoc = path.join(docsPath, 'notepad.md');
                if (require('fs').existsSync(notepadDoc)) {
                  await ragEngine.ingestMarkdownFile('Notepad', notepadDoc);
                }
              } catch (e) {
                console.log('[MAIN] No documentation found for Notepad - will use live UI only');
              }
            }

            // Get current active window title as app name
            const currentState = windowManager.getActiveWindow();
            const appName = currentState.appTitle || 'Unknown Application';

            console.log(`[MAIN] Starting reactive interactive tutor for: ${appName}`);

            // Start the reactive interactive loop
            await tutorWrapper.startLiveInteraction('teach me everything about this application', appName);

            return { success: true };
          } catch (error) {
            console.error('[MAIN] Failed to start live teaching:', error);
            // Fallback to existing Claude integration
            if (!companionManager) return { success: false, error: 'CompanionManager not initialized' };
            companionManager.shortcutMonitor.resetState();
            await companionManager.sendTranscriptToClaudeWithScreenshot('teach me everything about this application', false);
            return { success: true };
          }
        });

        ipcMain.handle('write-document', async (_, topic: string, docType: string) => {
          console.log(`[MAIN] Writing ${docType} about: ${topic}`);
          // For now, use Claude to write the document
          try {
            if (!companionManager) return { success: false, error: 'CompanionManager not initialized' };
            companionManager.shortcutMonitor.resetState();
            await companionManager.sendTranscriptToClaudeWithScreenshot(`Write a professional ${docType} about: ${topic}`, false);
            return { success: true };
          } catch (error) {
            console.error('[MAIN] Failed to write document:', error);
            return { success: false, error: String(error) };
          }
        });

        ipcMain.handle('teach-multiple-apps', async () => {
          console.log('[MAIN] Teaching multiple apps...');
          // For now, use Claude to explain multiple apps
          try {
            if (!companionManager) return { success: false, error: 'CompanionManager not initialized' };
            companionManager.shortcutMonitor.resetState();
            await companionManager.sendTranscriptToClaudeWithScreenshot('Teach me about all the applications I have open', false);
            return { success: true };
          } catch (error) {
            console.error('[MAIN] Failed to teach multiple apps:', error);
            return { success: false, error: String(error) };
          }
        });

        ipcMain.handle('overlay:submit-prompt', async (_, promptText: string) => {
          if (!companionManager) return false;
          companionManager.shortcutMonitor.resetState();
          await companionManager.sendTranscriptToClaudeWithScreenshot(promptText, false);
          return true;
        });

        ipcMain.on('overlay:set-click-through', (_, shouldIgnore: boolean) => {
          if (!companionManager) return;
          companionManager.overlayWindowManager.setClickThrough(Boolean(shouldIgnore));
        });

        ipcMain.on('clear-all-drawings', () => {
          clearAllDrawings();
        });

        ipcMain.on('replay-welcome', () => {
          if (!companionManager) return;
          const primaryWin = companionManager.overlayWindowManager.overlayWindowsByDisplayId.get(
            screen.getPrimaryDisplay().id
          );
          primaryWin?.webContents.send('trigger-welcome');
        });

        ipcMain.on('set-model', (_, modelName: string) => {
          if (!companionManager) return;
          companionManager.claudeAPI.model = modelName;
        });

        ipcMain.on('navigation-completed', () => {
          if (!companionManager) return;
          companionManager.anotherScreenNavigating = false;
        });

        ipcMain.on('tts-playback-ended', () => {
          if (!companionManager) return;
          companionManager.notifyTtsEnded();
          companionManager.setVoiceState('idle');
        });

        ipcMain.on('quit-app', () => {
          app.quit();
        });

        ipcMain.on('toggle-drawer', () => {
          if (!companionManager) return;
          companionManager.menuBarPanelManager.toggleDrawer();
        });

        ipcMain.handle('start-vision-teaching', async (_, goal: string) => {
          if (!companionManager) return false;
          await companionManager.startVisionTeaching(goal);
          return true;
        });

        ipcMain.on('stop-vision-teaching', () => {
          if (!companionManager) return;
          companionManager.stopVisionTeaching();
        });

        ipcMain.handle('start-comprehensive-teaching', async () => {
          if (!companionManager) return false;
          await companionManager.startComprehensiveAppTeaching();
          return true;
        });

        ipcMain.handle('start-specific-teaching', async (_, feature: string) => {
          if (!companionManager) return false;
          await companionManager.startSpecificFeatureTeaching(feature);
          return true;
        });

        ipcMain.on('stop-dynamic-teaching', () => {
          if (!companionManager) return;
          companionManager.stopDynamicTeaching();
        });

        ipcMain.handle('explore-ui-actions', async () => {
          if (!companionManager) return false;
          await companionManager.exploreUIActions();
          return true;
        });

        console.log('[MAIN] Registering drag handlers...');
        registerDragHandlers();

        console.log('[MAIN] Starting CompanionManager...');
        companionManager.start();
        console.log('[MAIN] CompanionManager started');

        // 1. Toggle Interactive Prompt Mode vs. Click-Through Mode
        console.log('[MAIN] Registering hotkeys...');
        globalShortcut.register('CommandOrControl+Shift+Space', () => {
          if (!companionManager) return;
          const manager = companionManager.overlayWindowManager;
          manager.setClickThrough(!manager.isClickThrough);
        });

        // 2. Instant UI Automation scan & visual guide for the active window
        globalShortcut.register('CommandOrControl+Shift+A', async () => {
          if (!companionManager) return;
          try {
            const commands: ParsedOverlayCommand[] = [];
            const routed = await routeSpecializedEngines('teach me this app and scan controls', commands, true);
            if (routed) {
              companionManager.overlayWindowManager.renderCommands(
                screen.getPrimaryDisplay().id,
                commands,
                true,
                'instant app scan (Ctrl+Shift+X clears)'
              );
            }
          } catch {
            /* instant scan is best-effort */
          }
        });

        // 3. Emergency clear overlay canvas
        globalShortcut.register('CommandOrControl+Shift+X', () => {
          clearAllDrawings();
        });

        // 4. Toggle Clicky Panel (Ctrl+Shift+K or Ctrl+Alt+K)
        // Changed from P to K to avoid conflicts with Excel (Ctrl+Shift+P = Format Cells)
        const togglePanel = () => {
          if (!companionManager) return;
          const panel = companionManager.menuBarPanelManager.panelWindow;
          if (panel) {
            if (panel.isVisible()) {
              panel.hide();
            } else {
              panel.show();
              panel.focus();
            }
          }
        };
        globalShortcut.register('CommandOrControl+Shift+K', togglePanel);
        globalShortcut.register('CommandOrControl+Alt+K', togglePanel);

        console.log('[MAIN] All hotkeys registered');
        console.log('[MAIN] Clicky startup complete!');
      }
    } catch (error) {
      console.error('[MAIN] Error during startup:', error);
      app.quit();
    }
  }).catch((error) => {
    console.error('[MAIN] Error in app.whenReady:', error);
  });
} else {
  console.log('[MAIN] App is undefined, running in non-Electron context');
}
