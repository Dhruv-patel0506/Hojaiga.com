/**
 * File 27 - Automated CLI health & verification runner for all modules
 * (adapted from the pasted source to this port's real APIs).
 *
 * Merge deviations from the pasted source:
 *  - The pasted runner depended on a CompanionManager class exposing
 *    routePromptToOverlay() returning replacement command arrays, plus
 *    instance members (safety/sandbox/autoRepair). This port keeps one
 *    in-place router instead, so each case is verified through
 *    routeSpecializedEngines(prompt, cmds, true), which mutates `cmds`.
 *  - Infra checks call the real static AutoRepairLoopEngine API
 *    (runAutoRepairLoop(code, language) -> { report, run, commands }) instead
 *    of the pasted `manager.autoRepair.runAutoRepairLoop(code, lang, 2)`.
 *  - Runs as an electron entry point (CompanionManager imports electron):
 *      node_modules\electron\dist\electron.exe dist\verifyAllEngines.js
 *    Electron leaves require.main undefined for the entry script, so the CLI
 *    trigger also matches process.argv; it is a no-op when merely imported.
 *
 * Like the app itself, a run may persist runtime data files (memory-palace
 * deck, Hojaiga capability registry) into the working directory.
 */
import { routeSpecializedEngines, ParsedOverlayCommand } from './CompanionManager';
import { WorkspaceSafetyManager } from './WorkspaceSafetyManager';
import { AutoRepairLoopEngine } from './AutoRepairLoopEngine';

interface EngineVerificationCase {
  moduleNumber: number;
  moduleName: string;
  samplePrompt: string;
}

const TEST_SUITE: EngineVerificationCase[] = [
  { moduleNumber: 1,  moduleName: 'DynamicAppScannerAndTeacher',      samplePrompt: 'teach me this app and scan buttons' },
  { moduleNumber: 6,  moduleName: 'HomeworkSocraticTutor',            samplePrompt: 'help me solve this physics homework problem 4' },
  { moduleNumber: 7,  moduleName: 'UGCContentEngine',                 samplePrompt: 'create a viral tiktok ugc script for AI headphones' },
  { moduleNumber: 8,  moduleName: 'GhostwritingEngine',               samplePrompt: 'ghostwrite a linkedin post about developer leverage' },
  { moduleNumber: 9,  moduleName: 'ProVideoEditorDirector',           samplePrompt: 'premiere pro retention video edit with j-cut' },
  { moduleNumber: 10, moduleName: 'CyberDefenseTutorEngine',          samplePrompt: 'explain zero trust and tls 1.3 security architecture' },
  { moduleNumber: 11, moduleName: 'InterviewCoachEngine',             samplePrompt: 'mock interview system design and salary negotiation' },
  { moduleNumber: 12, moduleName: 'LiveScreenTranslator',             samplePrompt: 'translate screen app labels in gujarati' },
  { moduleNumber: 13, moduleName: 'ChartPatternTutor',                samplePrompt: 'analyze tradingview candlestick fibonacci 25400 24800' },
  { moduleNumber: 14, moduleName: 'HardwareSchematicTutor',           samplePrompt: 'inspect esp32 i2c schematic voltage rail' },
  { moduleNumber: 15, moduleName: 'MemoryPalaceEngine',               samplePrompt: 'build a memory palace flashcard deck for distributed systems' },
  { moduleNumber: 16, moduleName: 'PolyglotVisualArchitectCoder',     samplePrompt: 'write code in typescript to filter and validate telemetry' },
  { moduleNumber: 17, moduleName: 'LiveIDEPairProgrammer',            samplePrompt: 'i am stuck on an async await promise race condition' },
  { moduleNumber: 18, moduleName: 'VisualAlgorithmStepDebugger',      samplePrompt: 'dry run trace this sliding window two pointer loop' },
  { moduleNumber: 19, moduleName: 'FullStackScaffoldAndVerifyEngine', samplePrompt: 'scaffold a clean architecture module called OrderSync' },
  { moduleNumber: 20, moduleName: 'BugRootCauseAutopsyEngine',        samplePrompt: 'why is this failing with TypeError cannot read properties of undefined' },
  { moduleNumber: 21, moduleName: 'SQLQueryPlanAndSchemaVisualizer',  samplePrompt: 'optimize query plan and b-tree index for postgres orders' },
  { moduleNumber: 22, moduleName: 'GitTimeMachineAndConflictResolver',samplePrompt: 'help me resolve a git rebase merge conflict safely' },
  { moduleNumber: 23, moduleName: 'RegexAndParserVisualWorkbench',    samplePrompt: 'build a regex pattern to extract email addresses' },
  { moduleNumber: 24, moduleName: 'APILoadAndLatencySimulator',       samplePrompt: 'benchmark api p95 latency on http://127.0.0.1:3000/health' },
  { moduleNumber: 25, moduleName: 'UIUXAccessibilityAndDesignCritic', samplePrompt: 'run a wcag contrast ratio and tailwind ui audit #38BDF8 #0F172A' }
];

async function runFullVerification(): Promise<void> {
  let passed = 0;

  console.log('====================================================================');
  console.log(' CLICKY / HOJAIGA TUTOR - 25-ENGINE AUTOMATED VERIFICATION SUITE');
  console.log('====================================================================');

  // Core infrastructure (#2 Safety, #3 Sandbox, #4 Auto-Repair, #5 Bridge)
  const safety = new WorkspaceSafetyManager();
  const safetyAllowed = safety.validateCommand('node -v');
  const safetyBlocked = safety.validateCommand('rm -rf /');
  const repairEngine = new AutoRepairLoopEngine();
  const repairCheck = await repairEngine.runAutoRepairLoop('console.log("sandbox_ok"', 'javascript');
  const infraOk =
    safetyAllowed.allowed === true &&
    safetyBlocked.allowed === false &&
    repairCheck.succeeded === true;

  console.log(
    `[INFRA #2-5] Safety allowlist ${safetyAllowed.allowed ? 'PASS' : 'FAIL'} | ` +
      `Safety blocklist ${!safetyBlocked.allowed ? 'PASS' : 'FAIL'} | ` +
      `Auto-Repair sandbox ${repairCheck.succeeded ? 'PASS' : 'FAIL'} ` +
      `(iterations=${repairCheck.iterations.length})`
  );
  if (infraOk) passed++;

  for (const testCase of TEST_SUITE) {
    const cmds: ParsedOverlayCommand[] = [];
    let routed = false;
    try {
      routed = await routeSpecializedEngines(testCase.samplePrompt, cmds, true);
    } catch {
      routed = false;
    }
    const hasBoard = cmds.some(c => c.type === 'BOARD');
    const ok = routed && hasBoard && cmds.length >= 2;
    if (ok) passed++;

    console.log(
      `[File #${String(testCase.moduleNumber).padStart(2, '0')}] ${testCase.moduleName.padEnd(34)} -> ${
        ok ? 'VERIFIED' : 'FAILED'
      } (${cmds.length} overlay commands)`
    );
  }

  console.log('--------------------------------------------------------------------');
  console.log(`FINAL RESULT: ${passed}/${TEST_SUITE.length + 1} (21 Routed Engines + 1 Core Infra Check).`);
  console.log('====================================================================');
}

async function main(): Promise<void> {
  // Under electron the suite behaves exactly like the smoke tests: wait for
  // app readiness first (some engines touch screen APIs). Under plain
  // node/ts-node, require('electron') resolves to the binary path string and
  // this is skipped.
  try {
    const electron = require('electron');
    if (electron && electron.app && typeof electron.app.whenReady === 'function') {
      await electron.app.whenReady();
    }
  } catch {
    /* not running under electron */
  }
  await runFullVerification();
}

if (require.main === module || /verifyAllEngines\.(js|ts)$/.test(process.argv[1] || '')) {
  main()
    .then(() => process.exit(0))
    .catch(err => {
      console.error('Verification failed:', err);
      process.exit(1);
    });
}
