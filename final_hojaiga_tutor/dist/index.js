"use strict";
/**
 * CLI Entry Point - Demonstrates interactive teaching on an active window
 * Production-ready live interactive teaching engine
 */
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
const TeachingStateMachine_1 = require("./TeachingStateMachine");
const readline_1 = __importDefault(require("readline"));
const rl = readline_1.default.createInterface({
    input: process.stdin,
    output: process.stdout
});
/**
 * Main execution
 */
async function main() {
    console.log('╔══════════════════════════════════════════════════════════════╗');
    console.log('║         Live Interactive Application Teacher                ║');
    console.log('║       Dynamic AI Tutor for ANY Desktop Application           ║');
    console.log('╚══════════════════════════════════════════════════════════════╝');
    console.log();
    console.log('Prerequisites:');
    console.log('  ✓ Ollama running on http://localhost:11434');
    console.log('  ✓ llava:latest model installed');
    console.log('  ✓ Python with pyautogui, pillow, pywin32');
    console.log();
    console.log('Safety Features:');
    console.log('  ✓ Input confinement to window bounds');
    console.log('  ✓ Emergency kill switch (move mouse to corner)');
    console.log('  ✓ State verification before proceeding');
    console.log('  ✓ No hallucinated states - only explains visible elements');
    console.log();
    // Get user goal
    const userGoal = await askQuestion('What do you want to learn about this application? ');
    if (!userGoal.trim()) {
        console.log('No goal provided. Exiting.');
        rl.close();
        return;
    }
    console.log();
    console.log('🎯 Teaching Goal:', userGoal);
    console.log('📋 Make sure the application you want to learn is ACTIVE');
    console.log('⏱️  Starting in 3 seconds...');
    console.log();
    await sleep(3000);
    // Create teaching state machine
    const teachingMachine = new TeachingStateMachine_1.TeachingStateMachine({
        maxActionsPerSession: 30,
        stateVerificationTimeout: 3000,
        inputBoundaryPadding: 20,
        enableKillSwitch: true
    });
    // Add event listeners with detailed logging
    teachingMachine.on((event) => {
        switch (event.type) {
            case 'stepStart':
                console.log(`\n📍 Step ${event.step.stepNumber}: ${event.step.explanation}`);
                console.log(`   Action: ${event.step.action.actionType} on ${event.step.action.targetName}`);
                console.log(`   Coordinates: (${event.step.action.normalizedCoords.x.toFixed(2)}, ${event.step.action.normalizedCoords.y.toFixed(2)})`);
                console.log(`   Description: ${event.step.action.description}`);
                break;
            case 'stepComplete':
                if (event.verification.success) {
                    console.log(`   ✅ Step complete (confidence: ${event.verification.confidence.toFixed(2)})`);
                    console.log(`   State transition: ${event.verification.beforeState.currentState} → ${event.verification.actualTransition}`);
                }
                else {
                    console.log(`   ⚠️  Step complete but verification failed: ${event.verification.reason}`);
                    console.log(`   Expected: ${event.verification.expectedTransition}, Got: ${event.verification.actualTransition}`);
                }
                break;
            case 'stepFailed':
                console.log(`   ❌ Step failed: ${event.error}`);
                break;
            case 'emergencyStop':
                console.log(`\n🚨 EMERGENCY STOP: ${event.signal.reason}`);
                break;
            case 'sessionComplete':
                console.log(`\n🎉 Teaching session complete! Total steps: ${event.totalSteps}`);
                console.log(`\n📋 SUMMARY:`);
                console.log(`   • Total actions performed: ${event.totalSteps}`);
                console.log(`   • App state: ready`);
                console.log(`   • Window: Active Application`);
                break;
            case 'error':
                console.log(`\n❌ Error: ${event.error.message} - ${event.context}`);
                break;
        }
    });
    // Start teaching
    try {
        await teachingMachine.startTeaching(userGoal);
    }
    catch (error) {
        console.error('Fatal error:', error);
    }
    finally {
        console.log();
        console.log('Session ended. Press Ctrl+C to exit.');
        rl.close();
    }
}
/**
 * Helper to ask question
 */
function askQuestion(question) {
    return new Promise((resolve) => {
        rl.question(question, (answer) => {
            resolve(answer);
        });
    });
}
/**
 * Sleep helper
 */
function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}
// Handle Ctrl+C
process.on('SIGINT', () => {
    console.log('\n\nInterrupted by user. Cleaning up...');
    rl.close();
    process.exit(0);
});
// Run main
main().catch(console.error);
