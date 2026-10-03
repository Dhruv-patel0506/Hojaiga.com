import { MsEdgeTTS, OUTPUT_FORMAT } from 'msedge-tts';

export class FreeTTSClient {
  /**
   * Free neural text-to-speech replacement for ElevenLabsTTSClient.swift.
   * Uses Microsoft Edge Neural TTS (0 cost, no API key) and returns base64 MP3.
   */
  async synthesizeSpeechBase64(text: string): Promise<string | null> {
    try {
      const tts = new MsEdgeTTS();
      await tts.setMetadata(
        'en-US-AndrewMultilingualNeural',
        OUTPUT_FORMAT.AUDIO_24KHZ_48KBITRATE_MONO_MP3
      );
      const { audioStream } = tts.toStream(text);
      const chunks: Buffer[] = [];

      return await new Promise<string>((resolve, reject) => {
        audioStream.on('data', (chunk) => chunks.push(Buffer.from(chunk)));
        audioStream.on('end', () => resolve(Buffer.concat(chunks).toString('base64')));
        audioStream.on('error', (err) => reject(err));
      });
    } catch (err) {
      console.warn('⚠️ Edge neural TTS failed, renderer will use native Windows TTS:', err);
      return null;
    }
  }
}