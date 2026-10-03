export class ClickyAnalytics {
  static trackOnboardingStarted() {
    console.log('📊 [Analytics] Onboarding started');
  }
  static trackOnboardingReplayed() {
    console.log('📊 [Analytics] Onboarding replayed');
  }
  static trackPushToTalkStarted() {
    console.log('📊 [Analytics] Push-to-talk started');
  }
  static trackPushToTalkReleased() {
    console.log('📊 [Analytics] Push-to-talk released');
  }
  static trackUserMessageSent(transcript: string) {
    console.log(`📊 [Analytics] User message sent: "${transcript}"`);
  }
  static trackElementPointed(elementLabel: string | null) {
    console.log(`📊 [Analytics] Element pointed: "${elementLabel ?? 'none'}"`);
  }
  static trackAIResponseReceived(response: string) {
    console.log(`📊 [Analytics] AI response spoken: "${response}"`);
  }
  static trackTTSError(error: string) {
    console.warn(`📊 [Analytics] TTS error: ${error}`);
  }
  static trackResponseError(error: string) {
    console.warn(`📊 [Analytics] Response error: ${error}`);
  }
}