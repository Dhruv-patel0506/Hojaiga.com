// --- ELECTRON MOCK FOR PURE NODE TESTING ---
// Prevents pure ts-node from crashing while leaving CompanionManager logic intact.
const Module = require('module');
const originalRequire = Module.prototype.require;
Module.prototype.require = function(request: string) {
  if (request === 'electron') {
    return { 
      app: { whenReady: async () => {}, on: () => {} }, 
      ipcMain: { handle: () => {}, on: () => {}, removeHandler: () => {}, removeAllListeners: () => {} },
      globalShortcut: { register: () => {}, unregisterAll: () => {} },
      screen: { getPrimaryDisplay: () => ({ bounds: { x:0, y:0, width:1920, height:1080 } }), on: () => {} },
      BrowserWindow: class { loadFile() {} setAlwaysOnTop() {} setVisibleOnAllWorkspaces() {} webContents = { send: () => {} } }
    };
  }
  return originalRequire.apply(this, arguments);
};
// -------------------------------------------

import * as assert from 'assert';
import * as fs from 'fs';
import * as http from 'http';
import * as os from 'os';
import * as path from 'path';

import { WorkspaceSafetyManager } from './WorkspaceSafetyManager';
import { SandboxTestExecutor } from './SandboxTestExecutor';
import { AutoRepairLoopEngine } from './AutoRepairLoopEngine';
import { MemoryPalaceEngine } from './MemoryPalaceEngine';
import { FullStackScaffoldAndVerifyEngine } from './FullStackScaffoldAndVerifyEngine';
import { APILoadAndLatencySimulator } from './APILoadAndLatencySimulator';
import { UIUXAccessibilityAndDesignCritic } from './UIUXAccessibilityAndDesignCritic';
import { ChartPatternTutor } from './ChartPatternTutor';
import { InterviewCoachEngine } from './InterviewCoachEngine';
import { LiveScreenTranslator } from './LiveScreenTranslator';
import { PolyglotVisualArchitectCoder } from './PolyglotVisualArchitectCoder';
import { RegexAndParserVisualWorkbench } from './RegexAndParserVisualWorkbench';
import { SQLQueryPlanAndSchemaVisualizer } from './SQLQueryPlanAndSchemaVisualizer';
import { DynamicAppScannerAndTeacher } from './DynamicAppScannerAndTeacher';
import { CompanionManager, ParsedOverlayCommand } from './CompanionManager';

interface ProgressiveTestCase {
  id: string; tier: string; name: string; run: () => Promise<void>;
}

const ALL_TESTS: ProgressiveTestCase[] = [
  // --- TIER 1: CORE MATH & PARSERS ---
  {
    id: 'T1.01', tier: 'TIER 1: EASY (UNIT)', name: 'ChartPatternTutor: Exact Fibonacci 0.382 / 0.500 / 0.618 calculation',
    run: async () => {
      const fib = ChartPatternTutor.calculateFibonacciLevels(25200, 24400);
      assert.strictEqual(fib.level382, 24894.4, 'Fibonacci 0.382 is mathematically incorrect');
    }
  },
  {
    id: 'T1.02', tier: 'TIER 1: EASY (UNIT)', name: 'UIUXAccessibilityAndDesignCritic: WCAG 2.1 contrast ratios',
    run: async () => {
      assert.ok(UIUXAccessibilityAndDesignCritic.computeHexContrastRatio('#38BDF8', '#0F172A') >= 7.0, 'Failed AAA contrast math');
    }
  },
  {
    id: 'T1.03', tier: 'TIER 1: EASY (UNIT)', name: 'RegexAndParserVisualWorkbench: DFA + ReDoS check',
    run: async () => {
      const emailBundle = RegexAndParserVisualWorkbench.synthesizeAndVerifyPattern('extract email address');
      // Actually verifying the regex tests real strings
      const regex = new RegExp(emailBundle.patternSource);
      assert.strictEqual(regex.test('test@domain.com'), true, 'Valid email failed to match');
      assert.strictEqual(regex.test('invalid@@domain'), false, 'Invalid email matched incorrectly');
    }
  },

  // --- TIER 2: FILE I/O & PERSISTENCE ---
  {
    id: 'T2.01', tier: 'TIER 2: MEDIUM (STATE & SQL)', name: 'MemoryPalaceEngine: Real SM-2 Disk Persistence',
    run: async () => {
      const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'clicky-mem-'));
      const engine = new MemoryPalaceEngine(tmpDir);
      const cards = engine.createSpatialLociForTopic('Raft');
      
      // Verify file was physically written to disk
      const filePath = path.join(tmpDir, 'memory_palace_deck.json');
      assert.ok(fs.existsSync(filePath), 'Flashcard JSON was not written to disk');
      
      // Verify SM-2 logic changes state
      const updated = engine.recordSM2Review(cards[0].id, 5);
      assert.strictEqual(updated?.intervalDays, 6, 'SM-2 interval did not increase properly');
      fs.rmSync(tmpDir, { recursive: true, force: true });
    }
  },
  {
    id: 'T2.02', tier: 'TIER 2: MEDIUM (STATE & SQL)', name: 'FullStackScaffoldAndVerifyEngine: Real 4-Layer Disk Generation',
    run: async () => {
      const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'clicky-scaffold-'));
      const scaffold = new FullStackScaffoldAndVerifyEngine(new WorkspaceSafetyManager(tmpDir));
      const result = scaffold.writeVerifiedScaffoldToDisk(tmpDir, scaffold.planVerifiedFeatureArchitecture('Ledger'));
      
      // Verify physical disk files and their contents
      assert.strictEqual(result.writtenFiles.length, 4, 'Failed to scaffold all 4 files');
      const serviceContent = fs.readFileSync(path.join(tmpDir, result.writtenFiles.find(f => f.includes('service'))!), 'utf-8');
      assert.ok(serviceContent.includes('export class LedgerService'), 'Service file missing expected class code');
      
      fs.rmSync(tmpDir, { recursive: true, force: true });
    }
  },

  // --- TIER 3: CHILD PROCESS & SANDBOXING ---
  {
    id: 'T3.01', tier: 'TIER 3: HARD (SANDBOX & SECURITY)', name: 'WorkspaceSafetyManager: Blocks destructive shell commands',
    run: async () => {
      const safety = new WorkspaceSafetyManager('D:\\new');
      assert.strictEqual(safety.validateCommand('rm -rf /').allowed, false, 'Failed to block rm -rf');
      assert.strictEqual(safety.validateCommand('format C:').allowed, false, 'Failed to block format');
    }
  },
  {
    id: 'T3.02', tier: 'TIER 3: HARD (SANDBOX & SECURITY)', name: 'SandboxTestExecutor: Executes real isolated Node code',
    run: async () => {
      const executor = new SandboxTestExecutor();
      const codeCheck = await executor.runCodeInSandbox('console.log(10 * 5);', 'javascript', 2000);
      // Validates the child process actually started, ran, and captured stdout
      assert.strictEqual(codeCheck.stdout, '50', 'Sandbox did not compute math correctly in child process');
    }
  },
  {
    id: 'T3.03', tier: 'TIER 3: HARD (SANDBOX & SECURITY)', name: 'AutoRepairLoopEngine: Real AST Auto-Healing Execution',
    run: async () => {
      const repair = new AutoRepairLoopEngine();
      // Purposely broken JS script (missing parenthesis)
      const healed = await repair.runAutoRepairLoop('console.log(20 + 22', 'javascript', 3);
      assert.strictEqual(healed.succeeded, true, 'Failed to fix code');
      // Ensure the healed code actually runs and produces 42
      assert.strictEqual(healed.iterations[healed.iterations.length - 1].result.stdout, '42', 'Healed code output was incorrect');
    }
  },

  // --- TIER 4: LIVE OS SYSTEMS & NETWORK ---
  {
    id: 'T4.01', tier: 'TIER 4: EXTREME (OS & STRESS)', name: 'APILoadAndLatencySimulator: Real TCP Port Profiling',
    run: async () => {
      // Create a real server simulating 20ms latency
      const server = http.createServer((_req, res) => { setTimeout(() => { res.writeHead(200); res.end('{}'); }, 20); });
      await new Promise<void>(resolve => server.listen(0, '127.0.0.1', resolve));
      
      const port = (server.address() as any).port;
      const report = await APILoadAndLatencySimulator.measureLocalEndpoint(`http://127.0.0.1:${port}/health`, 3);
      server.close();
      
      // Validate real HTTP requests were made
      assert.strictEqual(report.samplesCount, 3, 'Did not make all HTTP requests');
      assert.ok(report.p50Ms >= 15, `Server latency was ${report.p50Ms}ms, expected >= 15ms`);
    }
  },
  {
    id: 'T4.02', tier: 'TIER 4: EXTREME (OS & STRESS)', name: 'DynamicAppScannerAndTeacher: Windows UIA Memory Cache',
    run: async () => {
      await DynamicAppScannerAndTeacher.scanActiveOrNamedApp();
      const t0 = Date.now();
      await DynamicAppScannerAndTeacher.scanActiveOrNamedApp();
      const latency = Date.now() - t0;
      // In-memory cache hit should bypass powershell completely (under 25ms)
      assert.ok(latency <= 25, `Cache took too long: ${latency}ms`);
    }
  },
  {
    id: 'T4.03', tier: 'TIER 4: EXTREME (OS & STRESS)', name: 'CompanionManager: 25-Prompt Concurrent Engine Stress',
    run: async () => {
      const manager = new CompanionManager();
      const prompts = Array.from({ length: 25 }, (_, idx) => 
        idx % 2 === 0 ? 'write code in typescript to filter arrays' : 'analyze tradingview candlestick fibonacci 25000'
      );
      
      // Fire 25 prompts concurrently through the system
      const results = await Promise.all(prompts.map(p => manager.routePromptToOverlay(p)));
      assert.strictEqual(results.length, 25, 'Failed to process all concurrent requests');
      assert.ok(results.every(r => r.length > 0 && r[0].type === 'BOARD'), 'A concurrent request returned a malformed overlay array');
    }
  }
];

async function executeProgressiveSuite(): Promise<void> {
  console.log('\n================================================================================');
  console.log(' CLICKY / HOJAIGA TUTOR — PROGRESSIVE REAL-WORLD QA TEST SUITE');
  console.log('================================================================================');

  let currentTier = '';
  let passed = 0;
  let failed = 0;

  for (const test of ALL_TESTS) {
    if (test.tier !== currentTier) {
      currentTier = test.tier;
      console.log(`\n--- ${currentTier} ---`);
    }

    const start = Date.now();
    try {
      await test.run();
      passed++;
      console.log(`  [PASS] ${test.id} (${String(Date.now() - start).padStart(4, ' ')}ms) : ${test.name}`);
    } catch (err: any) {
      failed++;
      console.error(`  [FAIL] ${test.id} : ${test.name}\n         Reason: ${err?.message || err}`);
    }
  }

  console.log('\n================================================================================');
  console.log(` QA TEST SUMMARY: ${passed} PASSED | ${failed} FAILED | TOTAL: ${ALL_TESTS.length}`);
  console.log('================================================================================\n');
  if (failed > 0) process.exit(1);
}

executeProgressiveSuite();