/**
 * Test script to trigger Clicky's special app teaching features
 * Run this while Clicky is running (npm start)
 */

const { app, BrowserWindow } = require('electron');

console.log('=== Clicky App Teaching Test ===\n');

console.log('Clicky is already running.');
console.log('To test the special app teaching features, you need to:');
console.log('');
console.log('1. Open the Clicky panel (Ctrl+Shift+P or Ctrl+Alt+P)');
console.log('2. Type one of these commands in the panel:');
console.log('');
console.log('=== AVAILABLE TEACHING MODES ===');
console.log('');
console.log('1. COMPREHENSIVE TEACHING (Teach entire app):');
console.log('   Type: "teach me everything about this app"');
console.log('   This will: Detect login, explore entire app, teach all features');
console.log('');
console.log('2. SPECIFIC FEATURE TEACHING:');
console.log('   Type: "teach me how to [specific feature]"');
console('   Examples:');
console.log('   - "teach me how to export videos"');
console.log('   - "teach me how to create charts"');
console.log('   - "teach me how to use filters"');
console.log('');
console.log('3. UI ACTION EXPLORATION:');
console.log('   Type: "explore all UI actions"');
console.log('   This will: Try all click types, discover shortcuts, explain everything');
console.log('');
console.log('=== FOR EXCEL SPECIFICALLY ===');
console.log('');
console.log('Since you mentioned Excel, try these:');
console.log('- "teach me everything about Excel"');
console.log('- "teach me how to create formulas"');
console.log('- "teach me how to make charts"');
console.log('- "teach me how to use pivot tables"');
console.log('- "explore all UI actions"');
console.log('');
console.log('=== MANUAL IPC TRIGGER (Advanced) ===');
console.log('');
console.log('If you want to trigger via code, the IPC handlers are:');
console.log('- start-comprehensive-teaching');
console.log('- start-specific-teaching (with feature name)');
console.log('- stop-dynamic-teaching');
console.log('- explore-ui-actions');
console.log('');
console.log('Example to trigger comprehensive teaching:');
console.log('  ipcRenderer.invoke("start-comprehensive-teaching")');
console.log('');
console.log('=== REQUIREMENTS ===');
console.log('');
console.log('✓ Ollama server must be running (it is!)');
console.log('✓ LLaVA model must be downloaded (it is!)');
console.log('✓ Clicky must be running (it is!)');
console.log('✓ Target app must be open (Excel, etc.)');
console.log('');
console.log('=== NEXT STEPS ===');
console.log('');
console.log('1. Open Excel (or any app you want to learn)');
console.log('2. Make sure the app window is visible');
console.log('3. Open Clicky panel (Ctrl+Shift+P)');
console.log('4. Type your teaching command');
console.log('5. Watch Clicky explore and teach the app!');
console.log('');
console.log('The teaching will:');
console.log('- Detect if login is needed');
console.log('- Explore UI by clicking elements');
console(':- Try left/right/double clicks');
console.log('- Discover keyboard shortcuts');
console.log('- Build navigation graph');
console.log('- Teach what each button does');
console.log('- Explain workflows step-by-step');
console.log('');
