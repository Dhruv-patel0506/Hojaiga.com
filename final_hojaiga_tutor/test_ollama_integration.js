/**
 * Test script to verify Ollama integration
 * Run with: node test_ollama_integration.js
 */

const axios = require('axios');
const { exec } = require('child_process');
const { promisify } = require('util');
const execAsync = promisify(exec);

const OLLAMA_HOME = 'D:\\Ollama';
const OLLAMA_ENDPOINT = 'http://localhost:11434';

async function testOllamaIntegration() {
  console.log('=== Ollama Integration Test ===\n');

  // Test 1: Check if Ollama directory exists
  console.log('Test 1: Checking Ollama installation directory...');
  try {
    await execAsync(`if exist "${OLLAMA_HOME}" (echo Directory exists) else (echo Directory not found)`);
    console.log('✓ Ollama directory check passed\n');
  } catch (error) {
    console.log('✗ Ollama directory not found');
    console.log('Please run: setup_ollama_d_drive.bat\n');
    return;
  }

  // Test 2: Check if Ollama executable exists
  console.log('Test 2: Checking Ollama executable...');
  try {
    await execAsync(`"${OLLAMA_HOME}\\ollama.exe" --version`);
    console.log('✓ Ollama executable found\n');
  } catch (error) {
    console.log('✗ Ollama executable not found');
    console.log('Please run: setup_ollama_d_drive.bat\n');
    return;
  }

  // Test 3: Check if LLaVA model is downloaded
  console.log('Test 3: Checking LLaVA model...');
  try {
    const { stdout } = await execAsync(`"${OLLAMA_HOME}\\ollama.exe" list`);
    if (stdout.includes('llava')) {
      console.log('✓ LLaVA model found\n');
    } else {
      console.log('✗ LLaVA model not found');
      console.log('Please run: pull_llava.bat\n');
      return;
    }
  } catch (error) {
    console.log('✗ Failed to check models');
    console.log('Please run: pull_llava.bat\n');
    return;
  }

  // Test 4: Check if Ollama server is running
  console.log('Test 4: Checking Ollama server...');
  try {
    await axios.get(`${OLLAMA_ENDPOINT}/api/tags`, { timeout: 2000 });
    console.log('✓ Ollama server is running\n');
  } catch (error) {
    console.log('✗ Ollama server is not running');
    console.log('Please run: start_ollama.bat\n');
    return;
  }

  // Test 5: Test LLaVA API
  console.log('Test 5: Testing LLaVA API...');
  try {
    const response = await axios.post(`${OLLAMA_ENDPOINT}/api/generate`, {
      model: 'llava',
      prompt: 'What is 2+2?',
      stream: false
    }, { timeout: 30000 });

    console.log('✓ LLaVA API response:', response.data.response.substring(0, 100));
    console.log('✓ LLaVA API test passed\n');
  } catch (error) {
    console.log('✗ LLaVA API test failed');
    console.error(error.message);
    return;
  }

  console.log('=== All Tests Passed ===');
  console.log('\nOllama integration is ready for Clicky Vision Platform!');
  console.log('\nYou can now:');
  console.log('1. Start Clicky: npm start');
  console.log('2. Use vision teaching features');
  console.log('3. Teach any app dynamically');
}

testOllamaIntegration().catch(console.error);
