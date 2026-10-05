import * as assert from 'assert';
import { extractMathExpression } from '../src/CompanionManager';
import { UniversalCapabilitiesEngine } from '../src/UniversalCapabilitiesEngine';
import { CrossGameSensConverter, MousePrecisionAnalyzer, GamingAimAndSensEngine } from '../src/GamingAimAndSensEngine';
import { WorkspaceSafetyManager } from '../src/WorkspaceSafetyManager';
import { SandboxTestExecutor } from '../src/SandboxTestExecutor';
import { AutoRepairLoopEngine } from '../src/AutoRepairLoopEngine';
import { HojaigaIntegrationBridge } from '../src/HojaigaIntegrationBridge';
import { HomeworkSocraticTutor } from '../src/HomeworkSocraticTutor';
import { UGCContentEngine } from '../src/UGCContentEngine';
import { GhostwritingEngine } from '../src/GhostwritingEngine';
import { ProVideoEditorDirector } from '../src/ProVideoEditorDirector';
import { CyberDefenseTutorEngine } from '../src/CyberDefenseTutorEngine';


async function runProgressiveSuite() {
  console.log('=== STARTING PROGRESSIVE CLICKY / HOJAIGA TEST SUITE ===\n');


  // TIER 1 & 2: Math Extractor & Anti-x^2 Regression Guard
  console.log('[Tier 1-2] Testing Dynamic Math Extractor & Anti-x^2 Guard...');
  assert.strictEqual(extractMathExpression('spring motion and hooke law'), null, 'Plain English must not trigger math plot');
  assert.strictEqual(extractMathExpression('explain photosynthesis'), null, 'Biology topic must not trigger math plot');
  assert.strictEqual(extractMathExpression('Plot y = x^3 - 3x and explain'), 'x^3 - 3x');
  assert.strictEqual(extractMathExpression('graph f(x) = 2x^2 - 5x + 3'), '2x^2 - 5x + 3');
  console.log('  ✔ Passed Math Extractor & Anti-x^2 Guard\n');


  // TIER 3: Universal Capabilities (Wingman, Mood DJ, Athlete, Flowchart, Code Tracer, Field Sim)
  console.log('[Tier 3] Testing UniversalCapabilitiesEngine modes...');
  const wingmanCmds = UniversalCapabilitiesEngine.enrichCommands('Be my wingman, reply to her text about coffee', []);
  assert.ok(wingmanCmds.some(c => c.type === 'ACTOR' && c.pov === '2nd'), 'Wingman must spawn 2nd-POV actor');
  assert.ok(wingmanCmds.filter(c => c.type === 'WRITE').length >= 3, 'Wingman must provide 3 reply cards');


  const djCmds = UniversalCapabilitiesEngine.enrichCommands('Play a synthwave coding beat', []);
  assert.ok(djCmds.some(c => c.type === 'DJ' && c.genre === 'synthwave'), 'Mood DJ must trigger synthwave beat');


  const traceCmds = UniversalCapabilitiesEngine.enrichCommands('Show a bubble sort array step trace', []);
  assert.ok(traceCmds.some(c => c.type === 'TRACE'), 'Must inject TRACE command for sorting');
  console.log('  ✔ Passed UniversalCapabilitiesEngine (Wingman, DJ, Code Tracer)\n');


  // TIER 4A: Gaming Aim, Hand-Trace Telemetry & Cross-Game Sens Converter
  console.log('[Tier 4A] Testing GamingAimAndSensEngine...');
  const conv = CrossGameSensConverter.convert({
    sourceGameKey: 'valorant',
    targetGameKey: 'cs2',
    sourceSens: 0.35,
    dpi: 800,
    sourceStretched43: true
  });
  assert.strictEqual(conv.eDPI, 280);
  assert.ok(Math.abs(conv.targetSensRaw360 - 1.1136) < 0.01, 'Valorant 0.35 -> CS2 raw 360 sens should be ~1.1136');
  assert.ok(conv.targetSensStretchedAdjusted > conv.targetSensFovMatched, '4:3 stretched conversion must scale horizontal sens');


  const handTelemetry = MousePrecisionAnalyzer.analyzeHandTrace(
    [
      { x: 0, y: 0, t: 0 },
      { x: 120, y: 5, t: 40 },
      { x: 245, y: -4, t: 80 }, // 22.5% overshoot past x=200
      { x: 200, y: 0, t: 130 }
    ],
    { x: 0, y: 0 },
    { x: 200, y: 0 },
    800
  );
  assert.ok(handTelemetry.overshootPct >= 20, 'Must detect >20% target overshoot');
  assert.strictEqual(handTelemetry.recommendedSensMultiplier, 0.88, 'Must recommend lowering sens by 12% on overshoot');


  const aimOverlay = GamingAimAndSensEngine.handleGamingPrompt('Convert Valorant sens 0.35 at 800 dpi to CS2', []);
  assert.ok(aimOverlay && aimOverlay.some(c => c.type === 'AIM_TRAINER'), 'Must build AIM_TRAINER overlay');
  console.log('  ✔ Passed Cross-Game Sens Converter & Hand-Movement Telemetry\n');


  // TIER 4B: Homework, UGC, Ghostwriting, Pro Video Director & Cyber Defense
  console.log('[Tier 4B] Testing Specialized Content, Homework, Video & Security Tutors...');
  assert.ok(HomeworkSocraticTutor.isHomeworkPrompt('Help me solve this homework problem 4'));
  assert.ok(UGCContentEngine.isUGCPrompt('Make UGC TikTok script for my app'));
  assert.ok(GhostwritingEngine.isGhostwritePrompt('Ghostwrite a LinkedIn post about AI'));
  assert.ok(ProVideoEditorDirector.isVideoEditPrompt('Edit this video in Premiere Pro with J-cut'));
  assert.ok(CyberDefenseTutorEngine.isSecurityConceptPrompt('Explain TLS 1.3 and firewall architecture'));
  console.log('  ✔ Passed Specialized Tutor Routing\n');


  // TIER 5: Workspace Safety, Sandbox Execution, Auto-Repair Loop & Hojaiga Registry
  console.log('[Tier 5] Testing WorkspaceSafetyManager, SandboxTestExecutor & AutoRepairLoopEngine...');
  const safety = new WorkspaceSafetyManager('D:\\new_automation\\final hojaiga tutor');
  assert.strictEqual(safety.validateCommand('rm -rf /').allowed, false, 'Must block rm -rf');
  assert.strictEqual(safety.validateCommand('del /f /q C:\\Windows').allowed, false, 'Must block del /f /q');
  assert.strictEqual(safety.validateCommand('node test.js').allowed, true, 'Must allow node');
  assert.strictEqual(safety.isPathInsideWorkspace('C:\\Windows\\System32'), false, 'Must block outside paths');


  const repairEngine = new AutoRepairLoopEngine(new SandboxTestExecutor(safety));
  const brokenJS = `console.log(missingVar + 42`; // Missing variable + unclosed paren
  const repairOutcome = await repairEngine.runAutoRepairLoop(brokenJS, 'javascript', 3);
  assert.strictEqual(repairOutcome.succeeded, true, 'AutoRepairLoopEngine must fix missing paren + ReferenceError');
  assert.strictEqual(repairOutcome.iterations[repairOutcome.iterations.length - 1].result.stdout, '42');


  const hojaiga = new HojaigaIntegrationBridge();
  hojaiga.registerCapability({
    id: 'cap_math',
    name: 'Dynamic Math Tutor',
    category: 'tutor',
    description: 'Plots any equation',
    triggerKeywords: ['plot', 'graph'],
    handler: async () => [{ type: 'PLOT', expr: 'sin(x)' }]
  });
  assert.strictEqual(hojaiga.findMatchingCapability('please plot sin(x)')?.id, 'cap_math');
  console.log('  ✔ Passed Workspace Safety, Sandbox Runner, Auto-Repair Loop & Hojaiga Bridge\n');


  console.log('🎉 ALL 5 TIERS PASSED WITH 0 REGRESSIONS!');
}


runProgressiveSuite().catch(err => {
  console.error('❌ Test Suite Failed:', err);
  process.exit(1);
});
