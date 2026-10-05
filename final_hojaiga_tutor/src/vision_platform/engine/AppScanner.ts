import Tesseract from 'tesseract.js';
import { UIElement, BoundingBox } from '../types';

export class AppScanner {
  private ocrWorker: Tesseract.Worker | null = null;

  async initializeOCR(): Promise<void> {
    if (!this.ocrWorker) {
      this.ocrWorker = await Tesseract.createWorker('eng');
      console.log('[AppScanner] OCR worker initialized');
    }
  }

  async performOCR(imageBase64: string): Promise<UIElement[]> {
    console.log('[AppScanner] Running Tesseract OCR for text fallback...');

    try {
      await this.initializeOCR();

      if (!this.ocrWorker) {
        console.error('[AppScanner] OCR worker initialization failed');
        return [];
      }

      const imageBuffer = Buffer.from(imageBase64, 'base64');
      const result = await this.ocrWorker.recognize(imageBuffer);

      // tesseract.js v7+ returns result.data with text, lines, and words
      const words = (result.data as any).words || [];

      console.log(`[AppScanner] OCR found ${words.length} text elements`);

      return words.map((word: any) => ({
        id: `text_${Math.random().toString(36).substr(2, 9)}`,
        text: word.text,
        type: 'text' as const,
        bounds: {
          x: word.bbox?.x0 || 0,
          y: word.bbox?.y0 || 0,
          width: (word.bbox?.x1 || 0) - (word.bbox?.x0 || 0),
          height: (word.bbox?.y1 || 0) - (word.bbox?.y0 || 0)
        },
        confidence: word.confidence || 0
      })).filter((el: UIElement) => el.text && el.text.trim().length > 0); // Filter empty text
    } catch (error) {
      console.error('[AppScanner] OCR failed:', error);
      return [];
    }
  }

  async determineLayoutState(elements: UIElement[]): Promise<string> {
    // Analyze the UI elements to determine the app's current state
    // This could be enhanced with a RAG system for app-specific knowledge

    const textContent = elements.map(e => e.text).join(' ').toLowerCase();

    // Simple heuristic-based state detection
    if (textContent.includes('settings') || textContent.includes('preferences')) {
      return 'settings_menu';
    } else if (textContent.includes('export') || textContent.includes('save')) {
      return 'export_dialog';
    } else if (textContent.includes('error') || textContent.includes('warning')) {
      return 'error_state';
    } else if (textContent.includes('play') || textContent.includes('pause')) {
      return 'media_player';
    }

    return 'unknown_state';
  }

  async findElementByText(text: string, elements: UIElement[]): Promise<UIElement | null> {
    const targetLower = text.toLowerCase();
    const match = elements.find(el =>
      el.text?.toLowerCase().includes(targetLower) &&
      el.confidence && el.confidence > 50
    );
    return match || null;
  }

  async findElementByType(type: UIElement['type'], elements: UIElement[]): Promise<UIElement[]> {
    return elements.filter(el => el.type === type);
  }

  // Get the center point of a UI element for clicking
  getElementCenter(element: UIElement): { x: number; y: number } {
    return {
      x: element.bounds.x + element.bounds.width / 2,
      y: element.bounds.y + element.bounds.height / 2
    };
  }

  cleanup(): void {
    if (this.ocrWorker) {
      this.ocrWorker.terminate();
      this.ocrWorker = null;
    }
  }
}
