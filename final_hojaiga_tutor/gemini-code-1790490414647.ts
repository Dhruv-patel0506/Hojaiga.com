import { desktopCapturer, screen } from 'electron';
import { CompanionScreenCapture } from './types';

export class CompanionScreenCaptureUtility {
  /**
   * 1-to-1 Windows port of CompanionScreenCaptureUtility.swift.
   * Captures all connected displays as JPEG (quality 80), max dimension 1280px,
   * and sorts displays so the cursor screen is always first.
   */
  static async captureAllScreensAsJPEG(): Promise<CompanionScreenCapture[]> {
    const mouseLocation = screen.getCursorScreenPoint();
    const allDisplays = screen.getAllDisplays();

    if (allDisplays.length === 0) {
      throw new Error('No display available for capture');
    }

    // Sort displays so the cursor screen is always first
    const sortedDisplays = [...allDisplays].sort((a, b) => {
      const aContains = this.rectContains(a.bounds, mouseLocation);
      const bContains = this.rectContains(b.bounds, mouseLocation);
      if (aContains !== bContains) return aContains ? -1 : 1;
      return 0;
    });

    // Request screen thumbnails at max 1280 dimension from Electron's native desktopCapturer
    const sources = await desktopCapturer.getSources({
      types: ['screen'],
      thumbnailSize: { width: 1280, height: 1280 },
    });

    const capturedScreens: CompanionScreenCapture[] = [];

    for (let i = 0; i < sortedDisplays.length; i++) {
      const display = sortedDisplays[i];
      const isCursorScreen = this.rectContains(display.bounds, mouseLocation);

      const maxDimension = 1280;
      const aspectRatio = display.bounds.width / display.bounds.height;
      let targetWidth: number;
      let targetHeight: number;

      if (display.bounds.width >= display.bounds.height) {
        targetWidth = maxDimension;
        targetHeight = Math.round(maxDimension / aspectRatio);
      } else {
        targetHeight = maxDimension;
        targetWidth = Math.round(maxDimension * aspectRatio);
      }

      // Match source by display_id or fallback to index
      const matchedSource =
        sources.find((s) => s.display_id === String(display.id)) ||
        sources[i] ||
        sources[0];

      if (!matchedSource) continue;

      const resizedImage = matchedSource.thumbnail.resize({
        width: targetWidth,
        height: targetHeight,
        quality: 'good',
      });

      const jpegBuffer = resizedImage.toJPEG(80);
      const actualSize = resizedImage.getSize();

      let screenLabel = '';
      if (sortedDisplays.length === 1) {
        screenLabel = "user's screen (cursor is here)";
      } else if (isCursorScreen) {
        screenLabel = `screen ${i + 1} of ${sortedDisplays.length} — cursor is on this screen (primary focus)`;
      } else {
        screenLabel = `screen ${i + 1} of ${sortedDisplays.length} — secondary screen`;
      }

      capturedScreens.push({
        imageDataBase64: jpegBuffer.toString('base64'),
        label: screenLabel,
        isCursorScreen,
        displayId: display.id,
        displayWidthInPoints: display.bounds.width,
        displayHeightInPoints: display.bounds.height,
        displayFrame: display.bounds,
        screenshotWidthInPixels: actualSize.width,
        screenshotHeightInPixels: actualSize.height,
      });
    }

    if (capturedScreens.length === 0) {
      throw new Error('Failed to capture any screen');
    }

    return capturedScreens;
  }

  private static rectContains(
    rect: { x: number; y: number; width: number; height: number },
    pt: { x: number; y: number }
  ): boolean {
    return (
      pt.x >= rect.x &&
      pt.x <= rect.x + rect.width &&
      pt.y >= rect.y &&
      pt.y <= rect.y + rect.height
    );
  }
}