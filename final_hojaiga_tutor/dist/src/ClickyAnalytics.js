"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.ClickyAnalytics = void 0;
class ClickyAnalytics {
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
    static trackUserMessageSent(transcript) {
        console.log(`📊 [Analytics] User message sent: "${transcript}"`);
    }
    static trackElementPointed(elementLabel) {
        console.log(`📊 [Analytics] Element pointed: "${elementLabel ?? 'none'}"`);
    }
    static trackAIResponseReceived(response) {
        console.log(`📊 [Analytics] AI response spoken: "${response}"`);
    }
    static trackTTSError(error) {
        console.warn(`📊 [Analytics] TTS error: ${error}`);
    }
    static trackResponseError(error) {
        console.warn(`📊 [Analytics] Response error: ${error}`);
    }
}
exports.ClickyAnalytics = ClickyAnalytics;
