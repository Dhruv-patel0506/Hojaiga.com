"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.EdgeNeuralTTSClient = void 0;
const msedge_tts_1 = require("msedge-tts");
class EdgeNeuralTTSClient {
    isPlaying = false;
    async speakText(text) {
        const cleanText = EdgeNeuralTTSClient.sanitizeSpokenText(text);
        if (!cleanText)
            return null;
        try {
            const tts = new msedge_tts_1.MsEdgeTTS();
            await tts.setMetadata('en-US-AndrewMultilingualNeural', msedge_tts_1.OUTPUT_FORMAT.AUDIO_24KHZ_48KBITRATE_MONO_MP3);
            const { audioStream } = tts.toStream(cleanText);
            const chunks = [];
            return await new Promise((resolve, reject) => {
                audioStream.on('data', (chunk) => chunks.push(Buffer.from(chunk)));
                audioStream.on('end', () => {
                    this.isPlaying = true;
                    resolve(Buffer.concat(chunks).toString('base64'));
                });
                audioStream.on('error', (err) => reject(err));
            });
        }
        catch (err) {
            console.warn('⚠️ Edge neural TTS failed, falling back to Windows system TTS:', err);
            return null;
        }
    }
    /**
     * Strips any leftover bracket tags, coordinates, or long decimal sequences
     * so the TTS voice NEVER reads raw pixel coordinates out loud.
     * Also strips HTML-style <tags> that break the TTS stream.
     */
    static sanitizeSpokenText(raw) {
        return raw
            // Strip HTML-style <tags> that break TTS stream
            .replace(/<[^>]*>/g, '')
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
exports.EdgeNeuralTTSClient = EdgeNeuralTTSClient;
