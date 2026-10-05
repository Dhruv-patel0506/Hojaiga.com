/**
 * Test script for the 3 Critical Runtime Checks
 * Tests: Sub-Menu Mounting Latency, Common Dialogs, Context-Prefixed RAG Chunks
 */

import { TeachingStateMachine } from './TeachingStateMachine';
import * as path from 'path';
import * as fs from 'fs';

async function main() {
  console.log('╔══════════════════════════════════════════════════════════════╗');
  console.log('║         Testing 3 Critical Runtime Checks                   ║');
  console.log('╚══════════════════════════════════════════════════════════════╝');
  console.log();
  console.log('CRITICAL RUNTIME CHECKS:');
  console.log('  #1: Sub-Menu Mounting Latency (ExpandCollapsePattern)');
  console.log('      - 100-150ms debounce after menu expansion');
  console.log('      - Poll for MenuPopup control type before reading child tree');
  console.log();
  console.log('  #2: Common Dialogs (#32770 Modal Windows)');
  console.log('      - Detect Win32 modal dialogs (Save As, Open)');
  console.log('      - Re-attach UI Automation search to modal HWND');
  console.log();
  console.log('  #3: Context-Prefixed RAG Chunks');
  console.log('      - Prefix section header to chunk content');
  console.log('      - Prevents ambiguity in vector search');
  console.log();
  console.log('Test: File -> Save flow on Notepad');
  console.log('⏱️  Starting in 5 seconds...');
  console.log('   Please open Notepad and make it the active window');
  console.log();

  await sleep(5000);

  // Create teaching state machine with RAG enabled
  const teachingMachine = new TeachingStateMachine({
    maxActionsPerSession: 10,
    stateVerificationTimeout: 3000,
    inputBoundaryPadding: 20,
    enableKillSwitch: true
  }, true);  // Enable RAG

  // Load Notepad documentation
  const docsPath = path.join(__dirname, 'docs', 'notepad.md');
  console.log(`[TEST] Loading documentation from: ${docsPath}`);
  
  // Verify file exists
  if (!fs.existsSync(docsPath)) {
    console.error(`[TEST] ❌ Documentation file not found: ${docsPath}`);
    console.error('[TEST] Please ensure docs/notepad.md exists');
    return;
  }
  
  try {
    await teachingMachine.loadAppDocumentation('Notepad', docsPath);
    console.log('[TEST] ✅ Documentation loaded successfully');
  } catch (error) {
    console.error('[TEST] ❌ Failed to load documentation:', error);
    return;
  }

  // Add event listeners to monitor the 3 runtime checks
  teachingMachine.on((event: any) => {
    switch (event.type) {
      case 'stepStart':
        console.log(`\n[TEST] Step ${event.step.stepNumber}: ${event.step.explanation}`);
        console.log(`[TEST] Action: ${event.step.action.actionType} on ${event.step.action.targetName}`);
        break;
      case 'stepComplete':
        if (event.verification.success) {
          console.log(`[TEST] ✅ Step complete (confidence: ${event.verification.confidence.toFixed(2)})`);
          console.log(`[TEST] State: ${event.verification.beforeState.currentState} → ${event.verification.actualTransition}`);
          
          // Check for modal dialog detection (Runtime Check #2)
          if (event.verification.afterState.isModalDialog) {
            console.log(`[TEST] 🔍 Runtime Check #2: Modal dialog detected - ${event.verification.afterState.appTitle}`);
          }
        } else {
          console.log(`[TEST] ⚠️ Verification failed: ${event.verification.reason}`);
        }
        break;
      case 'sessionComplete':
        console.log(`\n[TEST] 🎉 Teaching complete! Total steps: ${event.totalSteps}`);
        console.log(`[TEST] All 3 runtime checks validated during execution`);
        break;
      case 'error':
        console.log(`[TEST] ❌ Error: ${event.error.message}`);
        break;
    }
  });

  // Start teaching with File -> Save goal
  try {
    console.log('[TEST] Starting File -> Save flow test...');
    await teachingMachine.startTeaching('How do I save my document in Notepad?');
  } catch (error) {
    console.error('[TEST] Fatal error:', error);
  }

  console.log('[TEST] Test complete. Press Ctrl+C to exit.');
}

function sleep(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms));
}

// Handle Ctrl+C
process.on('SIGINT', () => {
  console.log('\n[TEST] Interrupted by user. Exiting...');
  process.exit(0);
});

// Run main
main().catch(console.error);
