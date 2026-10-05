/**
 * Unit test for Runtime Check #3: Context-Prefixed RAG Chunks
 * Tests that section headers are prefixed to chunk content
 */

import { AppKnowledgeRAG } from './rag/AppKnowledgeRAG';
import * as path from 'path';
import * as fs from 'fs';

async function main() {
  console.log('╔══════════════════════════════════════════════════════════════╗');
  console.log('║         Test: Context-Prefixed RAG Chunks                     ║');
  console.log('╚══════════════════════════════════════════════════════════════╝');
  console.log();
  console.log('Testing that section headers are prefixed to chunk content');
  console.log('This prevents ambiguity like "Click + to add" (Source vs Scene)');
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

  // Query for a specific task
  const userIntent = 'How do I save my document?';
  console.log(`Query: "${userIntent}"`);
  console.log();

  const results = await ragEngine.queryKnowledge('Notepad', userIntent, 3);

  console.log(`Retrieved ${results.length} relevant chunks:`);
  console.log();

  results.forEach((result, index) => {
    console.log(`Chunk ${index + 1}:`);
    console.log(`  Topic: ${result.chunk.topic}`);
    console.log(`  Content: ${result.chunk.content.substring(0, 150)}...`);
    console.log();

    // CRITICAL RUNTIME CHECK #3: Verify context prefix
    if (result.chunk.content.startsWith('[Section:')) {
      console.log('  ✅ Context prefix detected - section header is included');
    } else {
      console.log('  ❌ Context prefix missing - section header not included');
    }
    console.log();
  });

  console.log('╔══════════════════════════════════════════════════════════════╗');
  console.log('║         Test Complete                                        ║');
  console.log('╚══════════════════════════════════════════════════════════════╝');
}

main().catch(console.error);
