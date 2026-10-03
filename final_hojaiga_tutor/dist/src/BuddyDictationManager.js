"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.BuddyDictationManager = void 0;
class BuddyDictationManager {
    isRecordingFromKeyboardShortcut = false;
    isFinalizingTranscript = false;
    isPreparingToRecord = false;
    currentAudioPowerLevel = 0;
    transcriptionProviderDisplayName = 'WebSpeech + Local Audio Engine';
    static baseKeyterms = [
        'Clicky',
        'parallelogram',
        'decagon',
        'hexagon',
        'logarithm',
        'log x',
        'sine curve',
        'cosine',
        'hypotenuse',
        'Pythagorean',
    ];
    get isDictationInProgress() {
        return (this.isPreparingToRecord ||
            this.isRecordingFromKeyboardShortcut ||
            this.isFinalizingTranscript);
    }
    buildTranscriptionKeyterms(custom = []) {
        return Array.from(new Set([...BuddyDictationManager.baseKeyterms, ...custom]));
    }
}
exports.BuddyDictationManager = BuddyDictationManager;
