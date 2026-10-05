import { MsEdgeTTS, OUTPUT_FORMAT } from 'msedge-tts';

export class ElevenLabsTTSClient {
  public isPlaying = false;

  async speakText(text: string): Promise<string | null> {
    const cleanText = ElevenLabsTTSClient.sanitizeSpokenText(text);
    if (!cleanText) return null;

    try {
      const tts = new MsEdgeTTS();
      await tts.setMetadata(
        'en-US-AndrewMultilingualNeural',
        OUTPUT_FORMAT.AUDIO_24KHZ_48KBITRATE_MONO_MP3
      );
      const { audioStream } = tts.toStream(cleanText);
      const chunks: Buffer[] = [];

      return await new Promise<string>((resolve, reject) => {
        audioStream.on('data', (chunk) => chunks.push(Buffer.from(chunk)));
        audioStream.on('end', () => {
          this.isPlaying = true;
          resolve(Buffer.concat(chunks).toString('base64'));
        });
        audioStream.on('error', (err) => reject(err));
      });
    } catch (err) {
      console.warn('⚠️ Edge neural TTS failed, falling back to Windows system TTS:', err);
      return null;
    }
  }

  /**
   * Strips any leftover bracket tags, coordinates, or long decimal sequences
   * so the TTS voice NEVER reads raw pixel coordinates out loud.
   */
  static sanitizeSpokenText(raw: string): string {
    return raw
      // Strip any [DRAW:...] or [POINT:...] tags even if malformed or unclosed
      .replace(/\[(?:DRAW|POINT|GRAPH|CURVE|LINE|CIRCLE|RECT|POLYGON|DECAGON)[^\]]*\]?/gi, '')
      // Strip raw coordinate lists like "640, 360" or "801.803, 550.211"
      .replace(/\b\d+(?:\.\d+)?\s*,\s*\d+(?:\.\d+)?(?:\s*,\s*\d+(?:\.\d+)?)*\b/g, '')
      // Strip sentences that talk about pixel coordinates
      .replace(/[^.?!]*\b(?:centered at|starts at|pixels wide|pixels tall|radius of)\b[^.?!]*[.?!]?/gi, '')
      .replace(/\s+/g, ' ')
      .trim();
  }
}