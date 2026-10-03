export class BuddyDictationManager {
  public isRecordingFromKeyboardShortcut = false;
  public isFinalizingTranscript = false;
  public isPreparingToRecord = false;
  public currentAudioPowerLevel = 0;
  public transcriptionProviderDisplayName = 'WebSpeech + Local Audio Engine';

  private static readonly baseKeyterms = [
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

  get isDictationInProgress(): boolean {
    return (
      this.isPreparingToRecord ||
      this.isRecordingFromKeyboardShortcut ||
      this.isFinalizingTranscript
    );
  }

  buildTranscriptionKeyterms(custom: string[] = []): string[] {
    return Array.from(new Set([...BuddyDictationManager.baseKeyterms, ...custom]));
  }
}
