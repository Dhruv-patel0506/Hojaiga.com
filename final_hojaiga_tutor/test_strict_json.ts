/**
 * Test script to verify strict JSON output from LLM
 * Tests the updated TeacherRAGWrapper with strict prompts
 */

import { AppKnowledgeRAG } from './rag/AppKnowledgeRAG';
import { TeacherRAGWrapper } from './rag/TeacherRAGWrapper';
import { UIElementNode } from './rag/types';
import * as path from 'path';
import * as fs from 'fs';

async function main() {
  console.log('╔══════════════════════════════════════════════════════════════╗');
  console.log('║         Test: Strict JSON Output from LLM                      ║');
  console.log('╚══════════════════════════════════════════════════════════════╝');
  console.log();
  console.log('Testing that LLM returns strict JSON (no conversational fluff)');
  console.log();

  // Check if Ollama is running
  try {
    const response = await fetch('http://127.0.0.1:11434/api/tags');
    if (!response.ok) {
      console.error('❌ Ollama not available. Please start Ollama first.');
      return;
    }
    console.log('✅ Ollama is running');
  } catch (error) {
    console.error('❌ Cannot connect to Ollama. Please start Ollama first.');
    return;
  }

  // Create RAG engine
  const ragEngine = new AppKnowledgeRAG();
  const ragWrapper = new TeacherRAGWrapper(ragEngine);

  // Load Notepad documentation
  const docsPath = path.join(__dirname, 'docs', 'notepad.md');
  
  if (!fs.existsSync(docsPath)) {
    console.error(`❌ Documentation file not found: ${docsPath}`);
    return;
  }

  console.log(`Loading documentation from: ${docsPath}`);
  await ragEngine.ingestMarkdownFile('Notepad', docsPath);
  console.log('✅ Documentation loaded');
  console.log();

  // Test 1: Single step (determineNextStep)
  console.log('═══════════════════════════════════════════════════════════════');
  console.log('TEST 1: Single Step (determineNextStep)');
  console.log('═══════════════════════════════════════════════════════════════');
  console.log();

  const mockUIElements: UIElementNode[] = [
    { name: 'File', automationId: 'MenuBarItem', controlType: 'MenuItem', bounds: { x: 0, y: 0, width: 100, height: 30 } },
    { name: 'Edit', automationId: 'MenuBarItem2', controlType: 'MenuItem', bounds: { x: 100, y: 0, width: 100, height: 30 } },
    { name: 'Save', automationId: 'SaveButton', controlType: 'Button', bounds: { x: 200, y: 0, width: 100, height: 30 } }
  ];

  try {
    const singleStep = await ragWrapper.determineNextStep('Notepad', 'How do I save my document?', mockUIElements);
    console.log('✅ Single step parsed successfully');
    console.log(`   Action: ${singleStep.actionType}`);
    console.log(`   Target: ${singleStep.targetName}`);
    console.log(`   Explanation: ${singleStep.explanation}`);
    console.log();
  } catch (error) {
    console.error('❌ Single step test failed:', error);
    console.log();
  }

  // Test 2: Multiple steps (determineNextSteps)
  console.log('═══════════════════════════════════════════════════════════════');
  console.log('TEST 2: Multiple Steps (determineNextSteps)');
  console.log('═══════════════════════════════════════════════════════════════');
  console.log();

  try {
    const multipleSteps = await ragWrapper.determineNextSteps('Notepad', 'How do I save my document?', mockUIElements, 3);
    console.log(`✅ Multiple steps parsed successfully (${multipleSteps.length} steps)`);
    
    multipleSteps.forEach((step, index) => {
      console.log(`   Step ${index + 1}:`);
      console.log(`     Action: ${step.actionType}`);
      console.log(`     Target: ${step.targetName}`);
      console.log(`     Explanation: ${step.explanation}`);
    });
    console.log();
  } catch (error) {
    console.error('❌ Multiple steps test failed:', error);
    console.log();
  }

  console.log('═══════════════════════════════════════════════════════════════');
  console.log('Test Complete');
  console.log('═══════════════════════════════════════════════════════════════');
}

main().catch(console.error);
