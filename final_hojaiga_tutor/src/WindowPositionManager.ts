import { shell } from 'electron';

export class WindowPositionManager {
  static hasAccessibilityPermission(): boolean {
    return true; // Native on Windows
  }
  static hasScreenRecordingPermission(): boolean {
    return true; // Native via desktopCapturer on Windows
  }
  static openPrivacySettings() {
    shell.openExternal('ms-settings:privacy-microphone');
  }
}
