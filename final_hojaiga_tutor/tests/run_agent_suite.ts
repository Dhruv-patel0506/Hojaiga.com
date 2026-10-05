import * as assert from 'assert';
import { MainOrchestrator } from '../src/MainOrchestrator';
import { TutoringAgent } from '../src/TutoringAgent';
import { CodebaseBuilderAgent } from '../src/CodebaseBuilderAgent';
import { WorkspaceSafetyManager } from '../src/WorkspaceSafetyManager';


async function runAgentSuite() {
  console.log('=== STARTING MULTI-AGENT ORCHESTRATOR TEST SUITE ===\n');


  // Initialize modules (assuming these match your current advanced src/ structure)
  const safetyManager = new WorkspaceSafetyManager('/mock/workspace/path');
  const tutor = new TutoringAgent();
  const builder = new CodebaseBuilderAgent(safetyManager);
  const orchestrator = new MainOrchestrator(tutor, builder);


  // ---------------------------------------------------------
  // TIER 1: Unit Routing (Easy)
  // ---------------------------------------------------------
  console.log('[Tier 1] Testing Direct Intent Routing...');
  
  const tutorRoute = await orchestrator.routeTask('Explain how binary search works like I am 10 years old.');
  assert.strictEqual(tutorRoute.targetModule, 'TutoringAgent', 'Should route education to Tutor');
  
  const buildRoute = await orchestrator.routeTask('Create a basic folder structure for a React app.');
  assert.strictEqual(buildRoute.targetModule, 'CodebaseBuilderAgent', 'Should route scaffold to Builder');
  
  const directRoute = await orchestrator.routeTask('Summarize these 5 bullet points.');
  assert.strictEqual(directRoute.targetModule, 'MainOrchestrator', 'General tasks should be handled directly');
  
  console.log('  ✔ Passed Tier 1 Routing\n');


  // ---------------------------------------------------------
  // TIER 2: State & Context Handoffs (Medium)
  // ---------------------------------------------------------
  console.log('[Tier 2] Testing Context & Multi-File Architecture...');
  
  const ambiguousRoute = await orchestrator.routeTask('WebSockets.');
  assert.strictEqual(ambiguousRoute.action, 'ASK_CLARIFICATION', 'Must ask user if they want to learn or build');


  const multiFileResult = await builder.completeCodebase({
    files: ['routes.js', 'empty_controller.js'],
    prompt: 'Finish this project.'
  });
  assert.ok(multiFileResult.editedFiles.includes('empty_controller.js'), 'Builder must detect and write the missing controller logic');
  
  console.log('  ✔ Passed Tier 2 Context & Architecture\n');


  // ---------------------------------------------------------
  // TIER 3: Chaining & Recovery (Hard)
  // ---------------------------------------------------------
  console.log('[Tier 3] Testing Multi-Agent Chaining & Misconception Recovery...');
  
  const chainedResult = await orchestrator.executeChainedTask('Build a JWT login in Node.js and then explain line-by-line how it works.');
  assert.strictEqual(chainedResult.steps[0].module, 'CodebaseBuilderAgent');
  assert.strictEqual(chainedResult.steps[1].module, 'TutoringAgent');
  assert.ok(chainedResult.steps[1].contextProvided, 'Builder code must be passed to Tutor for explanation');


  const tutorCorrection = await tutor.generateResponse('Since CSS is a backend language, how do I query my database in it?');
  assert.ok(tutorCorrection.includes('CSS is not'), 'Tutor must correct the false premise before answering');

  
  console.log('  ✔ Passed Tier 3 Chaining\n');


  // ---------------------------------------------------------
  // TIER 4: Safety & Adversarial (Extreme)
  // ---------------------------------------------------------
  console.log('[Tier 4] Testing Safety Boundaries & Circular Dependencies...');
  
  const destructiveCommand = safetyManager.validateCommand('rm -rf ../../system32');
  assert.strictEqual(destructiveCommand.allowed, false, 'Must strictly block path traversal and destructive deletes');


  const circularDepResult = await builder.resolveArchitecture({
    files: ['fileA.js', 'fileB.js'],
    issue: 'circular_dependency'
  });
  assert.ok(circularDepResult.createdFiles.includes('utils.js'), 'Must extract shared logic to break circular dependency');

  
  console.log('  ✔ Passed Tier 4 Safety & Stress Tests\n');
  console.log('🎉 ALL TIERS PASSED. SYSTEM IS ROBUST!');
}


runAgentSuite().catch(err => {
  console.error('\n❌ Test Suite Failed at Assertion:');
  console.error(err.message);
  console.log('\n--- Stack Trace ---');
  console.log(err.stack);
  process.exit(1);
});
