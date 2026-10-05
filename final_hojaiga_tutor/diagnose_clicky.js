/**
 * Diagnostic script to check Clicky status
 */

const { exec } = require('child_process');
const { promisify } = require('util');
const execAsync = promisify(exec);

async function diagnoseClicky() {
  console.log('=== Clicky Diagnostic ===\n');

  // Check 1: Is Electron running?
  console.log('Check 1: Is Electron running?');
  try {
    const { stdout } = await execAsync('tasklist | findstr electron');
    console.log('✓ Electron is running');
    console.log(stdout);
  } catch {
    console.log('✗ Electron is NOT running');
    console.log('Start Clicky with: npm start\n');
    return;
  }

  // Check 2: Is Ollama running?
  console.log('\nCheck 2: Is Ollama running?');
  try {
    await execAsync('curl http://localhost:11434/api/tags');
    console.log('✓ Ollama is running');
  } catch {
    console.log('✗ Ollama is NOT running');
    console.log('Start Ollama with: cd D:\\Ollama && ollama serve\n');
  }

  // Check 3: Panel window location
  console.log('\nCheck 3: Panel window info');
  console.log('The panel should be a small window in the bottom-right corner');
  console.log('Width: 330px, Height: 200px');
  console.log('If not visible, it might be behind other windows or minimized');

  // Check 4: Hotkey info
  console.log('\nCheck 4: Hotkey info');
  console.log('Current hotkeys:');
  console.log('  Ctrl+Shift+K - Toggle panel (NEW)');
  console.log('  Ctrl+Alt+K - Toggle panel (NEW)');
  console.log('  Ctrl+Shift+Space - Toggle click-through');
  console.log('  Ctrl+Shift+A - Instant app scan');
  console.log('  Ctrl+Shift+X - Clear overlay');

  console.log('\n=== Manual Panel Open ===');
  console.log('If hotkeys don\'t work, try:');
  console.log('1. Look for Clicky icon in system tray (bottom right)');
  console.log('2. Right-click the tray icon');
  console.log('3. Select "Show Panel" or similar option');
  console.log('4. Or look for a small window in bottom-right corner');

  console.log('\n=== Alternative: Try Tray Icon ===');
  console.log('Clicky should have a tray icon in the system tray');
  console.log('Right-click it to access the panel');
}

diagnoseClicky().catch(console.error);
