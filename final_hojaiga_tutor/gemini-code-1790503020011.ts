import { globalShortcut } from 'electron';

export type ShortcutTransition = 'pressed' | 'released' | 'none';

export class GlobalPushToTalkShortcutMonitor {
  private isListening = false;
  private onTransitionCallback?: (transition: ShortcutTransition) => void;

  start(onTransition: (transition: ShortcutTransition) => void) {
    this.onTransitionCallback = onTransition;
    globalShortcut.unregisterAll();

    // Register Ctrl+Alt+Space on Windows
    globalShortcut.register('CommandOrControl+Alt+Space', () => {
      if (!this.isListening) {
        this.isListening = true;
        this.onTransitionCallback?.('pressed');
      } else {
        this.isListening = false;
        this.onTransitionCallback?.('released');
      }
    });
  }

  resetState() {
    this.isListening = false;
  }

  stop() {
    globalShortcut.unregisterAll();
    this.isListening = false;
  }
}